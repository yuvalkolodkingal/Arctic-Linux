package wizard

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

// Env is what the wizard needs from the engine and the machine.
type Env interface {
	Catalog() *catalog.Catalog
	Disks() []hw.Disk
	Network() protocol.NetworkState
	Secrets() SecretsInfo
	Model() string // machine word for hostnames ("thinkpad")
	DetectTimezone() Detected
	Now() time.Time
	Firmware() string // uefi | bios
	// Hardware is what driver detection found (the catalog is already marked with it).
	Hardware() hw.Hardware
	// SystemNames are the user and group names the copied system already has; the new
	// account can't use them (useradd --user-group would fail).
	SystemNames() map[string]bool
}

// SecretsInfo tells validation whether secrets were set, never what they are.
type SecretsInfo struct {
	LUKSSet     bool
	LUKS        Strength
	PasswordSet bool
	Password    Strength
}

// Detected is the time zone guess.
type Detected struct {
	Timezone string `json:"timezone"`
	Source   string `json:"source"` // network | default
}

// Per-step data (the JSON "data" of GetStep / SetStep).
type (
	WelcomeData struct {
		Language string `json:"language"`
	}
	KeyboardData struct {
		Layout  string `json:"layout"`
		Variant string `json:"variant"`
	}
	NetworkData  struct{}
	TimezoneData struct {
		Timezone string `json:"timezone"`
		AutoTime bool   `json:"auto_time"`
	}
	DiskData struct {
		Disk string `json:"disk"`
		Mode string `json:"mode"` // erase | alongside
	}
	EncryptionData struct {
		Enabled bool `json:"enabled"`
	}
	AccountData struct {
		FullName  string `json:"full_name"`
		Username  string `json:"username"`
		Hostname  string `json:"hostname"`
		Autologin bool   `json:"autologin"`
	}
	AppsData struct {
		Selection catalog.Selection `json:"selection"`
	}
	DoneData struct {
		AppsInstalled int    `json:"apps_installed"`
		FirstName     string `json:"first_name"`
	}
)

// Disk modes.
const (
	ModeErase     = "erase"
	ModeAlongside = "alongside"
)

// Data is every answer the wizard collected.
type Data struct {
	Welcome    WelcomeData
	Keyboard   KeyboardData
	Timezone   TimezoneData
	Disk       DiskData
	Encryption EncryptionData
	Account    AccountData
	Apps       AppsData
}

// Phases of the whole session.
const (
	PhaseWizard     = "wizard"
	PhaseInstalling = "installing"
	PhaseAttention  = "attention"
	PhaseFailed     = "failed"
	PhaseDone       = "done"
)

// Wizard is the step state machine. It is not safe for concurrent use; the engine locks.
type Wizard struct {
	env  Env
	Data Data

	cur        int
	done       map[string]bool
	phase      string
	netSkipped bool
	returnTo   bool            // Next goes back to Summary (after Goto from Summary)
	returnLang string          // language when Goto left Summary (a change also shows Keyboard)
	diskStale  bool            // the disk changed after it was picked: the Disk step must be seen again
	userSet    map[string]bool // fields the person chose (not overwritten by suggestions)
	autoUser   string          // last suggested username / hostname
	autoHost   string

	AppsInstalled int
	// Set by the engine when the install finished (Done screen).
	DriverResults []protocol.DriverResult
	SecureBoot    *protocol.SecureBootInfo
	DoneNotes     []string
}

// New starts a wizard with defaults: the suggested language (from the live session's LANG),
// its keyboard layout, the detected time zone, the best disk erased and encrypted, and the
// catalog's default apps.
func New(env Env, lang string) *Wizard {
	w := &Wizard{env: env, done: map[string]bool{}, userSet: map[string]bool{}, phase: PhaseWizard}
	w.Data.Welcome.Language = GuessLanguage(lang)
	w.Data.Keyboard.Layout, w.Data.Keyboard.Variant = SuggestedLayout(w.Data.Welcome.Language)
	w.Data.Timezone = TimezoneData{Timezone: w.fallbackTimezone(), AutoTime: true}
	w.Data.Disk = DiskData{Disk: DefaultDisk(env.Disks()), Mode: ModeErase}
	w.Data.Encryption.Enabled = true
	w.Data.Apps.Selection = env.Catalog().DefaultSelection()
	return w
}

