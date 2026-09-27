// Package engine is the installer engine: it owns the wizard, the secrets and the install run,
// answers protocol requests (BUILD-SPEC §4) and broadcasts events to subscribed connections.
// The same engine serves arcticd (socket), `arctic-install bridge --mock` (in process) and
// `arctic-install unattended`.
package engine

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"sort"
	"sync"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/wizard"
)

// Options configure an Engine.
type Options struct {
	Catalog *catalog.Catalog
	// Log receives the engine log (never secrets). nil discards.
	Log io.Writer
	// LogPath is reported to the backend so it can copy the log to the target.
	LogPath string
	// Unattended answers attention events itself: one retry, then defer to first boot.
	Unattended bool
	Now        func() time.Time
}

// Engine is safe for concurrent use.
type Engine struct {
	mu   sync.Mutex
	b    backend.Backend
	cat  *catalog.Catalog
	info backend.Info
	wiz  *wizard.Wizard
	log  *log.Logger
	opts Options

	disks    []hw.Disk
	model    string
	tzCache  wizard.Detected
	tzAt     time.Time
	secrets  backend.Secrets
	luks     wizard.Strength
	password wizard.Strength

	sessions  map[*Session]bool
	listeners []func(ev any)

	// install run
	running   bool
	lastProg  *protocol.ProgressEvent
	modules   map[string]protocol.ModuleEvent
	modOrder  []string
	attention *protocol.AttentionEvent
	failed    *protocol.FailedEvent
	doneEv    *protocol.DoneEvent
	decision  chan backend.Decision
	retried   map[string]int
	cancelRun context.CancelFunc
}

