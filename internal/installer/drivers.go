package installer

import (
	"context"
	"errors"
	"fmt"
	"path"
	"sort"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Drivers (modules of the catalog's hardware category) are installed with the apps, in the
// chroot, from RPM Fusion. A driver with [akmod] is a kernel module that akmods builds on the
// computer; the installer builds it for the new system's kernels before the first boot, so the
// driver works right away (akmods.service rebuilds it for every later kernel).
//
//  1. prepareAkmods (once, before the driver's dnf transaction): install akmods with the
//     kernel-devel of the new system's kernel, and create its signing key (kmodgenca -a).
//     akmods requires (kernel-devel-matched if kernel-core), which dnf would otherwise
//     resolve to the newest kernel-devel-matched: that drags in the newest kernel-core and
//     kernel-modules-core but not kernel-modules (graphics, sound, Wi-Fi), and the newest
//     kernel boots by default. So kernel-devel-matched-<kver> is asked for by version; when
//     that version is gone from the repositories, a complete newest kernel is installed with
//     it instead. The akmod package's %posttrans starts a build in the background as soon as
//     it is installed; with the key already there, that build is signed too.
//  2. The driver packages go into the apps' dnf transaction (xorg-x11-drv-nvidia's
//     %posttrans adds its own nouveau blacklist with grubby). Right after it, waitAkmods waits
//     for that background build (akmods' lock), which ends by installing its kmod package
//     with dnf: no other dnf command may run into its rpm lock.
//     When the build is for the running kernel's version (the new system is a copy of the
//     live one), akmods also runs `modprobe -a -b` for every device's modalias, inside the
//     chroot but against the live kernel. That can load the new module into the installer's
//     session; it doesn't take the device over from the driver already bound to it
//     (nouveau, bcma), and with Secure Boot the live kernel refuses the (not yet enrolled)
//     key. akmods has no switch for it; this is accepted.
//  3. buildDriver: `akmods --kernels <kver> --akmod <name>` for every installed kernel that
//     has its kernel-devel (it waits on akmods' lock for the background build), then
//     `modinfo -k <kver>` proves the module is there. A failure asks the person (Try again /
//     Skip); skipping removes the driver's packages again (their %preun removes the
//     arguments).
//  4. The driver's [boot] kernel arguments go on every boot entry, /etc/default/grub and
//     /etc/kernel/cmdline (grubby --update-kernel=ALL) — only for a driver that was built.
//     A build put off to boot (unattended) gets none, and loses the blacklist its package's
//     %posttrans added, so the open driver keeps the screen if akmods fails at boot too; it
//     goes into pending.json, and arctic-firstboot builds it and adds the arguments.
//  5. With Secure Boot enforced, the akmods key is queued for enrolment with mokutil --import;
//     its password is the Done screen's one-time code, handed over as a SHA-512 crypt hash
//     on stdin (mokutil --hash-file), never as text. If the install then fails, cleanup
//     revokes the request (mokutil --revoke-import), so a retry's code is the only one.
//
// Offline (no connection at Start), drivers aren't tried: they go into pending.json with
// their akmod and kernel arguments, and arctic-firstboot installs, builds and enrolls them.

const (
	akmodsLockDir = "/run/akmods"
	// MOKHashPath keeps the one-time code's hash for arctic-firstboot when a driver that
	// needs the key was put off (mokutil --import --hash-file after it is built).
	MOKHashPath = "/var/lib/arctic/mok.hash"
)

// Driver install states inside the installer (protocol.Driver* plus the build put off to
// akmods.service at boot, reported as deferred).
const drvBootBuild = "boot-build"

func (in *Installer) driverStatus(id string) string {
	if in.drvStatus == nil {
		in.drvStatus = map[string]string{}
	}
	return in.drvStatus[id]
}

func (in *Installer) setDriverStatus(id, st string) {
	if in.drvStatus == nil {
		in.drvStatus = map[string]string{}
	}
	in.drvStatus[id] = st
}

// KernelFallback is what prepareAkmods installs when the new system's kernel-devel-matched
// is gone from the repositories: the newest kernel, complete (the live image has
// kernel-modules-extra too), with its development files.
var KernelFallback = []string{"akmods", "kernel", "kernel-core", "kernel-modules", "kernel-modules-core", "kernel-modules-extra", "kernel-devel-matched"}

// kernels lists the kernel versions installed in the new system (/lib/modules/<kver> with its
// vmlinuz, which kernel-core puts there).
func (in *Installer) kernels() ([]string, error) {
	kdirs, err := in.R.Glob(in.tgt("/lib/modules/*"))
	if err != nil {
		return nil, err
	}
	sort.Strings(kdirs)
	var out []string
	for _, kd := range kdirs {
		if in.R.Exists(kd + "/vmlinuz") {
			out = append(out, path.Base(kd))
		}
	}
	return out, nil
}

// prepareAkmods installs akmods with the development files of the new system's kernels and
// creates its signing key, once per install.
func (in *Installer) prepareAkmods(ctx context.Context) error {
	if in.akmodsReady {
		return nil
	}
	// akmods takes its lock in /run/akmods (created by tmpfiles at boot, not in a chroot;
	// the target's /run is the live system's).
	if err := in.R.MkdirAll(in.tgt(akmodsLockDir), 0o755); err != nil {
		return err
	}
	kvers, err := in.kernels()
	if err != nil {
		return err
	}
	pkgs := []string{"akmods"}
	for _, k := range kvers {
		pkgs = append(pkgs, "kernel-devel-matched-"+k)
	}
	res, err := in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, pkgs...), AllowFail: true}))
	if err != nil {
		return err
	}
	if res.ExitCode != 0 || len(kvers) == 0 {
		in.Rep.Logf("the kernel’s development files aren’t available any more: installing the newest kernel with them")
		if err := in.chroot(ctx, Cmd{Name: "dnf", Args: append([]string{"install", "-y"}, KernelFallback...)}); err != nil {
			return err
		}
	}
	if err := in.chroot(ctx, Cmd{Name: "kmodgenca", Args: []string{"-a"}}); err != nil {
		return err
	}
	in.akmodsReady = true
	return nil
}

