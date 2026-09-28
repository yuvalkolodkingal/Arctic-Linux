package engine

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

// client is a scripted JSON-lines client over an in-memory pipe.
type client struct {
	t      *testing.T
	w      io.Writer
	nextID int
	mu     sync.Mutex
	resp   map[int]chan map[string]any
	events chan map[string]any
	log    *strings.Builder
}

func newClient(t *testing.T, e *Engine) (*client, func()) {
	t.Helper()
	inR, inW := io.Pipe()
	outR, outW := io.Pipe()
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		e.ServeConn(ctx, inR, outW)
		outW.Close()
	}()
	c := &client{t: t, w: inW, resp: map[int]chan map[string]any{}, events: make(chan map[string]any, 10000), log: &strings.Builder{}}
	go func() {
		sc := bufio.NewScanner(outR)
		sc.Buffer(make([]byte, 1<<20), 1<<22)
		for sc.Scan() {
			var m map[string]any
			if err := json.Unmarshal(sc.Bytes(), &m); err != nil {
				t.Errorf("bad line from engine: %s", sc.Text())
				continue
			}
			if id, ok := m["id"].(float64); ok {
				c.mu.Lock()
				ch := c.resp[int(id)]
				c.mu.Unlock()
				ch <- m
			} else {
				c.events <- m
			}
		}
	}()
	return c, func() { inW.Close(); cancel(); e.Close() }
}

func (c *client) call(method string, params any) (map[string]any, map[string]any) {
	c.t.Helper()
	c.mu.Lock()
	c.nextID++
	id := c.nextID
	ch := make(chan map[string]any, 1)
	c.resp[id] = ch
	c.mu.Unlock()
	req := map[string]any{"id": id, "method": method}
	if params != nil {
		req["params"] = params
	}
	b, _ := json.Marshal(req)
	fmt.Fprintf(c.w, "%s\n", b)
	select {
	case m := <-ch:
		res, _ := m["result"].(map[string]any)
		errObj, _ := m["error"].(map[string]any)
		return res, errObj
	case <-time.After(10 * time.Second):
		c.t.Fatalf("no response to %s", method)
		return nil, nil
	}
}

func (c *client) ok(method string, params any) map[string]any {
	c.t.Helper()
	res, err := c.call(method, params)
	if err != nil {
		c.t.Fatalf("%s %v: error %v", method, params, err)
	}
	return res
}

func (c *client) waitEvent(pred func(map[string]any) bool, timeout time.Duration) map[string]any {
	c.t.Helper()
	deadline := time.After(timeout)
	for {
		select {
		case ev := <-c.events:
			if pred(ev) {
				return ev
			}
		case <-deadline:
			c.t.Fatal("timed out waiting for event")
			return nil
		}
	}
}

func newEngine(t *testing.T, mopts mock.Options, unattended bool) *Engine {
	t.Helper()
	if mopts.Speed == 0 {
		mopts.Speed = 400
	}
	mopts.LogDir = t.TempDir()
	return newEngineWith(t, mock.New(mopts), unattended)
}

func newEngineWith(t *testing.T, b backend.Backend, unattended bool) *Engine {
	t.Helper()
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	logBuf := &strings.Builder{}
	e, err := New(b, Options{Catalog: cat, Log: &lockedWriter{w: logBuf}, Unattended: unattended})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if strings.Contains(logBuf.String(), "acid acorn") || strings.Contains(logBuf.String(), "winter-fox") {
			t.Errorf("secret leaked into the engine log:\n%s", logBuf.String())
		}
	})
	return e
}

type lockedWriter struct {
	mu sync.Mutex
	w  io.Writer
}

func (l *lockedWriter) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.w.Write(p)
}

