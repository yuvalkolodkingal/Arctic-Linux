package installer

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Letting go of the new system at the end of the install (finalize) and the retries around
// network commands.
//
// A LUKS mapping can only be closed when nothing holds the file system on it. After
// `umount --recursive` of the target, three things were seen or are possible:
//
//   - processes still running inside the target: the build akmod-nvidia's %posttrans starts
//     in the background (it may take akmods' lock only after the engine's flock checked it),
//     gpg-agent/keyboxd/dirmngr that a key import started, a D-Bus daemon. They keep the
//     file system busy (root, working directory, open files), so umount fails.
//   - copies of the target's mounts in other mount namespaces: a service that starts while
//     the target is mounted (ProtectSystem=, PrivateTmp=, …: hostnamed, timedated, fwupd, a
//     udev-started helper) gets a copy of every mount, the private target included. Unmounting
//     here doesn't reach that copy, so umount succeeds and `cryptsetup close` then fails with
//     "Device or resource busy". These are unmounted inside that namespace (nsenter).
//   - udev still probing the mapper right after the unmount: settle and try again.
//
// stopTargetProcesses waits for real work (a build, a package transaction) to finish and
// stops helpers at once; releaseMountHolders unmounts the leftover copies; closeLUKS retries
// with a backoff and falls back to `dmsetup remove --retry` and a deferred close. Once the
// system is complete (finalize), a mapping that still can't be closed is not a failure: the
// data is synced, and the restart closes it.

// Proc is a process that keeps the new system busy.
type Proc struct {
	PID  int
	Comm string
	// Why: "root" (runs inside the target, e.g. through chroot), "cwd", "exe", "file" (holds
	// a file under the target open) or "mounts" (its mount namespace has the target's file
	// systems; one Proc per namespace).
	Why string
	// Mounts are the mount points of the target's file systems in that namespace ("mounts").
	Mounts []string
}

func (p Proc) String() string {
	s := fmt.Sprintf("%d %s (%s", p.PID, p.Comm, p.Why)
	if len(p.Mounts) > 0 {
		s += ": " + strings.Join(p.Mounts, " ")
	}
	return s + ")"
}

// ProcessRunner is implemented by runners that can see and signal processes (ExecRunner,
// and Recorder for plans and tests). Other runners skip these steps.
type ProcessRunner interface {
	// TargetUsers lists the processes that run in, work in or hold files under target.
	TargetUsers(target string) ([]Proc, error)
	// MountHolders lists the mount namespaces other than the engine's that still have a mount
	// under target or of one of the devices (one process for each).
	MountHolders(target string, devices []string) ([]Proc, error)
	// Signal sends sig to pid.
	Signal(pid int, sig syscall.Signal) error
}

// helperComms are programs a transaction or a key import in the chroot may leave running.
// They do no work worth waiting for and are stopped at once; anything else (a driver build,
// dnf, rpm) is waited for.
var helperComms = map[string]bool{
	"gpg-agent": true, "keyboxd": true, "dirmngr": true, "scdaemon": true, "gpg": true,
	"dbus-daemon": true, "dbus-broker": true, "dbus-broker-lau": true, "dbus-launch": true,
	"p11-kit-remote": true, "p11-kit-server": true, "pcscd": true,
}

// Waiting for work still running in the target: rounds of procPoll (20 min in all, far
// longer than an NVIDIA build takes on a slow laptop); then SIGTERM, and SIGKILL for what is
// still there procTermRounds seconds later.
const (
	procPoll       = 2 * time.Second
	procWaitRounds = 600
	procTermRounds = 5
)

// waitTargetWork waits (up to 20 minutes) until only helpers are left running inside the
// target: a driver build akmod's %posttrans started, and the dnf that installs its kmod,
// must never be cut short (an interrupted rpm transaction breaks the package database).
// It returns what still uses the target.
func (in *Installer) waitTargetWork(ctx context.Context) []Proc {
	pr, ok := in.R.(ProcessRunner)
	if !ok {
		return nil
	}
	var procs []Proc
	for round := 0; round < procWaitRounds; round++ {
		var err error
		procs, err = pr.TargetUsers(in.Opt.Target)
		if err != nil {
			in.Rep.Logf("couldn’t list the processes using %s: %v", in.Opt.Target, err)
			return nil
		}
		var work []string
		for _, p := range procs {
			if p.Why == "root" && !helperComms[p.Comm] {
				work = append(work, p.String())
			}
		}
		if len(work) == 0 {
			return procs
		}
		if round%30 == 0 {
			in.Rep.Logf("waiting for %s to finish in the new system", strings.Join(work, ", "))
		}
		if err := in.sleep(ctx, procPoll); err != nil {
			return procs
		}
	}
	in.Rep.Logf("gave up waiting after %s", procPoll*procWaitRounds)
	return procs
}

