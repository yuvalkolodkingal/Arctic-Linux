package installer

import (
	"bytes"
	"context"
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
