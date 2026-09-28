// Command arctic-install is the engine's command-line side:
//
//	arctic-install bridge [--socket PATH] [--mock]      stdin/stdout <-> engine, JSON lines (the UI runs this)
//	arctic-install plan --profile FILE [--firmware uefi|bios] [--inventory mock|system]
//	                                                    print the install's command plan (dry run)
//	arctic-install unattended --profile FILE [--mock]   install from a profile (CI); secrets from
//	                                                    ARCTIC_LUKS_PASSPHRASE / ARCTIC_USER_PASSWORD
//	arctic-install catalog [--json]                     print the app catalog
//	arctic-install version
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"text/tabwriter"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/daemon"
	"github.com/yuvalkolodkingal/o-tism/internal/engine"
	"github.com/yuvalkolodkingal/o-tism/internal/host"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/installer"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/profile"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
	"github.com/yuvalkolodkingal/o-tism/profiles"
)

const usage = `usage:
  arctic-install bridge [--socket PATH] [--mock]
  arctic-install plan --profile FILE [--firmware uefi|bios] [--inventory mock|system]
                      [--hardware none|system|mock:NAME [--secure-boot]] [--offline]
  arctic-install unattended --profile FILE [--mock]
  arctic-install catalog [--json]
  arctic-install version
`

func main() {
	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, usage)
		os.Exit(2)
	}
	var code int
	switch os.Args[1] {
	case "bridge":
		code = cmdBridge(os.Args[2:])
	case "plan":
		code = cmdPlan(os.Args[2:], os.Stdout)
	case "unattended":
		code = cmdUnattended(os.Args[2:], os.Stdout)
	case "catalog":
		code = cmdCatalog(os.Args[2:], os.Stdout)
	case "version", "--version":
		fmt.Println("arctic-install", backend.EngineVersion)
	case "help", "-h", "--help":
		fmt.Print(usage)
	default:
		fmt.Fprintf(os.Stderr, "arctic-install: unknown command %q\n%s", os.Args[1], usage)
		code = 2
	}
	os.Exit(code)
}

func fail(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "arctic-install: "+format+"\n", a...)
	return 1
}

func mockFlags(fs *flag.FlagSet, cfg *daemon.Config) {
	fs.Float64Var(&cfg.MockOptions.Speed, "mock-speed", 1, "mock: divide every delay by this (env ARCTIC_MOCK_SPEED)")
	fs.StringVar(&cfg.MockOptions.FailModule, "mock-fail", "", "mock: app whose first download fails; \"none\" for none (env ARCTIC_MOCK_FAIL)")
	fs.BoolVar(&cfg.MockOptions.Wired, "mock-wired", false, "mock: start online on a cable (env ARCTIC_MOCK_WIRED=1)")
	fs.StringVar(&cfg.MockOptions.Hardware, "mock-hw", "", "mock: hardware fixture, default nvidia-laptop (env ARCTIC_MOCK_HW)")
	fs.BoolVar(&cfg.MockOptions.NoSecureBoot, "mock-no-secureboot", false, "mock: Secure Boot off (env ARCTIC_MOCK_SECUREBOOT=0)")
	fs.StringVar(&cfg.CatalogDir, "catalog", "", "catalog directory (default: packaged, else embedded)")
	fs.StringVar(&cfg.LogPath, "log", "", "engine log file, - for stderr")
}

// ---- bridge ----

func cmdBridge(args []string) int {
	fs := flag.NewFlagSet("bridge", flag.ContinueOnError)
	var cfg daemon.Config
	socket := fs.String("socket", daemon.DefaultSocket, "engine socket")
	fs.BoolVar(&cfg.Mock, "mock", false, "run a mock engine in this process instead of connecting")
	mockFlags(fs, &cfg)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	cfg.Env()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if cfg.Mock {
		e, closeFn, err := daemon.NewEngine(cfg)
		if err != nil {
			return bridgeFailed(err.Error())
		}
		defer closeFn()
		done := make(chan error, 1)
		go func() { done <- e.ServeConn(ctx, os.Stdin, os.Stdout) }()
		select {
		case err := <-done:
			if err != nil && !errors.Is(err, context.Canceled) {
				return fail("bridge: %v", err)
			}
		case <-ctx.Done(): // SIGTERM from the UI: stop the in-process engine and leave
		}
		return 0
	}
	var conn net.Conn
	var err error
	deadline := time.Now().Add(5 * time.Second)
	for {
		conn, err = net.Dial("unix", *socket)
		if err == nil {
			break
		}
		if time.Now().After(deadline) {
			return bridgeFailed(fmt.Sprintf("Couldn’t reach the installer engine at %s: %v", *socket, err))
		}
		time.Sleep(200 * time.Millisecond)
	}
	defer conn.Close()
	done := make(chan struct{})
	go func() {
		io.Copy(conn, os.Stdin)
		if uc, ok := conn.(*net.UnixConn); ok {
			uc.CloseWrite()
		}
	}()
	go func() {
		io.Copy(os.Stdout, conn)
		close(done)
	}()
	select {
	case <-done:
	case <-ctx.Done():
	}
	return 0
}

