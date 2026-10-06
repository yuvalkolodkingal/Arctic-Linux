package catalog

import (
	"strings"
	"testing"
	"testing/fstest"

	"github.com/yuvalkolodkingal/o-tism/internal/hw"
)

func fixture(t *testing.T, name string) hw.Hardware {
	t.Helper()
	h, ok := hw.Fixture(name, false)
	if !ok {
		t.Fatalf("no fixture %q", name)
	}
	return h
}

func TestDetectRule(t *testing.T) {
	gpu := func(dev, class string) hw.PCIDevice {
		return hw.PCIDevice{Vendor: "10de", Device: dev, Class: class}
	}
	r := Detect{Bus: "pci", Vendor: "10de", Class: []string{"0300", "0302"}, DeviceMin: "1340", DeviceMax: "1dff", Exclude: []string{"1400"}}
	for _, c := range []struct {
		p    hw.PCIDevice
		want bool
	}{
		{gpu("1340", "0300"), true},
		{gpu("1c82", "0302"), true},
		{gpu("1dff", "0300"), true},
		{gpu("1e02", "0300"), false}, // above the range
		{gpu("1180", "0300"), false}, // below
		{gpu("1400", "0300"), false}, // excluded
		{gpu("1c82", "0403"), false}, // HDMI audio function
		{hw.PCIDevice{Vendor: "1002", Device: "1c82", Class: "0300"}, false},
	} {
		if got := r.Matches(c.p); got != c.want {
			t.Errorf("%+v: %v, want %v", c.p, got, c.want)
		}
	}
	list := Detect{Bus: "pci", Vendor: "14e4", Class: []string{"0280"}, Devices: []string{"43a0"}}
	if !list.Matches(hw.PCIDevice{Vendor: "14e4", Device: "43a0", Class: "0280"}) || list.Matches(hw.PCIDevice{Vendor: "14e4", Device: "43a3", Class: "0280"}) {
		t.Error("device list")
	}
}

// The NVIDIA hybrid laptop: NVIDIA's driver for the RTX 4060 (render-only, class 0302) and
// Intel's media driver for the Iris Xe that draws the screen.
func TestMarkDetectedHybridLaptop(t *testing.T) {
	c := load(t)
	found := c.MarkDetected(fixture(t, "nvidia-laptop"))
	var ids []string
	for _, m := range found {
		ids = append(ids, m.ID)
	}
	if strings.Join(ids, " ") != "nvidia intel-media" {
		t.Fatalf("detected %v", ids)
	}
	nv := c.Modules["nvidia"]
	if nv.Device != "NVIDIA GeForce RTX 4060 Max-Q / Mobile" || nv.BootDisplay || nv.PCI.Slot != "0000:01:00.0" {
		t.Errorf("nvidia: %q boot=%v %+v", nv.Device, nv.BootDisplay, nv.PCI)
	}
	if args := nv.KernelArgs(true); strings.Join(args, " ") != "rd.driver.blacklist=nouveau,nova_core modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1" {
		t.Errorf("hybrid kernel args %v", args)
	}
	if !c.Modules["intel-media"].BootDisplay {
		t.Error("the Iris Xe draws the screen")
	}
	sel := c.DefaultSelection()
	if strings.Join(sel["drivers"], " ") != "nvidia intel-media" {
		t.Errorf("default drivers %v", sel["drivers"])
	}
	if f := c.Validate(sel); len(f) != 0 {
		t.Errorf("defaults invalid: %v", f)
	}
	// Drivers are listed first in the picker, with the device, and not counted as apps.
	p := c.Picker()
	if p.Categories[0].ID != "drivers" || !p.Categories[0].Hardware || p.Modules[0].ID != "nvidia" || len(p.Modules) != 134 {
		t.Fatalf("picker %+v / %d modules, first %+v", p.Categories[0], len(p.Modules), p.Modules[0])
	}
	if p.Modules[0].Device != nv.Device || !strings.Contains(p.Modules[0].Summary, "your NVIDIA GeForce RTX 4060") || !p.Modules[0].Default {
		t.Errorf("nvidia tile %+v", p.Modules[0])
	}
	est := c.EstimateDownload(sel)
	if est.Apps != 6 || est.Drivers != 2 || !strings.HasPrefix(est.Label, "6 apps + 2 drivers · ") {
		t.Errorf("estimate %+v", est)
	}
	if len(c.Apps(sel)) != 6 || len(c.Drivers(sel)) != 2 {
		t.Errorf("apps %d drivers %d", len(c.Apps(sel)), len(c.Drivers(sel)))
	}
	// The build tools are counted once for two akmod drivers.
	sel2 := sel.Clone()
	sel2["drivers"] = []string{"nvidia"}
	one := c.EstimateDownload(sel2).Bytes
	sel2["drivers"] = []string{}
	none := c.EstimateDownload(sel2).Bytes
	if one-none != int64((540+300)*hw.MB) {
		t.Errorf("nvidia + akmods = %d MB", (one-none)/hw.MB)
	}
}

func TestNVIDIADesktopBootDisplay(t *testing.T) {
	c := load(t)
	c.MarkDetected(fixture(t, "nvidia-desktop"))
	nv := c.Modules["nvidia"]
	if !nv.Detected || !nv.BootDisplay {
		t.Fatalf("nvidia %+v", nv.PCI)
	}
	if args := nv.KernelArgs(true); args[len(args)-1] != "plymouth.use-simpledrm=1" {
		t.Errorf("LUKS args %v", args)
	}
	if args := nv.KernelArgs(false); strings.Contains(strings.Join(args, " "), "plymouth") {
		t.Errorf("no-LUKS args %v", args)
	}
}

