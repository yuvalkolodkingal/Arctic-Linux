package installer

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Options tune the pipeline.
type Options struct {
	// Target is where the new system is mounted (default /mnt).
	Target string
	// Source is the live root to copy ("" = /run/rootfsbase, else the mounted squashfs).
	Source string
	// FedoraRelease is the base release (RPM Fusion URLs, keys). Default "44".
	FedoraRelease string
	// LogPath is the engine log copied into the target (/var/log/arctic-install/).
	LogPath string
	// Salt fixes the password salt (tests); "" = random.
	Salt string
	// StopAfter ends the run successfully after the named phase (testing aid, e.g. "disk").
	StopAfter string
}

// LiveOnlyPackages are removed from the copied live root (PLAN §6.3).
var LiveOnlyPackages = []string{"arctic-live", "livesys-scripts", "arctic-installer", "dracut-live", "dracut-kiwi-live"}

// FlatpakRemotes maps catalog remote names to their .flatpakrepo URLs.
var FlatpakRemotes = map[string]string{
	"flathub": "https://dl.flathub.org/repo/flathub.flatpakrepo",
}

// Installer runs one install.
type Installer struct {
	R   Runner
	Job *backend.Job
	Rep backend.Reporter
	Opt Options

	t          *backend.Tracker
	cat        *catalog.Catalog
	lay        layout
	source     string
	reposDone  map[string]bool
	coprDone   map[string]bool
	remoteDone map[string]bool
	usedMethod map[string]catalog.Install
	skipped    map[string]bool
	deferred   []string
	flatpakRan bool
	bootNum    string // firmware boot entry this run created (removed again on failure)
}

type layout struct {
	disk                       string
	biosBoot, esp, boot, root  string
	espNum                     int
	espNew                     bool
	created                    []int // partitions sfdisk --append added (alongside), removed again on failure
	luks                       bool
	luksName, luksUUID         string
	rootDev                    string
	btrfsUUID, bootUUID, espID string
}

// New prepares an installer.
func New(r Runner, job *backend.Job, rep backend.Reporter, opt Options) *Installer {
	if opt.Target == "" {
		opt.Target = "/mnt"
	}
	if opt.FedoraRelease == "" {
		opt.FedoraRelease = "44"
	}
	if opt.LogPath == "" {
		opt.LogPath = job.LogPath
	}
	return &Installer{
		R: r, Job: job, Rep: rep, Opt: opt, cat: job.Catalog,
		reposDone: map[string]bool{}, coprDone: map[string]bool{}, remoteDone: map[string]bool{},
		usedMethod: map[string]catalog.Install{}, skipped: map[string]bool{},
	}
}

func (in *Installer) tgt(p string) string { return path.Join(in.Opt.Target, p) }

func (in *Installer) run(ctx context.Context, name string, args ...string) error {
	_, err := in.R.Run(ctx, Cmd{Name: name, Args: args})
	return err
}

func (in *Installer) chroot(ctx context.Context, c Cmd) error {
	_, err := in.R.Run(ctx, Chroot(in.Opt.Target, c))
	return err
}

func (in *Installer) output(ctx context.Context, name string, args ...string) (string, error) {
	res, err := in.R.Run(ctx, Cmd{Name: name, Args: args})
	return strings.TrimSpace(res.Stdout), err
}

func (in *Installer) write(p, content string, perm uint32) error {
	return in.R.WriteFile(p, []byte(content), fsMode(perm))
}

// Run executes the whole pipeline.
func (in *Installer) Run(ctx context.Context) error {
	apps := in.Job.Apps()
	in.t = backend.NewTracker(in.Rep, len(apps), 10*time.Minute, nil)
	for _, m := range apps {
		in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModQueued})
	}
	d := in.Job.Data
	in.R.Note("Arctic Linux install: %s %s (%s), firmware %s, encryption %v, %d apps",
		d.Disk.Mode, in.Job.Disk.Label(), in.Job.Disk.Path, in.Job.Firmware, d.Encryption.Enabled, len(apps))
	phases := []struct {
		phase, status string
		fn            func(context.Context) error
	}{
		{protocol.PhaseDisk, wizard.StatusDisk, in.diskPhase},
		{protocol.PhaseCopy, wizard.StatusCopy, in.copyPhase},
		{protocol.PhaseConfigure, wizard.StatusSetup, in.configurePhase},
		{protocol.PhaseBootloader, wizard.StatusBoot, in.bootloaderPhase},
		{protocol.PhaseApps, "Installing your apps…", in.appsPhase},
		{protocol.PhaseFinalize, wizard.StatusAccount, in.finalizePhase},
	}
	for _, p := range phases {
		if err := ctx.Err(); err != nil {
			return err
		}
		in.R.Note("")
		in.R.Note("== %s: %s", p.phase, p.status)
		in.t.Phase(p.phase, p.status)
		if err := p.fn(ctx); err != nil {
			in.Rep.Logf("%s failed: %v", p.phase, err)
			in.cleanup(context.Background())
			return fmt.Errorf("%s: %w", p.phase, err)
		}
		if p.phase == in.Opt.StopAfter {
			return nil
		}
	}
	in.t.Finish(wizard.StatusFinished)
	return nil
}

// cleanup unmounts and closes after a failure so "Try again" starts clean. In alongside mode
// it also removes the partitions this run added (wiping their signatures first), so the other
// system's disk is left as it was and a retry finds the same free space, and it removes the
// firmware boot entry this run created.
func (in *Installer) cleanup(ctx context.Context) {
	in.R.Note("cleanup after failure")
	in.R.Run(ctx, Cmd{Name: "umount", Args: []string{"-R", in.Opt.Target}, AllowFail: true})
	if in.lay.luksName != "" {
		in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=15"}, AllowFail: true})
		in.R.Run(ctx, Cmd{Name: "cryptsetup", Args: []string{"close", in.lay.luksName}, AllowFail: true})
	}
	in.R.Run(ctx, Cmd{Name: "umount", Args: []string{in.Opt.Target}, AllowFail: true}) // the private bind
	if len(in.lay.created) > 0 {
		args := []string{"--delete", in.lay.disk}
		for _, n := range in.lay.created {
			in.R.Run(ctx, Cmd{Name: "wipefs", Args: []string{"--all", hw.PartitionPath(in.lay.disk, n)}, AllowFail: true})
			args = append(args, strconv.Itoa(n))
		}
		in.R.Run(ctx, Cmd{Name: "sfdisk", Args: args, AllowFail: true})
		in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=15"}, AllowFail: true})
	}
	// A boot entry for an install that failed would start first next time (and, alongside,
	// instead of the other system).
	if in.bootNum != "" {
		in.R.Run(ctx, Cmd{Name: "efibootmgr", Args: []string{"--delete-bootnum", "--bootnum", in.bootNum}, AllowFail: true})
	}
}

// ---- disk ----

