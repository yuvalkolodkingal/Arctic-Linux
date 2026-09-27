// Package mock is the development backend (`arcticd --mock`, `arctic-install bridge --mock`):
// fake disks, Wi-Fi and locale, and an install that takes about 40 seconds with realistic
// progress, status lines and one optional-app failure. It never touches the system.
package mock

import (
	"context"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Options tune the simulation.
type Options struct {
	// Speed divides every delay (1 = about 40 s for a default install; tests use 1000).
	Speed float64
	// FailModule is the optional app whose first download fails: "" picks Steam when it is
	// selected, else the last Flatpak that has to be downloaded; "none" disables the failure.
	FailModule string
	// FailCore makes the first install attempt fail fatally while copying (error screen).
	FailCore bool
	// Wired starts with a cable plugged in and online (network step is skipped).
	Wired bool
	// Firmware reported by Hello ("uefi" default).
	Firmware string
	// LogDir is where SaveLog writes (default os.TempDir()).
	LogDir string
}

// Backend is the mock backend.
type Backend struct {
	opts Options

	mu       sync.Mutex
	online   bool
	wired    bool
	ssid     string
	networks []protocol.WifiNetwork
	attempts int
	logLines []string
}

// New creates a mock backend.
func New(opts Options) *Backend {
	if opts.Speed <= 0 {
		opts.Speed = 1
	}
	if opts.Firmware == "" {
		opts.Firmware = "uefi"
	}
	b := &Backend{opts: opts, wired: opts.Wired, online: opts.Wired}
	b.networks = []protocol.WifiNetwork{
		{SSID: "Tundra-5G", Signal: 82, Secure: true},
		{SSID: "Snowfield", Signal: 64, Secure: true},
		{SSID: "Cafe Polar", Signal: 41, Secure: false},
		{SSID: "Aurora-Guest", Signal: 23, Secure: true},
	}
	return b
}

func (b *Backend) logf(format string, a ...any) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.logLines = append(b.logLines, time.Now().Format("15:04:05 ")+fmt.Sprintf(format, a...))
}

// Info implements backend.Backend.
func (b *Backend) Info() backend.Info {
	return backend.Info{Mock: true, Live: true, Firmware: b.opts.Firmware}
}

// Language implements backend.Backend.
func (b *Backend) Language() string { return "en_US.UTF-8" }

// DMI implements backend.Backend.
func (b *Backend) DMI() wizard.DMI {
	return wizard.DMI{Vendor: "LENOVO", Family: "ThinkPad X1 Carbon Gen 11", Product: "21HMCTO1WW"}
}

// Inventory is the fake machine: a 512 GB NVMe with Windows 11 and 180 GB free, a 1 TB SATA
// disk, and the USB stick the installer runs from.
func Inventory() []hw.Disk {
	mib := func(n int64) int64 { return n * hw.MiB }
	nvme := hw.Disk{
		Path: "/dev/nvme0n1", Model: "Samsung SSD 980", Serial: "S69ENF0R804412X", SizeBytes: 512_110_190_592, Transport: "nvme",
		PTType: "gpt", PTUUID: "5b6f0c61-3a2e-4d4b-9f1e-2c7d8e9a0b1c", SectorSize: 512, ExistingOS: []string{"Windows 11"},
		Partitions: []hw.Partition{
			{Path: "/dev/nvme0n1p1", Number: 1, StartByte: mib(1), SizeBytes: mib(100), Type: hw.TypeESP, FSType: "vfat", PartLabel: "EFI system partition"},
			{Path: "/dev/nvme0n1p2", Number: 2, StartByte: mib(101), SizeBytes: mib(16), Type: hw.TypeMSR, PartLabel: "Microsoft reserved partition"},
			{Path: "/dev/nvme0n1p3", Number: 3, StartByte: mib(117), SizeBytes: mib(314713), Type: hw.TypeMSData, FSType: "ntfs", Label: "Windows", PartLabel: "Basic data partition"},
			{Path: "/dev/nvme0n1p4", Number: 4, StartByte: mib(486491), SizeBytes: mib(750), Type: hw.TypeWinRE, FSType: "ntfs", PartLabel: "Windows RE"},
		},
		FreeRegions: []hw.Region{{StartByte: mib(314830), SizeBytes: mib(171661)}},
	}
	sata := hw.Disk{
		Path: "/dev/sda", Model: "WDC WD10EZEX", Serial: "WD-WCC6Y4KZ1234", SizeBytes: 1_000_204_886_016, Transport: "sata", Rotational: true,
		PTType: "gpt", SectorSize: 512,
		Partitions: []hw.Partition{
			{Path: "/dev/sda1", Number: 1, StartByte: mib(1), SizeBytes: 1_000_204_886_016 - mib(2), Type: hw.TypeLinux, FSType: "ext4", Label: "data"},
		},
	}
	usb := hw.Disk{
		Path: "/dev/sdb", Model: "SanDisk Ultra", Serial: "4C530001230512117284", SizeBytes: 30_752_000_000, Transport: "usb", Removable: true,
		InstallMedia: true, ReadOnly: false, PTType: "dos", SectorSize: 512,
		Partitions: []hw.Partition{
			{Path: "/dev/sdb1", Number: 1, StartByte: 0, SizeBytes: 2_000_000_000, Type: "0x0", FSType: "iso9660", Label: "Arctic-Linux-0.2"},
		},
	}
	return []hw.Disk{nvme, sata, usb}
}