// inside keeps the processes that run inside the target (their root is there): the ones the
// install started through chroot. Others (a shell or file manager of the live session that
// looks into the target) are never signalled; unmountTarget detaches the target from them.
func inside(ps []Proc) []Proc {
	var out []Proc
	for _, p := range ps {
		if p.Why == "root" {
			out = append(out, p)
		}
	}
	return out
}

// stopTargetProcesses makes sure nothing runs inside the target any more: work is waited
// for (waitTargetWork), then whatever is left inside gets SIGTERM and, if it stays, SIGKILL.
func (in *Installer) stopTargetProcesses(ctx context.Context) {
	pr, ok := in.R.(ProcessRunner)
	if !ok {
		return
	}
	procs := inside(in.waitTargetWork(ctx))
	for _, sig := range []syscall.Signal{syscall.SIGTERM, syscall.SIGKILL} {
		if len(procs) == 0 {
			return
		}
		for _, p := range procs {
			in.Rep.Logf("stopping %s, which still uses the new system (%s)", p, sigName(sig))
			if err := pr.Signal(p.PID, sig); err != nil {
				in.Rep.Logf("  %v", err)
			}
		}
		for i := 0; i < procTermRounds; i++ {
			if err := in.sleep(ctx, time.Second); err != nil {
				return
			}
			left, err := pr.TargetUsers(in.Opt.Target)
			if procs = inside(left); err != nil || len(procs) == 0 {
				return
			}
		}
	}
	in.Rep.Logf("still running in the new system: %s", procList(procs))
}

func sigName(s syscall.Signal) string {
	if s == syscall.SIGKILL {
		return "SIGKILL"
	}
	return "SIGTERM"
}

// releaseMountHolders unmounts, inside every other mount namespace that still has them, the
// target's file systems (lazily: the service keeps running and never used them).
func (in *Installer) releaseMountHolders(ctx context.Context) {
	pr, ok := in.R.(ProcessRunner)
	if !ok {
		return
	}
	holders, err := pr.MountHolders(in.Opt.Target, in.targetDevices())
	if err != nil {
		in.Rep.Logf("couldn’t check other mount namespaces: %v", err)
		return
	}
	for _, h := range holders {
		in.Rep.Logf("the new system is still mounted in the mount namespace of %s", h)
		for _, mp := range topMounts(h.Mounts) {
			in.R.Run(ctx, Cmd{Name: "nsenter", Args: []string{"--target", strconv.Itoa(h.PID), "--mount", "--", "umount", "--recursive", "--lazy", mp}, AllowFail: true})
		}
	}
}

// targetDevices are the block devices of the new system's file systems.
func (in *Installer) targetDevices() []string {
	var out []string
	for _, d := range []string{in.lay.rootDev, in.lay.boot, in.lay.esp} {
		if d != "" {
			out = append(out, d)
		}
	}
	return out
}

// topMounts drops the mount points that lie below another one of the list (umount
// --recursive takes them along).
func topMounts(mps []string) []string {
	s := append([]string(nil), mps...)
	sort.Strings(s)
	var out []string
	for _, m := range s {
		covered := false
		for _, o := range out {
			if o == "/" || m == o || strings.HasPrefix(m, strings.TrimSuffix(o, "/")+"/") {
				covered = true
				break
			}
		}
		if !covered {
			out = append(out, m)
		}
	}
	return out
}