func (in *Installer) diskPhase(ctx context.Context) error {
	job := in.Job
	disk := job.Disk
	if !in.R.Exists(disk.Path) {
		return fmt.Errorf("%s is gone", disk.Path)
	}
	in.lay = layout{disk: disk.Path, luks: job.Data.Encryption.Enabled}
	if err := in.releaseDisk(ctx, disk.Path); err != nil {
		return err
	}
	var err error
	if job.Data.Disk.Mode == wizard.ModeAlongside {
		err = in.partitionAlongside(ctx)
	} else {
		err = in.partitionErase(ctx)
	}
	if err != nil {
		return err
	}
	in.t.Update(0.3, "")
	if err := in.waitForDevices(ctx, in.lay.boot, in.lay.root, in.lay.esp); err != nil {
		return err
	}
	if in.lay.espNew {
		if err := in.run(ctx, "mkfs.vfat", "-F", "32", "-n", "EFI", in.lay.esp); err != nil {
			return err
		}
	}
	if err := in.run(ctx, "mkfs.ext4", "-F", "-q", "-L", "arctic-boot", in.lay.boot); err != nil {
		return err
	}
	in.t.Update(0.5, "")
	in.lay.rootDev = in.lay.root
	if in.lay.luks {
		if len(job.Secrets.LUKS) == 0 {
			return errors.New("no disk passphrase")
		}
		if _, err := in.R.Run(ctx, Cmd{
			Name: "cryptsetup", Args: []string{"luksFormat", "--batch-mode", "--type", "luks2", "--pbkdf", "argon2id", "--label", "arctic-root", "--key-file", "-", in.lay.root},
			Stdin: job.Secrets.LUKS, Secret: true, SecretLabel: "disk passphrase",
		}); err != nil {
			return err
		}
		uuid, err := in.uuid(ctx, in.lay.root)
		if err != nil {
			return err
		}
		in.lay.luksUUID = uuid
		in.lay.luksName = "luks-" + uuid
		if _, err := in.R.Run(ctx, Cmd{
			Name: "cryptsetup", Args: []string{"open", "--allow-discards", "--key-file", "-", in.lay.root, in.lay.luksName},
			Stdin: job.Secrets.LUKS, Secret: true, SecretLabel: "disk passphrase",
		}); err != nil {
			return err
		}
		in.lay.rootDev = "/dev/mapper/" + in.lay.luksName
	}
	in.t.Update(0.7, "")
	if err := in.privateTarget(ctx); err != nil {
		return err
	}
	root, tgt := in.lay.rootDev, in.Opt.Target
	steps := [][]string{
		{"mkfs.btrfs", "-f", "-q", "-L", "arctic", root},
		{"mount", "-o", "compress=zstd:1", root, tgt},
	}
	for _, sv := range subvolumes {
		steps = append(steps, []string{"btrfs", "subvolume", "create", path.Join(tgt, sv.name)})
	}
	steps = append(steps, []string{"umount", tgt}, []string{"mount", "-o", "subvol=@,compress=zstd:1", root, tgt})
	for _, s := range steps {
		if err := in.run(ctx, s[0], s[1:]...); err != nil {
			return err
		}
	}
	for _, sv := range subvolumes[1:] {
		if err := in.R.MkdirAll(in.tgt(sv.mount), 0o755); err != nil {
			return err
		}
		if err := in.run(ctx, "mount", "-o", "subvol="+sv.name+",compress=zstd:1", root, in.tgt(sv.mount)); err != nil {
			return err
		}
	}
	if err := in.R.MkdirAll(in.tgt("/boot"), 0o755); err != nil {
		return err
	}
	if err := in.run(ctx, "mount", in.lay.boot, in.tgt("/boot")); err != nil {
		return err
	}
	if in.lay.esp != "" {
		if err := in.R.MkdirAll(in.tgt("/boot/efi"), 0o755); err != nil {
			return err
		}
		if err := in.run(ctx, "mount", "-o", "umask=0077", in.lay.esp, in.tgt("/boot/efi")); err != nil {
			return err
		}
	}
	for _, p := range []struct {
		dev string
		dst *string
	}{{in.lay.rootDev, &in.lay.btrfsUUID}, {in.lay.boot, &in.lay.bootUUID}, {in.lay.esp, &in.lay.espID}} {
		if p.dev == "" {
			continue
		}
		u, err := in.uuid(ctx, p.dev)
		if err != nil {
			return err
		}
		*p.dst = u
	}
	in.t.Update(1, "")
	return nil
}

// privateTarget makes the target directory a private mount point before anything is mounted
// on it. "/" is a shared mount (systemd), so every mount below it is copied into the mount
// namespaces of sandboxed services (ProtectSystem=, PrivateTmp=, …). Those copies drop out of
// umount propagation once the API file systems are bound in with --make-rslave, stay mounted,
// and keep the new btrfs alive, so closing LUKS at the end fails with "Device or resource
// busy". Under a private mount point the new system's mounts stay in this namespace.
func (in *Installer) privateTarget(ctx context.Context) error {
	tgt := in.Opt.Target
	if err := in.R.MkdirAll(tgt, 0o755); err != nil {
		return err
	}
	mnt, err := in.output(ctx, "findmnt", "--noheadings", "--output", "TARGET", "--mountpoint", tgt)
	if err != nil || strings.TrimSpace(mnt) == "" {
		// Not a mount point yet (findmnt exits 1): bind the directory onto itself.
		if err := in.run(ctx, "mount", "--bind", tgt, tgt); err != nil {
			return err
		}
	}
	return in.run(ctx, "mount", "--make-private", tgt)
}

// waitForDevices lets udev create the new partitions' device nodes (up to 15 s).
func (in *Installer) waitForDevices(ctx context.Context, devs ...string) error {
	if _, err := in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=15"}, AllowFail: true}); err != nil {
		return err
	}
	for i := 0; i < 75; i++ {
		missing := ""
		for _, d := range devs {
			// The node must exist and the kernel must know the partition (a stale node from
			// an earlier table can linger until udev catches up).
			if d != "" && (!in.R.Exists(d) || !in.R.Exists("/sys/class/block/"+path.Base(d))) {
				missing = d
			}
		}
		if missing == "" {
			return nil
		}
		if i == 0 {
			in.R.Run(ctx, Cmd{Name: "partprobe", Args: []string{in.lay.disk}, AllowFail: true})
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(200 * time.Millisecond):
		}
	}
	return fmt.Errorf("the new partitions on %s did not appear", in.lay.disk)
}

// blockNode is one device of `lsblk --json --tree --output PATH,TYPE,MOUNTPOINTS`: the disk,
// its partitions and, below them, their holders (md arrays, device-mapper devices).
type blockNode struct {
	Path        string      `json:"path"`
	Type        string      `json:"type"`
	Mountpoints []*string   `json:"mountpoints"`
	Children    []blockNode `json:"children"`
}

type diskMount struct{ dev, mountpoint string }

// diskUse lists what uses a disk: mounted file systems and swap anywhere below it, and the
// holders below its partitions (deepest first, each once).
func diskUse(nodes []blockNode) (mounts []diskMount, holders []blockNode) {
	seen := map[string]bool{}
	var walk func(n blockNode, depth int)
	walk = func(n blockNode, depth int) {
		for _, c := range n.Children {
			walk(c, depth+1)
		}
		for _, m := range n.Mountpoints {
			if m != nil && strings.TrimSpace(*m) != "" {
				mounts = append(mounts, diskMount{n.Path, strings.TrimSpace(*m)})
			}
		}
		if depth > 0 && n.Type != "part" && !seen[n.Path] {
			seen[n.Path] = true
			holders = append(holders, n)
		}
	}
	for _, n := range nodes {
		walk(n, 0)
	}
	// Unmount nested mount points before their parents.
	sort.SliceStable(mounts, func(i, j int) bool { return len(mounts[i].mountpoint) > len(mounts[j].mountpoint) })
	return mounts, holders
}