// Disks implements backend.Backend.
func (b *Backend) Disks(ctx context.Context) ([]hw.Disk, error) { return Inventory(), nil }

// Network implements backend.Backend.
func (b *Backend) Network(ctx context.Context) protocol.NetworkState {
	b.mu.Lock()
	defer b.mu.Unlock()
	return protocol.NetworkState{Online: b.online, Wired: b.wired, SSID: b.ssid}
}

// ScanWifi implements backend.Backend.
func (b *Backend) ScanWifi(ctx context.Context) ([]protocol.WifiNetwork, error) {
	if err := b.sleep(ctx, 800*time.Millisecond); err != nil {
		return nil, err
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	out := append([]protocol.WifiNetwork{}, b.networks...)
	for i := range out {
		out[i].Connected = out[i].SSID == b.ssid
	}
	return out, nil
}

// ConnectWifi implements backend.Backend. Secured networks accept any password of 8+
// characters except "wrong password"; "Aurora-Guest" always times out.
func (b *Backend) ConnectWifi(ctx context.Context, ssid, password string) error {
	b.mu.Lock()
	var nw *protocol.WifiNetwork
	for i := range b.networks {
		if b.networks[i].SSID == ssid {
			nw = &b.networks[i]
		}
	}
	b.mu.Unlock()
	if nw == nil {
		return protocol.Errorf(protocol.CodeNotFound, "%s isn’t in range any more.", ssid)
	}
	if err := b.sleep(ctx, 1500*time.Millisecond); err != nil {
		return err
	}
	if ssid == "Aurora-Guest" {
		return protocol.Errorf(protocol.CodeTimeout, "%s didn’t answer. Move closer to the router and try again.", ssid)
	}
	if nw.Secure && (len(password) < 8 || password == "wrong password") {
		return protocol.Errorf(protocol.CodeAuth, "That password didn’t work for %s. Check it and try again.", ssid)
	}
	b.mu.Lock()
	b.ssid, b.online = ssid, true
	b.mu.Unlock()
	b.logf("connected to %s", ssid)
	return nil
}

// DetectTimezone implements backend.Backend (GeoIP answers only when online).
func (b *Backend) DetectTimezone(ctx context.Context) wizard.Detected {
	if b.Network(ctx).Online {
		return wizard.Detected{Timezone: "Asia/Jerusalem", Source: "network"}
	}
	return wizard.Detected{}
}

// SaveLog implements backend.Backend. The mock has no USB stick: it writes to LogDir (default
// the temp dir) and answers like the real backend does without a stick.
func (b *Backend) SaveLog(ctx context.Context) (protocol.SaveLogResult, error) {
	dir := b.opts.LogDir
	if dir == "" {
		dir = os.TempDir()
	}
	b.mu.Lock()
	content := "Arctic Linux installer (mock) log\n" + strings.Join(b.logLines, "\n") + "\n"
	b.mu.Unlock()
	path := filepath.Join(dir, fmt.Sprintf("arctic-install-mock-%d.log", os.Getpid()))
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return protocol.SaveLogResult{}, err
	}
	return protocol.SaveLogResult{Path: path, Message: backend.SavedLogMessage(protocol.SaveLogResult{Path: path})}, nil
}