// unmountTarget unmounts the new system: processes inside it are stopped first, and a busy
// unmount is tried again (up to three times) before it is detached lazily.
func (in *Installer) unmountTarget(ctx context.Context) error {
	t := in.Opt.Target
	var last Result
	for attempt := 0; attempt < 3; attempt++ {
		in.stopTargetProcesses(ctx)
		res, err := in.R.Run(ctx, Cmd{Name: "umount", Args: []string{"--recursive", t}, AllowFail: true})
		if err != nil {
			return err
		}
		if res.ExitCode == 0 {
			return nil
		}
		last = res
		in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=15"}, AllowFail: true})
		if err := in.sleep(ctx, time.Duration(attempt+1)*2*time.Second); err != nil {
			return err
		}
	}
	in.Rep.Logf("%s is still busy (%s); detaching it", t, strings.TrimSpace(last.Output))
	res, err := in.R.Run(ctx, Cmd{Name: "umount", Args: []string{"--recursive", "--lazy", t}, AllowFail: true})
	if err != nil {
		return err
	}
	if res.ExitCode != 0 {
		return fmt.Errorf("couldn’t unmount %s: %s", t, strings.TrimSpace(res.Output))
	}
	return nil
}

// closeBackoff is the wait before each `cryptsetup close` attempt.
var closeBackoff = []time.Duration{0, time.Second, 2 * time.Second, 4 * time.Second, 8 * time.Second}

// closeLUKS closes the new system's LUKS mapping, retrying while something lets go of it.
func (in *Installer) closeLUKS(ctx context.Context) error {
	name := in.lay.luksName
	var last Result
	for _, wait := range closeBackoff {
		if err := in.sleep(ctx, wait); err != nil {
			return err
		}
		if wait > 0 && !in.R.Exists("/dev/mapper/"+name) {
			return nil // closed meanwhile (a deferred removal from an earlier attempt)
		}
		in.releaseMountHolders(ctx)
		// udev may still be probing the mapper after the unmount.
		if _, err := in.R.Run(ctx, Cmd{Name: "udevadm", Args: []string{"settle", "--timeout=30"}, AllowFail: true}); err != nil {
			return err
		}
		res, err := in.R.Run(ctx, Cmd{Name: "cryptsetup", Args: []string{"close", name}, AllowFail: true})
		if err != nil {
			return err
		}
		if res.ExitCode == 0 {
			return nil
		}
		last = res
	}
	in.Rep.Logf("cryptsetup close %s keeps failing: %s", name, strings.TrimSpace(last.Output))
	in.R.Run(ctx, Cmd{Name: "dmsetup", Args: []string{"info", name}, AllowFail: true})
	if res, err := in.R.Run(ctx, Cmd{Name: "dmsetup", Args: []string{"remove", "--retry", name}, AllowFail: true}); err != nil {
		return err
	} else if res.ExitCode == 0 {
		return nil
	}
	// The mapping goes away by itself as soon as its last user lets go.
	if res, err := in.R.Run(ctx, Cmd{Name: "dmsetup", Args: []string{"remove", "--deferred", name}, AllowFail: true}); err != nil {
		return err
	} else if res.ExitCode == 0 {
		in.Rep.Logf("%s closes as soon as its last user lets go (deferred removal)", name)
		return nil
	}
	return fmt.Errorf("the encrypted partition (%s) is still in use: %s", name, strings.TrimSpace(last.Output))
}

// releaseTarget unmounts the new system and closes its LUKS mapping.
func (in *Installer) releaseTarget(ctx context.Context) error {
	if err := in.unmountTarget(ctx); err != nil {
		return err
	}
	// Whatever still holds the file system, what the install wrote is on the disk.
	in.R.Run(ctx, Cmd{Name: "sync", AllowFail: true})
	if in.lay.luks && in.lay.luksName != "" {
		return in.closeLUKS(ctx)
	}
	return nil
}

// ---- network retries ----

// netError matches what dnf5 (librepo/curl) and flatpak print when a download failed
// because of the network, as opposed to a package that doesn't exist or a conflict.
var netError = regexp.MustCompile(`(?i)curl error|connection reset|connection refused|connection timed out|timeout was reached|operation too slow|could not resolve|temporary failure in name resolution|network is unreachable|no route to host|cannot download|failed to download|no more mirrors to try|librepo error|status code: 5\d\d|error fetching|while fetching|recv failure|send failure`)

// netRetryWaits are the pauses before each retry of a command that failed on the network.
// dnf5 already retries each download (retries=10), but not the metalink or repomd.xml that
// loading a repository starts with: one "Connection reset by peer" there fails the command.
var netRetryWaits = []time.Duration{5 * time.Second, 15 * time.Second, 45 * time.Second}

