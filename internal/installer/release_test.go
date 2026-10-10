package installer

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"
)

// efibootmgrCreated is efibootmgr's answer after --create added Boot0009 (the HP Victus log).
const efibootmgrCreated = "BootCurrent: 0001\nTimeout: 0 seconds\nBootOrder: 0009,0000,0001\nBoot0000* Windows Boot Manager\tHD(1,GPT,…)\nBoot0001* USB HDD\nBoot0009* Arctic Linux\tHD(2,GPT,…)/File(\\EFI\\fedora\\shimx64.efi)\n"

// busyRecorder simulates the real-hardware failure: akmod-nvidia's background build still
// runs after the flock, a gpg-agent is left in the chroot, a service's mount namespace holds a
// copy of the target's mounts, and `cryptsetup close` fails closeFails times with "Device or
// resource busy" (−1 = always, and dmsetup fails too).
func busyRecorder(closeFails int) *Recorder {
	var mu sync.Mutex
	closes := 0
	return &Recorder{
		Respond: func(c Cmd) (string, error) {
			switch {
			case c.Name == "efibootmgr":
				return efibootmgrCreated, nil
			case c.Name == "cryptsetup" && len(c.Args) > 0 && c.Args[0] == "close",
				closeFails < 0 && c.Name == "dmsetup" && len(c.Args) > 0 && c.Args[0] == "remove":
				mu.Lock()
				defer mu.Unlock()
				closes++
				if closeFails < 0 || closes <= closeFails {
					return "", errors.New("Device luks-cce9f6bd-0000-4000-8000-cdf4ebfdedad is still in use.\nDevice or resource busy (exit 5)")
				}
			}
			return DefaultRespond(c)
		},
		TargetUsersFn: func(n int) []Proc {
			switch n {
			case 0, 1: // after the driver transaction's flock: the background build
				return []Proc{{PID: 4242, Comm: "akmods", Why: "root"}}
			case 3: // finalize: a helper a key import left
				return []Proc{{PID: 5151, Comm: "gpg-agent", Why: "root"}}
			}
			return nil
		},
		MountHoldersFn: func(n int) []Proc {
			if n == 0 {
				return []Proc{{PID: 812, Comm: "systemd-hostnam", Why: "mounts", Mounts: []string{"/mnt", "/mnt/boot", "/mnt/boot/efi"}}}
			}
			return nil
		},
		ExistsFn: func(p string) bool {
			// The mapper is there until it is closed.
			return DefaultExists(p) || strings.HasPrefix(p, "/dev/mapper/")
		},
	}
}

// NVIDIA laptop (the HP Victus: Intel iGPU + RTX 4050, Secure Boot off), erase with LUKS:
// the disk is let go of although the driver build, a gpg-agent and another mount namespace
// hold it at first, and cryptsetup close needs a second try.
func TestGoldenNVIDIALUKSBusy(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", false)
	if !job.Data.Encryption.Enabled || strings.Join(job.Data.Apps.Selection["drivers"], ",") != "nvidia,intel-media" {
		t.Fatalf("encryption %v, drivers %v", job.Data.Encryption.Enabled, job.Data.Apps.Selection["drivers"])
	}
	rec := busyRecorder(1)
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	golden(t, "nvidia-luks-busy-uefi.plan", plan)
	checkNoSecrets(t, plan)
	idx := func(s string) int {
		i := strings.Index(plan, s)
		if i < 0 {
			t.Errorf("plan lacks %q", s)
		}
		return i
	}
	// The build is waited for (never signalled), before the next dnf/flatpak command.
	if strings.Contains(plan, "kill -TERM 4242") || strings.Contains(plan, "kill -KILL 4242") {
		t.Error("the akmods build was killed")
	}
	if !(idx("flock -w 1800 /run/akmods/akmods.lock true") < idx("? processes using /mnt: 4242 akmods (root)") &&
		idx("? processes using /mnt: 4242 akmods (root)") < idx("flatpak remote-add")) {
		t.Error("the background build isn't waited for right after the driver transaction")
	}
	// The helper is stopped before the unmount, the namespace copy unmounted before the close.
	if !(idx("$ kill -TERM 5151") < idx("$ umount --recursive /mnt") &&
		idx("$ umount --recursive /mnt") < idx("$ sync") &&
		idx("$ sync") < idx("$ nsenter --target 812 --mount -- umount --recursive --lazy /mnt") &&
		idx("$ nsenter --target 812 --mount -- umount --recursive --lazy /mnt") < idx("$ cryptsetup close")) {
		t.Error("wrong order of the release steps")
	}
	if strings.Count(plan, "$ nsenter ") != 1 {
		t.Error("nested mounts unmounted one by one (umount --recursive takes them)")
	}
	if strings.Count(plan, "$ cryptsetup close luks-") != 2 || !strings.Contains(plan, "# wait 1s") {
		t.Error("cryptsetup close not retried after a pause")
	}
	for _, not := range []string{"cleanup after failure", "--delete-bootnum", "dmsetup remove"} {
		if strings.Contains(plan, not) {
			t.Errorf("plan has %q", not)
		}
	}
	if !reflect.DeepEqual(job.Outcome.Notes, []string{NoteDictationPending}) {
		t.Errorf("notes %v", job.Outcome.Notes)
	}
}

