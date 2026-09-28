package wizard

import (
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

func newHWTest(t *testing.T, fixture string, secureBoot bool) *Wizard {
	t.Helper()
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	h, _ := hw.Fixture(fixture, secureBoot)
	cat.MarkDetected(h)
	env := &fakeEnv{cat: cat, disks: testDisks(), firmware: "uefi", names: map[string]bool{}, hw: h}
	return New(env, "en_US.UTF-8")
}

func driversRow(w *Wizard) (protocol.SummaryRow, bool) {
	for _, r := range w.Summary().Rows {
		if r.Label == "Drivers" {
			return r, true
		}
	}
	return protocol.SummaryRow{}, false
}

func TestSummaryDriversRow(t *testing.T) {
	w := newHWTest(t, "nvidia-laptop", true)
	r, ok := driversRow(w)
	if !ok || r.Step != StepApps || r.Icon != "cpu" || !strings.HasSuffix(r.Value, "Secure Boot is on: you’ll confirm the driver’s key once after restarting") {
		t.Fatalf("row %+v", r)
	}
	// The Apps row doesn't list drivers.
	for _, row := range w.Summary().Rows {
		if row.Label == "Apps" && strings.Contains(row.Value, "NVIDIA") {
			t.Errorf("apps row %q", row.Value)
		}
	}
	// Only the media driver (no akmod): no key to confirm.
	w.Data.Apps.Selection["drivers"] = []string{"intel-media"}
	if r, _ := driversRow(w); strings.Contains(r.Value, "Secure Boot") || r.Value != "Intel video acceleration for your Intel Iris Xe Graphics" {
		t.Errorf("row %q", r.Value)
	}
	w.Data.Apps.Selection["drivers"] = []string{}
	if r, _ := driversRow(w); !strings.HasPrefix(r.Value, "None") {
		t.Errorf("row %q", r.Value)
	}
	// Secure Boot off: no key.
	w = newHWTest(t, "nvidia-laptop", false)
	if r, _ := driversRow(w); strings.Contains(r.Value, "Secure Boot") {
		t.Errorf("row %q", r.Value)
	}
	// Nothing detected: no row.
	if _, ok := driversRow(newHWTest(t, "vm", true)); ok {
		t.Error("drivers row without drivers")
	}
}

func TestNetworkDriverHint(t *testing.T) {
	w := newHWTest(t, "broadcom-mac", false)
	res, _ := w.Get(StepNetwork)
	hint, _ := res.Options.(map[string]any)["driver_hint"].(string)
	if !strings.HasPrefix(hint, "Your Broadcom BCM4360 Wi-Fi needs Broadcom’s driver") {
		t.Errorf("hint %q", hint)
	}
	res, _ = newHWTest(t, "nvidia-laptop", false).Get(StepNetwork)
	if _, ok := res.Options.(map[string]any)["driver_hint"]; ok {
		t.Error("hint without a Wi-Fi driver")
	}
}

func TestDoneDriverCopy(t *testing.T) {
	w := newHWTest(t, "nvidia-laptop", true)
	nv := w.env.Catalog().Modules["nvidia"]
	sb := SecureBootSteps("12345678", false)
	w.SetDriverResults([]protocol.DriverResult{DriverResult(nv, protocol.DriverInstalled, true)}, sb)
	w.Finish(8)
	res, _ := w.Get(StepDone)
	opts := res.Options.(map[string]any)
	drv := opts["drivers"].([]protocol.DriverResult)
	if drv[0].Text != "The NVIDIA driver for your NVIDIA GeForce RTX 4060 Max-Q / Mobile starts once you’ve confirmed its key (below)." {
		t.Errorf("text %q", drv[0].Text)
	}
	if opts["secure_boot"].(*protocol.SecureBootInfo).Code != "12345678" || !strings.Contains(sb.Steps[2], "12345678") {
		t.Errorf("secure boot %+v", opts["secure_boot"])
	}
	if later := SecureBootSteps("12345678", true); !strings.HasPrefix(later.Steps[0], "Restart once the driver is installed") {
		t.Errorf("later %+v", later)
	}
	if d := DriverResult(nv, protocol.DriverDeferred, false); !strings.Contains(d.Text, "first time Arctic Linux is online") {
		t.Errorf("deferred %q", d.Text)
	}
	if d := DriverResult(nv, "weird", false); d.Status != protocol.DriverSkipped {
		t.Errorf("skipped %+v", d)
	}
	if f := SecureBootFailed(); !f.Failed || f.Code != "" || !strings.Contains(f.Steps[0], MOKKeyPath) {
		t.Errorf("failed %+v", f)
	}
}
