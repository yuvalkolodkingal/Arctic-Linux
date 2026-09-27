// Package catalog loads the app catalog (modules/<category>/<id>/module.toml plus
// modules/catalog.toml), validates picker selections and estimates download sizes.
//
// Everything the installer can put on a system is a module. Visible modules are the app tiles
// of the design's Ninite-style picker; hidden modules under modules/_system are always
// installed. Modules of a hardware category (drivers) carry [[detect]] rules and are only
// offered when MarkDetected finds a matching device. Profiles and API input only ever name
// module ids — never commands.
package catalog

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"regexp"
	"sort"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/toml"
)

// Install methods.
const (
	MethodDNF     = "dnf"
	MethodCopr    = "copr"
	MethodFlatpak = "flatpak"
	MethodNix     = "nix"
)

// Category is one picker section (design CATEGORIES).
type Category struct {
	ID       string `toml:"id" json:"id"`
	Name     string `toml:"name" json:"name"`
	Choice   string `toml:"choice" json:"choice"` // one | any
	Required bool   `toml:"required" json:"required"`
	Note     string `toml:"note" json:"note"`
	Role     string `toml:"role" json:"role"` // used in "Installing Zed, your code editor…"
	// Hardware categories (drivers) list modules that are offered only when their [[detect]]
	// rules match this computer; the category is left out of the picker otherwise.
	Hardware bool     `toml:"hardware" json:"hardware,omitempty"`
	Modules  []string `toml:"modules" json:"modules"`
}

// Rule is the picker hint ("Pick one" / "Pick any").
func (c Category) Rule() string {
	if c.Choice == "one" {
		return "Pick one"
	}
	return "Pick any"
}

// Install is one way to install a module; the first method that works wins.
type Install struct {
	Method     string   `toml:"method" json:"method"`
	Packages   []string `toml:"packages" json:"packages,omitempty"`
	Remove     []string `toml:"remove" json:"remove,omitempty"` // removed when a live-image default is unticked (default: packages)
	Copr       string   `toml:"copr" json:"copr,omitempty"`
	Repos      []string `toml:"repos" json:"repos,omitempty"` // repositories to enable first (rpmfusion-free, …)
	Swap       []string `toml:"swap" json:"swap,omitempty"`   // "from=to" dnf swaps (with --allowerasing)
	Remote     string   `toml:"remote" json:"remote,omitempty"`
	Ref        string   `toml:"ref" json:"ref,omitempty"` // flatpak app id; empty = only add the remote
	Attr       string   `toml:"attr" json:"attr,omitempty"`
	Verified   bool     `toml:"verified" json:"verified"`
	Runtime    string   `toml:"runtime" json:"runtime,omitempty"`
	DownloadMB float64  `toml:"download_mb" json:"download_mb"`
	DesktopID  string   `toml:"desktop_id" json:"desktop_id,omitempty"` // overrides [defaults] for this method
	Command    string   `toml:"command" json:"command,omitempty"`
	Note       string   `toml:"note" json:"-"`
}

// Defaults declares what the module becomes the default for.
type Defaults struct {
	DesktopID string   `toml:"desktop_id" json:"desktop_id,omitempty"`
	Mime      []string `toml:"mime" json:"mime,omitempty"`
	Role      string   `toml:"role" json:"role,omitempty"`       // key in /etc/arctic/default-apps
	Command   string   `toml:"command" json:"command,omitempty"` // may contain {terminal}
	Shell     string   `toml:"shell" json:"shell,omitempty"`     // login shell for the shell category
}

// Session holds desktop-component settings (only used by system modules in v0.1).
type Session struct {
	Services       []string `toml:"services" json:"services,omitempty"`               // systemctl --root enable
	GlobalServices []string `toml:"global_services" json:"global_services,omitempty"` // systemctl --global enable
}

// Detect is one hardware rule of a driver module: a device on the bus with this vendor, one
// of these classes (class + subclass, "0300") and either one of Devices or a device id in
// [DeviceMin, DeviceMax], and not in Exclude. Ids are four lower-case hex digits.
type Detect struct {
	Bus       string   `toml:"bus" json:"bus"` // "pci"
	Vendor    string   `toml:"vendor" json:"vendor"`
	Class     []string `toml:"class" json:"class"`
	Devices   []string `toml:"devices" json:"devices,omitempty"`
	DeviceMin string   `toml:"device_min" json:"device_min,omitempty"`
	DeviceMax string   `toml:"device_max" json:"device_max,omitempty"`
	Exclude   []string `toml:"exclude" json:"exclude,omitempty"`
}