// ApplyKeyboard implements backend.Backend (logged only).
func (b *Backend) ApplyKeyboard(ctx context.Context, x wizard.XKB) error {
	b.logf("keyboard for the live session: layout %s variant %q options %q", x.Layout, x.Variant, x.Options)
	return nil
}

// SystemNames implements backend.Backend: a few of the users and groups a Fedora image has.
func (b *Backend) SystemNames() []string {
	return []string{"root", "bin", "daemon", "adm", "wheel", "man", "video", "audio", "input", "render", "kvm", "sddm", "nixbld", "nixbld1"}
}

// Reboot implements backend.Backend (does nothing).
func (b *Backend) Reboot(ctx context.Context) error {
	b.logf("reboot requested (mock: ignored)")
	return nil
}

func (b *Backend) sleep(ctx context.Context, d time.Duration) error {
	t := time.NewTimer(time.Duration(float64(d) / b.opts.Speed))
	defer t.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-t.C:
		return nil
	}
}

// ticks runs n evenly spaced steps over d, calling fn with the fraction done.
func (b *Backend) ticks(ctx context.Context, d time.Duration, n int, fn func(frac float64)) error {
	for i := 1; i <= n; i++ {
		if err := b.sleep(ctx, d/time.Duration(n)); err != nil {
			return err
		}
		fn(float64(i) / float64(n))
	}
	return nil
}

// failTarget picks the module whose first download fails.
func (b *Backend) failTarget(c *catalog.Catalog, apps []*catalog.Module) string {
	switch b.opts.FailModule {
	case "none":
		return ""
	case "":
	default:
		return b.opts.FailModule
	}
	last := ""
	for _, m := range apps {
		if m.ID == "steam" {
			return "steam"
		}
		if !m.InLiveImage && m.Primary().Method == catalog.MethodFlatpak && m.Primary().Ref != "" {
			last = m.ID
		}
	}
	return last
}

// appDuration scales with what has to be downloaded (runtimes counted once).
func appDuration(c *catalog.Catalog, m *catalog.Module, seenRuntime map[string]bool) time.Duration {
	in := m.Primary()
	mb := in.DownloadMB
	if in.Runtime != "" && !seenRuntime[in.Runtime] {
		seenRuntime[in.Runtime] = true
		mb += c.Runtimes[in.Runtime]
	}
	secs := math.Max(1, math.Min(5, mb/160))
	return time.Duration(secs * float64(time.Second))
}