// The LUKS mapping can't be closed at all after the system is complete: that is not a
// failure. Nothing is cleaned up — the boot entry, the partitions and the key request stay —
// and the Done screen gets a note.
func TestLateCloseFailureKeepsSystem(t *testing.T) {
	job := loadHWJob(t, "defaults.toml", "uefi", "nvidia-laptop", true)
	rec := busyRecorder(-1)
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatalf("a late close failure failed the install: %v", err)
	}
	plan := rec.Plan()
	golden(t, "nvidia-luks-stuck-uefi.plan", plan)
	final := plan[strings.Index(plan, "# == finalize"):]
	for _, not := range []string{"cleanup after failure", "--delete-bootnum", "mokutil --revoke-import", "$ wipefs", "sfdisk --delete"} {
		if strings.Contains(final, not) {
			t.Errorf("plan has %q:\n%s", not, plan)
		}
	}
	if n := strings.Count(plan, "$ cryptsetup close luks-"); n != len(closeBackoff) {
		t.Errorf("%d close attempts, want %d", n, len(closeBackoff))
	}
	for _, w := range []string{"$ dmsetup remove --retry luks-", "$ dmsetup remove --deferred luks-", "$ umount /mnt"} {
		if !strings.Contains(plan, w) {
			t.Errorf("plan lacks %q", w)
		}
	}
	if !reflect.DeepEqual(job.Outcome.Notes, []string{NoteDictationPending, NoteStillOpen}) {
		t.Errorf("notes %v", job.Outcome.Notes)
	}
	if job.Outcome.MOK != "requested" {
		t.Errorf("key request %q", job.Outcome.MOK)
	}
	if !strings.Contains(strings.Join(rep.logs, "\n"), "the new system is complete; keeping it") {
		t.Errorf("logs %v", rep.logs)
	}
}

// A failure after the account was created (here: writing /etc/arctic/default-apps) fails the
// install, but cleanup only unmounts: the boot entry and the partitions stay.
func TestFailureAfterCommitKeepsBootEntry(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		switch {
		case c.Name == "efibootmgr":
			return efibootmgrCreated, nil
		case c.Name == "usermod":
			return "", errors.New("usermod: cannot lock /etc/passwd")
		}
		return DefaultRespond(c)
	}}
	err := runPlan(t, job, rec, newReporter())
	if err == nil || !strings.HasPrefix(err.Error(), "finalize: ") {
		t.Fatalf("got %v", err)
	}
	plan := rec.Plan()
	if !strings.Contains(plan, "cleanup after failure") || !strings.Contains(plan, "$ cryptsetup close luks-") {
		t.Errorf("no unmount/close after the failure:\n%s", plan)
	}
	if final := plan[strings.Index(plan, "# == finalize"):]; strings.Contains(final, "--delete-bootnum") || strings.Contains(final, "$ wipefs") {
		t.Errorf("cleanup removed the boot entry or partitions after the account step:\n%s", plan)
	}
}

// dnf failing on the network (the metalink's "Connection reset by peer") is tried again;
// a real error (no such package) is not.
func TestDNFNetworkRetry(t *testing.T) {
	job := loadJob(t, "defaults.toml", "uefi")
	job.Data.Apps.Selection["files"] = []string{"pcmanfm", "yazi"}
	var mu sync.Mutex
	fails := 0
	rec := &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && strings.Contains(c.String(), "dnf install -y yazi") {
			mu.Lock()
			defer mu.Unlock()
			if fails < 2 {
				fails++
				return "", errors.New(">>> Curl error (56): Failure when receiving data from the peer for https://mirrors.fedoraproject.org/metalink?repo=fedora-44&arch=x86_64 [Recv failure: Connection reset by peer]\nFailed to download metadata (metalink) for repository \"fedora\"")
			}
		}
		return DefaultRespond(c)
	}}
	rep := newReporter()
	if err := runPlan(t, job, rec, rep); err != nil {
		t.Fatal(err)
	}
	plan := rec.Plan()
	if n := strings.Count(plan, "dnf install -y yazi"); n != 3 {
		t.Errorf("dnf ran %d times, want 3", n)
	}
	if !strings.Contains(plan, "# wait 5s") || !strings.Contains(plan, "# wait 15s") {
		t.Error("no pause before the retries")
	}
	if len(rep.attention) != 0 {
		t.Errorf("attention %v", rep.attention)
	}

	// Not a network error: no retry.
	rec = &Recorder{Respond: func(c Cmd) (string, error) {
		if c.Name == "chroot" && strings.Contains(c.String(), "dnf install -y yazi") {
			return "", errors.New("No match for argument: yazi")
		}
		return DefaultRespond(c)
	}}
	job = loadJob(t, "defaults.toml", "uefi")
	job.Data.Apps.Selection["files"] = []string{"pcmanfm", "yazi"}
	runPlan(t, job, rec, newReporter())
	if strings.Contains(rec.Plan(), "# wait 5s") {
		t.Error("retried a failure that isn't the network's")
	}
}