// isNetCmd reports whether c downloads (dnf in the chroot or the host's flatpak).
func isNetCmd(c Cmd) bool {
	switch c.Name {
	case "dnf", "dnf5":
		return true
	case "flatpak":
		return len(c.Args) > 0 && (c.Args[0] == "install" || c.Args[0] == "remote-add" || c.Args[0] == "update")
	}
	return false
}

// runNet runs a command that downloads, and runs it again after a pause when it failed on
// the network (up to three times).
func (in *Installer) runNet(ctx context.Context, c Cmd) (Result, error) {
	for i := 0; ; i++ {
		res, err := in.R.Run(ctx, c)
		failed := err != nil || res.ExitCode != 0
		if !failed || !isNetCmd(unchroot(c)) || i >= len(netRetryWaits) || ctx.Err() != nil {
			return res, err
		}
		text := res.Output
		if err != nil {
			text += "\n" + err.Error()
		}
		if !netError.MatchString(text) {
			return res, err
		}
		in.Rep.Logf("%s failed on the network; trying again in %s", unchroot(c).Name, netRetryWaits[i])
		if serr := in.sleep(ctx, netRetryWaits[i]); serr != nil {
			return res, err
		}
	}
}

// unchroot returns the command a Chroot wraps.
func unchroot(c Cmd) Cmd {
	if c.Name == "chroot" && len(c.Args) >= 2 {
		return Cmd{Name: c.Args[1], Args: c.Args[2:]}
	}
	return c
}

// sleep waits d, or until ctx ends (a Recorder only notes it; sleepFn replaces it).
func (in *Installer) sleep(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	if in.sleepFn != nil {
		return in.sleepFn(ctx, d)
	}
	if _, ok := in.R.(*Recorder); ok {
		// Plans and tests: show the wait, don't take it.
		in.R.Note("wait %s", d)
		return ctx.Err()
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(d):
		return nil
	}
}

// ---- ExecRunner: /proc ----

// TargetUsers implements ProcessRunner from /proc.
func (r *ExecRunner) TargetUsers(target string) ([]Proc, error) {
	return scanTargetUsers("/proc", target, os.Getpid())
}

// MountHolders implements ProcessRunner from /proc.
func (r *ExecRunner) MountHolders(target string, devices []string) ([]Proc, error) {
	return scanMountHolders("/proc", target, devices, os.Getpid())
}

// Signal implements ProcessRunner.
func (r *ExecRunner) Signal(pid int, sig syscall.Signal) error {
	r.logf("$ kill -%s %d", strings.TrimPrefix(sigName(sig), "SIG"), pid)
	return syscall.Kill(pid, sig)
}

func under(p, target string) bool {
	t := strings.TrimSuffix(target, "/")
	return p == t || strings.HasPrefix(p, t+"/")
}

func pids(proc string) []int {
	ents, _ := os.ReadDir(proc)
	var out []int
	for _, e := range ents {
		if n, err := strconv.Atoi(e.Name()); err == nil && n > 0 {
			out = append(out, n)
		}
	}
	sort.Ints(out)
	return out
}

func comm(proc string, pid int) string {
	b, _ := os.ReadFile(filepath.Join(proc, strconv.Itoa(pid), "comm"))
	return strings.TrimSpace(string(b))
}

// scanTargetUsers finds processes whose root, working directory, executable or an open file
// lies under target. Kernel threads and the engine itself are skipped.
func scanTargetUsers(proc, target string, self int) ([]Proc, error) {
	if _, err := os.Stat(proc); err != nil {
		return nil, err
	}
	var out []Proc
	for _, pid := range pids(proc) {
		if pid == self {
			continue
		}
		dir := filepath.Join(proc, strconv.Itoa(pid))
		why := ""
		for _, l := range []string{"root", "cwd", "exe"} {
			if p, err := os.Readlink(filepath.Join(dir, l)); err == nil && under(p, target) {
				why = l
				break
			}
		}
		if why == "" {
			fds, _ := os.ReadDir(filepath.Join(dir, "fd"))
			for _, fd := range fds {
				if p, err := os.Readlink(filepath.Join(dir, "fd", fd.Name())); err == nil && under(p, target) {
					why = "file"
					break
				}
			}
		}
		if why != "" {
			out = append(out, Proc{PID: pid, Comm: comm(proc, pid), Why: why})
		}
	}
	return out, nil
}