func (in *Installer) diskTree(ctx context.Context, disk string) ([]blockNode, error) {
	out, err := in.output(ctx, "lsblk", "--json", "--tree", "--output", "PATH,TYPE,MOUNTPOINTS", disk)
	if err != nil {
		return nil, err
	}
	var doc struct {
		Blockdevices []blockNode `json:"blockdevices"`
	}
	if err := json.Unmarshal([]byte(out), &doc); err != nil || len(doc.Blockdevices) == 0 {
		return nil, fmt.Errorf("couldn’t list what uses %s (lsblk: %v)", disk, err)
	}
	return doc.Blockdevices, nil
}

// releasable reports whether the installer may unmount a mount point of the target disk:
// the live session's automounts (a partition opened in the file manager), swap, and
// leftovers of an earlier attempt under the target.
func (in *Installer) releasable(mp string) bool {
	t := strings.TrimSuffix(in.Opt.Target, "/")
	return mp == "[SWAP]" || strings.HasPrefix(mp, "/run/media/") || mp == t || strings.HasPrefix(mp, t+"/")
}

// releaseDisk makes sure nothing on the live system holds the target disk before the first
// destructive command: sfdisk refuses a disk that is in use, and in erase mode wipefs would
// already have cleared the table by then. Automounts, swap and leftovers of an earlier attempt
// are unmounted; md arrays that udev assembled and device-mapper devices (activated LVM, an
// open LUKS mapping) are stopped — deactivating them changes no data. Anything else mounted is
// left alone and the install stops before touching the disk.
func (in *Installer) releaseDisk(ctx context.Context, disk string) error {
	nodes, err := in.diskTree(ctx, disk)
	if err != nil {
		return err
	}
	mounts, holders := diskUse(nodes)
	for _, m := range mounts {
		if !in.releasable(m.mountpoint) {
			return fmt.Errorf("%s is in use (%s is mounted at %s)", disk, m.dev, m.mountpoint)
		}
	}
	if len(mounts) == 0 && len(holders) == 0 {
		return nil
	}
	in.R.Note("releasing %s: %d mounts, %d holders", disk, len(mounts), len(holders))
	for _, m := range mounts {
		c := Cmd{Name: "umount", Args: []string{m.mountpoint}, AllowFail: true}
		if m.mountpoint == "[SWAP]" {
			c = Cmd{Name: "swapoff", Args: []string{m.dev}, AllowFail: true}
		}
		if _, err := in.R.Run(ctx, c); err != nil {
			return err
		}
	}
	for _, h := range holders {
		c := Cmd{Name: "dmsetup", Args: []string{"remove", h.Path}, AllowFail: true}
		if strings.HasPrefix(h.Type, "raid") || h.Type == "md" {
			c = Cmd{Name: "mdadm", Args: []string{"--stop", h.Path}, AllowFail: true}
		}
		if _, err := in.R.Run(ctx, c); err != nil {
			return err
		}
	}
	in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=15"}, AllowFail: true})
	if nodes, err = in.diskTree(ctx, disk); err != nil {
		return err
	}
	mounts, holders = diskUse(nodes)
	if len(mounts) > 0 {
		return fmt.Errorf("%s is still in use (%s is mounted at %s)", disk, mounts[0].dev, mounts[0].mountpoint)
	}
	if len(holders) > 0 {
		return fmt.Errorf("%s is still in use by %s (%s)", disk, holders[0].Path, holders[0].Type)
	}
	return nil
}

var subvolumes = []struct{ name, mount string }{
	{"@", "/"}, {"@home", "/home"}, {"@var_log", "/var/log"}, {"@nix", "/nix"},
}

func (in *Installer) uuid(ctx context.Context, dev string) (string, error) {
	u, err := in.output(ctx, "blkid", "--match-tag", "UUID", "--output", "value", dev)
	if err != nil {
		return "", err
	}
	if u == "" {
		return "", fmt.Errorf("no UUID on %s", dev)
	}
	return u, nil
}

// partitionErase lays out the whole disk: BIOS boot, ESP, /boot, root (PLAN §6.2).
func (in *Installer) partitionErase(ctx context.Context) error {
	d := in.Job.Disk.Path
	rootType := hw.TypeLinux
	if in.lay.luks {
		rootType = hw.TypeLUKS
	}
	script := strings.Join([]string{
		"label: gpt",
		`size=1MiB, type=` + hw.TypeBIOSBoot + `, name="BIOS boot"`,
		`size=1GiB, type=` + hw.TypeESP + `, name="EFI System"`,
		`size=2GiB, type=` + hw.TypeLinux + `, name="Arctic boot"`,
		`type=` + rootType + `, name="Arctic root"`,
	}, "\n") + "\n"
	if err := in.run(ctx, "wipefs", "--all", "--force", d); err != nil {
		return err
	}
	if _, err := in.R.Run(ctx, Cmd{Name: "sfdisk", Args: []string{"--wipe", "always", "--wipe-partitions", "always", d}, Stdin: []byte(script)}); err != nil {
		return err
	}
	in.lay.biosBoot = hw.PartitionPath(d, 1)
	in.lay.esp, in.lay.espNum, in.lay.espNew = hw.PartitionPath(d, 2), 2, true
	in.lay.boot = hw.PartitionPath(d, 3)
	in.lay.root = hw.PartitionPath(d, 4)
	return nil
}

// partitionAlongside adds /boot and root (and a BIOS boot partition on GPT/BIOS when there
// is none) in the largest free region and reuses the existing ESP.
func (in *Installer) partitionAlongside(ctx context.Context) error {
	disk := in.Job.Disk
	free := disk.LargestFree()
	if free.SizeBytes < hw.MinInstallBytes {
		return fmt.Errorf("only %s free on %s", hw.SizeLabel(free.SizeBytes), disk.Path)
	}
	sector := disk.SectorSize
	if sector == 0 {
		sector = 512
	}
	// Align the start to 1 MiB.
	start := (free.StartByte + hw.MiB - 1) / hw.MiB * hw.MiB
	gpt := disk.PTType == "gpt"
	next := disk.NextPartitionNumber()
	var lines []string
	var nums []int
	add := func(size int64, gptType, mbrType, name string) string {
		// The device name pins the partition number: sfdisk refuses the line if that slot is
		// taken, so the paths used below are exactly the partitions this run creates.
		p := hw.PartitionPath(disk.Path, next)
		l := fmt.Sprintf("%s : start=%d", p, start/sector)
		if size > 0 {
			l += fmt.Sprintf(", size=%d", size/sector)
			start += size
		}
		if gpt {
			l += ", type=" + gptType + `, name="` + name + `"`
		} else {
			l += ", type=" + mbrType
		}
		lines = append(lines, l)
		nums = append(nums, next)
		next++
		return p
	}
	if in.Job.Firmware == "bios" && gpt {
		if bb, ok := disk.BIOSBoot(); ok {
			in.lay.biosBoot = bb.Path
		} else {
			in.lay.biosBoot = add(hw.MiB, hw.TypeBIOSBoot, "", "BIOS boot")
		}
	}
	rootType := hw.TypeLinux
	if in.lay.luks {
		rootType = hw.TypeLUKS
	}
	in.lay.boot = add(2*hw.GiB, hw.TypeLinux, "83", "Arctic boot")
	in.lay.root = add(0, rootType, "83", "Arctic root")
	if !gpt && len(disk.Partitions)+len(lines) > 4 {
		return fmt.Errorf("%s has an MBR partition table with no room for two more primary partitions", disk.Path)
	}
	// UEFI shares the existing ESP; BIOS leaves the other system's ESP alone.
	if in.Job.Firmware == "uefi" {
		esp, ok := disk.ESP()
		if !ok {
			return fmt.Errorf("%s has no EFI system partition to share", disk.Path)
		}
		in.lay.esp, in.lay.espNum = esp.Path, esp.Number
	}
	if _, err := in.R.Run(ctx, Cmd{Name: "sfdisk", Args: []string{"--append", disk.Path}, Stdin: []byte(strings.Join(lines, "\n") + "\n")}); err != nil {
		return err
	}
	in.lay.created = nums
	return nil
}

