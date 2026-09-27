package hw

import (
	"bufio"
	"fmt"
	"io"
	"sort"
	"strings"
)

// PCIDevice is one device of /sys/bus/pci/devices (internal/host ReadPCI). Ids are four
// lower-case hex digits without "0x".
type PCIDevice struct {
	Slot      string `json:"slot"` // "0000:01:00.0"
	Vendor    string `json:"vendor"`
	Device    string `json:"device"`
	SubVendor string `json:"subsystem_vendor,omitempty"`
	SubDevice string `json:"subsystem_device,omitempty"`
	// Class is the class and subclass ("0300" VGA, "0302" 3D controller, "0280" Wi-Fi).
	Class string `json:"class"`
	// Driver is the kernel driver bound to the device ("i915", "nouveau"; "" for none).
	Driver string `json:"driver,omitempty"`
	// BootVGA is set on the display device the firmware used (sysfs boot_vga = 1).
	BootVGA bool `json:"boot_vga,omitempty"`
	// Name is the pci.ids device name ("AD107M [GeForce RTX 4060 Max-Q / Mobile]"), if known.
	Name string `json:"name,omitempty"`
	// VendorName is the pci.ids vendor name ("NVIDIA Corporation"), if known.
	VendorName string `json:"vendor_name,omitempty"`
}

// Hardware is what the driver detection needs to know about the machine.
type Hardware struct {
	PCI       []PCIDevice `json:"pci"`
	CPUVendor string      `json:"cpu_vendor,omitempty"` // "GenuineIntel", "AuthenticAMD"
	// SecureBoot is true when the firmware enforces Secure Boot (and shim validation is on):
	// kernel modules built on the machine then need an enrolled key.
	SecureBoot bool `json:"secure_boot"`
}

// PCI vendor ids.
const (
	VendorNVIDIA   = "10de"
	VendorIntel    = "8086"
	VendorAMD      = "1002"
	VendorBroadcom = "14e4"
)

// vendorShort are the names people know the vendors by.
var vendorShort = map[string]string{
	VendorNVIDIA:   "NVIDIA",
	VendorIntel:    "Intel",
	VendorAMD:      "AMD",
	VendorBroadcom: "Broadcom",
	"1af4":         "Red Hat",
	"1234":         "QEMU",
	"15ad":         "VMware",
	"80ee":         "VirtualBox",
	"1b36":         "Red Hat",
}

// IsDisplay reports whether the device is a display controller (class 03xx).
func (p PCIDevice) IsDisplay() bool { return strings.HasPrefix(p.Class, "03") }

// VendorShort is the vendor's everyday name ("NVIDIA", "AMD"): from a fixed list, else the
// first word of the pci.ids vendor name, else the vendor id.
func (p PCIDevice) VendorShort() string {
	if s, ok := vendorShort[p.Vendor]; ok {
		return s
	}
	if f := strings.Fields(p.VendorName); len(f) > 0 {
		return strings.TrimRight(f[0], ",.")
	}
	return p.Vendor
}

// Label names the device for people: "NVIDIA GeForce RTX 4060 Max-Q / Mobile",
// "Intel Iris Xe Graphics", "Broadcom BCM4360 Wi-Fi". Without a pci.ids name it falls back
// to "NVIDIA graphics card (10de:28e0)".
func (p PCIDevice) Label() string {
	v := p.VendorShort()
	name := strings.TrimSpace(p.Name)
	if p.Class == "0280" {
		if f := strings.Fields(name); len(f) > 0 {
			return v + " " + f[0] + " Wi-Fi"
		}
		return fmt.Sprintf("%s Wi-Fi card (%s:%s)", v, p.Vendor, p.Device)
	}
	if name == "" {
		kind := "device"
		if p.IsDisplay() {
			kind = "graphics card"
		}
		return fmt.Sprintf("%s %s (%s:%s)", v, kind, p.Vendor, p.Device)
	}
	// The marketing name is in brackets: "AD107M [GeForce RTX 4060 Max-Q / Mobile]".
	if i := strings.LastIndexByte(name, '['); i >= 0 {
		if j := strings.IndexByte(name[i:], ']'); j > 1 {
			name = strings.TrimSpace(name[i+1 : i+j])
		}
	}
	if strings.HasPrefix(strings.ToLower(name), strings.ToLower(v)+" ") {
		return name
	}
	return v + " " + name
}