// Matches reports whether a PCI device satisfies the rule.
func (d Detect) Matches(p hw.PCIDevice) bool {
	if d.Bus != "pci" || p.Vendor != d.Vendor {
		return false
	}
	classOK := false
	for _, c := range d.Class {
		if c == p.Class {
			classOK = true
		}
	}
	if !classOK {
		return false
	}
	for _, x := range d.Exclude {
		if x == p.Device {
			return false
		}
	}
	if len(d.Devices) > 0 {
		for _, x := range d.Devices {
			if x == p.Device {
				return true
			}
		}
		return false
	}
	lo, hi := d.DeviceMin, d.DeviceMax
	if lo == "" {
		lo = "0000"
	}
	if hi == "" {
		hi = "ffff"
	}
	// Four lower-case hex digits compare like numbers.
	return p.Device >= lo && p.Device <= hi
}

// Akmod names a kernel module that akmods builds on the computer (RPM Fusion's akmod-<name>
// package) and the module file checked after the build.
type Akmod struct {
	Name   string `toml:"name" json:"name"`     // akmods --akmod <name>
	Module string `toml:"module" json:"module"` // modinfo -k <kernel> <module>
}

// Boot holds kernel command line arguments a driver needs (added with grubby once it is
// installed, removed by nothing: the driver's own packages remove theirs).
type Boot struct {
	KernelArgs []string `toml:"kernel_args" json:"kernel_args,omitempty"`
	// LUKSDisplayArgs are added too when the disk is encrypted and the matched device drives
	// the boot screen (plymouth.use-simpledrm=1: the passphrase prompt shows at once).
	LUKSDisplayArgs []string `toml:"luks_display_args" json:"luks_display_args,omitempty"`
}

// Hooks are fixed scripts shipped inside the catalog (none in v0.1).
type Hooks struct {
	Post []string `toml:"post" json:"post,omitempty"`
}

// Module is one catalog entry.
type Module struct {
	ID          string    `toml:"id" json:"id"`
	Name        string    `toml:"name" json:"name"`
	Short       string    `toml:"short" json:"short,omitempty"`
	Summary     string    `toml:"summary" json:"summary"`
	Category    string    `toml:"category" json:"category"`
	Role        string    `toml:"role" json:"role,omitempty"` // overrides the category role in status lines
	Default     bool      `toml:"default" json:"default"`
	Always      bool      `toml:"always" json:"always"` // installed whatever is picked (bash, system modules)
	Hidden      bool      `toml:"hidden" json:"hidden"`
	Tile        string    `toml:"tile" json:"tile"`
	Icon        string    `toml:"icon" json:"icon"`
	InLiveImage bool      `toml:"in_live_image" json:"in_live_image"`
	GPU         bool      `toml:"gpu" json:"gpu"`
	Requires    []string  `toml:"requires" json:"requires,omitempty"`
	Conflicts   []string  `toml:"conflicts" json:"conflicts,omitempty"`
	Install     []Install `toml:"install" json:"install"`
	Defaults    Defaults  `toml:"defaults" json:"defaults"`
	Session     Session   `toml:"session" json:"session"`
	Hooks       Hooks     `toml:"hooks" json:"-"`
	// Drivers (modules of a hardware category) only.
	Detect      []Detect `toml:"detect" json:"detect,omitempty"`
	Akmod       *Akmod   `toml:"akmod" json:"akmod,omitempty"`
	Boot        *Boot    `toml:"boot" json:"boot,omitempty"`
	NetworkHint string   `toml:"network_hint" json:"network_hint,omitempty"` // Network step, {device} filled in

	Dir string `toml:"-" json:"-"`
	// Set by MarkDetected: a device matched (Device is its label, PCI the device, BootDisplay
	// whether it drives the boot screen).
	Detected    bool         `toml:"-" json:"-"`
	Device      string       `toml:"-" json:"-"`
	PCI         hw.PCIDevice `toml:"-" json:"-"`
	BootDisplay bool         `toml:"-" json:"-"`
	hardware    bool
}

// IsHardware reports whether the module is a driver (listed in a hardware category).
func (m *Module) IsHardware() bool { return m.hardware }

// AkmodName is the akmods name of a driver built on the computer ("" for everything else).
func (m *Module) AkmodName() string {
	if m.Akmod == nil {
		return ""
	}
	return m.Akmod.Name
}