func (w *Wizard) fallbackTimezone() string {
	if d := w.env.DetectTimezone(); ValidTimezone(d.Timezone) {
		return d.Timezone
	}
	if l, ok := FindLanguage(w.Data.Welcome.Language); ok && l.Timezone != "" {
		return l.Timezone
	}
	return "UTC"
}

// DefaultDisk picks the install target: never the install media; prefer internal SSDs, then
// the largest disk.
func DefaultDisk(disks []hw.Disk) string {
	var cands []hw.Disk
	for _, d := range disks {
		if !d.InstallMedia && !d.ReadOnly {
			cands = append(cands, d)
		}
	}
	sort.SliceStable(cands, func(i, j int) bool {
		a, b := cands[i], cands[j]
		if a.Removable != b.Removable {
			return !a.Removable
		}
		bigA, bigB := a.SizeBytes >= hw.MinInstallBytes, b.SizeBytes >= hw.MinInstallBytes
		if bigA != bigB {
			return bigA
		}
		if a.Rotational != b.Rotational {
			return !a.Rotational
		}
		return a.SizeBytes > b.SizeBytes
	})
	if len(cands) == 0 {
		return ""
	}
	return cands[0].Path
}

// Phase is the session phase.
func (w *Wizard) Phase() string { return w.phase }

// Current is the id of the current screen.
func (w *Wizard) Current() string {
	if w.phase == PhaseDone {
		return StepDone
	}
	return Steps[w.cur].ID
}

// Done reports whether a step is done.
func (w *Wizard) Done(id string) bool { return w.done[id] }

// Snapshot is the GetWizard result.
func (w *Wizard) Snapshot() protocol.WizardResult {
	res := protocol.WizardResult{Current: w.Current(), State: w.phase}
	for i, s := range Steps {
		st := "todo"
		switch {
		case w.phase == PhaseDone || w.done[s.ID]:
			st = "done"
		case i == w.cur:
			st = "current"
		}
		if s.ID == StepInstall && (w.phase == PhaseAttention || w.phase == PhaseFailed) {
			st = "error"
		}
		res.Steps = append(res.Steps, protocol.StepState{ID: s.ID, Title: s.Name, State: st})
	}
	// The final screen is listed too (not drawn in the rail): every screen id is here.
	doneState := "todo"
	if w.phase == PhaseDone {
		doneState = "current"
	}
	res.Steps = append(res.Steps, protocol.StepState{ID: StepDone, Title: DoneDef.Name, State: doneState})
	return res
}

func stateErr(format string, a ...any) *protocol.Error {
	return protocol.Errorf(protocol.CodeState, format, a...)
}

// Next validates the current step and moves forward.
func (w *Wizard) Next() *protocol.Error {
	if w.phase != PhaseWizard {
		return stateErr("The installer is already past the wizard.")
	}
	id := Steps[w.cur].ID
	switch id {
	case StepSummary:
		// Summary's primary button: validate everything and move to the install screen;
		// Start then begins the install.
		if err := w.ReadyToInstall(); err != nil {
			return err
		}
		w.done[StepSummary] = true
		w.returnTo = false
		w.cur = StepIndex(StepInstall)
		return nil
	case StepInstall:
		return stateErr("Use Start to begin installing.")
	}
	if err := w.Validate(id, true); err != nil {
		return err
	}
	w.done[id] = true
	if id == StepDisk {
		w.diskStale = false
	}
	target := w.cur + 1
	if w.returnTo && id == StepWelcome && w.Data.Welcome.Language != w.returnLang {
		// A new language suggests other layouts: show Keyboard before going back to Summary.
		w.returnLang = w.Data.Welcome.Language
	} else if w.returnTo {
		w.returnTo = false
		all := true
		for i := target; i < StepIndex(StepSummary); i++ {
			if !w.done[Steps[i].ID] {
				all = false
			}
		}
		if all {
			target = StepIndex(StepSummary)
		}
	}
	if Steps[target].ID == StepNetwork {
		if n := w.env.Network(); n.Online && n.Wired {
			w.done[StepNetwork] = true
			w.netSkipped = true
			target++
		} else {
			w.netSkipped = false
		}
	}
	if Steps[target].ID == StepTimezone && !w.userSet["timezone"] {
		w.Data.Timezone.Timezone = w.fallbackTimezone()
	}
	w.cur = target
	return nil
}

