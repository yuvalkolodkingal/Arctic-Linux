package installer

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/hw"
)

// TestRealDiskPhase runs the disk phase for real against a disposable block device, e.g. a
// loop device in a privileged container:
//
//	ARCTIC_E2E_DEVICE=/dev/loop0 go test ./internal/installer -run RealDiskPhase -v
//
// It partitions, formats (LUKS2 + btrfs subvolumes, and plain btrfs), mounts, checks the
// result with the real tools and cleans up. Skipped unless ARCTIC_E2E_DEVICE is set.
func TestRealDiskPhase(t *testing.T) {
	dev := os.Getenv("ARCTIC_E2E_DEVICE")
	if dev == "" {
		t.Skip("set ARCTIC_E2E_DEVICE to a disposable block device to run")
	}
	if os.Geteuid() != 0 {
		t.Skip("needs root")
	}
	out, err := exec.Command("blockdev", "--getsize64", dev).Output()
	if err != nil {
		t.Fatal(err)
	}
	size, _ := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
	for _, luks := range []bool{true, false} {
		name := "plain"
		if luks {
			name = "luks"
		}
		t.Run(name, func(t *testing.T) {
			job := loadJob(t, "defaults.toml", "uefi")
			job.Disk = hw.Disk{Path: dev, Model: "e2e", SizeBytes: size, SectorSize: 512}
			job.Data.Disk.Disk = dev
			job.Data.Encryption.Enabled = luks
			if !luks {
				job.Secrets.LUKS = nil
			}
			_, dmErr := os.Stat("/dev/mapper/control")
			noDM := luks && dmErr != nil
			var log bytes.Buffer
			target := t.TempDir()
			in := New(&ExecRunner{Log: &log}, job, newReporter(), Options{Target: target, StopAfter: "disk"})
			err := in.Run(context.Background())
			t.Logf("runner log:\n%s", log.String())
			if noDM {
				// No device-mapper here (e.g. a container): luksFormat must have worked, the
				// open must be the step that failed; check the header with the real tools.
				if err == nil || !strings.Contains(err.Error(), "cryptsetup open") {
					t.Fatalf("want the failure at cryptsetup open, got %v", err)
				}
				checkLUKSHeader(t, hw.PartitionPath(dev, 4))
				t.Skip("no device-mapper: LUKS header checked, open/mount not possible here")
			}
			defer func() {
				exec.Command("umount", "-R", target).Run()
				if in.lay.luksName != "" {
					exec.Command("cryptsetup", "close", in.lay.luksName).Run()
				}
			}()
			if err != nil && !kernelHas("btrfs") && strings.Contains(err.Error(), "mount -o compress=zstd:1") {
				// This kernel can't mount btrfs (e.g. a minimal VM kernel): everything up to
				// mkfs.btrfs ran for real; mounting and subvolumes can't be checked here.
				t.Skipf("kernel has no btrfs; verified partitioning and formatting only: %v", err)
			}
			if err != nil {
				t.Fatal(err)
			}
			mounts, _ := exec.Command("findmnt", "-R", "-n", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", target).CombinedOutput()
			t.Logf("mounts:\n%s", mounts)
			for _, want := range []string{target + "/home", target + "/var/log", target + "/nix", target + "/boot", target + "/boot/efi", "subvol=/@home", "zstd:1"} {
				if !strings.Contains(string(mounts), want) {
					t.Errorf("mount table lacks %q", want)
				}
			}
			sv, err := exec.Command("btrfs", "subvolume", "list", target).CombinedOutput()
			if err != nil {
				t.Fatalf("btrfs subvolume list: %v %s", err, sv)
			}
			for _, want := range []string{"path @\n", "path @home", "path @var_log", "path @nix"} {
				if !strings.Contains(string(sv)+"\n", want) {
					t.Errorf("subvolumes lack %q:\n%s", want, sv)
				}
			}
			parts, _ := exec.Command("sfdisk", "-d", dev).CombinedOutput()
			t.Logf("partitions:\n%s", parts)
			if luks {
				checkLUKSHeader(t, in.lay.root)
			}
			fstab := in.fstab()
			t.Logf("fstab:\n%s", fstab)
			if strings.Contains(fstab, "UUID= ") {
				t.Errorf("empty UUID in fstab")
			}
			if strings.Contains(log.String(), testLUKS) {
				t.Errorf("passphrase leaked into the runner log")
			}
		})
	}
}

// checkLUKSHeader verifies the LUKS2 header and that exactly the passphrase unlocks it.
func checkLUKSHeader(t *testing.T, part string) {
	t.Helper()
	c := exec.Command("cryptsetup", "open", "--test-passphrase", "--key-file", "-", part)
	c.Stdin = strings.NewReader(testLUKS)
	if o, err := c.CombinedOutput(); err != nil {
		t.Errorf("the passphrase does not unlock %s: %v %s", part, err, o)
	}
	c = exec.Command("cryptsetup", "open", "--test-passphrase", "--key-file", "-", part)
	c.Stdin = strings.NewReader(testLUKS + "\n")
	if err := c.Run(); err == nil {
		t.Errorf("the passphrase plus a newline must not unlock it (key bytes must be exact)")
	}
	dump, _ := exec.Command("cryptsetup", "luksDump", part).CombinedOutput()
	for _, want := range []string{"Version:", "2", "argon2id", "arctic-root"} {
		if !strings.Contains(string(dump), want) {
			t.Errorf("luksDump lacks %q:\n%s", want, dump)
		}
	}
	t.Logf("luksDump (head):\n%s", firstLines(string(dump), 12))
}

func firstLines(s string, n int) string {
	l := strings.SplitN(s, "\n", n+1)
	if len(l) > n {
		l = l[:n]
	}
	return strings.Join(l, "\n")
}

func kernelHas(fs string) bool {
	b, _ := os.ReadFile("/proc/filesystems")
	for _, l := range strings.Split(string(b), "\n") {
		if strings.TrimSpace(strings.TrimPrefix(l, "nodev")) == fs {
			return true
		}
	}
	return false
}

// failingRunner runs everything for real except the first command named fail, which fails.
type failingRunner struct {
	*ExecRunner
	fail   string
	failed bool
}

func (r *failingRunner) Run(ctx context.Context, c Cmd) (Result, error) {
	if c.Name == r.fail && !r.failed {
		r.failed = true
		return Result{ExitCode: 1}, &CmdError{Cmd: c.String(), Err: errors.New("simulated failure")}
	}
	return r.ExecRunner.Run(ctx, c)
}

// TestRealAlongsideCleanup installs alongside an existing system on a disposable block device
// and fails right after partitioning: the partitions the run added must be gone again, and
// the other system's partitions untouched, so "Try again" finds the same free space.
//
//	ARCTIC_E2E_DEVICE=/dev/loop0 go test ./internal/installer -run RealAlongsideCleanup -v
//
// The device must be at least 45 GB (a sparse loop file is fine). Skipped unless
// ARCTIC_E2E_DEVICE is set.
func TestRealAlongsideCleanup(t *testing.T) {
	dev := os.Getenv("ARCTIC_E2E_DEVICE")
	if dev == "" {
		t.Skip("set ARCTIC_E2E_DEVICE to a disposable block device to run")
	}
	if os.Geteuid() != 0 {
		t.Skip("needs root")
	}
	out, err := exec.Command("blockdev", "--getsize64", dev).Output()
	if err != nil {
		t.Fatal(err)
	}
	size, _ := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64)
	if size < 45*hw.GB {
		t.Skipf("%s is %d bytes; needs 45 GB", dev, size)
	}
	// The "other system": an ESP and a data partition at the start of a GPT disk.
	other := "label: gpt\nsize=100MiB, type=" + hw.TypeESP + "\nsize=1GiB, type=" + hw.TypeMSData + ", name=\"Basic data partition\"\n"
	c := exec.Command("sfdisk", "--wipe", "always", dev)
	c.Stdin = strings.NewReader(other)
	if o, err := c.CombinedOutput(); err != nil {
		t.Fatalf("sfdisk: %v %s", err, o)
	}
	exec.Command("udevadm", "settle").Run()
	before, _ := exec.Command("sfdisk", "--dump", dev).Output()
	start := int64(2048+204800+2097152) * 512
	disk := hw.Disk{Path: dev, Model: "e2e", SizeBytes: size, SectorSize: 512, PTType: "gpt",
		Partitions: []hw.Partition{
			{Path: hw.PartitionPath(dev, 1), Number: 1, StartByte: 2048 * 512, SizeBytes: 100 * hw.MiB, Type: hw.TypeESP},
			{Path: hw.PartitionPath(dev, 2), Number: 2, StartByte: (2048 + 204800) * 512, SizeBytes: hw.GiB, Type: hw.TypeMSData},
		},
		FreeRegions: []hw.Region{{StartByte: start, SizeBytes: size - start - 34*512}},
	}
	job := loadJob(t, "defaults.toml", "uefi")
	job.Disk = disk
	job.Data.Disk.Disk, job.Data.Disk.Mode = dev, "alongside"
	job.Data.Encryption.Enabled = false
	job.Secrets.LUKS = nil
	var log bytes.Buffer
	r := &failingRunner{ExecRunner: &ExecRunner{Log: &log}, fail: "mkfs.ext4"}
	in := New(r, job, newReporter(), Options{Target: t.TempDir(), StopAfter: "disk"})
	err = in.Run(context.Background())
	t.Logf("runner log:\n%s", log.String())
	if err == nil || !strings.Contains(err.Error(), "simulated failure") {
		t.Fatalf("want the simulated mkfs failure, got %v", err)
	}
	if !strings.Contains(log.String(), "sfdisk --append") || !strings.Contains(log.String(), "sfdisk --delete "+dev+" 3 4") {
		t.Errorf("the run did not add and then delete partitions 3 and 4")
	}
	after, _ := exec.Command("sfdisk", "--dump", dev).Output()
	if string(after) != string(before) {
		t.Errorf("partition table not restored:\nbefore:\n%s\nafter:\n%s", before, after)
	}
}