// fullWizard walks every step through the protocol.
func fullWizard(t *testing.T, c *client) {
	t.Helper()
	h := c.ok("Hello", map[string]any{"client": "installer-ui", "version": 1})
	if h["mock"] != true || h["firmware"] != "uefi" || h["engine_version"] != "0.1.0" {
		t.Fatalf("hello %v", h)
	}
	c.ok("Subscribe", nil)
	w := c.ok("GetWizard", nil)
	if w["current"] != "welcome" || len(w["steps"].([]any)) != 11 {
		t.Fatalf("wizard %v", w)
	}
	for _, id := range []string{"welcome", "keyboard"} {
		s := c.ok("GetStep", map[string]any{"id": id})
		c.ok("SetStep", map[string]any{"id": id, "data": s["data"]})
		c.ok("Next", nil)
	}
	// Network: offline until we connect.
	if _, err := c.call("Next", nil); err == nil || err["code"] != "offline" {
		t.Fatalf("network Next offline: %v", err)
	}
	nets := c.ok("ScanWifi", nil)["networks"].([]any)
	if len(nets) != 4 {
		t.Fatalf("wifi %v", nets)
	}
	if _, err := c.call("ConnectWifi", map[string]any{"ssid": "Tundra-5G", "password": "wrong password"}); err == nil || err["code"] != "auth" {
		t.Fatalf("wrong password: %v", err)
	}
	c.ok("ConnectWifi", map[string]any{"ssid": "Tundra-5G", "password": "correct horse"})
	if ns := c.ok("NetworkState", nil); ns["online"] != true || ns["ssid"] != "Tundra-5G" {
		t.Fatalf("network %v", ns)
	}
	c.ok("Next", nil)
	tz := c.ok("GetStep", map[string]any{"id": "timezone"})
	det := tz["options"].(map[string]any)["detected"].(map[string]any)
	if det["city"] != "Jerusalem" || det["source"] != "network" || tz["data"].(map[string]any)["timezone"] != "Asia/Jerusalem" {
		t.Fatalf("timezone %v", tz)
	}
	c.ok("Next", nil)
	disk := c.ok("GetStep", map[string]any{"id": "disk"})
	disks := disk["options"].(map[string]any)["disks"].([]any)
	if len(disks) != 2 || disk["data"].(map[string]any)["disk"] != "/dev/nvme0n1" {
		t.Fatalf("disk %v", disk)
	}
	c.ok("SetStep", map[string]any{"id": "disk", "data": map[string]any{"disk": "/dev/nvme0n1", "mode": "erase"}})
	c.ok("Next", nil)
	// Encryption: weak passphrase, then a suggested one.
	if s := c.ok("CheckPassphrase", map[string]any{"text": "hunter2"}); s["label"] != "Too short" || s["ok"] != false {
		t.Fatalf("check %v", s)
	}
	c.ok("SetSecrets", map[string]any{"luks_passphrase": "aaaaaaaaaaaa"})
	if _, err := c.call("Next", nil); err == nil || err["fields"].(map[string]any)["passphrase"] == nil {
		t.Fatalf("weak passphrase accepted: %v", err)
	}
	sug := c.ok("SuggestPassphrase", nil)["text"].(string)
	if len(strings.Fields(sug)) != 4 {
		t.Fatalf("suggestion %q", sug)
	}
	c.ok("SetSecrets", map[string]any{"luks_passphrase": "acid acorn acre aged"})
	c.ok("Next", nil)
	// Account.
	if s := c.ok("SuggestAccount", map[string]any{"full_name": "Noa Levi"}); s["username"] != "noa" || s["hostname"] != "noa-thinkpad" {
		t.Fatalf("suggest %v", s)
	}
	set := c.ok("SetStep", map[string]any{"id": "account", "data": map[string]any{"full_name": "Noa Levi"}})
	if d := set["data"].(map[string]any); d["username"] != "noa" || d["hostname"] != "noa-thinkpad" {
		t.Fatalf("autofill %v", d)
	}
	if _, err := c.call("SetStep", map[string]any{"id": "account", "data": map[string]any{"username": "Noa!"}}); err == nil ||
		err["fields"].(map[string]any)["username"] != "Use lowercase letters, numbers, - and _." {
		t.Fatalf("bad username: %v", err)
	}
	c.ok("SetStep", map[string]any{"id": "account", "data": map[string]any{"username": "noa"}})
	c.ok("SetSecrets", map[string]any{"user_password": "winter-fox-2026"})
	c.ok("Next", nil)
	// Apps: add Steam so the mock fails it.
	apps := c.ok("GetStep", map[string]any{"id": "apps"})
	// The mock is an NVIDIA hybrid laptop: NVIDIA's and Intel's drivers are offered first,
	// ticked, and counted apart from the apps.
	if apps["note"] != "8 apps + 2 drivers · 3 GB download" {
		t.Fatalf("apps footer %v", apps["note"])
	}
	opts := apps["options"].(map[string]any)
	if cat0 := opts["categories"].([]any)[0].(map[string]any); cat0["id"] != "drivers" || cat0["hardware"] != true {
		t.Fatalf("first category %v", cat0)
	}
	if m0 := opts["modules"].([]any)[0].(map[string]any); m0["id"] != "nvidia" || m0["device"] != "NVIDIA GeForce RTX 4060 Max-Q / Mobile" || m0["default"] != true {
		t.Fatalf("first module %v", m0)
	}
	c.ok("SetStep", map[string]any{"id": "apps", "data": map[string]any{"selection": map[string]any{"extras": []string{"steam"}}}})
	est := c.ok("EstimateDownload", map[string]any{"selection": map[string]any{
		"browser": []string{"zen"}, "editor": []string{"zed"}, "terminal": []string{"kitty"}, "shell": []string{"zsh"},
		"files": []string{"yazi", "thunar"}, "office": []string{"collabora"}, "video": []string{"vlc"}, "extras": []string{"steam"}}})
	if est["apps"] != float64(9) {
		t.Fatalf("estimate %v", est)
	}
	c.ok("Next", nil)
	sum := c.ok("GetSummary", nil)
	rows := sum["rows"].([]any)
	if sum["primary_label"] != "Erase disk and install" || len(rows) != 8 {
		t.Fatalf("summary %v", sum)
	}
	if drv := rows[7].(map[string]any); drv["label"] != "Drivers" || drv["icon"] != "cpu" ||
		drv["value"] != "NVIDIA driver for your NVIDIA GeForce RTX 4060 Max-Q / Mobile; Intel video acceleration for your Intel Iris Xe Graphics. Secure Boot is on: you’ll confirm the driver’s key once after restarting" {
		t.Fatalf("drivers row %v", drv)
	}
	// Summary's primary button: Next moves to the install screen, Start begins.
	if w := c.ok("Next", nil); w["current"] != "install" {
		t.Fatalf("Next from summary: %v", w)
	}
	if _, err := c.call("Goto", map[string]any{"id": "done"}); err == nil {
		t.Fatal("Goto done must fail")
	}
}