// Back moves to the previous step (skipping an auto-skipped network step). After a failed
// install it goes back to Summary, so the answers can be changed before trying again.
func (w *Wizard) Back() *protocol.Error {
	if w.phase == PhaseFailed {
		w.reopen()
		w.returnTo = false
		w.cur = StepIndex(StepSummary)
		return nil
	}
	if w.phase != PhaseWizard {
		return stateErr("You can’t go back while installing.")
	}
	if w.cur == 0 {
		return stateErr("This is the first step.")
	}
	w.returnTo = false
	target := w.cur - 1
	if Steps[target].ID == StepNetwork && w.netSkipped {
		if n := w.env.Network(); n.Online && n.Wired {
			target--
		}
	}
	w.cur = target
	return nil
}

// Goto jumps to a done step (Summary "Change" links). From the install screen (before Start,
// or after a failed install) it can also go to Summary.
func (w *Wizard) Goto(id string) *protocol.Error {
	if w.phase != PhaseWizard && w.phase != PhaseFailed {
		return stateErr("You can’t change answers while installing.")
	}
	i := StepIndex(id)
	if i < 0 {
		return protocol.Errorf(protocol.CodeNotFound, "There is no step called %q.", id)
	}
	if i == w.cur {
		return nil
	}
	fromInstall := Steps[w.cur].ID == StepInstall
	if id == StepSummary && fromInstall {
		w.reopen()
		w.returnTo = false
		w.cur = i
		return nil
	}
	if !w.done[id] || i >= StepIndex(StepSummary) {
		return stateErr("You can only go back to steps you’ve finished.")
	}
	w.returnTo = Steps[w.cur].ID == StepSummary || fromInstall
	w.returnLang = w.Data.Welcome.Language
	w.reopen()
	w.cur = i
	return nil
}

// reopen returns to the wizard after a failed install (the answers and secrets are kept;
// Start re-checks everything, the disk included).
func (w *Wizard) reopen() {
	if w.phase == PhaseFailed {
		w.phase = PhaseWizard
		w.done[StepSummary] = false
		w.done[StepInstall] = false
	}
}

// DiskChanged records that the chosen disk is no longer what the person picked (found by the
// engine's probe before Start). Installing is refused until the Disk step is passed again.
func (w *Wizard) DiskChanged() { w.diskStale = true }

// ReadyToInstall checks that every step before Summary is done and still valid.
func (w *Wizard) ReadyToInstall() *protocol.Error {
	if id := Steps[w.cur].ID; id != StepSummary && id != StepInstall {
		return stateErr("Finish the steps before Summary first.")
	}
	if w.diskStale {
		return stateErr(MsgDiskChanged)
	}
	for _, s := range Steps[:StepIndex(StepSummary)] {
		if !w.done[s.ID] {
			return stateErr("The %s step isn’t finished.", s.Name)
		}
		if s.ID == StepNetwork {
			continue // being offline now is handled by the app downloads, not by blocking the start
		}
		if err := w.Validate(s.ID, true); err != nil {
			return err
		}
	}
	return nil
}

// BeginInstall moves to the install step.
func (w *Wizard) BeginInstall() {
	w.phase = PhaseInstalling
	w.cur = StepIndex(StepInstall)
	w.done[StepSummary] = true
}

// SetPhase is used by the engine while installing (attention, failed, installing again).
func (w *Wizard) SetPhase(p string) { w.phase = p }

// Finish moves to the done screen.
func (w *Wizard) Finish(appsInstalled int) {
	w.phase = PhaseDone
	w.done[StepInstall] = true
	w.AppsInstalled = appsInstalled
}

// ---- GetStep ----

