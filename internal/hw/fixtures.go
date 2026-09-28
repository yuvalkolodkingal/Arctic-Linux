package hw

import "sort"

// Fixtures are sample machines for the mock backend (`arcticd --mock --mock-hw NAME`),
// `arctic-install plan --hardware mock:NAME` and the tests. Names and ids are real
// (pci.ids 2026-09-25). Secure Boot is off in all of them; callers turn it on.
var Fixtures = map[string]Hardware{
	// A hybrid laptop: Intel Iris Xe draws the screen, an RTX 4060 renders on demand
	// (class 0302, no outputs), still on nouveau in the live system.
	"nvidia-laptop": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		intelIrisXe,
		{Slot: "0000:01:00.0", Vendor: VendorNVIDIA, Device: "28e0", SubVendor: "17aa", SubDevice: "3c6b", Class: "0302", Driver: "nouveau",
			Name: "AD107M [GeForce RTX 4060 Max-Q / Mobile]", VendorName: "NVIDIA Corporation"},
	}},
	// Intel graphics only (the ThinkPad X1 Carbon the mock's DMI names).
	"intel": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{intelIrisXe}},
	// A desktop whose screen is on an RTX 4060 (and its HDMI audio function).
	"nvidia-desktop": {CPUVendor: "AuthenticAMD", PCI: []PCIDevice{
		{Slot: "0000:01:00.0", Vendor: VendorNVIDIA, Device: "2882", SubVendor: "1462", SubDevice: "5156", Class: "0300", Driver: "nouveau", BootVGA: true,
			Name: "AD107 [GeForce RTX 4060]", VendorName: "NVIDIA Corporation"},
		{Slot: "0000:01:00.1", Vendor: VendorNVIDIA, Device: "22be", SubVendor: "1462", SubDevice: "5156", Class: "0403", Driver: "snd_hda_intel",
			Name: "AD107 High Definition Audio Controller", VendorName: "NVIDIA Corporation"},
	}},
	// Pascal: NVIDIA's 580 series is the last driver for it.
	"pascal": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		{Slot: "0000:01:00.0", Vendor: VendorNVIDIA, Device: "1c82", Class: "0300", Driver: "nouveau", BootVGA: true,
			Name: "GP107 [GeForce GTX 1050 Ti]", VendorName: "NVIDIA Corporation"},
	}},
	// Maxwell (GTX 970): also the 580 series.
	"maxwell": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		{Slot: "0000:01:00.0", Vendor: VendorNVIDIA, Device: "13c2", Class: "0300", Driver: "nouveau", BootVGA: true,
			Name: "GM204 [GeForce GTX 970]", VendorName: "NVIDIA Corporation"},
	}},
	// Kepler (GTX 680): only the 470 series drives it, which has no GBM (Mango can't run on
	// it), so nothing is offered and it stays on nouveau.
	"kepler": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		{Slot: "0000:01:00.0", Vendor: VendorNVIDIA, Device: "1180", Class: "0300", Driver: "nouveau", BootVGA: true,
			Name: "GK104 [GeForce GTX 680]", VendorName: "NVIDIA Corporation"},
	}},
	// An older MacBook: Haswell graphics and a BCM4360, which only Broadcom's wl drives.
	"broadcom-mac": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		{Slot: "0000:00:02.0", Vendor: VendorIntel, Device: "0a2e", Class: "0300", Driver: "i915", BootVGA: true,
			Name: "Haswell-ULT Integrated Graphics Controller", VendorName: "Intel Corporation"},
		{Slot: "0000:03:00.0", Vendor: VendorBroadcom, Device: "43a0", SubVendor: "106b", SubDevice: "0117", Class: "0280",
			Name: "BCM4360 802.11ac Dual Band Wireless Network Adapter", VendorName: "Broadcom Inc. and subsidiaries"},
	}},
	// An AMD-only desktop (Radeon RX 7900 and its HDMI audio).
	"amd": {CPUVendor: "AuthenticAMD", PCI: []PCIDevice{
		{Slot: "0000:03:00.0", Vendor: VendorAMD, Device: "744c", Class: "0300", Driver: "amdgpu", BootVGA: true,
			Name: "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]", VendorName: "Advanced Micro Devices, Inc. [AMD/ATI]"},
		{Slot: "0000:03:00.1", Vendor: VendorAMD, Device: "ab30", Class: "0403", Driver: "snd_hda_intel",
			Name: "Navi 31 HDMI/DP Audio", VendorName: "Advanced Micro Devices, Inc. [AMD/ATI]"},
	}},
	// A virtual machine (QEMU with virtio-gpu): nothing to offer.
	"vm": {CPUVendor: "GenuineIntel", PCI: []PCIDevice{
		{Slot: "0000:00:01.0", Vendor: "1af4", Device: "1050", SubVendor: "1af4", SubDevice: "1100", Class: "0300", Driver: "virtio-pci", BootVGA: true,
			Name: "Virtio 1.0 GPU", VendorName: "Red Hat, Inc."},
	}},
	// No PCI devices known at all.
	"none": {},
}

var intelIrisXe = PCIDevice{Slot: "0000:00:02.0", Vendor: VendorIntel, Device: "a7a0", SubVendor: "17aa", SubDevice: "3c6b", Class: "0300", Driver: "i915", BootVGA: true,
	Name: "Raptor Lake-P [Iris Xe Graphics]", VendorName: "Intel Corporation"}

// DefaultFixture is the mock backend's machine unless told otherwise.
const DefaultFixture = "nvidia-laptop"

// Fixture returns a copy of a named fixture (secureBoot sets SecureBoot).
func Fixture(name string, secureBoot bool) (Hardware, bool) {
	f, ok := Fixtures[name]
	if !ok {
		return Hardware{}, false
	}
	f.PCI = append([]PCIDevice(nil), f.PCI...)
	f.SecureBoot = secureBoot
	return f, true
}

// FixtureNames lists the fixtures, sorted.
func FixtureNames() []string {
	var out []string
	for k := range Fixtures {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}