func TestFullSessionWithAttention(t *testing.T) {
	e := newEngine(t, mock.Options{}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	if _, err := c.call("Start", nil); err == nil || err["code"] != "state" {
		t.Fatalf("second Start: %v", err)
	}
	att := c.waitEvent(func(m map[string]any) bool { return m["event"] == "attention" }, 20*time.Second)
	mod := att["module"].(map[string]any)
	if mod["id"] != "steam" || att["optional"] != true || att["skip_label"] != "Skip Steam" || att["title"] != "Steam couldn’t be downloaded" {
		t.Fatalf("attention %v", att)
	}
	if w := c.ok("GetWizard", nil); w["state"] != "attention" {
		t.Fatalf("wizard during attention %v", w)
	}
	if _, err := c.call("SkipModule", map[string]any{"id": "zed"}); err == nil {
		t.Fatal("skipping the wrong module must fail")
	}
	c.ok("SkipModule", map[string]any{"id": "steam"})
	done := c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
	if done["apps_installed"] != float64(8) || done["first_name"] != "Noa" {
		t.Fatalf("done %v", done)
	}
	drivers := done["drivers"].([]any)
	if len(drivers) != 2 || drivers[0].(map[string]any)["status"] != "installed" ||
		drivers[0].(map[string]any)["text"] != "The NVIDIA driver for your NVIDIA GeForce RTX 4060 Max-Q / Mobile starts once you’ve confirmed its key (below)." {
		t.Fatalf("done drivers %v", drivers)
	}
	sb := done["secure_boot"].(map[string]any)
	code, _ := sb["code"].(string)
	if len(code) != 8 || strings.Trim(code, "0123456789") != "" || !strings.Contains(sb["steps"].([]any)[2].(string), code) {
		t.Fatalf("secure boot %v", sb)
	}
	w := c.ok("GetWizard", nil)
	if w["current"] != "done" || w["state"] != "done" {
		t.Fatalf("wizard after done %v", w)
	}
	st := c.ok("GetStep", map[string]any{"id": "done"})
	if st["help"] != "Everything is installed, including 8 apps. Welcome aboard, Noa." {
		t.Fatalf("done help %v", st["help"])
	}
	if o := st["options"].(map[string]any); o["secure_boot"].(map[string]any)["code"] != code || len(o["drivers"].([]any)) != 2 {
		t.Fatalf("done step options %v", o)
	}
	states := map[string]string{}
	for _, m := range e.ModuleStates() {
		states[m.ID] = m.Status
	}
	if states["steam"] != "skipped" || states["zed"] != "installed" || states["kitty"] != "installed" {
		t.Fatalf("module states %v", states)
	}
	c.ok("Reboot", nil)
	if p := c.ok("SaveLog", nil)["path"].(string); !strings.HasSuffix(p, ".log") {
		t.Fatalf("log path %q", p)
	}
}

func TestRetryModule(t *testing.T) {
	e := newEngine(t, mock.Options{}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "attention" }, 20*time.Second)
	c.ok("RetryModule", map[string]any{"id": "steam"})
	done := c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
	if done["apps_installed"] != float64(9) {
		t.Fatalf("done %v", done)
	}
}