// Get returns a step's copy, data and options.
func (w *Wizard) Get(id string) (protocol.StepResult, *protocol.Error) {
	def, ok := FindStep(id)
	if !ok {
		return protocol.StepResult{}, protocol.Errorf(protocol.CodeNotFound, "There is no step called %q.", id)
	}
	res := protocol.StepResult{ID: def.ID, Title: def.Title, Help: def.Help, Note: def.Note, Primary: def.Primary}
	cat := w.env.Catalog()
	switch id {
	case StepWelcome:
		res.Data = w.Data.Welcome
		res.Options = map[string]any{"languages": Languages, "suggested": GuessLanguage(w.Data.Welcome.Language)}
	case StepKeyboard:
		res.Data = KeyboardView{w.Data.Keyboard, KeyboardConfig(w.Data.Keyboard)}
		res.Options = map[string]any{
			"layouts":  LayoutsFor(w.Data.Welcome.Language),
			"try_it":   "Try it",
			"try_help": "Type a few letters to check the layout matches your keys.",
		}
	case StepNetwork:
		n := w.env.Network()
		res.Data = NetworkData{}
		res.Options = map[string]any{
			"online": n.Online, "wired": n.Wired, "ssid": n.SSID,
			"info_title": CopyNetworkWhyTitle, "info": CopyNetworkWhy,
			"auto_skipped": w.netSkipped,
		}
		if h := w.driverHint(); h != "" {
			res.Options.(map[string]any)["driver_hint"] = h
		}
	case StepTimezone:
		d := w.env.DetectTimezone()
		if !ValidTimezone(d.Timezone) {
			d = Detected{Timezone: w.Data.Timezone.Timezone, Source: "default"}
		}
		c := LookupCity(d.Timezone)
		now := w.env.Now()
		detected := map[string]any{
			"city": c.City, "country": c.Country, "timezone": d.Timezone, "source": d.Source,
			"local_time": LocalTime(d.Timezone, now), "offset": UTCOffsetLabel(d.Timezone, now),
		}
		if d.Source == "network" {
			detected["description"] = "Found from your network. Local time is " + LocalTime(d.Timezone, now) + "."
		} else {
			detected["description"] = "Local time is " + LocalTime(d.Timezone, now) + "."
		}
		res.Data = w.Data.Timezone
		res.Options = map[string]any{
			"detected": detected, "regions": Regions, "region": RegionOf(w.Data.Timezone.Timezone),
			"auto_time_label": "Set the time automatically from the internet",
		}
	case StepDisk:
		res.Data = w.Data.Disk
		res.Options = map[string]any{
			"disks": w.diskOptions(), "min_bytes": int64(hw.MinInstallBytes),
			"erase_title": CopyEraseTitle, "erase_tag": "Recommended", "erase_description": CopyEraseDesc,
			"warning": CopyEraseWarning,
		}
	case StepEncryption:
		s := w.env.Secrets()
		opts := map[string]any{
			"min_score": MinPassphraseScore, "warning": CopyPassphraseWarn, "help": CopyPassphraseHelp,
			"off_warning": CopyNoEncryptWarn, "passphrase_set": s.LUKSSet,
			"suggest_label": "Suggest a passphrase", "confirm_label": "Type it again",
		}
		if s.LUKSSet {
			opts["strength"] = s.LUKS
			opts["meter_label"] = s.LUKS.MeterLabel()
		}
		res.Data = w.Data.Encryption
		res.Options = opts
	case StepAccount:
		s := w.env.Secrets()
		res.Data = w.Data.Account
		res.Options = map[string]any{
			"username_hint": CopyUsernameHint, "hostname_hint": CopyHostnameHint, "hostname_help": CopyHostnameHelp,
			"password_set": s.PasswordSet, "min_score": MinPasswordScore,
			"same_passphrase_label": "Use this password for the disk passphrase too",
			"encryption":            w.Data.Encryption.Enabled,
		}
	case StepApps:
		res.Data = w.Data.Apps
		p := cat.Picker()
		est := cat.EstimateDownload(w.Data.Apps.Selection)
		res.Note = est.Label
		res.Options = map[string]any{"categories": p.Categories, "modules": p.Modules, "estimate": est}
	case StepSummary:
		sum := w.Summary()
		res.Primary = sum.PrimaryLabel
		res.Data = map[string]any{}
		res.Options = sum
	case StepInstall:
		res.Data = map[string]any{}
		res.Options = map[string]any{"tip_title": "While you wait", "tip": CopyWhileYouWait}
	case StepDone:
		first := FirstName(w.Data.Account.FullName)
		res.Help = strings.NewReplacer("{n}", fmt.Sprint(w.AppsInstalled), "{first}", first).Replace(def.Help)
		usb := CopyRemoveUSB
		if !w.Data.Encryption.Enabled {
			usb = CopyRemoveUSBNoLUKS
		}
		res.Data = DoneData{AppsInstalled: w.AppsInstalled, FirstName: first}
		opts := map[string]any{"card_title": CopyRemoveUSBTitle, "card": usb, "secondary": "Keep trying"}
		if len(w.DriverResults) > 0 {
			opts["drivers"] = w.DriverResults
		}
		if w.SecureBoot != nil {
			opts["secure_boot"] = w.SecureBoot
		}
		if len(w.DoneNotes) > 0 {
			opts["notes"] = w.DoneNotes
		}
		res.Options = opts
	}
	return res, nil
}