// KernelArgs are the arguments the driver adds to the kernel command line; luks says the
// disk is encrypted (then the display arguments apply when the device drives the screen).
func (m *Module) KernelArgs(luks bool) []string {
	if m.Boot == nil {
		return nil
	}
	args := append([]string{}, m.Boot.KernelArgs...)
	if luks && m.BootDisplay {
		args = append(args, m.Boot.LUKSDisplayArgs...)
	}
	return args
}

// Fill replaces {device} in a driver's copy with the detected device's label.
func (m *Module) Fill(s string) string {
	dev := m.Device
	if dev == "" {
		dev = "hardware"
	}
	return strings.ReplaceAll(s, "{device}", dev)
}

// Available reports whether the picker may offer the module: visible, and for drivers only
// when their hardware was detected.
func (m *Module) Available() bool {
	return !m.Hidden && (len(m.Detect) == 0 || m.Detected)
}

// DisplayShort is the short name used in summaries ("Zen", "Collabora").
func (m *Module) DisplayShort() string {
	if m.Short != "" {
		return m.Short
	}
	return m.Name
}

// RemovePackages are the packages removed when this live-image module is unticked.
func (in Install) RemovePackages() []string {
	if len(in.Remove) > 0 {
		return in.Remove
	}
	return in.Packages
}

// MarkPreinstalled sets InLiveImage on the Flatpak apps the live image ships although the
// catalog doesn't list them there (the ISO build preinstalls Zen only while the ISO stays
// under 2 GiB). has reports whether a ref is installed in the image. It returns the ids.
func (c *Catalog) MarkPreinstalled(has func(ref string) bool) []string {
	var ids []string
	for _, id := range c.Order {
		m := c.Modules[id]
		p := m.Primary()
		if !m.InLiveImage && p.Method == MethodFlatpak && p.Ref != "" && has(p.Ref) {
			m.InLiveImage = true
			ids = append(ids, id)
		}
	}
	return ids
}

// Primary is the preferred install method.
func (m *Module) Primary() Install {
	if len(m.Install) == 0 {
		return Install{}
	}
	return m.Install[0]
}

// DownloadMB is the download size of the preferred method (0 when in the live image).
func (m *Module) DownloadMB() float64 {
	if m.InLiveImage {
		return 0
	}
	return m.Primary().DownloadMB
}

// Catalog is the loaded catalog.
type Catalog struct {
	Nixpkgs    string             `json:"nixpkgs"`
	Categories []Category         `json:"categories"`
	Runtimes   map[string]float64 `json:"runtimes"` // flatpak runtime ref → download MB
	Modules    map[string]*Module `json:"-"`
	// Order lists visible modules in picker order, then system modules.
	Order []string `json:"-"`
}

type catalogFile struct {
	Nixpkgs    string             `toml:"nixpkgs"`
	Categories []Category         `toml:"category"`
	Runtimes   map[string]float64 `toml:"runtimes"`
}

// DefaultDirs is where arcticd looks for the catalog, in order.
var DefaultDirs = []string{"/usr/share/arctic/catalog"}