func TestProgressEvents(t *testing.T) {
	e := newEngine(t, mock.Options{FailModule: "none"}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	last := -1
	statuses := map[string]bool{}
	for {
		ev := c.waitEvent(func(m map[string]any) bool { return m["event"] == "progress" || m["event"] == "done" }, 30*time.Second)
		if ev["event"] == "done" {
			break
		}
		p := int(ev["percent"].(float64))
		if p < last {
			t.Fatalf("progress went backwards: %d after %d", p, last)
		}
		last = p
		statuses[ev["status"].(string)] = true
		if len(ev["substeps"].([]any)) != 4 {
			t.Fatalf("substeps %v", ev["substeps"])
		}
	}
	if last != 100 {
		t.Errorf("last percent %d", last)
	}
	for _, s := range []string{"Preparing the disk…", "Copying Arctic Linux…", "Installing Zed, your code editor…", "Installing Collabora Office, your office suite…", "Setting up your account…", "Almost there — tidying up…"} {
		if !statuses[s] {
			t.Errorf("missing status %q (got %v)", s, statuses)
		}
	}
}

func TestFatalFailureAndTryAgain(t *testing.T) {
	e := newEngine(t, mock.Options{FailCore: true, FailModule: "none"}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	f := c.waitEvent(func(m map[string]any) bool { return m["event"] == "failed" }, 20*time.Second)
	if f["fatal"] != true || !strings.Contains(f["details"].(string), "No space left") {
		t.Fatalf("failed %v", f)
	}
	if w := c.ok("GetWizard", nil); w["state"] != "failed" {
		t.Fatalf("state %v", w)
	}
	c.ok("Start", nil) // Try again
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
}

// After a fatal failure the person can go back, change answers and start again.
func TestFatalFailureBackAndChange(t *testing.T) {
	e := newEngine(t, mock.Options{FailCore: true, FailModule: "none"}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	f := c.waitEvent(func(m map[string]any) bool { return m["event"] == "failed" }, 20*time.Second)
	if f["can_change"] != true || !strings.Contains(f["message"].(string), "go back and change your choices") {
		t.Fatalf("failed %v", f)
	}
	if _, err := c.call("SetStep", map[string]any{"id": "disk", "data": map[string]any{"disk": "/dev/sda"}}); err == nil || err["code"] != "state" {
		t.Fatalf("SetStep while failed: %v", err)
	}
	// "Change" on the disk: leaves the failure for the wizard; every UI hears about it.
	w := c.ok("Goto", map[string]any{"id": "disk"})
	if w["state"] != "wizard" || w["current"] != "disk" {
		t.Fatalf("Goto disk after failure: %v", w)
	}
	ev := c.waitEvent(func(m map[string]any) bool { return m["event"] == "wizard" && m["state"] == "wizard" }, 5*time.Second)
	if ev["current"] != "disk" {
		t.Fatalf("wizard event %v", ev)
	}
	if h := c.ok("Hello", map[string]any{"client": "installer-ui"}); h["state"] != "wizard" {
		t.Fatalf("hello state %v", h)
	}
	if st := c.ok("GetStep", map[string]any{"id": "install"}); st["options"].(map[string]any)["failed"] != nil {
		t.Fatalf("the failure must be forgotten: %v", st["options"])
	}
	c.ok("SetStep", map[string]any{"id": "disk", "data": map[string]any{"disk": "/dev/sda", "mode": "erase"}})
	if w := c.ok("Next", nil); w["current"] != "summary" {
		t.Fatalf("Next after the change: %v", w)
	}
	if sum := c.ok("GetSummary", nil); !strings.Contains(sum["warning"].(string), "WDC WD10EZEX") {
		t.Fatalf("summary %v", sum)
	}
	c.ok("Next", nil)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
	if p := c.ok("SaveLog", nil); p["message"] == "" || p["on_usb"] != false {
		t.Fatalf("save log %v", p)
	}
}

// Back from a failure goes to Summary.
func TestFatalFailureBack(t *testing.T) {
	e := newEngine(t, mock.Options{FailCore: true, FailModule: "none"}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "failed" }, 20*time.Second)
	if w := c.ok("Back", nil); w["state"] != "wizard" || w["current"] != "summary" {
		t.Fatalf("Back after failure: %v", w)
	}
	// A UI that connects now sees the wizard, not the old failure.
	c2, stop2 := newClient(t, e)
	defer stop2()
	c2.ok("Subscribe", nil)
	select {
	case ev := <-c2.events:
		t.Fatalf("replayed %v after going back", ev)
	case <-time.After(100 * time.Millisecond):
	}
	c.ok("Next", nil)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
}

// diskSwapBackend is the mock with a disk inventory the test can change.
type diskSwapBackend struct {
	*mock.Backend
	mu    sync.Mutex
	disks []hw.Disk
}

func (b *diskSwapBackend) Disks(ctx context.Context) ([]hw.Disk, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return append([]hw.Disk{}, b.disks...), nil
}

func (b *diskSwapBackend) set(disks []hw.Disk) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.disks = disks
}

// Start re-probes: a different disk at the chosen path (or a changed partition table in
// alongside mode) is refused until the person looks at the Disk step again.
func TestStartRechecksTheDisk(t *testing.T) {
	b := &diskSwapBackend{Backend: mock.New(mock.Options{Speed: 400, FailModule: "none", LogDir: t.TempDir()}), disks: mock.Inventory()}
	e := newEngineWith(t, b, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	swapped := mock.Inventory()
	swapped[0].Model, swapped[0].Serial = "Other SSD", "OTHER123"
	b.set(swapped)
	if _, err := c.call("Start", nil); err == nil || err["code"] != "state" || !strings.Contains(err["message"].(string), "The disk changed") {
		t.Fatalf("Start with a swapped disk: %v", err)
	}
	if w := c.ok("GetWizard", nil); w["state"] != "wizard" {
		t.Fatalf("nothing may start: %v", w)
	}
	// Pressing the button again is not enough: the Disk step has to be seen again.
	if _, err := c.call("Start", nil); err == nil || !strings.Contains(err["message"].(string), "The disk changed") {
		t.Fatalf("second Start: %v", err)
	}
	c.ok("Goto", map[string]any{"id": "disk"})
	if st := c.ok("GetStep", map[string]any{"id": "disk"}); st["options"].(map[string]any)["disks"].([]any)[0].(map[string]any)["model"] != "Other SSD" {
		t.Fatalf("disk step %v", st["options"])
	}
	c.ok("Next", nil)
	if sum := c.ok("GetSummary", nil); !strings.Contains(sum["warning"].(string), "Other SSD") {
		t.Fatalf("summary after the probe %v", sum)
	}
	c.ok("Next", nil)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)

	// Alongside: the free space changed since the Summary.
	b2 := &diskSwapBackend{Backend: mock.New(mock.Options{Speed: 400, FailModule: "none", LogDir: t.TempDir()}), disks: mock.Inventory()}
	e2 := newEngineWith(t, b2, false)
	c2, stop2 := newClient(t, e2)
	defer stop2()
	fullWizard(t, c2)
	c2.ok("Goto", map[string]any{"id": "disk"})
	c2.ok("SetStep", map[string]any{"id": "disk", "data": map[string]any{"disk": "/dev/nvme0n1", "mode": "alongside"}})
	c2.ok("Next", nil)
	c2.ok("Next", nil)
	changed := mock.Inventory()
	changed[0].Partitions = append(changed[0].Partitions, hw.Partition{Path: "/dev/nvme0n1p5", Number: 5, StartByte: changed[0].FreeRegions[0].StartByte, SizeBytes: 10 * hw.GB, Type: hw.TypeLinux})
	changed[0].FreeRegions[0].StartByte += 10 * hw.GB
	changed[0].FreeRegions[0].SizeBytes -= 10 * hw.GB
	b2.set(changed)
	if _, err := c2.call("Start", nil); err == nil || !strings.Contains(err["message"].(string), "The disk changed") {
		t.Fatalf("Start with a changed table: %v", err)
	}
	// The disk vanished.
	b2.set(mock.Inventory()[1:])
	if _, err := c2.call("Start", nil); err == nil || !strings.Contains(err["message"].(string), "gone") {
		t.Fatalf("Start without the disk: %v", err)
	}
}

func TestUnattendedDefers(t *testing.T) {
	e := newEngine(t, mock.Options{FailModule: "zed"}, true)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	done := c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
	// The mock's retry succeeds, so unattended mode ends with everything installed.
	if done["apps_installed"] != float64(9) {
		t.Fatalf("done %v", done)
	}
}

func TestStartNeedsSummary(t *testing.T) {
	e := newEngine(t, mock.Options{}, false)
	c, stop := newClient(t, e)
	defer stop()
	if _, err := c.call("Start", nil); err == nil || err["code"] != "state" {
		t.Fatalf("Start before summary: %v", err)
	}
	if _, err := c.call("Bogus", nil); err == nil || err["code"] != "unknown_method" {
		t.Fatalf("unknown method: %v", err)
	}
	fmt.Fprintf(c.w, "not json\n")
	if _, err := c.call("GetStep", map[string]any{"id": 5}); err == nil || err["code"] != "bad_request" {
		t.Fatalf("bad params: %v", err)
	}
}

func TestSubscribeReplay(t *testing.T) {
	e := newEngine(t, mock.Options{FailModule: "none", Speed: 100}, false)
	c, stop := newClient(t, e)
	defer stop()
	fullWizard(t, c)
	c.ok("Start", nil)
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "module" }, 10*time.Second)
	// A second UI connects mid-install and gets the current state at once.
	c2, stop2 := newClient(t, e)
	defer stop2()
	c2.ok("Subscribe", nil)
	ev := c2.waitEvent(func(m map[string]any) bool { return true }, 5*time.Second)
	if ev["event"] != "progress" {
		t.Fatalf("first replayed event %v", ev)
	}
	st := c2.ok("GetStep", map[string]any{"id": "install"})
	if st["options"].(map[string]any)["modules"] == nil {
		t.Fatalf("install step options %v", st["options"])
	}
	c.waitEvent(func(m map[string]any) bool { return m["event"] == "done" }, 30*time.Second)
}