// bridgeFailed tells the UI (which only reads stdout) that there is no engine.
func bridgeFailed(details string) int {
	b, _ := json.Marshal(protocol.FailedEvent{Event: protocol.EventFailed, Title: "The installer couldn’t start",
		Message: "The installer engine isn’t running. Restart the computer from the USB stick and try again.", Details: details, Fatal: true})
	fmt.Println(string(b))
	fmt.Fprintln(os.Stderr, "arctic-install bridge:", details)
	return 1
}

// ---- profiles ----

func loadProfile(path string) (*profile.Profile, error) {
	p, err := profile.Load(path)
	if err == nil || !errors.Is(err, fs.ErrNotExist) {
		return p, err
	}
	// Fall back to the packaged and embedded copies ("profiles/ci/default.toml", "defaults.toml").
	rel := strings.TrimPrefix(filepath.ToSlash(path), "profiles/")
	if p2, err2 := profile.Load(filepath.Join("/usr/share/arctic/profiles", rel)); err2 == nil {
		return p2, nil
	}
	if data, err2 := profiles.FS.ReadFile(rel); err2 == nil {
		return profile.Parse(data)
	}
	return nil, err
}

// ---- plan ----

type quietReporter struct{}

func (quietReporter) Progress(protocol.ProgressEvent) {}
func (quietReporter) Module(protocol.ModuleEvent)     {}
func (quietReporter) Attention(context.Context, protocol.AttentionEvent) backend.Decision {
	return backend.Skip
}
func (quietReporter) Logf(string, ...any) {}