// DiskOption is one entry of the disk dropdown.
type DiskOption struct {
	Path                 string   `json:"path"`
	Model                string   `json:"model"`
	Label                string   `json:"label"`
	SizeBytes            int64    `json:"size_bytes"`
	SizeLabel            string   `json:"size_label"`
	Removable            bool     `json:"removable"`
	InstallMedia         bool     `json:"install_media"`
	ExistingOS           []string `json:"existing_os"`
	TooSmall             bool     `json:"too_small"`
	AlongsidePossible    bool     `json:"alongside_possible"`
	AlongsideLabel       string   `json:"alongside_label"`
	AlongsideTitle       string   `json:"alongside_title"`
	AlongsideDescription string   `json:"alongside_description"`
	FreeBytes            int64    `json:"free_bytes"`
}

func (w *Wizard) diskOptions() []DiskOption {
	out := []DiskOption{}
	for _, d := range w.env.Disks() {
		if d.InstallMedia {
			continue
		}
		free := d.LargestFree().SizeBytes
		o := DiskOption{
			Path: d.Path, Model: d.Model, Label: d.Label(), SizeBytes: d.SizeBytes, SizeLabel: hw.SizeLabel(d.SizeBytes),
			Removable: d.Removable, ExistingOS: append([]string{}, d.ExistingOS...), TooSmall: d.SizeBytes < hw.MinInstallBytes,
			AlongsidePossible: d.AlongsidePossibleFor(w.env.Firmware()), FreeBytes: free,
		}
		if o.AlongsidePossible {
			o.AlongsideLabel = "Uses " + hw.SizeLabel(free) + " of free space"
			o.AlongsideTitle = "Install alongside " + d.OSName()
			if len(d.ExistingOS) > 0 {
				o.AlongsideDescription = "Keeps " + d.OSName() + ". You choose which one to start each time. " + o.AlongsideLabel + "."
			} else {
				o.AlongsideDescription = "Keeps what’s already on this disk. " + o.AlongsideLabel + "."
			}
		}
		out = append(out, o)
	}
	return out
}

func (w *Wizard) disk(path string) (hw.Disk, bool) {
	for _, d := range w.env.Disks() {
		if d.Path == path {
			return d, true
		}
	}
	return hw.Disk{}, false
}

// SelectedDisk returns the chosen disk.
func (w *Wizard) SelectedDisk() (hw.Disk, bool) { return w.disk(w.Data.Disk.Disk) }

// ---- SetStep ----