// ---- copy ----

func (in *Installer) liveSource(ctx context.Context) (string, error) {
	if in.Opt.Source != "" {
		return in.Opt.Source, nil
	}
	if in.R.Exists("/run/rootfsbase") {
		return "/run/rootfsbase", nil
	}
	out, err := in.output(ctx, "findmnt", "--raw", "--noheadings", "--output", "TARGET", "--types", "squashfs")
	if err == nil {
		for _, t := range strings.Fields(out) {
			if in.R.Exists(path.Join(t, "usr/bin")) {
				return t, nil
			}
		}
	}
	return "", errors.New("couldn’t find the live system image to copy (no /run/rootfsbase or squashfs root)")
}

var percentRe = regexp.MustCompile(`(\d{1,3})%`)

// ParsePercent finds "NN%" in a progress line (rsync --info=progress2, flatpak).
func ParsePercent(line string) (int, bool) {
	m := percentRe.FindAllStringSubmatch(line, -1)
	if len(m) == 0 {
		return 0, false
	}
	n, err := strconv.Atoi(m[len(m)-1][1])
	if err != nil || n > 100 {
		return 0, false
	}
	return n, true
}

var dnfRe = regexp.MustCompile(`^\[\s*(\d+)/(\d+)\]`)

// ParseDNF reads dnf5's "[ 3/45] Installing foo" counters.
func ParseDNF(line string) (done, total int, ok bool) {
	m := dnfRe.FindStringSubmatch(strings.TrimSpace(line))
	if m == nil {
		return 0, 0, false
	}
	done, _ = strconv.Atoi(m[1])
	total, _ = strconv.Atoi(m[2])
	return done, total, total > 0
}

func (in *Installer) copyPhase(ctx context.Context) error {
	src, err := in.liveSource(ctx)
	if err != nil {
		return err
	}
	in.source = src
	if err := in.copyRoot(ctx, src); err != nil {
		return err
	}
	in.t.Update(0.9, "")
	// API file systems for the chroot steps; /run carries the resolver stub for dnf.
	for _, s := range [][]string{
		{"mount", "--rbind", "/dev", in.tgt("/dev")},
		{"mount", "--make-rslave", in.tgt("/dev")},
		{"mount", "-t", "proc", "proc", in.tgt("/proc")},
		{"mount", "--rbind", "/sys", in.tgt("/sys")},
		{"mount", "--make-rslave", in.tgt("/sys")},
		{"mount", "--bind", "/run", in.tgt("/run")},
	} {
		if err := in.run(ctx, s[0], s[1:]...); err != nil {
			return err
		}
	}
	// Live-only packages and files (livesys creates liveuser at boot, so the image has none).
	if err := in.chroot(ctx, Cmd{Name: "dnf", Args: append([]string{"remove", "-y", "--no-autoremove"}, LiveOnlyPackages...)}); err != nil {
		return err
	}
	for _, f := range []string{"/etc/sddm.conf.d/90-arctic-live.conf", "/etc/sysconfig/livesys"} {
		if err := in.R.Remove(in.tgt(f)); err != nil {
			return err
		}
	}
	in.t.Update(1, "")
	return nil
}

// copyRoot copies the live root to the target, then the ESP's files.
//
// The ESP is vfat, mounted at /boot/efi before the copy. The main rsync must not touch that
// mount point at all: -X would try to set the image's SELinux label on the vfat root, which
// fails (EOPNOTSUPP) and makes rsync exit 23. So /boot/efi/ itself is excluded when an ESP is
// mounted there, and its files are copied separately without owners, permissions or xattrs,
// as Anaconda does for live images. The security.selinux xattr is not copied at all (the
// kiwi-built image has files whose label the running policy can't set or remove, another
// exit-23 failure); setfiles relabels the whole target in the finalize phase.
func (in *Installer) copyRoot(ctx context.Context, src string) error {
	esp := "/boot/efi/*" // no ESP mounted: keep the (empty) directory from the image
	if in.lay.esp != "" {
		esp = "/boot/efi/"
	}
	excludes := []string{"/dev/*", "/proc/*", "/sys/*", "/run/*", "/tmp/*", "/mnt/*", "/media/*", "/var/tmp/*",
		esp, "/boot/loader/entries/*", "/boot/initramfs-*", "/boot/vmlinuz-0-rescue-*",
		// The live image's rescue kernel belongs to its machine id; kernel-install makes one.
		"/var/cache/dnf/*", "/var/cache/libdnf5/*",
		"/etc/machine-id", "/lost+found"}
	args := []string{"-aAXH", "--numeric-ids", "--info=progress2", "--no-inc-recursive", "--filter=-x security.selinux"}
	for _, e := range excludes {
		args = append(args, "--exclude="+e)
	}
	args = append(args, strings.TrimSuffix(src, "/")+"/", strings.TrimSuffix(in.Opt.Target, "/")+"/")
	if _, err := in.R.Run(ctx, Cmd{Name: "rsync", Args: args, OnLine: func(l string) {
		if p, ok := ParsePercent(l); ok {
			in.t.Update(float64(p)/100*0.85, "")
		}
	}}); err != nil {
		return err
	}
	// The ESP's files without owners/permissions/xattrs (and without touching the vfat root's
	// times), then the signed shim and GRUB (F44 also keeps them under /usr/lib/efi).
	if in.lay.esp != "" {
		if in.R.Exists(path.Join(src, "boot/efi")) {
			if err := in.run(ctx, "rsync", "-rt", "--omit-dir-times", path.Join(src, "boot/efi")+"/", in.tgt("/boot/efi")+"/"); err != nil {
				return err
			}
		}
		dirs, _ := in.R.Glob(in.tgt("/usr/lib/efi/*/*/EFI"))
		sort.Strings(dirs)
		for _, dir := range dirs {
			if err := in.run(ctx, "cp", "-rn", dir, in.tgt("/boot/efi")+"/"); err != nil {
				return err
			}
		}
	}
	return nil
}

// ---- configure ----