// Displays are the display controllers (class 03xx), in slot order.
func (h Hardware) Displays() []PCIDevice {
	var out []PCIDevice
	for _, p := range h.PCI {
		if p.IsDisplay() {
			out = append(out, p)
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Slot < out[j].Slot })
	return out
}

// BootDisplay is the display device the firmware (and wlroots, which prefers boot_vga) draws
// on: the one with boot_vga = 1, else the only display device.
func (h Hardware) BootDisplay() (PCIDevice, bool) {
	d := h.Displays()
	for _, p := range d {
		if p.BootVGA {
			return p, true
		}
	}
	if len(d) == 1 {
		return d[0], true
	}
	return PCIDevice{}, false
}

// Summary describes the machine for the engine log: "displays: 0000:00:02.0 8086:a7a0
// (i915, boot) Intel Iris Xe Graphics; …; Secure Boot on".
func (h Hardware) Summary() string {
	var parts []string
	for _, p := range h.Displays() {
		drv := p.Driver
		if drv == "" {
			drv = "no driver"
		}
		if p.BootVGA {
			drv += ", boot"
		}
		parts = append(parts, fmt.Sprintf("%s %s:%s class %s (%s) %s", p.Slot, p.Vendor, p.Device, p.Class, drv, p.Label()))
	}
	s := "displays: none"
	if len(parts) > 0 {
		s = "displays: " + strings.Join(parts, "; ")
	}
	for _, p := range h.PCI {
		if p.Class == "0280" {
			drv := p.Driver
			if drv == "" {
				drv = "no driver"
			}
			s += fmt.Sprintf("; Wi-Fi: %s %s:%s (%s) %s", p.Slot, p.Vendor, p.Device, drv, p.Label())
		}
	}
	if h.SecureBoot {
		s += "; Secure Boot on"
	} else {
		s += "; Secure Boot off"
	}
	if h.CPUVendor != "" {
		s += "; CPU " + h.CPUVendor
	}
	return s
}

// ParsePCIIDs reads the pci.ids database (/usr/share/hwdata/pci.ids): vendors under their
// id ("10de" → "NVIDIA Corporation") and devices under "vendor:device" ("10de:28e0" →
// "AD107M [GeForce RTX 4060 Max-Q / Mobile]"). Subsystem lines and the class section at the
// end are skipped.
func ParsePCIIDs(r io.Reader) map[string]string {
	out := map[string]string{}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 1024*1024)
	vendor := ""
	for sc.Scan() {
		l := sc.Text()
		if l == "" || l[0] == '#' {
			continue
		}
		if strings.HasPrefix(l, "C ") {
			break // device classes: no more vendors
		}
		switch {
		case strings.HasPrefix(l, "\t\t"): // subsystem
		case l[0] == '\t':
			if vendor == "" {
				continue
			}
			id, name, ok := splitID(l[1:])
			if ok {
				out[vendor+":"+id] = name
			}
		default:
			id, name, ok := splitID(l)
			if ok {
				vendor = id
				out[id] = name
			} else {
				vendor = ""
			}
		}
	}
	return out
}

// splitID splits "28e0  AD107M [GeForce …]" into a lower-case 4-digit hex id and the name.
func splitID(s string) (string, string, bool) {
	if len(s) < 6 || !IsHex4(s[:4]) || (s[4] != ' ' && s[4] != '\t') {
		return "", "", false
	}
	return strings.ToLower(s[:4]), strings.TrimSpace(s[5:]), true
}

// IsHex4 reports whether s is exactly four lower- or upper-case hex digits.
func IsHex4(s string) bool {
	if len(s) != 4 {
		return false
	}
	for _, r := range s {
		if !(r >= '0' && r <= '9' || r >= 'a' && r <= 'f' || r >= 'A' && r <= 'F') {
			return false
		}
	}
	return true
}

// NameDevices fills Name and VendorName from a ParsePCIIDs map.
func NameDevices(devs []PCIDevice, ids map[string]string) {
	for i := range devs {
		d := &devs[i]
		if d.Name == "" {
			d.Name = ids[d.Vendor+":"+d.Device]
		}
		if d.VendorName == "" {
			d.VendorName = ids[d.Vendor]
		}
	}
}