// Install implements backend.Backend: a scripted install of about 40 seconds.
func (b *Backend) Install(ctx context.Context, job *backend.Job, r backend.Reporter) error {
	b.mu.Lock()
	b.attempts++
	attempt := b.attempts
	b.mu.Unlock()
	c := job.Catalog
	apps := job.Apps()
	t := backend.NewTracker(r, len(apps), time.Duration(40*float64(time.Second)/b.opts.Speed), nil)
	b.logf("install attempt %d: disk %s (%s), encrypted=%v, %d apps", attempt, job.Disk.Path, job.Data.Disk.Mode, job.Data.Encryption.Enabled, len(apps))
	r.Logf("mock install: %d apps on %s", len(apps), job.Disk.Path)
	for _, m := range apps {
		r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModQueued})
	}

	t.Phase(protocol.PhaseDisk, wizard.StatusDisk)
	if err := b.ticks(ctx, 4*time.Second, 8, func(f float64) { t.Update(f, "") }); err != nil {
		return err
	}
	t.Phase(protocol.PhaseCopy, wizard.StatusCopy)
	failCore := b.opts.FailCore && attempt == 1
	if err := b.ticks(ctx, 10*time.Second, 25, func(f float64) {
		if !failCore || f <= 0.5 {
			t.Update(f, "")
		}
	}); err != nil {
		return err
	}
	if failCore {
		b.logf("copy failed (simulated)")
		return fmt.Errorf(`rsync: [receiver] write failed on "/mnt/usr/lib64/libLLVM.so.21": No space left on device (28)`)
	}
	t.Phase(protocol.PhaseConfigure, wizard.StatusSetup)
	if err := b.ticks(ctx, 3*time.Second, 6, func(f float64) { t.Update(f, "") }); err != nil {
		return err
	}
	t.Phase(protocol.PhaseBootloader, wizard.StatusBoot)
	if err := b.ticks(ctx, 3*time.Second, 6, func(f float64) { t.Update(f, "") }); err != nil {
		return err
	}

	// Apps: the diff against the live image.
	t.Phase(protocol.PhaseApps, "Installing your apps…")
	var removed []*catalog.Module
	for _, id := range c.Order {
		m := c.Modules[id]
		if m.InLiveImage && !m.Always && !job.Data.Apps.Selection.Contains(id) {
			removed = append(removed, m)
		}
	}
	if len(removed) > 0 {
		t.Update(0, wizard.StatusRemove)
		if err := b.sleep(ctx, time.Second); err != nil {
			return err
		}
		for _, m := range removed {
			b.logf("removed %s", m.ID)
		}
	}
	failID := b.failTarget(c, apps)
	seen := map[string]bool{}
	var total time.Duration
	durs := map[string]time.Duration{}
	for _, m := range apps {
		d := 200 * time.Millisecond
		if !m.InLiveImage {
			d = appDuration(c, m, seen)
		}
		durs[m.ID] = d
		total += d
	}
	var elapsed time.Duration
	for _, m := range apps {
		d := durs[m.ID]
		base := float64(elapsed) / float64(total)
		span := float64(d) / float64(total)
		if m.InLiveImage {
			if err := b.sleep(ctx, d); err != nil {
				return err
			}
			r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModInstalled, Percent: 100})
			t.AppDone()
			t.Update(base+span, "")
			elapsed += d
			continue
		}
		status := backend.InstallingStatus(c, m)
		failed := false
		for try := 0; ; try++ {
			t.Update(base, status)
			failNow := m.ID == failID && try == 0 && !failed
			err := b.ticks(ctx, d, 10, func(f float64) {
				if failNow && f > 0.6 {
					return
				}
				r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModDownloading, Percent: int(f * 100)})
				t.Update(base+span*f, "")
			})
			if err != nil {
				return err
			}
			if !failNow {
				r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModInstalled, Percent: 100})
				b.logf("installed %s", m.ID)
				break
			}
			failed = true
			r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: protocol.ModFailed, Percent: 60})
			t.Paused("Paused on " + m.Name)
			b.logf("%s: download failed (simulated)", m.ID)
			details := fmt.Sprintf("flatpak install --system -y flathub %s\nerror: Unable to connect to dl.flathub.org: Could not connect: Connection timed out", m.Primary().Ref)
			dec := r.Attention(ctx, backend.AttentionFor(m, "The download server didn’t answer.", details))
			if ctx.Err() != nil {
				return ctx.Err()
			}
			if dec == backend.Retry {
				b.logf("%s: retry", m.ID)
				continue
			}
			st := protocol.ModSkipped
			if dec == backend.Defer {
				st = protocol.ModDeferred
			}
			b.logf("%s: %s", m.ID, st)
			r.Module(protocol.ModuleEvent{ID: m.ID, Name: m.Name, Status: st, Percent: 0})
			status = "Installing your apps…"
			break
		}
		t.AppDone()
		elapsed += d
		t.Update(base+span, status)
	}
	// Hidden modules that are downloaded (codecs) finish quietly inside the apps phase.
	t.Update(1, "")

	t.Phase(protocol.PhaseFinalize, wizard.StatusAccount)
	if err := b.ticks(ctx, 2*time.Second, 4, func(f float64) { t.Update(f/2, "") }); err != nil {
		return err
	}
	t.Update(0.5, wizard.StatusTidy)
	if err := b.ticks(ctx, 2*time.Second, 4, func(f float64) { t.Update(0.5+f/2, "") }); err != nil {
		return err
	}
	t.Finish(wizard.StatusFinished)
	b.logf("install finished")
	return nil
}