func (in *Installer) configurePhase(ctx context.Context) error {
	d := in.Job.Data
	if err := in.R.Remove(in.tgt("/etc/machine-id")); err != nil {
		return err
	}
	if err := in.run(ctx, "systemd-machine-id-setup", "--root="+in.Opt.Target); err != nil {
		return err
	}
	if err := in.run(ctx, "systemd-firstboot", "--root="+in.Opt.Target, "--force",
		"--locale="+d.Welcome.Language, "--timezone="+d.Timezone.Timezone, "--hostname="+d.Account.Hostname); err != nil {
		return err
	}
	in.t.Update(0.3, "")
	kb := wizard.KeyboardConfig(d.Keyboard)
	first, _, _ := strings.Cut(kb.Layout, ",")
	files := []struct {
		path, content string
		perm          uint32
	}{
		{"/etc/vconsole.conf", vconsoleConf(kb), 0o644},
		{"/etc/arctic/mango/keyboard.conf", KeyboardConf(kb), 0o644},
		{"/etc/arctic/sddm-keyboard.conf", KeyboardConf(kb), 0o644},
		// The login screen's Wayland greeter can't report the layout, so the theme reads the
		// one it starts with here.
		{"/usr/share/sddm/themes/arctic/theme.conf.user", fmt.Sprintf("# Written by the Arctic Linux installer: the keyboard layout you picked.\n[General]\nkeyboardLayout=%s\n", first), 0o644},
		{"/etc/fstab", in.fstab(), 0o644},
	}
	if in.lay.luks {
		files = append(files, struct {
			path, content string
			perm          uint32
		}{"/etc/crypttab", fmt.Sprintf("%s UUID=%s none discard\n", in.lay.luksName, in.lay.luksUUID), 0o600})
	}
	if d.Account.Autologin {
		files = append(files, struct {
			path, content string
			perm          uint32
		}{"/etc/sddm.conf.d/50-arctic-autologin.conf", fmt.Sprintf("# Written by the Arctic Linux installer (\"Log in automatically\").\n[Autologin]\nUser=%s\nSession=mango.desktop\n", d.Account.Username), 0o644})
	}
	for _, f := range files {
		if err := in.write(in.tgt(f.path), f.content, f.perm); err != nil {
			return err
		}
	}
	in.t.Update(0.6, "")
	var units []string
	for _, m := range in.cat.Resolve(d.Apps.Selection) {
		units = append(units, m.Session.Services...)
	}
	timeAction := "enable"
	if !d.Timezone.AutoTime {
		timeAction = "disable"
	}
	// One unit per call: a unit missing from the image is logged, not fatal.
	type unitAction struct{ action, unit string }
	var actions []unitAction
	for _, u := range units {
		actions = append(actions, unitAction{"enable", u})
	}
	actions = append(actions, unitAction{timeAction, "chronyd.service"})
	for _, a := range actions {
		res, err := in.R.Run(ctx, Cmd{Name: "systemctl", Args: []string{"--root=" + in.Opt.Target, a.action, a.unit}, AllowFail: true})
		if err != nil {
			return err
		}
		if res.ExitCode != 0 {
			in.Rep.Logf("warning: systemctl %s %s failed (exit %d)", a.action, a.unit, res.ExitCode)
		}
	}
	if err := in.run(ctx, "systemctl", "--root="+in.Opt.Target, "set-default", "graphical.target"); err != nil {
		return err
	}
	// Wi-Fi profiles from the live session, so the new system is online at first login.
	if in.R.Exists("/etc/NetworkManager/system-connections") {
		if err := in.run(ctx, "rsync", "-a", "/etc/NetworkManager/system-connections/", in.tgt("/etc/NetworkManager/system-connections")+"/"); err != nil {
			return err
		}
	}
	in.t.Update(1, "")
	return nil
}

// KeyboardConf is the mango (session and login screen) keyboard file. Empty values are left
// out: mango rejects a "key=" line with no value.
func KeyboardConf(kb wizard.XKB) string {
	var b strings.Builder
	b.WriteString("# Written by the Arctic Linux installer: the keyboard layout you picked.\n")
	if !kb.Latin {
		b.WriteString("# English (US) comes first so passwords are typed the same everywhere; Alt+Shift switches.\n")
	}
	b.WriteString("xkb_rules_layout=" + kb.Layout + "\n")
	if kb.Variant != "" {
		b.WriteString("xkb_rules_variant=" + kb.Variant + "\n")
	}
	if kb.Options != "" {
		b.WriteString("xkb_rules_options=" + kb.Options + "\n")
	}
	return b.String()
}

// vconsoleConf is /etc/vconsole.conf: the console keymap (in the initramfs, where the disk
// passphrase is typed) and the X11 layouts for tools that read them.
func vconsoleConf(kb wizard.XKB) string {
	s := "KEYMAP=" + kb.Keymap + "\nXKBLAYOUT=" + kb.Layout + "\n"
	if kb.Variant != "" {
		s += "XKBVARIANT=" + kb.Variant + "\n"
	}
	if kb.Options != "" {
		s += "XKBOPTIONS=" + kb.Options + "\n"
	}
	return s
}

func (in *Installer) fstab() string {
	var b strings.Builder
	b.WriteString("# /etc/fstab — written by the Arctic Linux installer.\n")
	for i, sv := range subvolumes {
		opts := "subvol=" + sv.name + ",compress=zstd:1"
		if i == 0 {
			opts += ",x-systemd.device-timeout=0"
		}
		fmt.Fprintf(&b, "UUID=%s %-10s btrfs %s 0 0\n", in.lay.btrfsUUID, sv.mount, opts)
	}
	fmt.Fprintf(&b, "UUID=%s %-10s ext4 defaults 1 2\n", in.lay.bootUUID, "/boot")
	if in.lay.esp != "" {
		fmt.Fprintf(&b, "UUID=%s %-10s vfat umask=0077,shortname=winnt 0 2\n", in.lay.espID, "/boot/efi")
	}
	return b.String()
}

// ---- bootloader ----

// kernelArgs are the arguments after "root=UUID=… ro" in /etc/kernel/cmdline (kernel-install
// writes them into each BLS entry).
func (in *Installer) kernelArgs() string {
	return "rootflags=subvol=@ " + in.grubArgs()
}

// grubArgs is GRUB_CMDLINE_LINUX. grub2-mkconfig rewrites the BLS entries' options from it,
// and its 10_linux adds "rootflags=subvol=@" itself for a btrfs subvolume root, so it is not
// repeated here (as Anaconda does; it would otherwise appear twice on the command line).
func (in *Installer) grubArgs() string {
	args := ""
	if in.lay.luks {
		args = "rd.luks.uuid=" + in.lay.luksName + " "
	}
	return args + "rhgb quiet"
}