// Set stores a step's data (merged over the current values) and validates the fields that
// were sent. The draft is stored even when field errors are returned. Any step before
// Summary can be set at any time during the wizard; Next still walks them in order.
func (w *Wizard) Set(id string, raw json.RawMessage) (any, *protocol.Error) {
	switch w.phase {
	case PhaseWizard:
	case PhaseFailed:
		return nil, stateErr("Go back to the %s step first (Back, or Change on the Summary).", stepName(id))
	default:
		return nil, stateErr("The installer is already running.")
	}
	i := StepIndex(id)
	if i < 0 {
		return nil, protocol.Errorf(protocol.CodeNotFound, "There is no step called %q.", id)
	}
	if len(bytes.TrimSpace(raw)) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		raw = json.RawMessage("{}")
	}
	var present map[string]json.RawMessage
	if err := json.Unmarshal(raw, &present); err != nil {
		return nil, protocol.Errorf(protocol.CodeBadRequest, "data must be an object")
	}
	decode := func(dst any) *protocol.Error {
		if err := json.Unmarshal(raw, dst); err != nil {
			return protocol.Errorf(protocol.CodeBadRequest, "bad data for %s: %v", id, err)
		}
		return nil
	}
	var data any
	switch id {
	case StepWelcome:
		d := w.Data.Welcome
		if err := decode(&d); err != nil {
			return nil, err
		}
		if d.Language != w.Data.Welcome.Language && !w.userSet["keyboard"] {
			if _, ok := FindLanguage(d.Language); ok {
				w.Data.Keyboard.Layout, w.Data.Keyboard.Variant = SuggestedLayout(d.Language)
			}
		}
		w.Data.Welcome = d
		data = d
	case StepKeyboard:
		d := w.Data.Keyboard
		if err := decode(&d); err != nil {
			return nil, err
		}
		if _, ok := present["layout"]; ok {
			if _, v := present["variant"]; !v {
				d.Variant = ""
			}
		}
		w.userSet["keyboard"] = true
		w.Data.Keyboard = d
		data = KeyboardView{d, KeyboardConfig(d)}
	case StepNetwork:
		data = NetworkData{}
	case StepTimezone:
		d := w.Data.Timezone
		if err := decode(&d); err != nil {
			return nil, err
		}
		if _, ok := present["timezone"]; ok {
			w.userSet["timezone"] = true
		}
		w.Data.Timezone = d
		data = d
	case StepDisk:
		d := w.Data.Disk
		if err := decode(&d); err != nil {
			return nil, err
		}
		w.Data.Disk = d
		data = d
	case StepEncryption:
		d := w.Data.Encryption
		if err := decode(&d); err != nil {
			return nil, err
		}
		w.Data.Encryption = d
		data = d
	case StepAccount:
		d := w.Data.Account
		if err := decode(&d); err != nil {
			return nil, err
		}
		if _, ok := present["username"]; ok && d.Username != w.autoUser {
			w.userSet["username"] = d.Username != ""
		}
		if _, ok := present["hostname"]; ok && d.Hostname != w.autoHost {
			w.userSet["hostname"] = d.Hostname != ""
		}
		if _, ok := present["full_name"]; ok {
			u, h := w.SuggestAccount(d.FullName)
			if strings.TrimSpace(d.FullName) == "" {
				u, h = "", ""
			}
			if !w.userSet["username"] {
				d.Username = u
				present["username"] = nil
			}
			if !w.userSet["hostname"] {
				d.Hostname = SuggestHostname(d.Username, w.env.Model())
				if d.Username == "" {
					d.Hostname = h
				}
				present["hostname"] = nil
			}
			w.autoUser, w.autoHost = d.Username, d.Hostname
		} else if _, ok := present["username"]; ok && !w.userSet["hostname"] && d.Username != "" {
			d.Hostname = SuggestHostname(d.Username, w.env.Model())
			w.autoHost = d.Hostname
			present["hostname"] = nil
		}
		w.Data.Account = d
		data = d
	case StepApps:
		d := AppsData{Selection: w.Data.Apps.Selection.Clone()}
		if err := decode(&d); err != nil {
			return nil, err
		}
		d.Selection = w.env.Catalog().Normalize(d.Selection)
		w.Data.Apps = d
		data = d
	default:
		return nil, stateErr("The %s step has nothing to set.", Steps[i].Name)
	}
	fields := w.fieldErrors(id, false)
	for k := range fields {
		if _, sent := present[k]; !sent && !(id == StepApps && present["selection"] != nil) {
			delete(fields, k)
		}
	}
	if len(fields) > 0 {
		return data, protocol.FieldErrors("Fix the highlighted field to continue.", fields)
	}
	return data, nil
}

// SuggestAccount derives username and hostname from a full name (never a name the system
// already uses).
func (w *Wizard) SuggestAccount(fullName string) (string, string) {
	u := SuggestUsernameAvoiding(fullName, w.env.SystemNames())
	return u, SuggestHostname(u, w.env.Model())
}