// New creates an engine for a backend.
func New(b backend.Backend, opts Options) (*Engine, error) {
	if opts.Catalog == nil {
		return nil, errors.New("engine: no catalog")
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	w := opts.Log
	if w == nil {
		w = io.Discard
	}
	e := &Engine{
		b: b, cat: opts.Catalog, info: b.Info(), opts: opts,
		log:      log.New(w, "arcticd: ", log.LstdFlags|log.Lmsgprefix),
		sessions: map[*Session]bool{},
		decision: make(chan backend.Decision, 1),
		retried:  map[string]int{},
	}
	e.model = wizard.ModelName(b.DMI())
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	disks, err := b.Disks(ctx)
	if err != nil {
		e.log.Printf("disk probe failed: %v", err)
	}
	e.disks = disks
	e.wiz = wizard.New(envAdapter{e}, b.Language())
	e.log.Printf("engine %s started (mock=%v live=%v firmware=%s, %d disks, model %q)",
		backend.EngineVersion, e.info.Mock, e.info.Live, e.info.Firmware, len(disks), e.model)
	return e, nil
}

// Wizard gives tests and the unattended runner access to the wizard (lock with Do).
func (e *Engine) Do(fn func(w *wizard.Wizard)) {
	e.mu.Lock()
	defer e.mu.Unlock()
	fn(e.wiz)
}

// envAdapter lets the wizard read engine state. Called with e.mu held.
type envAdapter struct{ e *Engine }

func (a envAdapter) Catalog() *catalog.Catalog { return a.e.cat }
func (a envAdapter) Disks() []hw.Disk          { return a.e.disks }
func (a envAdapter) Network() protocol.NetworkState {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return a.e.b.Network(ctx)
}
func (a envAdapter) Secrets() wizard.SecretsInfo {
	return wizard.SecretsInfo{
		LUKSSet: len(a.e.secrets.LUKS) > 0, LUKS: a.e.luks,
		PasswordSet: len(a.e.secrets.Password) > 0, Password: a.e.password,
	}
}
func (a envAdapter) Model() string  { return a.e.model }
func (a envAdapter) Now() time.Time { return a.e.opts.Now() }
func (a envAdapter) DetectTimezone() wizard.Detected {
	e := a.e
	if e.tzCache.Source == "network" {
		return e.tzCache
	}
	// GeoIP needs the internet; retry at most every 30 s while online.
	if !a.Network().Online {
		return wizard.Detected{}
	}
	if !e.tzAt.IsZero() && e.opts.Now().Sub(e.tzAt) < 30*time.Second {
		return e.tzCache
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	e.tzCache = e.b.DetectTimezone(ctx)
	e.tzAt = e.opts.Now()
	return e.tzCache
}

// Handle answers one request. sess may be nil (no events).
func (e *Engine) Handle(ctx context.Context, sess *Session, req protocol.Request) protocol.Response {
	if protocol.SecretMethods[req.Method] {
		e.log.Printf("-> %s (params withheld)", req.Method)
	} else if len(req.Params) > 0 && len(req.Params) < 4096 {
		e.log.Printf("-> %s %s", req.Method, req.Params)
	} else {
		e.log.Printf("-> %s", req.Method)
	}
	res, perr := e.dispatch(ctx, sess, req)
	resp := protocol.Response{ID: req.ID}
	if perr != nil {
		e.log.Printf("<- %s error %s: %s %v", req.Method, perr.Code, perr.Message, perr.Fields)
		resp.Error = perr
	} else {
		resp.Result = res
	}
	return resp
}

func decodeParams(raw json.RawMessage, v any) *protocol.Error {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	if err := json.Unmarshal(raw, v); err != nil {
		return protocol.Errorf(protocol.CodeBadRequest, "bad params: %v", err)
	}
	return nil
}

func (e *Engine) dispatch(ctx context.Context, sess *Session, req protocol.Request) (any, *protocol.Error) {
	switch req.Method {
	case protocol.MethodHello:
		var p protocol.HelloParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		return protocol.HelloResult{
			EngineVersion: backend.EngineVersion, ProtocolVersion: protocol.Version,
			Mock: e.info.Mock, Live: e.info.Live, Firmware: e.info.Firmware, State: e.wiz.Phase(),
		}, nil

	case protocol.MethodGetWizard:
		e.mu.Lock()
		defer e.mu.Unlock()
		return e.wiz.Snapshot(), nil

	case protocol.MethodGetStep:
		var p protocol.IDParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		if p.ID == wizard.StepDisk {
			e.refreshDisks(ctx)
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		res, perr := e.wiz.Get(p.ID)
		if perr != nil {
			return nil, perr
		}
		if p.ID == wizard.StepInstall {
			opts := res.Options.(map[string]any)
			if e.lastProg != nil {
				opts["progress"] = *e.lastProg
			}
			opts["modules"] = e.moduleListLocked()
			if e.attention != nil {
				opts["attention"] = *e.attention
			}
			if e.failed != nil {
				opts["failed"] = *e.failed
			}
		}
		return res, nil

	case protocol.MethodSetStep:
		var p protocol.SetStepParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		data, perr := e.wiz.Set(p.ID, p.Data)
		if perr != nil {
			return nil, perr
		}
		return protocol.SetStepResult{OK: true, Data: data}, nil

	case protocol.MethodNext, protocol.MethodBack:
		e.mu.Lock()
		defer e.mu.Unlock()
		var perr *protocol.Error
		if req.Method == protocol.MethodNext {
			perr = e.wiz.Next()
		} else {
			perr = e.wiz.Back()
		}
		if perr != nil {
			return nil, perr
		}
		return e.wiz.Snapshot(), nil

	case protocol.MethodGoto:
		var p protocol.IDParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		if perr := e.wiz.Goto(p.ID); perr != nil {
			return nil, perr
		}
		return e.wiz.Snapshot(), nil

	case protocol.MethodScanWifi:
		nets, err := e.b.ScanWifi(ctx)
		if err != nil {
			return nil, toProtoErr(err)
		}
		if nets == nil {
			nets = []protocol.WifiNetwork{}
		}
		return protocol.ScanWifiResult{Networks: nets}, nil

	case protocol.MethodConnectWifi:
		var p protocol.ConnectWifiParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		if p.SSID == "" {
			return nil, protocol.FieldErrors("Pick a network.", map[string]string{"ssid": "Pick a network."})
		}
		if err := e.b.ConnectWifi(ctx, p.SSID, p.Password); err != nil {
			return nil, toProtoErr(err)
		}
		return protocol.OKResult{OK: true}, nil

	case protocol.MethodNetworkState:
		return e.b.Network(ctx), nil

	case protocol.MethodCheckPassphrase:
		var p protocol.TextParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		s := wizard.CheckPassphrase(p.Text)
		return protocol.PassphraseResult{Score: s.Score, Label: s.Label, Words: s.Words, OK: s.OK}, nil

	case protocol.MethodSuggestPassphrase:
		text, err := wizard.SuggestPassphrase()
		if err != nil {
			return nil, protocol.Errorf(protocol.CodeInternal, "could not pick words: %v", err)
		}
		return protocol.SuggestPassphraseResult{Text: text}, nil

	case protocol.MethodSuggestAccount:
		var p protocol.SuggestAccountParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		u, h := e.wiz.SuggestAccount(p.FullName)
		return protocol.SuggestAccountResult{Username: u, Hostname: h}, nil

	case protocol.MethodSetSecrets:
		var p protocol.SetSecretsParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		e.mu.Lock()
		defer e.mu.Unlock()
		if e.running {
			return nil, protocol.Errorf(protocol.CodeState, "The install is already running.")
		}
		if p.LUKSPassphrase != nil {
			wipe(e.secrets.LUKS)
			e.secrets.LUKS = []byte(*p.LUKSPassphrase)
			e.luks = wizard.CheckPassphrase(*p.LUKSPassphrase)
		}
		if p.UserPassword != nil {
			wipe(e.secrets.Password)
			e.secrets.Password = []byte(*p.UserPassword)
			e.password = wizard.CheckPassphrase(*p.UserPassword)
		}
		return protocol.OKResult{OK: true}, nil

	case protocol.MethodEstimateDownload:
		var p protocol.EstimateParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		sel := catalog.Selection(p.Selection)
		if p.Selection == nil {
			e.mu.Lock()
			sel = e.wiz.Data.Apps.Selection
			e.mu.Unlock()
		}
		est := e.cat.EstimateDownload(e.cat.Normalize(sel))
		return protocol.EstimateResult{Apps: est.Apps, Bytes: est.Bytes, Label: est.Label}, nil

	case protocol.MethodGetCatalog:
		e.mu.Lock()
		sel := e.wiz.Data.Apps.Selection
		e.mu.Unlock()
		p := e.cat.Picker()
		return map[string]any{"categories": p.Categories, "modules": p.Modules, "estimate": e.cat.EstimateDownload(sel)}, nil

	case protocol.MethodGetSummary:
		e.mu.Lock()
		defer e.mu.Unlock()
		return e.wiz.Summary(), nil

	case protocol.MethodStart:
		if perr := e.Start(); perr != nil {
			return nil, perr
		}
		return protocol.OKResult{OK: true}, nil

	case protocol.MethodRetryModule, protocol.MethodSkipModule:
		var p protocol.IDParams
		if err := decodeParams(req.Params, &p); err != nil {
			return nil, err
		}
		d := backend.Retry
		if req.Method == protocol.MethodSkipModule {
			d = backend.Skip
		}
		if perr := e.decide(p.ID, d); perr != nil {
			return nil, perr
		}
		return protocol.OKResult{OK: true}, nil

	case protocol.MethodSaveLog:
		path, err := e.b.SaveLog(ctx)
		if err != nil {
			return nil, protocol.Errorf(protocol.CodeInternal, "Couldn’t save the log: %v", err)
		}
		return protocol.SaveLogResult{Path: path}, nil

	case protocol.MethodReboot:
		e.mu.Lock()
		running := e.running
		e.mu.Unlock()
		if running {
			return nil, protocol.Errorf(protocol.CodeState, "Wait for the install to finish first.")
		}
		if err := e.b.Reboot(ctx); err != nil {
			return nil, protocol.Errorf(protocol.CodeInternal, "Couldn’t restart: %v", err)
		}
		return protocol.OKResult{OK: true}, nil

	case protocol.MethodSubscribe:
		// Connections subscribe through ServeConn, which orders the reply before the replay.
		return nil, protocol.Errorf(protocol.CodeState, "This connection can’t receive events.")
	}
	return nil, protocol.Errorf(protocol.CodeUnknown, "Unknown method %q.", req.Method)
}

func toProtoErr(err error) *protocol.Error {
	var pe *protocol.Error
	if errors.As(err, &pe) {
		return pe
	}
	return protocol.Errorf(protocol.CodeInternal, "%v", err)
}

func wipe(b []byte) {
	for i := range b {
		b[i] = 0
	}
}

func (e *Engine) refreshDisks(ctx context.Context) {
	e.mu.Lock()
	running := e.running
	e.mu.Unlock()
	if running {
		return
	}
	disks, err := e.b.Disks(ctx)
	if err != nil {
		e.log.Printf("disk probe failed: %v", err)
		return
	}
	e.mu.Lock()
	e.disks = disks
	e.mu.Unlock()
}

// ---- install run ----

// Start begins the install (also "Try again" after a fatal failure).
func (e *Engine) Start() *protocol.Error {
	e.mu.Lock()
	defer e.mu.Unlock()
	switch e.wiz.Phase() {
	case wizard.PhaseInstalling, wizard.PhaseAttention:
		return protocol.Errorf(protocol.CodeState, "The install is already running.")
	case wizard.PhaseDone:
		return protocol.Errorf(protocol.CodeState, "Arctic Linux is already installed.")
	case wizard.PhaseWizard:
		if perr := e.wiz.ReadyToInstall(); perr != nil {
			return perr
		}
	}
	d := e.wiz.Data
	if d.Encryption.Enabled && len(e.secrets.LUKS) == 0 {
		return protocol.Errorf(protocol.CodeState, "The encryption passphrase is missing. Go back to the Encryption step.")
	}
	if len(e.secrets.Password) == 0 {
		return protocol.Errorf(protocol.CodeState, "The account password is missing. Go back to the Account step.")
	}
	disk, ok := e.wiz.SelectedDisk()
	if !ok {
		return protocol.Errorf(protocol.CodeState, "The chosen disk is gone. Go back to the Disk step.")
	}
	sec := &backend.Secrets{LUKS: append([]byte{}, e.secrets.LUKS...), Password: append([]byte{}, e.secrets.Password...)}
	if !d.Encryption.Enabled {
		wipe(sec.LUKS)
		sec.LUKS = nil
	}
	d.Apps.Selection = d.Apps.Selection.Clone()
	job := &backend.Job{Data: d, Disk: disk, Firmware: e.info.Firmware, Catalog: e.cat, Secrets: sec, LogPath: e.opts.LogPath}

	e.wiz.BeginInstall()
	e.running = true
	e.lastProg, e.attention, e.failed, e.doneEv = nil, nil, nil, nil
	e.modules = map[string]protocol.ModuleEvent{}
	e.modOrder = nil
	e.retried = map[string]int{}
	select { // drop a stale decision
	case <-e.decision:
	default:
	}
	ctx, cancel := context.WithCancel(context.Background())
	e.cancelRun = cancel
	e.log.Printf("install started: disk=%s mode=%s encrypted=%v firmware=%s apps=%v",
		disk.Path, d.Disk.Mode, d.Encryption.Enabled, job.Firmware, d.Apps.Selection)
	e.broadcastLocked(protocol.WizardEvent{Event: protocol.EventWizard, WizardResult: e.wiz.Snapshot()}, false)
	go e.run(ctx, job)
	return nil
}

func (e *Engine) run(ctx context.Context, job *backend.Job) {
	err := e.b.Install(ctx, job, e)
	job.Secrets.Wipe()
	e.mu.Lock()
	defer e.mu.Unlock()
	e.running = false
	e.cancelRun = nil
	if err != nil {
		e.log.Printf("install failed: %v", err)
		e.wiz.SetPhase(wizard.PhaseFailed)
		ev := protocol.FailedEvent{
			Event: protocol.EventFailed, Title: "Something went wrong while installing",
			Message: "Arctic Linux couldn’t finish installing. Your files on other disks are untouched. Save the log to the USB stick and try again.",
			Details: err.Error(), Fatal: true,
		}
		e.failed = &ev
		e.broadcastLocked(ev, false)
		e.broadcastLocked(protocol.WizardEvent{Event: protocol.EventWizard, WizardResult: e.wiz.Snapshot()}, false)
		return
	}
	installed := 0
	var deferred []string
	for _, id := range e.modOrder {
		m := e.modules[id]
		if mod, ok := e.cat.Modules[id]; !ok || mod.Hidden {
			continue
		}
		switch m.Status {
		case protocol.ModInstalled:
			installed++
		case protocol.ModDeferred:
			deferred = append(deferred, id)
		}
	}
	e.wiz.Finish(installed)
	first := wizard.FirstName(job.Data.Account.FullName)
	res, _ := e.wiz.Get(wizard.StepDone)
	ev := protocol.DoneEvent{Event: protocol.EventDone, AppsInstalled: installed, FirstName: first, Deferred: deferred, Title: res.Title, Help: res.Help}
	e.doneEv = &ev
	// The secrets are not needed any more.
	wipe(e.secrets.LUKS)
	wipe(e.secrets.Password)
	e.secrets = backend.Secrets{}
	e.log.Printf("install finished: %d apps installed, deferred %v", installed, deferred)
	e.broadcastLocked(ev, false)
	e.broadcastLocked(protocol.WizardEvent{Event: protocol.EventWizard, WizardResult: e.wiz.Snapshot()}, false)
}

// Progress implements backend.Reporter.
func (e *Engine) Progress(ev protocol.ProgressEvent) {
	ev.Event = protocol.EventProgress
	e.mu.Lock()
	defer e.mu.Unlock()
	e.lastProg = &ev
	e.broadcastLocked(ev, true)
}

// Module implements backend.Reporter.
func (e *Engine) Module(ev protocol.ModuleEvent) {
	ev.Event = protocol.EventModule
	e.mu.Lock()
	defer e.mu.Unlock()
	if _, ok := e.modules[ev.ID]; !ok {
		e.modOrder = append(e.modOrder, ev.ID)
	}
	e.modules[ev.ID] = ev
	e.broadcastLocked(ev, ev.Status == protocol.ModDownloading)
}

// Logf implements backend.Reporter.
func (e *Engine) Logf(format string, a ...any) { e.log.Printf(format, a...) }

// Attention implements backend.Reporter: it pauses until RetryModule / SkipModule.
func (e *Engine) Attention(ctx context.Context, ev protocol.AttentionEvent) backend.Decision {
	ev.Event = protocol.EventAttention
	e.mu.Lock()
	if e.opts.Unattended {
		n := e.retried[ev.Module.ID]
		e.retried[ev.Module.ID] = n + 1
		e.mu.Unlock()
		if n == 0 {
			e.log.Printf("unattended: retrying %s (%s)", ev.Module.ID, ev.Message)
			return backend.Retry
		}
		e.log.Printf("unattended: deferring %s to first boot", ev.Module.ID)
		return backend.Defer
	}
	e.wiz.SetPhase(wizard.PhaseAttention)
	e.attention = &ev
	e.log.Printf("attention: %s: %s (%s)", ev.Module.ID, ev.Message, ev.Details)
	e.broadcastLocked(ev, false)
	e.broadcastLocked(protocol.WizardEvent{Event: protocol.EventWizard, WizardResult: e.wiz.Snapshot()}, false)
	e.mu.Unlock()

	var d backend.Decision
	select {
	case d = <-e.decision:
	case <-ctx.Done():
		d = backend.Skip
	}
	e.mu.Lock()
	e.attention = nil
	e.wiz.SetPhase(wizard.PhaseInstalling)
	e.broadcastLocked(protocol.WizardEvent{Event: protocol.EventWizard, WizardResult: e.wiz.Snapshot()}, false)
	e.mu.Unlock()
	return d
}

func (e *Engine) decide(id string, d backend.Decision) *protocol.Error {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.attention == nil {
		return protocol.Errorf(protocol.CodeState, "No app is waiting for an answer.")
	}
	if e.attention.Module.ID != id {
		return protocol.Errorf(protocol.CodeNotFound, "%q isn’t the app that needs attention (%s is).", id, e.attention.Module.ID)
	}
	select {
	case e.decision <- d:
	default:
		return protocol.Errorf(protocol.CodeState, "An answer is already on its way.")
	}
	return nil
}

func (e *Engine) moduleListLocked() []protocol.ModuleEvent {
	out := make([]protocol.ModuleEvent, 0, len(e.modOrder))
	for _, id := range e.modOrder {
		out = append(out, e.modules[id])
	}
	return out
}

// State returns the session phase (for the unattended runner and tests).
func (e *Engine) State() string {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.wiz.Phase()
}

// Close cancels a running install.
func (e *Engine) Close() {
	e.mu.Lock()
	cancel := e.cancelRun
	e.mu.Unlock()
	if cancel != nil {
		cancel()
	}
}

// ModuleStates returns the last status of every module (sorted by first appearance).
func (e *Engine) ModuleStates() []protocol.ModuleEvent {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.moduleListLocked()
}

// DebugString summarises the engine (never secrets).
func (e *Engine) DebugString() string {
	e.mu.Lock()
	defer e.mu.Unlock()
	ids := make([]string, 0, len(e.sessions))
	for s := range e.sessions {
		ids = append(ids, fmt.Sprint(s.id))
	}
	sort.Strings(ids)
	return fmt.Sprintf("phase=%s current=%s sessions=%v", e.wiz.Phase(), e.wiz.Current(), ids)
}