// Nothing detected: no drivers section, and asking for a driver is refused.
func TestNoDriversOffered(t *testing.T) {
	c := load(t)
	c.MarkDetected(fixture(t, "vm"))
	p := c.Picker()
	for _, cat := range p.Categories {
		if cat.ID == "drivers" {
			t.Fatal("drivers section without a driver")
		}
	}
	for _, m := range p.Modules {
		if m.Category == "drivers" {
			t.Fatalf("driver %s offered", m.ID)
		}
	}
	sel := c.DefaultSelection()
	sel["drivers"] = []string{"nvidia"}
	if f := c.Validate(sel); !strings.Contains(f["drivers"], "hardware this computer doesn’t have") {
		t.Errorf("validate %v", f)
	}
}

// Two conflicting drivers both detected (a Turing and a Pascal card): only the first is ticked.
func TestConflictingDriversDefault(t *testing.T) {
	c := load(t)
	h := fixture(t, "nvidia-desktop")
	h.PCI = append(h.PCI, hw.PCIDevice{Slot: "0000:02:00.0", Vendor: "10de", Device: "1c82", Class: "0300"})
	c.MarkDetected(h)
	sel := c.DefaultSelection()
	if strings.Join(sel["drivers"], " ") != "nvidia" {
		t.Fatalf("defaults %v", sel["drivers"])
	}
	sel["drivers"] = []string{"nvidia", "nvidia-580xx"}
	if f := c.Validate(sel); !strings.Contains(f["drivers"], "can't be installed together") {
		t.Errorf("validate %v", f)
	}
}

// The detection schema is strict.
func TestDriverSchema(t *testing.T) {
	const cat = `
[[category]]
id = "drivers"
name = "Drivers"
choice = "any"
hardware = true
modules = ["gpu"]

[[category]]
id = "video"
name = "Video"
choice = "any"
modules = ["player"]
`
	const player = `
id = "player"
name = "Player"
summary = "Plays."
category = "video"
tile = "mpv"
[[install]]
method = "dnf"
packages = ["mpv"]
`
	const gpuHead = `
id = "gpu"
name = "GPU driver"
summary = "For your {device}."
category = "drivers"
tile = "driver-gpu"
`
	const install = `
[[install]]
method = "dnf"
packages = ["akmod-x"]
repos = ["rpmfusion-nonfree"]
`
	good := gpuHead + `
[[detect]]
bus = "pci"
vendor = "10de"
class = ["0300"]
device_min = "1e00"
[akmod]
name = "x"
module = "x"
[boot]
kernel_args = ["modprobe.blacklist=nouveau,nova_core"]
` + install
	mk := func(gpu, pl, catalog string) error {
		_, err := Load(fstest.MapFS{
			"catalog.toml":             {Data: []byte(catalog)},
			"drivers/gpu/module.toml":  {Data: []byte(gpu)},
			"video/player/module.toml": {Data: []byte(pl)},
		})
		return err
	}
	if err := mk(good, player, cat); err != nil {
		t.Fatalf("good catalog: %v", err)
	}
	bad := map[string]struct{ gpu, player, cat, want string }{
		"no detect":         {gpuHead + install, player, cat, "need at least one [[detect]]"},
		"upper-case hex":    {strings.Replace(good, `"10de"`, `"10DE"`, 1), player, cat, "four lower-case hex digits"},
		"short id":          {strings.Replace(good, `"1e00"`, `"1e0"`, 1), player, cat, "four lower-case hex digits"},
		"list and range":    {strings.Replace(good, `device_min = "1e00"`, "device_min = \"1e00\"\ndevices = [\"1e02\"]", 1), player, cat, "not both"},
		"inverted range":    {strings.Replace(good, `device_min = "1e00"`, "device_min = \"2000\"\ndevice_max = \"1000\"", 1), player, cat, "above device_max"},
		"bus":               {strings.Replace(good, `bus = "pci"`, `bus = "usb"`, 1), player, cat, `bus must be "pci"`},
		"no class":          {strings.Replace(good, `class = ["0300"]`, `class = []`, 1), player, cat, "at least one class"},
		"unknown key":       {strings.Replace(good, `bus = "pci"`, "bus = \"pci\"\nsubvendor = \"17aa\"", 1), player, cat, "unknown key"},
		"akmod not nonfree": {strings.Replace(good, `repos = ["rpmfusion-nonfree"]`, `repos = []`, 1), player, cat, "rpmfusion-nonfree"},
		"shell in arg":      {strings.Replace(good, `"modprobe.blacklist=nouveau,nova_core"`, `"a=b; reboot"`, 1), player, cat, "not a single name[=value] word"},
		"detect on app":     {good, player + "[[detect]]\nbus = \"pci\"\nvendor = \"10de\"\nclass = [\"0300\"]\n", cat, "only allowed in a hardware category"},
		"hint on app":       {good, "network_hint = \"x\"\n" + player, cat, "only allowed in a hardware category"},
		"required drivers":  {good, player, strings.Replace(cat, "hardware = true", "hardware = true\nrequired = true", 1), "hardware categories must be"},
		"hidden driver":     {strings.Replace(good, `tile = "driver-gpu"`, "tile = \"driver-gpu\"\nhidden = true", 1), player, cat, "drivers can't be hidden"},
	}
	for name, b := range bad {
		err := mk(b.gpu, b.player, b.cat)
		if err == nil || !strings.Contains(err.Error(), b.want) {
			t.Errorf("%s: %v (want %q)", name, err, b.want)
		}
	}
}