// unescapeMount undoes mountinfo's octal escapes (\040 for a space, …).
func unescapeMount(s string) string {
	if !strings.Contains(s, `\`) {
		return s
	}
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if s[i] == '\\' && i+4 <= len(s) {
			if n, err := strconv.ParseUint(s[i+1:i+4], 8, 8); err == nil {
				b.WriteByte(byte(n))
				i += 3
				continue
			}
		}
		b.WriteByte(s[i])
	}
	return b.String()
}

// ParseMountinfo returns the mount points of a mountinfo file that lie under target or whose
// source is one of the devices.
func ParseMountinfo(data, target string, devices []string) []string {
	var out []string
	for _, line := range strings.Split(data, "\n") {
		f := strings.Fields(line)
		if len(f) < 10 {
			continue
		}
		sep := -1
		for i := 6; i < len(f); i++ {
			if f[i] == "-" {
				sep = i
				break
			}
		}
		if sep < 0 || sep+2 >= len(f) {
			continue
		}
		mp := unescapeMount(f[4])
		src := unescapeMount(f[sep+2])
		hit := under(mp, target)
		for _, d := range devices {
			if src == d {
				hit = true
			}
		}
		if hit {
			out = append(out, mp)
		}
	}
	return out
}

// scanMountHolders finds the mount namespaces other than self's that still have the target's
// file systems: one process of each (the lowest pid), with the mount points.
func scanMountHolders(proc, target string, devices []string, self int) ([]Proc, error) {
	own, err := os.Readlink(filepath.Join(proc, strconv.Itoa(self), "ns", "mnt"))
	if err != nil {
		return nil, err
	}
	// Device paths as the kernel writes them in mountinfo (/dev/mapper/luks-… is a link to
	// /dev/dm-N; mountinfo shows the name mount was given, so both are checked).
	var devs []string
	for _, d := range devices {
		devs = append(devs, d)
		if real, err := filepath.EvalSymlinks(d); err == nil && real != d {
			devs = append(devs, real)
		}
	}
	seen := map[string]bool{own: true}
	var out []Proc
	for _, pid := range pids(proc) {
		dir := filepath.Join(proc, strconv.Itoa(pid))
		ns, err := os.Readlink(filepath.Join(dir, "ns", "mnt"))
		if err != nil || seen[ns] {
			continue
		}
		seen[ns] = true
		b, err := os.ReadFile(filepath.Join(dir, "mountinfo"))
		if err != nil {
			continue
		}
		if mps := ParseMountinfo(string(b), target, devs); len(mps) > 0 {
			out = append(out, Proc{PID: pid, Comm: comm(proc, pid), Why: "mounts", Mounts: mps})
		}
	}
	return out, nil
}

// ---- Recorder ----

// TargetUsers implements ProcessRunner: the plan shows the check; TargetUsersFn (tests)
// answers it, called with how many times it was asked before.
func (r *Recorder) TargetUsers(target string) ([]Proc, error) {
	r.mu.Lock()
	n := r.targetCalls
	r.targetCalls++
	r.mu.Unlock()
	var procs []Proc
	if r.TargetUsersFn != nil {
		procs = r.TargetUsersFn(n)
	}
	r.emit(fmt.Sprintf("? processes using %s: %s", target, procList(procs)))
	return procs, nil
}

// MountHolders implements ProcessRunner (MountHoldersFn answers, like TargetUsersFn).
func (r *Recorder) MountHolders(target string, devices []string) ([]Proc, error) {
	r.mu.Lock()
	n := r.holderCalls
	r.holderCalls++
	r.mu.Unlock()
	var procs []Proc
	if r.MountHoldersFn != nil {
		procs = r.MountHoldersFn(n)
	}
	r.emit(fmt.Sprintf("? other mount namespaces with %s: %s", target, procList(procs)))
	return procs, nil
}

// Signal implements ProcessRunner.
func (r *Recorder) Signal(pid int, sig syscall.Signal) error {
	r.emit(fmt.Sprintf("$ kill -%s %d", strings.TrimPrefix(sigName(sig), "SIG"), pid))
	return nil
}

func procList(ps []Proc) string {
	if len(ps) == 0 {
		return "none"
	}
	var s []string
	for _, p := range ps {
		s = append(s, p.String())
	}
	return strings.Join(s, ", ")
}