func cmdPlan(args []string, out io.Writer) int {
	fs := flag.NewFlagSet("plan", flag.ContinueOnError)
	profilePath := fs.String("profile", "", "profile file (required)")
	firmware := fs.String("firmware", "", "uefi or bios (default: uefi for the mock inventory, else this machine's)")
	inventory := fs.String("inventory", "", "mock (the fake machine) or system (probe this machine read-only); default: system on the live ISO, else mock")
	catalogDir := fs.String("catalog", "", "catalog directory")
	target := fs.String("target", "/mnt", "mount point for the new system")
	hardware := fs.String("hardware", "", "driver detection: none, system (this machine's PCI devices and Secure Boot) or mock:NAME ("+strings.Join(hw.FixtureNames(), ", ")+"); default: system with --inventory system, else none")
	secureBoot := fs.Bool("secure-boot", false, "with --hardware mock:NAME: Secure Boot on")
	offline := fs.Bool("offline", false, "plan as if there were no internet connection (drivers are put off to first boot)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *profilePath == "" {
		return fail("plan: --profile is required")
	}
	p, err := loadProfile(*profilePath)
	if err != nil {
		return fail("plan: %v", err)
	}
	cat, where, err := daemon.LoadCatalog(*catalogDir)
	if err != nil {
		return fail("plan: catalog %s: %v", where, err)
	}
	inv := *inventory
	if inv == "" {
		inv = "mock"
		if host.IsLive() {
			inv = "system"
		}
	}
	var disks []hw.Disk
	var model string
	switch inv {
	case "mock":
		m := mock.New(mock.Options{})
		disks, _ = m.Disks(context.Background())
		model = wizard.ModelName(m.DMI())
		if *firmware == "" {
			*firmware = "uefi"
		}
	case "system":
		h := host.New(host.Options{})
		disks, err = h.Disks(context.Background())
		if err != nil {
			return fail("plan: probing disks: %v", err)
		}
		model = wizard.ModelName(h.DMI())
		if *firmware == "" {
			*firmware = host.Firmware()
		}
	default:
		return fail("plan: --inventory must be mock or system")
	}
	if *firmware != "uefi" && *firmware != "bios" {
		return fail("plan: --firmware must be uefi or bios")
	}
	hwName := *hardware
	if hwName == "" {
		hwName = "none"
		if inv == "system" {
			hwName = "system"
		}
	}
	var machine hw.Hardware
	switch {
	case hwName == "none":
	case hwName == "system":
		machine = host.ProbeHardware("/")
	case strings.HasPrefix(hwName, "mock:"):
		var ok bool
		if machine, ok = hw.Fixture(strings.TrimPrefix(hwName, "mock:"), *secureBoot); !ok {
			return fail("plan: no hardware fixture %q (have %s)", hwName, strings.Join(hw.FixtureNames(), ", "))
		}
	default:
		return fail("plan: --hardware must be none, system or mock:NAME")
	}
	var found []string
	for _, m := range cat.MarkDetected(machine) {
		found = append(found, m.ID+" ("+m.Device+")")
	}
	data, disk, err := p.Data(cat, disks, model)
	if err != nil {
		return fail("plan: %v", err)
	}
	fmt.Fprintf(out, "# arctic-install plan — dry run: nothing below is executed.\n")
	fmt.Fprintf(out, "# profile: %s (%s)\n# inventory: %s · firmware: %s · catalog: %s\n", *profilePath, p.Description, inv, *firmware, where)
	fmt.Fprintf(out, "# secrets are never printed: the disk passphrase reaches cryptsetup on stdin, the password is\n# hashed in Go (SHA-512 crypt) and redacted here.\n")
	if hwName != "none" {
		fmt.Fprintf(out, "# hardware: %s\n# drivers offered: %s\n", machine.Summary(), strings.Join(found, ", "))
	}
	job := &backend.Job{Data: data, Disk: disk, Firmware: *firmware, Catalog: cat, LogPath: daemon.DefaultLogPath,
		Secrets: &backend.Secrets{LUKS: []byte("dry-run"), Password: []byte("dry-run")}, Hardware: machine, Offline: *offline}
	if job.NeedsMOK() {
		job.MOKCode = "00000000" // dry run: only its hash is used, and never printed
	}
	if !data.Encryption.Enabled {
		job.Secrets.LUKS = nil
	}
	rec := &installer.Recorder{Out: out}
	if err := installer.New(rec, job, quietReporter{}, installer.Options{Target: *target}).Run(context.Background()); err != nil {
		return fail("plan: %v", err)
	}
	return 0
}

// ---- unattended ----

func cmdUnattended(args []string, out io.Writer) int {
	fs := flag.NewFlagSet("unattended", flag.ContinueOnError)
	var cfg daemon.Config
	profilePath := fs.String("profile", "", "profile file (required)")
	fs.BoolVar(&cfg.Mock, "mock", false, "run against the mock backend (nothing is touched)")
	fs.StringVar(&cfg.TestHardware, "test-hardware", "", "VM tests: detect this hardware fixture's PCI devices ("+strings.Join(hw.FixtureNames(), ", ")+") instead of the real ones, so its drivers are installed and built")
	fs.BoolVar(&cfg.TestOnline, "test-online", false, "VM tests: treat the network as online (the guest reaches the mirrors through a proxy that NetworkManager's check can't see)")
	mockFlags(fs, &cfg)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *profilePath == "" {
		return fail("unattended: --profile is required")
	}
	if cfg.TestHardware != "" {
		if _, ok := hw.Fixture(cfg.TestHardware, false); !ok {
			return fail("unattended: unknown --test-hardware %q (%s)", cfg.TestHardware, strings.Join(hw.FixtureNames(), ", "))
		}
	}
	p, err := loadProfile(*profilePath)
	if err != nil {
		return fail("unattended: %v", err)
	}
	luks, password := os.Getenv("ARCTIC_LUKS_PASSPHRASE"), os.Getenv("ARCTIC_USER_PASSWORD")
	encrypt := p.Encryption.Enabled == nil || *p.Encryption.Enabled
	if encrypt && luks == "" {
		return fail("unattended: set ARCTIC_LUKS_PASSPHRASE (the profile turns encryption on)")
	}
	if password == "" {
		return fail("unattended: set ARCTIC_USER_PASSWORD")
	}
	if !cfg.Mock && os.Geteuid() != 0 {
		return fail("unattended: must run as root (or use --mock)")
	}
	cfg.Unattended = true
	if cfg.Mock {
		cfg.MockOptions.Wired = true
	}
	cfg.Env()
	e, closeFn, err := daemon.NewEngine(cfg)
	if err != nil {
		return fail("unattended: %v", err)
	}
	defer closeFn()
	events := make(chan any, 4096)
	e.AddListener(func(ev any) {
		select {
		case events <- ev:
		default:
		}
	})
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	u := &unattended{e: e, ctx: ctx, out: out}
	mode := "real"
	if cfg.Mock {
		mode = "mock"
	}
	fmt.Fprintf(out, "arctic-install: unattended install from %s (%s)\n", *profilePath, mode)
	if err := u.walk(p, luks, password); err != nil {
		return fail("unattended: %v", err)
	}
	if _, err := u.call(protocol.MethodStart, nil); err != nil {
		return fail("unattended: Start: %v", err)
	}
	return u.follow(events)
}