func TestHandleWithoutSession(t *testing.T) {
	e := newEngine(t, mock.Options{}, false)
	resp := e.Handle(context.Background(), nil, protocol.Request{Method: "Subscribe"})
	if resp.Error == nil {
		t.Fatal("Subscribe without a session must fail")
	}
}

// kbBackend records what the live session was told to use.
type kbBackend struct {
	*mock.Backend
	mu      sync.Mutex
	applied []wizard.XKB
}

func (b *kbBackend) ApplyKeyboard(ctx context.Context, x wizard.XKB) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.applied = append(b.applied, x)
	return nil
}

// A layout that is set is applied to the live session with the same layouts the installed
// system gets (us first for non-Latin layouts); a rejected one is not.
func TestKeyboardAppliedLive(t *testing.T) {
	b := &kbBackend{Backend: mock.New(mock.Options{Speed: 400, LogDir: t.TempDir()})}
	e := newEngineWith(t, b, false)
	c, stop := newClient(t, e)
	defer stop()
	res := c.ok("SetStep", map[string]any{"id": "keyboard", "data": map[string]any{"layout": "ru"}})
	x := res["data"].(map[string]any)["xkb"].(map[string]any)
	if x["layout"] != "us,ru" || x["options"] != "grp:alt_shift_toggle" || x["keymap"] != "ru" {
		t.Fatalf("xkb %v", x)
	}
	if _, err := c.call("SetStep", map[string]any{"id": "keyboard", "data": map[string]any{"layout": "xx"}}); err == nil {
		t.Fatal("unknown layout accepted")
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.applied) != 1 || b.applied[0].Layout != "us,ru" {
		t.Fatalf("applied %+v", b.applied)
	}
}