func (in *Installer) bootloaderPhase(ctx context.Context) error {
	job := in.Job
	grub := strings.Join([]string{
		"# Written by the Arctic Linux installer.",
		"GRUB_TIMEOUT=5",
		`GRUB_DISTRIBUTOR="Arctic Linux"`,
		"GRUB_DEFAULT=saved",
		"GRUB_DISABLE_SUBMENU=true",
		`GRUB_TERMINAL_OUTPUT="gfxterm"`,
		`GRUB_CMDLINE_LINUX="` + in.grubArgs() + `"`,
		`GRUB_DISABLE_RECOVERY="true"`,
		"GRUB_ENABLE_BLSCFG=true",
	}, "\n") + "\n"
	if in.R.Exists(in.tgt("/boot/grub2/themes/arctic/theme.txt")) {
		grub += `GRUB_THEME="/boot/grub2/themes/arctic/theme.txt"` + "\n"
	}
	// os-prober lists the other systems for "alongside"; on an erased disk there are none, and
	// running it from the chroot only mounts and probes the new system itself.
	if job.Data.Disk.Mode == wizard.ModeAlongside {
		grub += "GRUB_DISABLE_OS_PROBER=false\n"
	} else {
		grub += "GRUB_DISABLE_OS_PROBER=true\n"
	}
	cmdline := fmt.Sprintf("root=UUID=%s ro %s\n", in.lay.btrfsUUID, in.kernelArgs())
	if err := in.write(in.tgt("/etc/default/grub"), grub, 0o644); err != nil {
		return err
	}
	if err := in.write(in.tgt("/etc/kernel/cmdline"), cmdline, 0o644); err != nil {
		return err
	}
	kdirs, err := in.R.Glob(in.tgt("/lib/modules/*"))
	if err != nil {
		return err
	}
	sort.Strings(kdirs)
	if len(kdirs) == 0 {
		return errors.New("no kernel in the copied system")
	}
	for i, kd := range kdirs {
		kver := path.Base(kd)
		if err := in.chroot(ctx, Cmd{Name: "kernel-install", Args: []string{"add", kver, "/lib/modules/" + kver + "/vmlinuz"}}); err != nil {
			return err
		}
		in.t.Update(0.6*float64(i+1)/float64(len(kdirs)), "")
	}
	if err := in.R.MkdirAll(in.tgt("/boot/grub2"), 0o755); err != nil {
		return err
	}
	if err := in.chroot(ctx, Cmd{Name: "grub2-mkconfig", Args: []string{"-o", "/boot/grub2/grub.cfg"}}); err != nil {
		return err
	}
	in.t.Update(0.8, "")
	if job.Firmware == "uefi" {
		stub := fmt.Sprintf("search --no-floppy --fs-uuid --set=dev %s\nset prefix=($dev)/grub2\nexport $prefix\nconfigfile $prefix/grub.cfg\n", in.lay.bootUUID)
		if err := in.write(in.tgt("/boot/efi/EFI/fedora/grub.cfg"), stub, 0o600); err != nil {
			return err
		}
		out, err := in.output(ctx, "efibootmgr", "--create", "--disk", in.lay.disk, "--part", strconv.Itoa(in.lay.espNum),
			"--label", bootLabel, "--loader", `\EFI\fedora\shimx64.efi`)
		if err != nil {
			return err
		}
		in.bootNum = newBootEntry(out, bootLabel)
	} else {
		if err := in.chroot(ctx, Cmd{Name: "grub2-install", Args: []string{"--target=i386-pc", in.lay.disk}}); err != nil {
			return err
		}
	}
	in.t.Update(1, "")
	return nil
}

// bootLabel names the firmware boot entry.
const bootLabel = "Arctic Linux"

// newBootEntry finds the entry `efibootmgr --create` just added in its output: the first one
// in BootOrder (new entries go first), if it carries our label. "" when unsure.
func newBootEntry(out, label string) string {
	var first string
	for _, l := range strings.Split(out, "\n") {
		if v, ok := strings.CutPrefix(strings.TrimSpace(l), "BootOrder:"); ok {
			first, _, _ = strings.Cut(strings.TrimSpace(v), ",")
			break
		}
	}
	if first == "" {
		return ""
	}
	for _, l := range strings.Split(out, "\n") {
		l = strings.TrimSpace(l)
		if rest, ok := strings.CutPrefix(l, "Boot"+first); ok && strings.HasPrefix(strings.TrimLeft(strings.TrimPrefix(rest, "*"), " "), label) {
			return first
		}
	}
	return ""
}

// ---- apps ----

func (in *Installer) flatpakEnv() []string {
	return []string{
		"FLATPAK_SYSTEM_DIR=" + in.tgt("/var/lib/flatpak"),
		"FLATPAK_CONFIG_DIR=" + in.tgt("/etc/flatpak"),
		"FLATPAK_OS_CONFIG_DIR=" + in.tgt("/usr/share/flatpak"),
		"FLATPAK_DOWNLOAD_TMPDIR=" + in.tgt("/var/tmp"),
		"LC_ALL=C.UTF-8",
	}
}

func isDNF(in catalog.Install) bool {
	return in.Method == catalog.MethodDNF || in.Method == catalog.MethodCopr
}

func (in *Installer) langpack() string {
	code, _, _ := strings.Cut(in.Job.Data.Welcome.Language, "_")
	return "glibc-langpack-" + code
}

func (in *Installer) appsPhase(ctx context.Context) error {
	sel := in.Job.Data.Apps.Selection
	resolved := in.cat.Resolve(sel)
	visible := in.isApp

	// 1. Apps already in the live image are installed by the copy.
	for _, m := range resolved {
		if m.InLiveImage {
			in.usedMethod[m.ID] = m.Primary()
			if visible(m) {
				in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModInstalled, Percent: 100})
				in.t.AppDone()
			}
		}
	}
	// 2. Remove default apps the person unticked.
	var rmPkgs, rmRefs []string
	for _, id := range in.cat.Order {
		m := in.cat.Modules[id]
		if !m.InLiveImage || m.Always || sel.Contains(id) {
			continue
		}
		p := m.Primary()
		switch {
		case isDNF(p):
			rmPkgs = append(rmPkgs, p.RemovePackages()...)
		case p.Method == catalog.MethodFlatpak && p.Ref != "":
			rmRefs = append(rmRefs, p.Ref)
		}
	}
	if len(rmPkgs) > 0 || len(rmRefs) > 0 {
		in.t.Update(0, wizard.StatusRemove)
	}
	if len(rmPkgs) > 0 {
		if err := in.chroot(ctx, Cmd{Name: "dnf", Args: append([]string{"remove", "-y", "--no-autoremove"}, rmPkgs...)}); err != nil {
			in.Rep.Logf("removing unticked apps failed (continuing): %v", err)
		}
	}
	for _, ref := range rmRefs {
		if _, err := in.R.Run(ctx, Cmd{Name: "flatpak", Args: []string{"uninstall", "--system", "-y", "--noninteractive", ref}, Env: in.flatpakEnv()}); err != nil {
			in.Rep.Logf("removing %s failed (continuing): %v", ref, err)
		}
	}

	// 3. Download what the live image doesn't have. dnf/COPR modules go in one transaction.
	var todo []*catalog.Module
	for _, m := range resolved {
		if !m.InLiveImage {
			todo = append(todo, m)
		}
	}
	extra := []string{in.langpack()}
	if in.Job.Data.Disk.Mode == wizard.ModeAlongside {
		extra = append(extra, "os-prober")
	}
	var batch []*catalog.Module
	for _, m := range todo {
		if isDNF(m.Primary()) {
			batch = append(batch, m)
		}
	}
	// Make sure the picked apps the live image ships are complete (e.g. vlc-plugins-freeworld
	// when the ISO was built without RPM Fusion): installed packages are a no-op for dnf.
	var ensure []*catalog.Module
	for _, m := range resolved {
		if m.InLiveImage && in.isApp(m) && m.Primary().Method == catalog.MethodDNF {
			ensure = append(ensure, m)
			extra = append(extra, m.Primary().Packages...)
		}
	}
	total := len(todo)
	done := 0
	step := func() {
		done++
		in.t.Update(float64(done)/float64(total+1), "")
	}
	batchOK := false
	if len(batch) > 0 {
		in.t.Update(0.02, in.batchStatus(batch))
		for _, m := range batch {
			if visible(m) {
				in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModDownloading})
			}
		}
		err := in.dnfInstall(ctx, batch, ensure, extra, func(frac float64) {
			in.t.Update(frac*float64(len(batch))/float64(total+1), "")
		})
		if err == nil {
			batchOK = true
			for _, m := range batch {
				in.usedMethod[m.ID] = m.Primary()
				if visible(m) {
					in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModInstalled, Percent: 100})
					in.t.AppDone()
				}
				step()
			}
		} else {
			in.Rep.Logf("batched dnf install failed, installing one by one: %v", err)
			if _, e := in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, extra...), AllowFail: true})); e != nil {
				return e
			}
		}
	} else if len(extra) > 0 {
		if _, err := in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, extra...), AllowFail: true})); err != nil {
			return err
		}
	}
	for _, m := range todo {
		if batchOK && isDNF(m.Primary()) {
			continue
		}
		if err := in.installWithAttention(ctx, m); err != nil {
			return err
		}
		step()
	}
	if in.flatpakRan {
		if err := in.write(in.tgt("/var/lib/flatpak/.fedora-initialized"), "", 0o644); err != nil {
			return err
		}
	}
	in.t.Update(1, "")
	return nil
}