func TestParseMountinfo(t *testing.T) {
	info := `22 1 0:21 / / rw,relatime shared:1 - overlay LiveOS_rootfs rw
120 22 253:0 / /mnt rw,relatime - btrfs /dev/mapper/luks-abc rw,subvol=/@
121 120 8:18 / /mnt/boot rw,relatime - ext4 /dev/sdb2 rw
122 121 8:17 / /mnt/boot/efi rw,relatime - vfat /dev/sdb1 rw
123 22 253:0 /@home /srv/other\040dir rw,relatime - btrfs /dev/mapper/luks-abc rw
124 22 0:5 / /dev rw - devtmpfs devtmpfs rw
`
	got := ParseMountinfo(info, "/mnt", []string{"/dev/mapper/luks-abc"})
	want := []string{"/mnt", "/mnt/boot", "/mnt/boot/efi", "/srv/other dir"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
	if got := topMounts(want); !reflect.DeepEqual(got, []string{"/mnt", "/srv/other dir"}) {
		t.Errorf("topMounts %q", got)
	}
}

// scanTargetUsers and scanMountHolders on a fake /proc.
func TestScanProc(t *testing.T) {
	proc := t.TempDir()
	mk := func(pid, comm, root, cwd, ns, mountinfo string, fds ...string) {
		d := filepath.Join(proc, pid)
		os.MkdirAll(filepath.Join(d, "fd"), 0o755)
		os.MkdirAll(filepath.Join(d, "ns"), 0o755)
		os.WriteFile(filepath.Join(d, "comm"), []byte(comm+"\n"), 0o644)
		os.Symlink(root, filepath.Join(d, "root"))
		os.Symlink(cwd, filepath.Join(d, "cwd"))
		os.Symlink("/usr/bin/"+comm, filepath.Join(d, "exe"))
		os.Symlink(ns, filepath.Join(d, "ns", "mnt"))
		os.WriteFile(filepath.Join(d, "mountinfo"), []byte(mountinfo), 0o644)
		for i, f := range fds {
			os.Symlink(f, filepath.Join(d, "fd", string(rune('3'+i))))
		}
	}
	own := "mnt:[4026531841]"
	ours := "120 22 253:0 / /mnt rw - btrfs /dev/mapper/luks-abc rw\n"
	mk("1", "systemd", "/", "/", own, ours)
	mk("100", "arcticd", "/", "/", own, ours)
	mk("4242", "akmods", "/mnt", "/tmp", own, ours)
	mk("5000", "bash", "/", "/mnt/root", own, ours)
	mk("5100", "less", "/", "/", own, ours, "/dev/pts/0", "/mnt/var/log/x.log")
	mk("6000", "mnt", "/", "/", own, ours) // a name that isn't a path
	mk("812", "systemd-hostnam", "/", "/", "mnt:[4026532301]", ours+"121 120 8:18 / /mnt/boot rw - ext4 /dev/sdb2 rw\n")
	mk("813", "systemd-hostnam", "/", "/", "mnt:[4026532301]", ours)
	mk("900", "fwupd", "/", "/", "mnt:[4026532400]", "22 1 0:21 / / rw - overlay LiveOS_rootfs rw\n")
	os.MkdirAll(filepath.Join(proc, "self"), 0o755)

	users, err := scanTargetUsers(proc, "/mnt", 100)
	if err != nil {
		t.Fatal(err)
	}
	want := []Proc{{PID: 4242, Comm: "akmods", Why: "root"}, {PID: 5000, Comm: "bash", Why: "cwd"}, {PID: 5100, Comm: "less", Why: "file"}}
	if !reflect.DeepEqual(users, want) {
		t.Errorf("users %+v", users)
	}
	holders, err := scanMountHolders(proc, "/mnt", []string{"/dev/mapper/luks-abc"}, 100)
	if err != nil {
		t.Fatal(err)
	}
	if len(holders) != 1 || holders[0].PID != 812 || !reflect.DeepEqual(holders[0].Mounts, []string{"/mnt", "/mnt/boot"}) {
		t.Errorf("holders %+v", holders)
	}
}
