package host

import (
	"context"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/hw"
)

// EFI variable names (/sys/firmware/efi/efivars): 4 attribute bytes, then the value.
const (
	efiVarSecureBoot = "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
	efiVarSetupMode  = "SetupMode-8be4df61-93ca-11d2-aa0d-00e098032b8c"
	// shim's "validation disabled" state (mokutil --disable-validation): the kernel then
	// doesn't enforce module signatures although the firmware has Secure Boot on.
	efiVarMokSBStateRT = "MokSBStateRT-605dab50-e046-4300-abb6-3dd810dd8b23"
)

// PCIIDsPaths are where hwdata (and older distributions) put the PCI name database.
var PCIIDsPaths = []string{"usr/share/hwdata/pci.ids", "usr/share/misc/pci.ids"}

// ProbeHardware reads the PCI devices, the Secure Boot state and the CPU vendor below root
// ("/" on a real system; tests pass a fake tree with sys/, proc/ and usr/share/hwdata/).
// Anything missing is left empty: detection then simply finds nothing.
func ProbeHardware(root string) hw.Hardware {
	h := hw.Hardware{
		PCI:        ReadPCI(filepath.Join(root, "sys/bus/pci/devices")),
		SecureBoot: SecureBoot(filepath.Join(root, "sys/firmware/efi/efivars")),
		CPUVendor:  CPUVendor(filepath.Join(root, "proc/cpuinfo")),
	}
	for _, p := range PCIIDsPaths {
		f, err := os.Open(filepath.Join(root, p))
		if err != nil {
			continue
		}
		ids := hw.ParsePCIIDs(f)
		f.Close()
		hw.NameDevices(h.PCI, ids)
		break
	}
	return h
}

// Hardware implements backend.Backend: the live system's PCI devices and Secure Boot state.
func (b *Backend) Hardware(ctx context.Context) hw.Hardware {
	return ProbeHardware("/")
}

// ReadPCI lists the devices of a /sys/bus/pci/devices directory, in slot order.
func ReadPCI(dir string) []hw.PCIDevice {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	var out []hw.PCIDevice
	for _, e := range entries {
		d := filepath.Join(dir, e.Name())
		p := hw.PCIDevice{
			Slot:      e.Name(),
			Vendor:    hexID(readTrim(filepath.Join(d, "vendor"))),
			Device:    hexID(readTrim(filepath.Join(d, "device"))),
			SubVendor: hexID(readTrim(filepath.Join(d, "subsystem_vendor"))),
			SubDevice: hexID(readTrim(filepath.Join(d, "subsystem_device"))),
			BootVGA:   readTrim(filepath.Join(d, "boot_vga")) == "1",
		}
		// class is "0x030000": class, subclass, programming interface.
		if c := strings.TrimPrefix(strings.ToLower(readTrim(filepath.Join(d, "class"))), "0x"); len(c) >= 4 {
			p.Class = c[:4]
		}
		if l, err := os.Readlink(filepath.Join(d, "driver")); err == nil {
			p.Driver = filepath.Base(l)
		}
		if !hw.IsHex4(p.Vendor) || !hw.IsHex4(p.Device) {
			continue
		}
		out = append(out, p)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Slot < out[j].Slot })
	return out
}

// hexID turns sysfs' "0x10de" into "10de" ("" when it isn't a 16-bit id).
func hexID(s string) string {
	s = strings.TrimPrefix(strings.ToLower(strings.TrimSpace(s)), "0x")
	if !hw.IsHex4(s) {
		return ""
	}
	return s
}

// efiByte returns the first data byte of an EFI variable file (after the 4 attribute bytes).
func efiByte(p string) (byte, bool) {
	b, err := os.ReadFile(p)
	if err != nil || len(b) < 5 {
		return 0, false
	}
	return b[4], true
}

// SecureBoot reports whether Secure Boot is enforced, from an efivarfs directory: SecureBoot
// is 1, the firmware is not in setup mode, and shim's validation is not disabled.
func SecureBoot(efivars string) bool {
	if v, ok := efiByte(filepath.Join(efivars, efiVarSecureBoot)); !ok || v != 1 {
		return false
	}
	if v, ok := efiByte(filepath.Join(efivars, efiVarSetupMode)); ok && v == 1 {
		return false
	}
	if v, ok := efiByte(filepath.Join(efivars, efiVarMokSBStateRT)); ok && v == 1 {
		return false
	}
	return true
}

// CPUVendor is the first vendor_id of /proc/cpuinfo ("GenuineIntel", "AuthenticAMD").
func CPUVendor(cpuinfo string) string {
	for _, l := range strings.Split(readTrim(cpuinfo), "\n") {
		k, v, ok := strings.Cut(l, ":")
		if ok && strings.TrimSpace(k) == "vendor_id" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}