func (in *Installer) batchStatus(batch []*catalog.Module) string {
	var vis []*catalog.Module
	for _, m := range batch {
		if in.isApp(m) {
			vis = append(vis, m)
		}
	}
	if len(vis) == 1 {
		return backend.InstallingStatus(in.cat, vis[0])
	}
	return "Installing your apps…"
}

// isApp reports whether a module is one of the apps the person ticked (progress, events).
func (in *Installer) isApp(m *catalog.Module) bool {
	return !m.Hidden && in.Job.Data.Apps.Selection.Contains(m.ID)
}

// installWithAttention tries every method of a module; when all fail it asks the person
// (Try again / Skip) or, unattended, retries once and then defers to first boot.
func (in *Installer) installWithAttention(ctx context.Context, m *catalog.Module) error {
	for {
		if in.isApp(m) {
			in.t.Update(0, backend.InstallingStatus(in.cat, m))
			in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModDownloading})
		}
		var lastErr error
		for _, meth := range m.Install {
			err := in.installMethod(ctx, m, meth)
			if err == nil {
				in.usedMethod[m.ID] = meth
				if in.isApp(m) {
					in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModInstalled, Percent: 100})
					in.t.AppDone()
				}
				return nil
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			lastErr = err
			in.Rep.Logf("%s: %s failed: %v", m.ID, meth.Method, err)
		}
		if in.isApp(m) {
			in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModFailed})
			in.t.Paused("Paused on " + m.Name)
		}
		dec := in.Rep.Attention(ctx, backend.AttentionFor(m, failureMessage(lastErr), errText(lastErr)))
		if ctx.Err() != nil {
			return ctx.Err()
		}
		switch dec {
		case backend.Retry:
			continue
		case backend.Defer:
			in.deferred = append(in.deferred, m.ID)
			if in.isApp(m) {
				in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModDeferred})
				in.t.AppDone()
			}
			return nil
		default:
			in.skipped[m.ID] = true
			if in.isApp(m) {
				in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModSkipped})
				in.t.AppDone()
			}
			return nil
		}
	}
}

func errText(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func failureMessage(err error) string {
	s := strings.ToLower(errText(err))
	switch {
	case strings.Contains(s, "could not resolve") || strings.Contains(s, "timed out") || strings.Contains(s, "couldn't connect") ||
		strings.Contains(s, "could not connect") || strings.Contains(s, "curl error") || strings.Contains(s, "network"):
		return "The download server didn’t answer."
	case strings.Contains(s, "no space left"):
		return "The disk is full."
	case strings.Contains(s, "no match for argument") || strings.Contains(s, "not found"):
		return "The app isn’t available from its source right now."
	}
	return "The download didn’t finish."
}

// setupRepos enables the repositories a dnf method needs (keys from distribution-gpg-keys).
func (in *Installer) setupRepos(ctx context.Context, meth catalog.Install) error {
	for _, repo := range meth.Repos {
		if in.reposDone[repo] {
			continue
		}
		kind := strings.TrimPrefix(repo, "rpmfusion-") // free | nonfree
		rel := in.Opt.FedoraRelease
		key := fmt.Sprintf("/usr/share/distribution-gpg-keys/rpmfusion/RPM-GPG-KEY-rpmfusion-%s-fedora-%s", kind, rel)
		url := fmt.Sprintf("https://mirrors.rpmfusion.org/%s/fedora/rpmfusion-%s-release-%s.noarch.rpm", kind, kind, rel)
		if err := in.chroot(ctx, Cmd{Name: "rpm", Args: []string{"--import", key}}); err != nil {
			return err
		}
		if err := in.chroot(ctx, Cmd{Name: "dnf", Args: []string{"install", "-y", url}}); err != nil {
			return err
		}
		in.reposDone[repo] = true
	}
	if meth.Method == catalog.MethodCopr && !in.coprDone[meth.Copr] {
		if err := in.chroot(ctx, Cmd{Name: "dnf", Args: []string{"copr", "enable", "-y", meth.Copr}}); err != nil {
			return err
		}
		in.coprDone[meth.Copr] = true
	}
	for _, s := range meth.Swap {
		from, to, _ := strings.Cut(s, "=")
		if err := in.chroot(ctx, Cmd{Name: "dnf", Args: []string{"swap", "-y", "--allowerasing", from, to}}); err != nil {
			return err
		}
	}
	return nil
}

func (in *Installer) dnfInstall(ctx context.Context, mods, ensure []*catalog.Module, extra []string, progress func(float64)) error {
	var pkgs []string
	for _, m := range mods {
		p := m.Primary()
		if err := in.setupRepos(ctx, p); err != nil {
			return err
		}
		pkgs = append(pkgs, p.Packages...)
	}
	for _, m := range ensure {
		if err := in.setupRepos(ctx, m.Primary()); err != nil {
			return err
		}
	}
	pkgs = append(pkgs, extra...)
	return in.chroot(ctx, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, pkgs...), OnLine: func(l string) {
		if d, t, ok := ParseDNF(l); ok && progress != nil {
			progress(float64(d) / float64(t))
		}
	}})
}

func (in *Installer) installMethod(ctx context.Context, m *catalog.Module, meth catalog.Install) error {
	report := func(p int) {
		if in.isApp(m) {
			in.Rep.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModDownloading, Percent: p})
		}
	}
	switch meth.Method {
	case catalog.MethodDNF, catalog.MethodCopr:
		if err := in.setupRepos(ctx, meth); err != nil {
			return err
		}
		return in.chroot(ctx, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, meth.Packages...), OnLine: func(l string) {
			if d, t, ok := ParseDNF(l); ok {
				report(100 * d / t)
			}
		}})
	case catalog.MethodFlatpak:
		in.flatpakRan = true
		if !in.remoteDone[meth.Remote] {
			url, ok := FlatpakRemotes[meth.Remote]
			if !ok {
				return fmt.Errorf("unknown flatpak remote %q", meth.Remote)
			}
			if _, err := in.R.Run(ctx, Cmd{Name: "flatpak", Args: []string{"remote-add", "--system", "--if-not-exists", meth.Remote, url}, Env: in.flatpakEnv()}); err != nil {
				return err
			}
			in.remoteDone[meth.Remote] = true
		}
		if meth.Ref == "" {
			return nil
		}
		_, err := in.R.Run(ctx, Cmd{Name: "flatpak", Args: []string{"install", "--system", "-y", "--noninteractive", meth.Remote, meth.Ref}, Env: in.flatpakEnv(),
			OnLine: func(l string) {
				if p, ok := ParsePercent(l); ok {
					report(p)
				}
			}})
		return err
	case catalog.MethodNix:
		pin := in.cat.Nixpkgs
		if pin == "" {
			pin = "nixpkgs"
		}
		_, err := in.R.Run(ctx, Cmd{Name: "nix", Args: []string{
			"--extra-experimental-features", "nix-command flakes", "--store", in.Opt.Target,
			"profile", "add", "--profile", in.tgt("/nix/var/nix/profiles/default"), pin + "#" + meth.Attr, "--log-format", "internal-json",
		}})
		return err
	}
	return fmt.Errorf("unknown install method %q", meth.Method)
}