// usernameError is ValidateUsername plus the users and groups the copied system has.
func (w *Wizard) usernameError(u string) string {
	if m := ValidateUsername(u); m != "" {
		return m
	}
	if w.env.SystemNames()[u] {
		return MsgNameTaken
	}
	return ""
}

// alongsideProblem says why installing alongside on d isn't possible ("" when it is).
func alongsideProblem(d hw.Disk, firmware string) string {
	switch {
	case d.AlongsidePossibleFor(firmware):
		return ""
	case d.PTType == "" || d.LargestFree().SizeBytes < hw.MinInstallBytes:
		return "There isn’t enough free space to install alongside. Arctic Linux needs 40 GB."
	case !d.AlongsidePossible():
		return "This disk has no room for two more partitions, so Arctic Linux can’t install alongside. Erase the disk instead."
	default:
		return "This disk has no EFI system partition to share, so Arctic Linux can’t start alongside it. Erase the disk instead."
	}
}

// MsgDiskChanged is the Start error when the chosen disk changed after it was picked.
const MsgDiskChanged = "The disk changed since you picked it. Go back to the Disk step and check your choice."

// KeyboardView is the keyboard step's data as GetStep and SetStep return it: the choice plus
// the configuration it gives (xkb, read-only: SetStep ignores it). The live session applies
// xkb so passwords are typed on the same layouts as on the installed system.
type KeyboardView struct {
	KeyboardData
	XKB XKB `json:"xkb"`
}

func stepName(id string) string {
	if def, ok := FindStep(id); ok {
		return def.Name
	}
	return id
}

// ---- validation ----

// Validate checks a whole step. full also checks secrets and the network.
func (w *Wizard) Validate(id string, full bool) *protocol.Error {
	if id == StepNetwork && full {
		if !w.env.Network().Online {
			return protocol.Errorf(protocol.CodeOffline, "Connect to the internet to continue.")
		}
		return nil
	}
	if f := w.fieldErrors(id, full); len(f) > 0 {
		return protocol.FieldErrors("Fix the highlighted field to continue.", f)
	}
	return nil
}

func (w *Wizard) fieldErrors(id string, full bool) map[string]string {
	f := map[string]string{}
	switch id {
	case StepWelcome:
		if _, ok := FindLanguage(w.Data.Welcome.Language); !ok || !strings.HasSuffix(w.Data.Welcome.Language, ".UTF-8") {
			f["language"] = "Pick a language from the list."
		}
	case StepKeyboard:
		if _, ok := FindLayout(w.Data.Keyboard.Layout, w.Data.Keyboard.Variant); !ok {
			f["layout"] = "Pick a layout from the list."
		}
	case StepTimezone:
		if !ValidTimezone(w.Data.Timezone.Timezone) {
			f["timezone"] = "Pick a city from the list."
		}
	case StepDisk:
		d, ok := w.disk(w.Data.Disk.Disk)
		switch {
		case !ok || d.InstallMedia:
			f["disk"] = "Pick a disk from the list."
		case d.ReadOnly:
			f["disk"] = "This disk can’t be written to."
		case d.SizeBytes < hw.MinInstallBytes:
			f["disk"] = "This disk is too small. Arctic Linux needs at least 40 GB."
		}
		switch w.Data.Disk.Mode {
		case ModeErase:
		case ModeAlongside:
			if ok {
				if m := alongsideProblem(d, w.env.Firmware()); m != "" {
					f["mode"] = m
				}
			}
		default:
			f["mode"] = "Pick how to install."
		}
	case StepEncryption:
		if full && w.Data.Encryption.Enabled {
			s := w.env.Secrets()
			switch {
			case !s.LUKSSet:
				f["passphrase"] = "Type a passphrase."
			case s.LUKS.Score < MinPassphraseScore:
				f["passphrase"] = "Make it a bit longer — four random words work well."
			}
		}
	case StepAccount:
		a := w.Data.Account
		if m := ValidateFullName(a.FullName); m != "" {
			f["full_name"] = m
		}
		if m := w.usernameError(a.Username); m != "" {
			f["username"] = m
		}
		if m := ValidateHostname(a.Hostname); m != "" {
			f["hostname"] = m
		}
		if full {
			s := w.env.Secrets()
			switch {
			case !s.PasswordSet:
				f["password"] = "Type a password."
			case s.Password.Score == 0:
				f["password"] = "Use at least 8 characters."
			case s.Password.Score < MinPasswordScore:
				f["password"] = "That password is too easy to guess. Pick another one."
			}
		}
	case StepApps:
		for k, v := range w.env.Catalog().Validate(w.Data.Apps.Selection) {
			f[k] = v
		}
	}
	return f
}