var idRe = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*$`)

// LoadDir loads a catalog from a directory.
func LoadDir(dir string) (*Catalog, error) {
	return Load(os.DirFS(dir))
}

// Load loads a catalog from a file system rooted at the catalog directory.
func Load(fsys fs.FS) (*Catalog, error) {
	data, err := fs.ReadFile(fsys, "catalog.toml")
	if err != nil {
		return nil, fmt.Errorf("catalog: %w", err)
	}
	var cf catalogFile
	if err := toml.Unmarshal(data, &cf); err != nil {
		return nil, fmt.Errorf("catalog.toml: %w", err)
	}
	c := &Catalog{Nixpkgs: cf.Nixpkgs, Categories: cf.Categories, Runtimes: cf.Runtimes, Modules: map[string]*Module{}}
	if c.Runtimes == nil {
		c.Runtimes = map[string]float64{}
	}
	paths, err := fs.Glob(fsys, "*/*/module.toml")
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	var errs []error
	for _, p := range paths {
		data, err := fs.ReadFile(fsys, p)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		m := &Module{}
		if err := toml.Unmarshal(data, m); err != nil {
			errs = append(errs, fmt.Errorf("%s: %w", p, err))
			continue
		}
		m.Dir = path.Dir(p)
		dirCat, dirID := path.Split(m.Dir)
		dirCat = strings.TrimSuffix(dirCat, "/")
		if m.ID != dirID {
			errs = append(errs, fmt.Errorf("%s: id %q does not match its directory", p, m.ID))
		}
		if dirCat == "_system" {
			if m.Category != "system" || !m.Hidden {
				errs = append(errs, fmt.Errorf("%s: modules in _system need category = \"system\" and hidden = true", p))
			}
		} else if m.Category != dirCat {
			errs = append(errs, fmt.Errorf("%s: category %q does not match its directory", p, m.Category))
		}
		if _, dup := c.Modules[m.ID]; dup {
			errs = append(errs, fmt.Errorf("%s: duplicate module id %q", p, m.ID))
			continue
		}
		c.Modules[m.ID] = m
	}
	if len(errs) > 0 {
		return nil, errors.Join(errs...)
	}
	for _, cat := range c.Categories {
		for _, id := range cat.Modules {
			if m, ok := c.Modules[id]; ok && cat.Hardware {
				m.hardware = true
			}
		}
	}
	if err := c.check(); err != nil {
		return nil, err
	}
	for _, cat := range c.Categories {
		c.Order = append(c.Order, cat.Modules...)
	}
	var sys []string
	for id, m := range c.Modules {
		if m.Hidden {
			sys = append(sys, id)
		}
	}
	sort.Strings(sys)
	c.Order = append(c.Order, sys...)
	return c, nil
}

// check validates the catalog's internal consistency.
func (c *Catalog) check() error {
	var errs []error
	bad := func(format string, a ...any) { errs = append(errs, fmt.Errorf(format, a...)) }
	seen := map[string]string{}
	catIDs := map[string]bool{}
	for _, cat := range c.Categories {
		if !idRe.MatchString(cat.ID) {
			bad("category %q: invalid id", cat.ID)
		}
		catIDs[cat.ID] = true
		if cat.Choice != "one" && cat.Choice != "any" {
			bad("category %q: choice must be \"one\" or \"any\"", cat.ID)
		}
		if cat.Name == "" {
			bad("category %q: missing name", cat.ID)
		}
		defaults := 0
		for _, id := range cat.Modules {
			m, ok := c.Modules[id]
			if !ok {
				bad("category %q lists unknown module %q", cat.ID, id)
				continue
			}
			if prev, dup := seen[id]; dup {
				bad("module %q is listed in %q and %q", id, prev, cat.ID)
			}
			seen[id] = cat.ID
			if m.Category != cat.ID {
				bad("module %q has category %q but is listed in %q", id, m.Category, cat.ID)
			}
			if m.Default {
				defaults++
			}
		}
		if cat.Choice == "one" && defaults > 1 {
			bad("category %q: %d defaults for a pick-one category", cat.ID, defaults)
		}
		if cat.Required && defaults == 0 {
			bad("category %q is required but has no default", cat.ID)
		}
		if cat.Hardware && (cat.Choice != "any" || cat.Required) {
			bad("category %q: hardware categories must be choice = \"any\" and not required", cat.ID)
		}
	}
	for id, m := range c.Modules {
		if !idRe.MatchString(id) {
			bad("module %q: invalid id", id)
		}
		if m.Name == "" {
			bad("module %q: missing name", id)
		}
		if !m.Hidden {
			if _, ok := seen[id]; !ok {
				bad("module %q is not listed in any category", id)
			}
			if !catIDs[m.Category] {
				bad("module %q: unknown category %q", id, m.Category)
			}
			if m.Summary == "" || m.Tile == "" {
				bad("module %q: visible modules need summary and tile", id)
			}
		} else if m.Default {
			bad("module %q: hidden modules cannot be defaults (use always)", id)
		}
		if len(m.Install) == 0 {
			bad("module %q: needs at least one [[install]]", id)
		}
		for i, in := range m.Install {
			where := fmt.Sprintf("module %q install[%d]", id, i)
			switch in.Method {
			case MethodDNF:
				if len(in.Packages) == 0 {
					bad("%s: dnf needs packages", where)
				}
				for _, s := range in.Swap {
					if f, t, ok := strings.Cut(s, "="); !ok || f == "" || t == "" {
						bad("%s: swap %q must be \"from=to\"", where, s)
					}
				}
			case MethodCopr:
				if len(in.Packages) == 0 || !strings.Contains(in.Copr, "/") {
					bad("%s: copr needs copr = \"owner/project\" and packages", where)
				}
			case MethodFlatpak:
				if in.Remote == "" {
					bad("%s: flatpak installs must name their remote", where)
				}
			case MethodNix:
				if in.Attr == "" {
					bad("%s: nix needs attr", where)
				}
				if m.GPU {
					bad("%s: nix is only allowed for CLI/TUI modules (gpu = false)", where)
				}
			default:
				bad("%s: unknown method %q", where, in.Method)
			}
			for _, r := range in.Repos {
				if _, ok := KnownRepos[r]; !ok {
					bad("%s: unknown repo %q", where, r)
				}
			}
			// A shared download (Flatpak runtime, the kernel module build tools) is counted
			// once per install, so it needs its size in catalog.toml.
			if in.Runtime != "" {
				if _, ok := c.Runtimes[in.Runtime]; !ok {
					bad("%s: runtime %q has no size in catalog.toml [runtimes]", where, in.Runtime)
				}
			}
		}
		for _, r := range append(append([]string{}, m.Requires...), m.Conflicts...) {
			if _, ok := c.Modules[r]; !ok {
				bad("module %q: requires/conflicts names unknown module %q", id, r)
			}
		}
		c.checkDriver(m, bad)
	}
	return errors.Join(errs...)
}

var (
	akmodNameRe   = regexp.MustCompile(`^[a-z0-9-]+$`)
	akmodModuleRe = regexp.MustCompile(`^[a-z0-9_]+$`)
	// One kernel argument: name[=value], no spaces or quotes (grubby gets them as one word).
	kernelArgRe = regexp.MustCompile(`^[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,:/-]+)?$`)
)

// checkDriver validates the hardware fields: [[detect]] only (and always) on modules of a
// hardware category, strict ids, [akmod] only with an RPM Fusion nonfree dnf method, and
// kernel arguments that are single plain words.
func (c *Catalog) checkDriver(m *Module, bad func(string, ...any)) {
	id := m.ID
	switch {
	case m.hardware && len(m.Detect) == 0:
		bad("module %q: modules of a hardware category need at least one [[detect]]", id)
	case !m.hardware && len(m.Detect) > 0:
		bad("module %q: [[detect]] is only allowed in a hardware category", id)
	}
	if !m.hardware && (m.Akmod != nil || m.Boot != nil || m.NetworkHint != "") {
		bad("module %q: [akmod], [boot] and network_hint are only allowed in a hardware category", id)
	}
	if m.hardware && (m.Always || m.Hidden) {
		bad("module %q: drivers can't be hidden or always installed", id)
	}
	for i, d := range m.Detect {
		where := fmt.Sprintf("module %q detect[%d]", id, i)
		if d.Bus != "pci" {
			bad("%s: bus must be \"pci\"", where)
		}
		if !hex4Re.MatchString(d.Vendor) {
			bad("%s: vendor %q must be four lower-case hex digits", where, d.Vendor)
		}
		if len(d.Class) == 0 {
			bad("%s: needs at least one class", where)
		}
		for _, list := range [][]string{d.Class, d.Devices, d.Exclude} {
			for _, x := range list {
				if !hex4Re.MatchString(x) {
					bad("%s: %q must be four lower-case hex digits", where, x)
				}
			}
		}
		for _, x := range []string{d.DeviceMin, d.DeviceMax} {
			if x != "" && !hex4Re.MatchString(x) {
				bad("%s: device range %q must be four lower-case hex digits", where, x)
			}
		}
		if len(d.Devices) > 0 && (d.DeviceMin != "" || d.DeviceMax != "") {
			bad("%s: use devices or device_min/device_max, not both", where)
		}
		if d.DeviceMin != "" && d.DeviceMax != "" && d.DeviceMin > d.DeviceMax {
			bad("%s: device_min %s is above device_max %s", where, d.DeviceMin, d.DeviceMax)
		}
	}
	if a := m.Akmod; a != nil {
		if !akmodNameRe.MatchString(a.Name) || !akmodModuleRe.MatchString(a.Module) {
			bad("module %q: [akmod] needs name (a-z, 0-9, -) and module (a-z, 0-9, _)", id)
		}
		p := m.Primary()
		nonfree := false
		for _, r := range p.Repos {
			if r == "rpmfusion-nonfree" {
				nonfree = true
			}
		}
		if p.Method != MethodDNF || !nonfree {
			bad("module %q: [akmod] drivers need a first [[install]] with method = \"dnf\" and repos including rpmfusion-nonfree", id)
		}
	}
	if b := m.Boot; b != nil {
		for _, a := range append(append([]string{}, b.KernelArgs...), b.LUKSDisplayArgs...) {
			if !kernelArgRe.MatchString(a) {
				bad("module %q: kernel argument %q is not a single name[=value] word", id, a)
			}
		}
	}
}

var hex4Re = regexp.MustCompile(`^[0-9a-f]{4}$`)

// KnownRepos are the extra repositories a dnf method may ask for. Setting them up is code
// owned by the installer (keys from distribution-gpg-keys, never --nogpgcheck).
var KnownRepos = map[string]string{
	"rpmfusion-free":    "RPM Fusion free",
	"rpmfusion-nonfree": "RPM Fusion nonfree",
}

// Category returns a category by id.
func (c *Catalog) Category(id string) (Category, bool) {
	for _, cat := range c.Categories {
		if cat.ID == id {
			return cat, true
		}
	}
	return Category{}, false
}

// RoleFor is the plain-language role used in "Installing Zed, your code editor…".
func (c *Catalog) RoleFor(m *Module) string {
	if m.Role != "" {
		return m.Role
	}
	if cat, ok := c.Category(m.Category); ok && cat.Role != "" {
		return cat.Role
	}
	return "app"
}

// Selection maps category id → module ids.
type Selection map[string][]string

// Clone copies a selection.
func (s Selection) Clone() Selection {
	out := Selection{}
	for k, v := range s {
		out[k] = append([]string{}, v...)
	}
	return out
}

// Contains reports whether id is selected.
func (s Selection) Contains(id string) bool {
	for _, ids := range s {
		for _, x := range ids {
			if x == id {
				return true
			}
		}
	}
	return false
}

// DefaultSelection is what the picker starts with. Drivers are ticked only when their device
// was detected, and not when an earlier driver that conflicts with them is ticked already
// (a machine with two NVIDIA cards of different generations gets the first one's driver).
func (c *Catalog) DefaultSelection() Selection {
	sel := Selection{}
	for _, cat := range c.Categories {
		sel[cat.ID] = []string{}
		for _, id := range cat.Modules {
			m := c.Modules[id]
			if !m.Default || (m.hardware && !m.Detected) {
				continue
			}
			clash := false
			for _, x := range m.Conflicts {
				if sel.Contains(x) {
					clash = true
				}
			}
			for _, prev := range sel[cat.ID] {
				for _, x := range c.Modules[prev].Conflicts {
					if x == id {
						clash = true
					}
				}
			}
			if !clash {
				sel[cat.ID] = append(sel[cat.ID], id)
			}
		}
	}
	return sel
}

// MarkDetected matches the drivers' [[detect]] rules against the machine's PCI devices and
// records the first matching device on each driver (Detected, Device, PCI, BootDisplay).
// Drivers that match nothing are not offered. It returns the detected drivers in catalog
// order. Call it once, before DefaultSelection, Picker and Validate are used.
func (c *Catalog) MarkDetected(h hw.Hardware) []*Module {
	boot, hasBoot := h.BootDisplay()
	var out []*Module
	for _, id := range c.Order {
		m := c.Modules[id]
		if !m.hardware {
			continue
		}
		m.Detected, m.Device, m.PCI, m.BootDisplay = false, "", hw.PCIDevice{}, false
		for _, p := range h.PCI {
			if !m.MatchesDevice(p) {
				continue
			}
			m.Detected, m.Device, m.PCI = true, p.Label(), p
			m.BootDisplay = hasBoot && p.IsDisplay() && p.Slot == boot.Slot
			break
		}
		if m.Detected {
			out = append(out, m)
		}
	}
	return out
}

// MatchesDevice reports whether any of the module's [[detect]] rules matches the device.
func (m *Module) MatchesDevice(p hw.PCIDevice) bool {
	for _, d := range m.Detect {
		if d.Matches(p) {
			return true
		}
	}
	return false
}

// DetectedDrivers are the drivers MarkDetected found hardware for, in catalog order.
func (c *Catalog) DetectedDrivers() []*Module {
	var out []*Module
	for _, id := range c.Order {
		if m := c.Modules[id]; m.hardware && m.Detected {
			out = append(out, m)
		}
	}
	return out
}

// Normalize orders each category's ids in catalog order and drops duplicates. Unknown ids are
// kept (Validate reports them).
func (c *Catalog) Normalize(sel Selection) Selection {
	out := Selection{}
	for k, ids := range sel {
		pos := map[string]int{}
		if cat, ok := c.Category(k); ok {
			for i, id := range cat.Modules {
				pos[id] = i
			}
		}
		seen := map[string]bool{}
		var list []string
		for _, id := range ids {
			if !seen[id] {
				seen[id] = true
				list = append(list, id)
			}
		}
		sort.SliceStable(list, func(i, j int) bool {
			pi, iok := pos[list[i]]
			pj, jok := pos[list[j]]
			if iok && jok {
				return pi < pj
			}
			return iok && !jok
		})
		if list == nil {
			list = []string{}
		}
		out[k] = list
	}
	for _, cat := range c.Categories {
		if _, ok := out[cat.ID]; !ok {
			out[cat.ID] = []string{}
		}
	}
	return out
}

// Validate checks a selection: known ids in the right categories, pick-one rules, required
// categories, conflicts and requires. It returns field errors keyed by category id.
func (c *Catalog) Validate(sel Selection) map[string]string {
	fields := map[string]string{}
	set := func(k, msg string) {
		if _, ok := fields[k]; !ok {
			fields[k] = msg
		}
	}
	for k, ids := range sel {
		cat, ok := c.Category(k)
		if !ok {
			set(k, "This isn't one of the app groups.")
			continue
		}
		for _, id := range ids {
			m, ok := c.Modules[id]
			if !ok || m.Hidden {
				set(k, fmt.Sprintf("We don't know an app called %q.", id))
			} else if m.hardware && !m.Detected {
				set(k, fmt.Sprintf("%s is only for hardware this computer doesn’t have.", m.Name))
			} else if m.Category != k {
				set(k, fmt.Sprintf("%s belongs under %s.", m.Name, c.catName(m.Category)))
			}
		}
		if cat.Choice == "one" && len(ids) > 1 {
			set(k, fmt.Sprintf("Pick just one %s.", strings.ToLower(cat.Name)))
		}
	}
	for _, cat := range c.Categories {
		if cat.Required && len(sel[cat.ID]) == 0 {
			set(cat.ID, fmt.Sprintf("Pick a %s.", strings.ToLower(cat.Name)))
		}
	}
	if len(fields) > 0 {
		return fields
	}
	chosen := c.Resolve(sel)
	have := map[string]bool{}
	for _, m := range chosen {
		have[m.ID] = true
	}
	for _, m := range chosen {
		for _, x := range m.Conflicts {
			if have[x] {
				set(m.Category, fmt.Sprintf("%s and %s can't be installed together.", m.Name, c.Modules[x].Name))
			}
		}
		for _, r := range m.Requires {
			if !have[r] {
				set(m.Category, fmt.Sprintf("%s needs %s. Tick it too.", m.Name, c.Modules[r].Name))
			}
		}
	}
	return fields
}

func (c *Catalog) catName(id string) string {
	if cat, ok := c.Category(id); ok {
		return cat.Name
	}
	return id
}

// Resolve returns every module that ends up on the system for a selection, in catalog order:
// selected apps, apps that are always installed (bash) and hidden system modules. Unknown ids
// are ignored (Validate reports them).
func (c *Catalog) Resolve(sel Selection) []*Module {
	var out []*Module
	for _, id := range c.Order {
		m := c.Modules[id]
		if m.Always || sel.Contains(id) {
			out = append(out, m)
		}
	}
	return out
}

// Apps are the apps the person ticked, in catalog order: what "9 apps" counts. Modules that
// are installed anyway (bash, hidden system modules) are not counted unless ticked.
func (c *Catalog) Apps(sel Selection) []*Module {
	var out []*Module
	for _, m := range c.Resolve(sel) {
		if !m.Hidden && !m.hardware && sel.Contains(m.ID) {
			out = append(out, m)
		}
	}
	return out
}

// Drivers are the drivers a selection installs (modules of a hardware category), in catalog
// order. They are not counted as apps.
func (c *Catalog) Drivers(sel Selection) []*Module {
	var out []*Module
	for _, m := range c.Resolve(sel) {
		if m.hardware && sel.Contains(m.ID) {
			out = append(out, m)
		}
	}
	return out
}

// Estimate is the picker footer.
type Estimate struct {
	Apps    int    `json:"apps"`
	Drivers int    `json:"drivers,omitempty"`
	Bytes   int64  `json:"bytes"`
	Label   string `json:"label"`
}

// EstimateDownload counts the apps a selection installs and sums what has to be downloaded:
// modules already in the live image cost nothing, shared Flatpak runtimes are counted once.
func (c *Catalog) EstimateDownload(sel Selection) Estimate {
	var mb float64
	runtimes := map[string]bool{}
	apps, drivers := 0, 0
	for _, m := range c.Resolve(sel) {
		switch {
		case m.hardware && sel.Contains(m.ID):
			drivers++
		case !m.Hidden && sel.Contains(m.ID):
			apps++
		}
		if m.InLiveImage {
			continue
		}
		in := m.Primary()
		mb += in.DownloadMB
		if in.Runtime != "" && !runtimes[in.Runtime] {
			runtimes[in.Runtime] = true
			mb += c.Runtimes[in.Runtime]
		}
	}
	bytes := int64(mb * hw.MB)
	count := plural(apps, "app", "apps")
	if drivers > 0 {
		count += " + " + plural(drivers, "driver", "drivers")
	}
	label := fmt.Sprintf("%s · %s download", count, hw.DownloadLabel(bytes))
	if bytes == 0 {
		label = fmt.Sprintf("%s · nothing to download", count)
	}
	return Estimate{Apps: apps, Drivers: drivers, Bytes: bytes, Label: label}
}

func plural(n int, one, many string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, one)
	}
	return fmt.Sprintf("%d %s", n, many)
}

// PickerCategory / PickerModule are the JSON shapes of the apps step options.
type PickerCategory struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Choice   string `json:"choice"`
	Required bool   `json:"required"`
	Rule     string `json:"rule"`
	Note     string `json:"note"`
	// Hardware marks the drivers section (only present when a driver was detected).
	Hardware bool `json:"hardware,omitempty"`
}

type PickerModule struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Summary     string  `json:"summary"`
	Category    string  `json:"category"`
	Default     bool    `json:"default"`
	Always      bool    `json:"always"`
	Tile        string  `json:"tile"`
	Icon        string  `json:"icon"`
	DownloadMB  float64 `json:"download_mb"`
	Source      string  `json:"source"` // "Flathub", "Fedora", "COPR", "Nix"
	Method      string  `json:"method"`
	Verified    bool    `json:"verified"`
	InLiveImage bool    `json:"in_live_image"`
	// Device names the detected hardware a driver is for ("NVIDIA GeForce RTX 4060 …").
	Device string `json:"device,omitempty"`
}

// Picker is the catalog as the apps step shows it.
type Picker struct {
	Categories []PickerCategory `json:"categories"`
	Modules    []PickerModule   `json:"modules"`
}

// Picker returns the visible catalog in picker order. Drivers appear only when their
// hardware was detected, and a hardware category only when it offers a driver.
func (c *Catalog) Picker() Picker {
	p := Picker{Categories: []PickerCategory{}, Modules: []PickerModule{}}
	def := c.DefaultSelection()
	for _, cat := range c.Categories {
		var mods []PickerModule
		for _, id := range cat.Modules {
			m := c.Modules[id]
			if !m.Available() {
				continue
			}
			in := m.Primary()
			pm := PickerModule{
				ID: m.ID, Name: m.Name, Summary: m.Summary, Category: m.Category, Default: m.Default, Always: m.Always,
				Tile: m.Tile, Icon: m.Icon, DownloadMB: m.DownloadMB(), Source: SourceLabel(in), Method: in.Method,
				Verified: in.Verified, InLiveImage: m.InLiveImage,
			}
			if m.hardware {
				pm.Summary, pm.Device, pm.Default = m.Fill(m.Summary), m.Device, def.Contains(m.ID)
			}
			mods = append(mods, pm)
		}
		if cat.Hardware && len(mods) == 0 {
			continue
		}
		p.Categories = append(p.Categories, PickerCategory{ID: cat.ID, Name: cat.Name, Choice: cat.Choice, Required: cat.Required, Rule: cat.Rule(), Note: cat.Note, Hardware: cat.Hardware})
		p.Modules = append(p.Modules, mods...)
	}
	return p
}

// SourceLabel names where an install method downloads from.
func SourceLabel(in Install) string {
	switch in.Method {
	case MethodFlatpak:
		if in.Remote == "flathub" {
			return "Flathub"
		}
		return "Flatpak"
	case MethodCopr:
		return "COPR"
	case MethodNix:
		return "Nix"
	case MethodDNF:
		for _, r := range in.Repos {
			if strings.HasPrefix(r, "rpmfusion") {
				return "RPM Fusion"
			}
		}
		return "Fedora"
	}
	return in.Method
}