type unattended struct {
	e   *engine.Engine
	ctx context.Context
	out io.Writer
}

func (u *unattended) call(method string, params any) (any, error) {
	var raw json.RawMessage
	if params != nil {
		b, err := json.Marshal(params)
		if err != nil {
			return nil, err
		}
		raw = b
	}
	resp := u.e.Handle(u.ctx, nil, protocol.Request{ID: json.RawMessage("1"), Method: method, Params: raw})
	if resp.Error != nil {
		return nil, resp.Error
	}
	return resp.Result, nil
}

func (u *unattended) current() (string, error) {
	r, err := u.call(protocol.MethodGetWizard, nil)
	if err != nil {
		return "", err
	}
	return r.(protocol.WizardResult).Current, nil
}

func (u *unattended) walk(p *profile.Profile, luks, password string) error {
	encrypt := p.Encryption.Enabled == nil || *p.Encryption.Enabled
	for i := 0; i < 20; i++ {
		cur, err := u.current()
		if err != nil {
			return err
		}
		if cur == wizard.StepSummary {
			break
		}
		data := map[string]any{}
		switch cur {
		case wizard.StepWelcome:
			if p.Welcome.Language != "" {
				data["language"] = p.Welcome.Language
			}
		case wizard.StepKeyboard:
			if p.Keyboard.Layout != "" {
				data["layout"], data["variant"] = p.Keyboard.Layout, p.Keyboard.Variant
			}
		case wizard.StepTimezone:
			if p.Timezone.Timezone != "" {
				data["timezone"] = p.Timezone.Timezone
			}
			if p.Timezone.AutoTime != nil {
				data["auto_time"] = *p.Timezone.AutoTime
			}
		case wizard.StepDisk:
			if p.Disk.Mode != "" {
				data["mode"] = p.Disk.Mode
			}
			disk := p.Disk.Disk
			if disk == "" && p.Disk.Mode == wizard.ModeAlongside {
				r, err := u.call(protocol.MethodGetStep, protocol.IDParams{ID: wizard.StepDisk})
				if err != nil {
					return err
				}
				for _, o := range r.(protocol.StepResult).Options.(map[string]any)["disks"].([]wizard.DiskOption) {
					if o.AlongsidePossible {
						disk = o.Path
						break
					}
				}
			}
			if disk != "" {
				data["disk"] = disk
			}
		case wizard.StepEncryption:
			data["enabled"] = encrypt
			if encrypt {
				if _, err := u.call(protocol.MethodSetSecrets, protocol.SetSecretsParams{LUKSPassphrase: &luks}); err != nil {
					return err
				}
			}
		case wizard.StepAccount:
			data["full_name"] = p.Account.FullName
			if p.Account.Username != "" {
				data["username"] = p.Account.Username
			}
			if p.Account.Hostname != "" {
				data["hostname"] = p.Account.Hostname
			}
			data["autologin"] = p.Account.Autologin
			if _, err := u.call(protocol.MethodSetSecrets, protocol.SetSecretsParams{UserPassword: &password}); err != nil {
				return err
			}
		case wizard.StepApps:
			if len(p.Apps) > 0 {
				data["selection"] = p.Apps
			}
		}
		if len(data) > 0 {
			res, err := u.call(protocol.MethodSetStep, map[string]any{"id": cur, "data": data})
			if err != nil {
				return fmt.Errorf("%s: %v", cur, err)
			}
			b, _ := json.Marshal(res.(protocol.SetStepResult).Data)
			fmt.Fprintf(u.out, "  %-10s %s\n", cur, b)
		}
		if _, err := u.call(protocol.MethodNext, nil); err != nil {
			return fmt.Errorf("%s: %v", cur, err)
		}
	}
	r, err := u.call(protocol.MethodGetSummary, nil)
	if err != nil {
		return err
	}
	sum := r.(protocol.SummaryResult)
	fmt.Fprintln(u.out, "Summary:")
	for _, row := range sum.Rows {
		fmt.Fprintf(u.out, "  %-22s %s\n", row.Label+":", row.Value)
	}
	fmt.Fprintf(u.out, "  %s\n  → %s\n", sum.Warning, sum.PrimaryLabel)
	return nil
}

