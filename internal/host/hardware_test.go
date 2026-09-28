package host

import (
	"os"
	"path/filepath"
	"testing"
)

// fakeSys builds a /sys, /proc and hwdata tree like a hybrid laptop's: an Intel iGPU that
// drew the boot screen (i915) and an NVIDIA 3D controller on nouveau, plus a host bridge.
func fakeSys(t *testing.T, secureBoot, setupMode, mokValidationOff byte) string {
	t.Helper()
	root := t.TempDir()
	write := func(p, s string) {
		p = filepath.Join(root, p)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	dev := func(slot, vendor, device, class, driver, bootVGA string) {
		d := "sys/bus/pci/devices/" + slot + "/"
		write(d+"vendor", vendor+"\n")
		write(d+"device", device+"\n")
		write(d+"class", class+"\n")
		write(d+"subsystem_vendor", "0x17aa\n")
		write(d+"subsystem_device", "0x3c6b\n")
		if bootVGA != "" {
			write(d+"boot_vga", bootVGA+"\n")
		}
		if driver != "" {
			drv := filepath.Join(root, "sys/bus/pci/drivers", driver)
			if err := os.MkdirAll(drv, 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(drv, filepath.Join(root, d, "driver")); err != nil {
				t.Fatal(err)
			}
		}
	}
	dev("0000:01:00.0", "0x10de", "0x28E0", "0x030200", "nouveau", "0")
	dev("0000:00:02.0", "0x8086", "0xa7a0", "0x030000", "i915", "1")
	dev("0000:00:00.0", "0x8086", "0xa706", "0x060000", "", "")
	write("sys/bus/pci/devices/0000:02:00.0/vendor", "garbage\n") // unreadable entries are skipped
	efi := func(name string, v byte) {
		write("sys/firmware/efi/efivars/"+name, string([]byte{0x06, 0, 0, 0, v}))
	}
	efi(efiVarSecureBoot, secureBoot)
	efi(efiVarSetupMode, setupMode)
	if mokValidationOff != 0 {
		efi(efiVarMokSBStateRT, mokValidationOff)
	}
	write("proc/cpuinfo", "processor\t: 0\nvendor_id\t: GenuineIntel\ncpu family\t: 6\n")
	write("usr/share/hwdata/pci.ids", "# pci.ids\n8086  Intel Corporation\n\ta706  Raptor Lake-P/U 4p+8e cores Host Bridge/DRAM Controller\n\ta7a0  Raptor Lake-P [Iris Xe Graphics]\n\t\t17aa 3c6b  ThinkPad\n10de  NVIDIA Corporation\n\t28e0  AD107M [GeForce RTX 4060 Max-Q / Mobile]\nC 03  Display controller\n\t00  VGA compatible controller\n")
	return root
}

func TestProbeHardware(t *testing.T) {
	h := ProbeHardware(fakeSys(t, 1, 0, 0))
	if len(h.PCI) != 3 {
		t.Fatalf("devices %+v", h.PCI)
	}
	nv := h.PCI[2]
	if nv.Slot != "0000:01:00.0" || nv.Vendor != "10de" || nv.Device != "28e0" || nv.Class != "0302" || nv.Driver != "nouveau" || nv.BootVGA {
		t.Errorf("nvidia %+v", nv)
	}
	if nv.Label() != "NVIDIA GeForce RTX 4060 Max-Q / Mobile" || nv.SubVendor != "17aa" {
		t.Errorf("label %q %+v", nv.Label(), nv)
	}
	boot, ok := h.BootDisplay()
	if !ok || boot.Device != "a7a0" || boot.Label() != "Intel Iris Xe Graphics" {
		t.Errorf("boot display %+v", boot)
	}
	if !h.SecureBoot || h.CPUVendor != "GenuineIntel" {
		t.Errorf("secure boot %v cpu %q", h.SecureBoot, h.CPUVendor)
	}
	if len(h.Displays()) != 2 {
		t.Errorf("displays %v", h.Displays())
	}
}

func TestSecureBootStates(t *testing.T) {
	for _, c := range []struct {
		sb, setup, mok byte
		want           bool
	}{
		{1, 0, 0, true},
		{0, 0, 0, false},
		{1, 1, 0, false}, // setup mode: no keys enforced
		{1, 0, 1, false}, // mokutil --disable-validation
	} {
		root := fakeSys(t, c.sb, c.setup, c.mok)
		if got := SecureBoot(filepath.Join(root, "sys/firmware/efi/efivars")); got != c.want {
			t.Errorf("SecureBoot=%d SetupMode=%d MokSBStateRT=%d: %v", c.sb, c.setup, c.mok, got)
		}
	}
	// BIOS (no efivars) and an empty tree.
	if SecureBoot(filepath.Join(t.TempDir(), "nope")) {
		t.Error("secure boot without efivars")
	}
	if h := ProbeHardware(t.TempDir()); len(h.PCI) != 0 || h.SecureBoot {
		t.Errorf("empty tree %+v", h)
	}
}
