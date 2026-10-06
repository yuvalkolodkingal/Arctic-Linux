package mock

import (
	"context"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

func TestInventory(t *testing.T) {
	d := Inventory()
	if len(d) != 3 {
		t.Fatal(len(d))
	}
	nvme, sata, usb := d[0], d[1], d[2]
	if nvme.Label() != "Samsung SSD 980 · 512 GB" || !nvme.AlongsidePossible() || hw.SizeLabel(nvme.LargestFree().SizeBytes) != "180 GB" {
		t.Errorf("nvme %s free %s", nvme.Label(), hw.SizeLabel(nvme.LargestFree().SizeBytes))
	}
	if sata.Label() != "WDC WD10EZEX · 1 TB" || sata.AlongsidePossible() {
		t.Errorf("sata %s", sata.Label())
	}
	if !usb.InstallMedia || !usb.Removable {
		t.Errorf("usb %+v", usb)
	}
	if nvme.NextPartitionNumber() != 5 {
		t.Errorf("next partition %d", nvme.NextPartitionNumber())
	}
}

func TestFailTarget(t *testing.T) {
	c, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	b := New(Options{})
	sel := c.DefaultSelection()
	if got := b.failTarget(c, c.Apps(sel)); got != "" {
		t.Errorf("preloaded defaults must not simulate an app download failure: %q", got)
	}
	sel["office"] = []string{"collabora"}
	if got := b.failTarget(c, c.Apps(sel)); got != "collabora" {
		t.Errorf("optional office selection: %q, want the last flatpak (collabora)", got)
	}
	sel["gaming"] = []string{"steam"}
	sel["graphics"] = []string{"gimp"}
	if got := b.failTarget(c, c.Apps(sel)); got != "steam" {
		t.Errorf("with steam: %q", got)
	}
	if got := New(Options{FailModule: "none"}).failTarget(c, c.Apps(sel)); got != "" {
		t.Errorf("none: %q", got)
	}
}

func TestWifi(t *testing.T) {
	b := New(Options{Speed: 1000})
	ctx := context.Background()
	if b.Network(ctx).Online {
		t.Fatal("mock starts offline")
	}
	err := b.ConnectWifi(ctx, "Aurora-Guest", "whatever-long")
	if pe, ok := err.(*protocol.Error); !ok || pe.Code != protocol.CodeTimeout {
		t.Errorf("timeout: %v", err)
	}
	err = b.ConnectWifi(ctx, "Snowfield", "short")
	if pe, ok := err.(*protocol.Error); !ok || pe.Code != protocol.CodeAuth {
		t.Errorf("auth: %v", err)
	}
	if err := b.ConnectWifi(ctx, "Cafe Polar", ""); err != nil {
		t.Errorf("open network: %v", err)
	}
	n := b.Network(ctx)
	if !n.Online || n.SSID != "Cafe Polar" || n.Wired {
		t.Errorf("network %+v", n)
	}
	if New(Options{Wired: true}).Network(ctx) != (protocol.NetworkState{Online: true, Wired: true}) {
		t.Error("wired option")
	}
}