// ---- finalize ----

func (in *Installer) finalizePhase(ctx context.Context) error {
	d := in.Job.Data
	shell := "/bin/bash"
	for _, id := range d.Apps.Selection["shell"] {
		if m, ok := in.cat.Modules[id]; ok && m.Defaults.Shell != "" && !in.skipped[id] {
			shell = m.Defaults.Shell
			break
		}
	}
	// The password is hashed here (SHA-512 crypt) and handed to useradd pre-hashed, so no PAM
	// stack (F45 moves chpasswd to PAM) and no plaintext is involved. Plans and logs redact it.
	var hash string
	var err error
	if in.Opt.Salt != "" {
		hash, err = SHA512Crypt(in.Job.Secrets.Password, "$6$"+in.Opt.Salt)
	} else {
		hash, err = HashPassword(in.Job.Secrets.Password)
	}
	if err != nil {
		return err
	}
	args := []string{"--root", in.Opt.Target, "--create-home", "--user-group", "--groups", "wheel",
		"--shell", shell, "--comment", d.Account.FullName, "--password", hash, d.Account.Username}
	if _, err := in.R.Run(ctx, Cmd{Name: "useradd", Args: args, Redact: []int{len(args) - 2}, SecretLabel: "password hash"}); err != nil {
		return err
	}
	if err := in.run(ctx, "usermod", "--root", in.Opt.Target, "--lock", "root"); err != nil {
		return err
	}
	in.t.Update(0.3, "")
	if err := in.write(in.tgt("/etc/arctic/default-apps"), in.defaultApps(), 0o644); err != nil {
		return err
	}
	if mime := in.mimeApps(); mime != "" {
		if err := in.write(in.tgt("/etc/xdg/mimeapps.list"), mime, 0o644); err != nil {
			return err
		}
	}
	if len(in.deferred) > 0 {
		// Version 2 carries each module's install methods, because the catalog leaves the
		// installed system together with arctic-installer (arctic-firstboot reads this).
		type pendingModule struct {
			ID      string            `json:"id"`
			Name    string            `json:"name"`
			Install []catalog.Install `json:"install"`
		}
		var mods []pendingModule
		for _, id := range in.deferred {
			if m := in.cat.Modules[id]; m != nil {
				mods = append(mods, pendingModule{ID: m.ID, Name: m.Name, Install: m.Install})
			}
		}
		b, _ := json.MarshalIndent(map[string]any{"version": 2, "nixpkgs": in.cat.Nixpkgs, "modules": mods}, "", "  ")
		if err := in.write(in.tgt("/var/lib/arctic/pending.json"), string(b)+"\n", 0o644); err != nil {
			return err
		}
	}
	in.t.Update(0.5, wizard.StatusTidy)
	if in.Opt.LogPath != "" {
		if err := in.R.MkdirAll(in.tgt("/var/log/arctic-install"), 0o755); err != nil {
			return err
		}
		if _, err := in.R.Run(ctx, Cmd{Name: "cp", Args: []string{in.Opt.LogPath, in.tgt("/var/log/arctic-install/")}, AllowFail: true}); err != nil {
			return err
		}
	}
	// SELinux labels before unmounting; fall back to a relabel at first boot.
	t := in.Opt.Target
	res, err := in.R.Run(ctx, Cmd{Name: "setfiles", Args: []string{"-F", "-r", t,
		"-e", in.tgt("/proc"), "-e", in.tgt("/sys"), "-e", in.tgt("/dev"), "-e", in.tgt("/run"), "-e", in.tgt("/boot/efi"),
		in.tgt("/etc/selinux/targeted/contexts/files/file_contexts"), t}, AllowFail: true})
	if err != nil {
		return err
	}
	if res.ExitCode != 0 {
		in.Rep.Logf("setfiles failed (exit %d); relabelling at first boot instead", res.ExitCode)
		if err := in.write(in.tgt("/.autorelabel"), "-F\n", 0o644); err != nil {
			return err
		}
	}
	in.t.Update(0.8, "")
	if err := in.run(ctx, "umount", "--recursive", t); err != nil {
		return err
	}
	if in.lay.luks {
		// udev may still be probing the mapper after the unmount.
		if _, err := in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=30"}, AllowFail: true}); err != nil {
			return err
		}
		if err := in.run(ctx, "cryptsetup", "close", in.lay.luksName); err != nil {
			return err
		}
	}
	// The private bind of the target directory (privateTarget).
	_, err = in.R.Run(ctx, Cmd{Name: "umount", Args: []string{t}, AllowFail: true})
	return err
}

// roleOrder is the order of /etc/arctic/default-apps (arctic-open roles).
var roleOrder = []string{"terminal", "browser", "editor", "files", "files-tui"}

func (in *Installer) command(m *catalog.Module) string {
	cmd := m.Defaults.Command
	if u, ok := in.usedMethod[m.ID]; ok && u.Command != "" {
		cmd = u.Command
	}
	return cmd
}

func (in *Installer) desktopID(m *catalog.Module) string {
	id := m.Defaults.DesktopID
	if u, ok := in.usedMethod[m.ID]; ok && u.DesktopID != "" {
		id = u.DesktopID
	}
	return id
}

func (in *Installer) installedApps() []*catalog.Module {
	var out []*catalog.Module
	for _, m := range in.cat.Resolve(in.Job.Data.Apps.Selection) {
		if !m.Hidden && !in.skipped[m.ID] {
			out = append(out, m)
		}
	}
	return out
}

func (in *Installer) defaultApps() string {
	apps := in.installedApps()
	terminal := "kitty"
	for _, m := range apps {
		if m.Defaults.Role == "terminal" && in.Job.Data.Apps.Selection.Contains(m.ID) {
			terminal = in.command(m)
			break
		}
	}
	chosen := map[string]string{}
	for _, m := range apps {
		r := m.Defaults.Role
		if r == "" || chosen[r] != "" || !in.Job.Data.Apps.Selection.Contains(m.ID) {
			continue
		}
		chosen[r] = strings.ReplaceAll(in.command(m), "{terminal}", terminal)
	}
	var b strings.Builder
	b.WriteString("# Written by the Arctic Linux installer: the apps you picked, as role=command.\n")
	b.WriteString("# arctic-open reads this; override any line in ~/.config/arctic/default-apps.\n")
	for _, r := range roleOrder {
		if c := chosen[r]; c != "" {
			fmt.Fprintf(&b, "%s=%s\n", r, c)
		}
	}
	return b.String()
}

func (in *Installer) mimeApps() string {
	seen := map[string]bool{}
	var lines []string
	for _, m := range in.installedApps() {
		if !in.Job.Data.Apps.Selection.Contains(m.ID) {
			continue
		}
		id := in.desktopID(m)
		if id == "" {
			continue
		}
		for _, mt := range m.Defaults.Mime {
			if !seen[mt] {
				seen[mt] = true
				lines = append(lines, mt+"="+id)
			}
		}
	}
	if len(lines) == 0 {
		return ""
	}
	return "# Written by the Arctic Linux installer from the apps you picked.\n[Default Applications]\n" + strings.Join(lines, "\n") + "\n"
}
