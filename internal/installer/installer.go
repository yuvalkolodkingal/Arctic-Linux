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
}

type layout struct {
	disk                       string
	biosBoot, esp, boot, root  string
	espNum                     int
	espNew                     bool
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

// cleanup unmounts and closes after a failure so "Try again" starts clean.
func (in *Installer) cleanup(ctx context.Context) {
	in.R.Note("cleanup after failure")
	in.R.Run(ctx, Cmd{Name: "umount", Args: []string{"-R", in.Opt.Target}, AllowFail: true})
	if in.lay.luksName != "" {
		in.R.Run(ctx, Cmd{Name: "cryptsetup", Args: []string{"close", in.lay.luksName}, AllowFail: true})
	}
}

// ---- disk ----

func (in *Installer) diskPhase(ctx context.Context) error {
	job := in.Job
	disk := job.Disk
	if !in.R.Exists(disk.Path) {
		return fmt.Errorf("%s is gone", disk.Path)
	}
	mounts, err := in.output(ctx, "lsblk", "--noheadings", "--raw", "--output", "MOUNTPOINTS", disk.Path)
	if err != nil {
		return err
	}
	if m := strings.TrimSpace(mounts); m != "" {
		return fmt.Errorf("%s is in use (mounted at %s)", disk.Path, strings.Join(strings.Fields(m), ", "))
	}
	in.lay = layout{disk: disk.Path, luks: job.Data.Encryption.Enabled}
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
	add := func(size int64, gptType, mbrType, name string) string {
		l := fmt.Sprintf("start=%d", start/sector)
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
		p := hw.PartitionPath(disk.Path, next)
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
	_, err := in.R.Run(ctx, Cmd{Name: "sfdisk", Args: []string{"--append", disk.Path}, Stdin: []byte(strings.Join(lines, "\n") + "\n")})
	return err
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
	excludes := []string{"/dev/*", "/proc/*", "/sys/*", "/run/*", "/tmp/*", "/mnt/*", "/media/*", "/var/tmp/*",
		"/boot/efi/*", "/boot/loader/entries/*", "/boot/initramfs-*", "/var/cache/dnf/*", "/var/cache/libdnf5/*",
		"/etc/machine-id", "/lost+found"}
	args := []string{"-aAXH", "--numeric-ids", "--info=progress2", "--no-inc-recursive"}
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
	// The ESP is vfat: copy its files without owners/permissions, then make sure the signed
	// shim and GRUB are there (F44 also keeps them under /usr/lib/efi).
	if in.lay.esp != "" {
		if in.R.Exists(path.Join(src, "boot/efi")) {
			if err := in.run(ctx, "rsync", "-rt", path.Join(src, "boot/efi")+"/", in.tgt("/boot/efi")+"/"); err != nil {
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
	kb := d.Keyboard
	keymap := kb.Layout
	if kb.Variant != "" {
		keymap += "-" + kb.Variant
	}
	files := []struct {
		path, content string
		perm          uint32
	}{
		{"/etc/vconsole.conf", fmt.Sprintf("KEYMAP=%s\nXKBLAYOUT=%s\nXKBVARIANT=%s\n", keymap, kb.Layout, kb.Variant), 0o644},
		{"/etc/arctic/mango/keyboard.conf", keyboardConf(kb), 0o644},
		{"/etc/arctic/sddm-keyboard.conf", keyboardConf(kb), 0o644},
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

func keyboardConf(kb wizard.KeyboardData) string {
	return fmt.Sprintf("# Written by the Arctic Linux installer: the keyboard layout you picked.\nxkb_rules_layout=%s\nxkb_rules_variant=%s\n", kb.Layout, kb.Variant)
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

func (in *Installer) kernelArgs() string {
	args := "rootflags=subvol=@"
	if in.lay.luks {
		args += " rd.luks.uuid=" + in.lay.luksName
	}
	return args + " rhgb quiet"
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
		`GRUB_CMDLINE_LINUX="` + in.kernelArgs() + `"`,
		`GRUB_DISABLE_RECOVERY="true"`,
		"GRUB_ENABLE_BLSCFG=true",
	}, "\n") + "\n"
	if in.R.Exists(in.tgt("/boot/grub2/themes/arctic/theme.txt")) {
		grub += `GRUB_THEME="/boot/grub2/themes/arctic/theme.txt"` + "\n"
	}
	if job.Data.Disk.Mode == wizard.ModeAlongside {
		grub += "GRUB_DISABLE_OS_PROBER=false\n"
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
		if err := in.run(ctx, "efibootmgr", "--create", "--disk", in.lay.disk, "--part", strconv.Itoa(in.lay.espNum),
			"--label", "Arctic Linux", "--loader", `\EFI\fedora\shimx64.efi`); err != nil {
			return err
		}
	} else {
		if err := in.chroot(ctx, Cmd{Name: "grub2-install", Args: []string{"--target=i386-pc", in.lay.disk}}); err != nil {
			return err
		}
	}
	in.t.Update(1, "")
	return nil
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
		b, _ := json.MarshalIndent(map[string]any{"version": 1, "modules": in.deferred}, "", "  ")
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
		if err := in.run(ctx, "cryptsetup", "close", in.lay.luksName); err != nil {
			return err
		}
	}
	return nil
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
