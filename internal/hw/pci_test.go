package hw

import (
	"strings"
	"testing"
)

func TestParsePCIIDs(t *testing.T) {
	ids := ParsePCIIDs(strings.NewReader("# comment\n10de  NVIDIA Corporation\n\t1C82  GP107 [GeForce GTX 1050 Ti]\n\t\t1043 85cd  subsystem\n14e4  Broadcom Inc. and subsidiaries\n\t43a0  BCM4360 802.11ac Dual Band Wireless Network Adapter\nC 03  Display controller\n\t00  VGA compatible controller\n"))
	if ids["10de"] != "NVIDIA Corporation" || ids["10de:1c82"] != "GP107 [GeForce GTX 1050 Ti]" || ids["14e4:43a0"] == "" {
		t.Errorf("ids %v", ids)
	}
	if _, ok := ids["1043:85cd"]; ok || len(ids) != 4 {
		t.Errorf("subsystems or classes parsed: %v", ids)
	}
}

func TestLabels(t *testing.T) {
	for _, c := range []struct {
		p    PCIDevice
		want string
	}{
		{PCIDevice{Vendor: "10de", Device: "28e0", Class: "0302", Name: "AD107M [GeForce RTX 4060 Max-Q / Mobile]"}, "NVIDIA GeForce RTX 4060 Max-Q / Mobile"},
		{PCIDevice{Vendor: "8086", Device: "a7a0", Class: "0300", Name: "Raptor Lake-P [Iris Xe Graphics]"}, "Intel Iris Xe Graphics"},
		{PCIDevice{Vendor: "1002", Device: "744c", Class: "0300", Name: "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]"}, "AMD Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M"},
		{PCIDevice{Vendor: "14e4", Device: "43a0", Class: "0280", Name: "BCM4360 802.11ac Dual Band Wireless Network Adapter"}, "Broadcom BCM4360 Wi-Fi"},
		{PCIDevice{Vendor: "10de", Device: "2d04", Class: "0300"}, "NVIDIA graphics card (10de:2d04)"},
		{PCIDevice{Vendor: "14e4", Device: "4365", Class: "0280"}, "Broadcom Wi-Fi card (14e4:4365)"},
		{PCIDevice{Vendor: "abcd", Device: "0001", Class: "0300", VendorName: "Acme, Inc.", Name: "Rocket GPU"}, "Acme Rocket GPU"},
	} {
		if got := c.p.Label(); got != c.want {
			t.Errorf("%+v: %q, want %q", c.p, got, c.want)
		}
	}
}

func TestFixtures(t *testing.T) {
	for _, name := range FixtureNames() {
		h, _ := Fixture(name, true)
		if !h.SecureBoot {
			t.Errorf("%s: secure boot not set", name)
		}
		for _, p := range h.PCI {
			if !IsHex4(p.Vendor) || !IsHex4(p.Device) || len(p.Class) != 4 || p.Slot == "" || strings.ToLower(p.Device) != p.Device {
				t.Errorf("%s: bad device %+v", name, p)
			}
		}
	}
	h, _ := Fixture(DefaultFixture, false)
	boot, ok := h.BootDisplay()
	if !ok || boot.Vendor != VendorIntel || len(h.Displays()) != 2 {
		t.Errorf("default fixture: boot %+v", boot)
	}
	// Fixture returns a copy.
	h.PCI[0].Device = "ffff"
	if again, _ := Fixture(DefaultFixture, false); again.PCI[0].Device == "ffff" {
		t.Error("fixture shared")
	}
	if s := h.Summary(); !strings.Contains(s, "0000:01:00.0 10de:28e0 class 0302 (nouveau)") || !strings.Contains(s, "Secure Boot off") {
		t.Errorf("summary %q", s)
	}
}