// ---- summary ----

// Summary is the GetSummary result.
func (w *Wizard) Summary() protocol.SummaryResult {
	d := w.Data
	lang, _ := FindLanguage(d.Welcome.Language)
	kb, _ := FindLayout(d.Keyboard.Layout, d.Keyboard.Variant)
	city := LookupCity(d.Timezone.Timezone)
	tz := city.City
	if off := UTCOffsetLabel(d.Timezone.Timezone, w.env.Now()); off != "" && off != tz {
		tz += " (" + off + ")"
	}
	disk, _ := w.SelectedDisk()
	enc := "On — you’ll type your passphrase each time the computer starts"
	if !d.Encryption.Enabled {
		enc = "Off — anyone with this computer can read your files"
	}
	keyboard := kb.Name + " layout"
	if x := KeyboardConfig(d.Keyboard); !x.Latin {
		keyboard += ", plus English (US) for passwords — Alt+Shift switches"
	}
	diskName := strings.TrimSpace(disk.Model)
	if diskName == "" {
		diskName = disk.Path
	}
	var diskValue, warning, primary string
	if d.Disk.Mode == ModeAlongside {
		free := hw.SizeLabel(disk.LargestFree().SizeBytes)
		diskValue = fmt.Sprintf("Next to %s on %s (uses %s)", disk.OSName(), disk.Label(), free)
		warning = fmt.Sprintf("Arctic Linux will use %s of free space on %s. %s and its files stay as they are.", free, diskName, capitalize(disk.OSName()))
		primary = "Install alongside " + disk.OSName()
	} else {
		diskValue = fmt.Sprintf("Erase %s", disk.Label())
		warning = fmt.Sprintf("Installing will erase everything on %s. This can’t be undone.", diskName)
		primary = "Erase disk and install"
	}
	account := fmt.Sprintf("%s (%s) on %s", d.Account.FullName, d.Account.Username, d.Account.Hostname)
	if d.Account.Autologin {
		account += ", logs in automatically"
	}
	var apps []string
	cat := w.env.Catalog()
	for _, m := range cat.Apps(d.Apps.Selection) {
		apps = append(apps, m.DisplayShort())
	}
	rows := []protocol.SummaryRow{
		{Step: StepWelcome, Icon: "language", Label: "Language", Value: lang.Name},
		{Step: StepKeyboard, Icon: "keyboard", Label: "Keyboard", Value: keyboard},
		{Step: StepTimezone, Icon: "clock", Label: "Time zone", Value: tz},
		{Step: StepDisk, Icon: "disk", Label: "Disk", Value: diskValue},
		{Step: StepEncryption, Icon: "shield-lock", Label: "Encryption", Value: enc},
		{Step: StepAccount, Icon: "user", Label: "Account", Value: account},
		{Step: StepApps, Icon: "grid", Label: "Apps", Value: appList(apps)},
	}
	if v, ok := w.driversSummary(); ok {
		rows = append(rows, protocol.SummaryRow{Step: StepApps, Icon: "cpu", Label: "Drivers", Value: v})
	}
	return protocol.SummaryResult{
		Rows:         rows,
		Warning:      warning,
		PrimaryLabel: primary,
	}
}

// summaryApps is how many app names the Summary's Apps row lists before "and N more":
// the Summary page doesn't scroll, and a long pick would push the erase warning under
// the footer.
const summaryApps = 12

// appList is the Summary's Apps value: the names, or the first summaryApps of them and
// how many more.
func appList(names []string) string {
	if len(names) <= summaryApps {
		return strings.Join(names, ", ")
	}
	return fmt.Sprintf("%s and %d more", strings.Join(names[:summaryApps], ", "), len(names)-summaryApps)
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