// waitAkmods waits for the build an akmod package's %posttrans started in the background
// (it holds akmods' lock until it has installed the kmod package with dnf).
func (in *Installer) waitAkmods(ctx context.Context) {
	in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "flock", Args: []string{"-w", "1800", akmodsLockDir + "/akmods.lock", "true"}, AllowFail: true}))
}

// akmodsBuild builds a driver for every kernel of the new system that has its development
// files and checks that the module is installed for it.
func (in *Installer) akmodsBuild(ctx context.Context, m *catalog.Module) error {
	kvers, err := in.kernels()
	if err != nil {
		return err
	}
	built := 0
	for _, kver := range kvers {
		if !in.R.Exists(in.tgt("/usr/src/kernels/" + kver + "/Makefile")) {
			in.R.Note("%s: no kernel-devel for %s, akmods builds it when that kernel boots", m.ID, kver)
			continue
		}
		if err := in.chroot(ctx, Cmd{Name: "akmods", Args: []string{"--force", "--kernels", kver, "--akmod", m.Akmod.Name}}); err != nil {
			return err
		}
		if err := in.chroot(ctx, Cmd{Name: "modinfo", Args: []string{"-k", kver, "-F", "version", m.Akmod.Module}}); err != nil {
			return fmt.Errorf("akmods didn’t install the %s module for %s (see /var/cache/akmods/%s/)", m.Akmod.Module, kver, m.Akmod.Name)
		}
		built++
	}
	if built == 0 {
		return errors.New("no installed kernel has its development files (kernel-devel)")
	}
	return nil
}

// buildDriver runs akmodsBuild until it works or the person skips (unattended: akmods builds
// it at boot instead). It returns the driver's state.
func (in *Installer) buildDriver(ctx context.Context, m *catalog.Module) (string, error) {
	for {
		in.t.Update(0.95, backend.BuildingStatus(m))
		err := in.akmodsBuild(ctx, m)
		if err == nil {
			return protocol.DriverInstalled, nil
		}
		if ctx.Err() != nil {
			return "", ctx.Err()
		}
		in.Rep.Logf("%s: build failed: %v", m.ID, err)
		switch in.Rep.Attention(ctx, backend.AttentionFor(m, "The driver didn’t build for this computer’s kernel.", errText(err))) {
		case backend.Retry:
			if ctx.Err() != nil {
				return "", ctx.Err()
			}
			continue
		case backend.Defer:
			return drvBootBuild, nil
		default:
			in.removeDriver(ctx, m)
			return protocol.DriverSkipped, nil
		}
	}
}

// removeDriver takes a skipped driver's packages out again (with what they pulled in), and its
// kernel arguments.
func (in *Installer) removeDriver(ctx context.Context, m *catalog.Module) {
	in.skipped[m.ID] = true
	in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "dnf", Args: append([]string{"remove", "-y"}, m.Primary().Packages...), AllowFail: true}))
	if args := m.KernelArgs(in.lay.luks); len(args) > 0 {
		in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "grubby", Args: []string{"--update-kernel=ALL", "--remove-args=" + strings.Join(args, " ")}, AllowFail: true}))
	}
}

