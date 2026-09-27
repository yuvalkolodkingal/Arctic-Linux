package installer

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
)

// TestRealCopyESP runs the copy of the live root for real (rsync, cp) into a target whose
// /boot/efi is a separate mount that can't store extended attributes, like the vfat ESP:
//
//	ARCTIC_E2E_COPY=1 go test ./internal/installer -run RealCopyESP -v    (as root)
//
// The ESP is a vfat loop mount when the kernel has vfat, else ramfs, which has no xattr
// support at all and answers setxattr with the same EOPNOTSUPP vfat gives. The source
// carries security.selinux and user.* xattrs, as the kiwi-built image does. Skipped unless
// ARCTIC_E2E_COPY is set.
func TestRealCopyESP(t *testing.T) {
	if os.Getenv("ARCTIC_E2E_COPY") == "" {
		t.Skip("set ARCTIC_E2E_COPY=1 (as root) to run")
	}
	if os.Geteuid() != 0 {
		t.Skip("needs root")
	}
	if _, err := exec.LookPath("rsync"); err != nil {
		t.Skip("needs rsync")
	}
	src := t.TempDir()
	for p, body := range map[string]string{
		"usr/bin/arctic-tool":                           "#!/bin/sh\n",
		"etc/os-release":                                "NAME=\"Arctic Linux\"\n",
		"boot/efi/EFI/fedora/shimx64.efi":               "shim",
		"boot/efi/EFI/BOOT/BOOTX64.EFI":                 "boot",
		"usr/lib/efi/grub2/2.12/EFI/fedora/grubx64.efi": "grub",
	} {
		full := filepath.Join(src, p)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	labelled := false
	for p, label := range map[string]string{"boot/efi": "system_u:object_r:boot_t:s0", "etc/os-release": "system_u:object_r:etc_t:s0"} {
		full := filepath.Join(src, p)
		if err := syscall.Setxattr(full, "user.arctic", []byte("1"), 0); err != nil {
			t.Logf("user xattr on %s: %v", p, err)
		}
		if err := syscall.Setxattr(full, "security.selinux", []byte(label), 0); err == nil {
			labelled = true
		} else {
			t.Logf("security.selinux on %s: %v", p, err)
		}
	}

	newTarget := func() (string, string) {
		tgt := t.TempDir()
		esp := filepath.Join(tgt, "boot/efi")
		if err := os.MkdirAll(esp, 0o755); err != nil {
			t.Fatal(err)
		}
		return tgt, mountESP(t, esp)
	}

	// The old exclude (/boot/efi/* only) reaches the mount point: rsync tries to give the vfat
	// root the source directory's xattrs and exits 23. This shows the environment reproduces
	// the failure the fix is about.
	oldTgt, kind := newTarget()
	old := exec.Command("rsync", "-aAXH", "--numeric-ids", "--exclude=/boot/efi/*", src+"/", oldTgt+"/")
	out, err := old.CombinedOutput()
	t.Logf("old exclude on %s ESP: err=%v\n%s", kind, err, out)
	if err == nil {
		t.Logf("note: the old exclude did not fail here (no xattr could be set on the source)")
	}

	tgt, kind := newTarget()
	job := loadJob(t, "defaults.toml", "uefi")
	var log bytes.Buffer
	in := New(&ExecRunner{Log: &log}, job, newReporter(), Options{Target: tgt})
	in.lay.esp = "/dev/esp-under-test"
	in.t = backend.NewTracker(in.Rep, 0, time.Minute, nil)
	err = in.copyRoot(context.Background(), src)
	t.Logf("runner log (%s ESP):\n%s", kind, log.String())
	if err != nil {
		t.Fatalf("copy failed: %v", err)
	}
	for _, p := range []string{"usr/bin/arctic-tool", "etc/os-release", "boot/efi/EFI/fedora/shimx64.efi", "boot/efi/EFI/BOOT/BOOTX64.EFI", "boot/efi/EFI/fedora/grubx64.efi"} {
		if _, err := os.Stat(filepath.Join(tgt, p)); err != nil {
			t.Errorf("missing after the copy: %s", p)
		}
	}
	var buf [256]byte
	if n, err := syscall.Getxattr(filepath.Join(tgt, "etc/os-release"), "user.arctic", buf[:]); err != nil || string(buf[:n]) != "1" {
		t.Errorf("user xattr not copied: %v", err)
	}
	if labelled {
		if n, err := syscall.Getxattr(filepath.Join(tgt, "etc/os-release"), "security.selinux", buf[:]); err == nil && strings.Contains(string(buf[:n]), "etc_t") {
			t.Errorf("security.selinux was copied (%q); setfiles labels the target instead", buf[:n])
		}
	}
}

// mountESP mounts a vfat loop image at dir, or ramfs when the kernel has no vfat.
func mountESP(t *testing.T, dir string) string {
	t.Helper()
	img := filepath.Join(t.TempDir(), "esp.img")
	if exec.Command("truncate", "-s", "64M", img).Run() == nil &&
		exec.Command("mkfs.vfat", "-F", "32", img).Run() == nil &&
		exec.Command("mount", "-o", "loop,umask=0077", img, dir).Run() == nil {
		t.Cleanup(func() { exec.Command("umount", dir).Run() })
		return "vfat"
	}
	if out, err := exec.Command("mount", "-t", "ramfs", "ramfs", dir).CombinedOutput(); err != nil {
		t.Skipf("can't mount a vfat or ramfs ESP here: %v %s", err, out)
	}
	t.Cleanup(func() { exec.Command("umount", dir).Run() })
	return "ramfs"
}