func (u *unattended) follow(events <-chan any) int {
	lastStatus := ""
	for {
		select {
		case <-u.ctx.Done():
			return fail("interrupted")
		case ev := <-events:
			switch x := ev.(type) {
			case protocol.ProgressEvent:
				if x.Status != lastStatus {
					lastStatus = x.Status
					fmt.Fprintf(u.out, "[%3d%%] %s\n", x.Percent, x.Status)
				}
			case protocol.ModuleEvent:
				if x.Status != protocol.ModDownloading && x.Status != protocol.ModQueued {
					fmt.Fprintf(u.out, "       %s: %s\n", x.ID, x.Status)
				}
			case protocol.AttentionEvent:
				fmt.Fprintf(u.out, "       %s: %s\n", x.Title, x.Message)
			case protocol.FailedEvent:
				fmt.Fprintf(u.out, "FAILED: %s\n%s\n", x.Title, x.Details)
				return 1
			case protocol.DoneEvent:
				fmt.Fprintf(u.out, "Done: %s %s\n", x.Title, x.Help)
				if len(x.Deferred) > 0 {
					fmt.Fprintf(u.out, "Deferred to first boot: %s\n", strings.Join(x.Deferred, ", "))
				}
				for _, d := range x.Drivers {
					fmt.Fprintf(u.out, "Driver %s: %s\n", d.ID, d.Text)
				}
				// The one-time code is only ever shown to whoever runs the install.
				if sb := x.SecureBoot; sb != nil {
					fmt.Fprintf(u.out, "%s\n%s\n", sb.Title, sb.Intro)
					for i, st := range sb.Steps {
						fmt.Fprintf(u.out, "  %d. %s\n", i+1, st)
					}
				}
				return 0
			}
		}
	}
}

// ---- catalog ----

func cmdCatalog(args []string, out io.Writer) int {
	fs := flag.NewFlagSet("catalog", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print JSON (every module with its install methods)")
	dir := fs.String("catalog", "", "catalog directory")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	cat, where, err := daemon.LoadCatalog(*dir)
	if err != nil {
		return fail("catalog %s: %v", where, err)
	}
	if *asJSON {
		mods := make([]*catalog.Module, 0, len(cat.Order))
		for _, id := range cat.Order {
			mods = append(mods, cat.Modules[id])
		}
		def := cat.DefaultSelection()
		doc := map[string]any{
			"source": where, "nixpkgs": cat.Nixpkgs, "categories": cat.Categories, "runtimes": cat.Runtimes,
			"modules": mods, "defaults": def, "estimate": cat.EstimateDownload(def),
		}
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		if err := enc.Encode(doc); err != nil {
			return fail("catalog: %v", err)
		}
		return 0
	}
	tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	fmt.Fprintln(tw, "CATEGORY\tID\tNAME\tSOURCE\tDEFAULT\tLIVE\tDOWNLOAD")
	for _, id := range cat.Order {
		m := cat.Modules[id]
		flags := ""
		if m.Default {
			flags = "yes"
		}
		if m.Always {
			flags = "always"
		}
		live := ""
		if m.InLiveImage {
			live = "yes"
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", m.Category, m.ID, m.Name, catalog.SourceLabel(m.Primary()), flags, live, hw.DownloadLabel(int64(m.DownloadMB()*hw.MB)))
	}
	tw.Flush()
	fmt.Fprintf(out, "\nDefaults: %s (catalog: %s)\n", cat.EstimateDownload(cat.DefaultSelection()).Label, where)
	return 0
}