// finishDrivers builds the installed drivers, sets their kernel arguments, queues the key
// enrolment and records the outcome for the Done screen.
func (in *Installer) finishDrivers(ctx context.Context) error {
	drivers := in.Job.Drivers()
	if len(drivers) == 0 {
		return nil
	}
	var args []string
	seen := map[string]bool{}
	needKey := false // a built (or boot-built) akmod driver: enroll now
	for _, m := range drivers {
		st := in.driverStatus(m.ID)
		if st == "" {
			switch {
			case in.skipped[m.ID]:
				st = protocol.DriverSkipped
			case in.isDeferred(m.ID):
				st = protocol.DriverDeferred
			default:
				st = protocol.DriverInstalled
			}
		}
		if st == protocol.DriverInstalled && m.AkmodName() != "" {
			var err error
			if st, err = in.buildDriver(ctx, m); err != nil {
				return err
			}
		}
		in.setDriverStatus(m.ID, st)
		switch st {
		case protocol.DriverInstalled:
			for _, a := range m.KernelArgs(in.lay.luks) {
				if !seen[a] {
					seen[a] = true
					args = append(args, a)
				}
			}
			if m.AkmodName() != "" {
				needKey = true
			}
		case drvBootBuild:
			// No arguments until the module exists: arctic-firstboot builds it (after
			// akmods.service's own try) and adds them; the %posttrans blacklist goes too.
			if ka := m.KernelArgs(in.lay.luks); len(ka) > 0 {
				in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "grubby", Args: []string{"--update-kernel=ALL", "--remove-args=" + strings.Join(ka, " ")}, AllowFail: true}))
			}
			if !in.isDeferred(m.ID) {
				in.deferred = append(in.deferred, m.ID)
			}
			needKey = true // the key exists now; enrolling it now saves a second code
		}
		out := st
		if st == drvBootBuild {
			out = protocol.DriverDeferred
		}
		in.Job.Outcome.Drivers = append(in.Job.Outcome.Drivers, backend.DriverOutcome{ID: m.ID, Status: out})
		in.R.Note("driver %s for %s: %s", m.ID, m.Device, st)
	}
	if len(args) > 0 {
		if err := in.chroot(ctx, Cmd{Name: "grubby", Args: []string{"--update-kernel=ALL", "--args=" + strings.Join(args, " ")}}); err != nil {
			return err
		}
	}
	if needKey && in.Job.NeedsMOK() && in.Job.MOKCode != "" {
		hash, err := in.mokHash()
		if err != nil {
			return err
		}
		res, err := in.R.Run(ctx, Chroot(in.Opt.Target, Cmd{Name: "mokutil", Args: []string{"--import", wizard.MOKKeyPath, "--hash-file", "/dev/stdin"},
			Stdin: []byte(hash + "\n"), Secret: true, SecretLabel: "one-time code hash", AllowFail: true}))
		if err != nil {
			return err
		}
		if res.ExitCode != 0 {
			in.Rep.Logf("mokutil --import failed (exit %d): the driver won’t load until its key is enrolled", res.ExitCode)
			in.Job.Outcome.MOK = backend.MOKFailed
		} else {
			in.Job.Outcome.MOK = backend.MOKRequested
			in.mokImported = true
		}
	}
	return nil
}

// mokHash is the one-time code as mokutil --generate-hash would print it: a SHA-512 crypt
// string with the default 5000 rounds ("$6$<salt>$<hash>"), which --hash-file reads.
func (in *Installer) mokHash() (string, error) {
	if in.Opt.Salt != "" {
		return SHA512Crypt([]byte(in.Job.MOKCode), "$6$"+in.Opt.Salt)
	}
	return HashPassword([]byte(in.Job.MOKCode))
}

// revokeMOK withdraws this run's key enrolment request after a failure, so the next restart
// doesn't ask for a code a retried install no longer shows.
func (in *Installer) revokeMOK(ctx context.Context) {
	if !in.mokImported {
		return
	}
	in.R.Run(ctx, Cmd{Name: "mokutil", Args: []string{"--revoke-import"}, AllowFail: true})
	in.mokImported = false
	in.Job.Outcome.MOK = backend.MOKNone
}

func (in *Installer) isDeferred(id string) bool {
	for _, d := range in.deferred {
		if d == id {
			return true
		}
	}
	return false
}

// pendingDriverKey writes the one-time code's hash for arctic-firstboot when a driver that
// needs the enrolled key is put off to first boot. It returns the path ("" when not needed).
func (in *Installer) pendingDriverKey(ctx context.Context) (string, error) {
	if !in.Job.NeedsMOK() || in.Job.MOKCode == "" || in.Job.Outcome.MOK != backend.MOKNone {
		return "", nil
	}
	need := false
	for _, id := range in.deferred {
		if m := in.cat.Modules[id]; m != nil && m.AkmodName() != "" {
			need = true
		}
	}
	if !need {
		return "", nil
	}
	hash, err := in.mokHash()
	if err != nil {
		return "", err
	}
	if _, err := in.R.Run(ctx, Cmd{Name: "install", Args: []string{"-D", "-m", "0600", "/dev/stdin", in.tgt(MOKHashPath)},
		Stdin: []byte(hash + "\n"), Secret: true, SecretLabel: "one-time code hash"}); err != nil {
		return "", err
	}
	in.Job.Outcome.MOK = backend.MOKRequested
	return MOKHashPath, nil
}
