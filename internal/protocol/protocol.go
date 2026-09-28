// Package protocol defines the engine <-> installer UI protocol (BUILD-SPEC §4): newline
// delimited JSON over a unix socket, one object per line.
//
//	request  {"id": 7, "method": "SetStep", "params": {...}}
//	response {"id": 7, "result": {...}}
//	         {"id": 7, "error": {"code": "invalid", "message": "…", "fields": {"username": "…"}}}
//	event    {"event": "progress", ...}   (no id; sent to every connection after Subscribe)
//
// Tell events from responses by the "event" key: module events also carry an "id" (the
// module id), so the absence of "id" is not a reliable test.
//
// Notes on semantics that the table in the spec leaves open:
//   - SetStep stores the submitted draft even when it answers with field errors, so the engine
//     always holds exactly what the UI shows. Next refuses to leave a step that has errors.
//   - GetWizard step titles are the short rail labels ("Time zone"); GetStep titles are the
//     screen headings ("Where are you?").
//   - After Goto from Summary, Next on the edited step returns straight to Summary as long as
//     every step in between is still done (a changed language shows Keyboard first).
//   - After a fatal failure (state "failed"), Back goes to Summary and Goto to a done step (or
//     Summary); both return to the wizard with every answer and secret kept. Start retries.
//   - Start re-probes the disks and refuses (code "state") when the chosen disk changed since
//     it was picked, until the Disk step is passed again.
package protocol

import (
	"encoding/json"
	"fmt"
)

// Version is the protocol version reported by Hello.
const Version = 1

// Method names.
const (
	MethodHello             = "Hello"
	MethodGetWizard         = "GetWizard"
	MethodGetStep           = "GetStep"
	MethodSetStep           = "SetStep"
	MethodNext              = "Next"
	MethodBack              = "Back"
	MethodGoto              = "Goto"
	MethodScanWifi          = "ScanWifi"
	MethodConnectWifi       = "ConnectWifi"
	MethodNetworkState      = "NetworkState"
	MethodCheckPassphrase   = "CheckPassphrase"
	MethodSuggestPassphrase = "SuggestPassphrase"
	MethodSuggestAccount    = "SuggestAccount"
	MethodSetSecrets        = "SetSecrets"
	MethodEstimateDownload  = "EstimateDownload"
	MethodGetCatalog        = "GetCatalog"
	MethodGetSummary        = "GetSummary"
	MethodStart             = "Start"
	MethodRetryModule       = "RetryModule"
	MethodSkipModule        = "SkipModule"
	MethodSaveLog           = "SaveLog"
	MethodReboot            = "Reboot"
	MethodSubscribe         = "Subscribe"
)

// SecretMethods carry secrets in their params; their params are never logged.
var SecretMethods = map[string]bool{
	MethodSetSecrets:      true,
	MethodConnectWifi:     true,
	MethodCheckPassphrase: true,
}

// Error codes.
const (
	CodeInvalid    = "invalid"     // validation failed; see Fields
	CodeBadRequest = "bad_request" // malformed JSON / params
	CodeUnknown    = "unknown_method"
	CodeState      = "state"     // not allowed right now (e.g. Goto to a todo step, Start twice)
	CodeNotFound   = "not_found" // unknown step / module / disk
	CodeAuth       = "auth"      // Wi-Fi password rejected
	CodeTimeout    = "timeout"   // Wi-Fi connect timed out
	CodeOffline    = "offline"   // network step without a connection
	CodeInternal   = "internal"
)

// Request is one call from the UI.
type Request struct {
	ID     json.RawMessage `json:"id,omitempty"`
	Method string          `json:"method"`
	Params json.RawMessage `json:"params,omitempty"`
}

// Response answers one Request (same id).
type Response struct {
	ID     json.RawMessage `json:"id,omitempty"`
	Result any             `json:"result,omitempty"`
	Error  *Error          `json:"error,omitempty"`
}

// Error is a structured error. Fields maps a data field (or category id) to a message shown
// next to it.
type Error struct {
	Code    string            `json:"code"`
	Message string            `json:"message"`
	Fields  map[string]string `json:"fields,omitempty"`
}

func (e *Error) Error() string {
	if len(e.Fields) > 0 {
		return fmt.Sprintf("%s: %s %v", e.Code, e.Message, e.Fields)
	}
	return e.Code + ": " + e.Message
}

// Errorf builds an Error.
func Errorf(code, format string, a ...any) *Error {
	return &Error{Code: code, Message: fmt.Sprintf(format, a...)}
}

// FieldErrors builds an "invalid" error with per-field messages.
func FieldErrors(message string, fields map[string]string) *Error {
	return &Error{Code: CodeInvalid, Message: message, Fields: fields}
}

// ---- params and results ----

type HelloParams struct {
	Client  string `json:"client"`
	Version any    `json:"version,omitempty"`
}

type HelloResult struct {
	EngineVersion   string `json:"engine_version"`
	ProtocolVersion int    `json:"protocol_version"`
	Mock            bool   `json:"mock"`
	Live            bool   `json:"live"`
	Firmware        string `json:"firmware"`
	State           string `json:"state"` // wizard | installing | attention | failed | done
}

type StepState struct {
	ID    string `json:"id"`
	Title string `json:"title"`
	State string `json:"state"` // done | current | todo | error
}

type WizardResult struct {
	Steps   []StepState `json:"steps"`
	Current string      `json:"current"`
	State   string      `json:"state"`
}

type IDParams struct {
	ID string `json:"id"`
}

type StepResult struct {
	ID      string `json:"id"`
	Title   string `json:"title"`
	Help    string `json:"help"`
	Note    string `json:"note,omitempty"`    // bottom-left reassurance note
	Primary string `json:"primary,omitempty"` // label of the primary button
	Data    any    `json:"data"`
	Options any    `json:"options"`
}

type SetStepParams struct {
	ID   string          `json:"id"`
	Data json.RawMessage `json:"data"`
}

type SetStepResult struct {
	OK   bool `json:"ok"`
	Data any  `json:"data"`
}

type OKResult struct {
	OK bool `json:"ok"`
}

type WifiNetwork struct {
	SSID      string `json:"ssid"`
	Signal    int    `json:"signal"`
	Secure    bool   `json:"secure"`
	Connected bool   `json:"connected"`
}

type ScanWifiResult struct {
	Networks []WifiNetwork `json:"networks"`
}

type ConnectWifiParams struct {
	SSID     string `json:"ssid"`
	Password string `json:"password"`
}

type NetworkState struct {
	Online bool   `json:"online"`
	Wired  bool   `json:"wired"`
	SSID   string `json:"ssid,omitempty"`
}

type TextParams struct {
	Text string `json:"text"`
}

type PassphraseResult struct {
	Score int    `json:"score"`
	Label string `json:"label"`
	Words int    `json:"words"`
	OK    bool   `json:"ok"`
}

type SuggestPassphraseResult struct {
	Text string `json:"text"`
}

type SuggestAccountParams struct {
	FullName string `json:"full_name"`
}

type SuggestAccountResult struct {
	Username string `json:"username"`
	Hostname string `json:"hostname"`
}

type SetSecretsParams struct {
	LUKSPassphrase *string `json:"luks_passphrase,omitempty"`
	UserPassword   *string `json:"user_password,omitempty"`
}

type EstimateParams struct {
	Selection map[string][]string `json:"selection"`
}

type EstimateResult struct {
	Apps  int    `json:"apps"`
	Bytes int64  `json:"bytes"`
	Label string `json:"label"`
}

type SummaryRow struct {
	Step  string `json:"step"`
	Icon  string `json:"icon,omitempty"`
	Label string `json:"label"`
	Value string `json:"value"`
}

type SummaryResult struct {
	Rows         []SummaryRow `json:"rows"`
	Warning      string       `json:"warning"`
	PrimaryLabel string       `json:"primary_label"`
}

// SaveLogResult says where SaveLog put the log. Path is the file's real path when it was
// written: under a mount point that stays reachable (an already mounted stick, the live
// user's home, /tmp), or, for a USB stick the engine mounted itself and unmounted again (so it
// can be unplugged), the file's path from the root of that stick with Device and Label set.
type SaveLogResult struct {
	Path string `json:"path"`
	// OnUSB is true when the log is on a removable disk (it survives a restart).
	OnUSB bool `json:"on_usb"`
	// Device is the partition written to (USB only), e.g. "/dev/sdc1".
	Device string `json:"device,omitempty"`
	// Label names the stick (file system label, else the disk model), e.g. "KINGSTON".
	Label string `json:"label,omitempty"`
	// SafeToRemove is true when the stick was unmounted again after writing.
	SafeToRemove bool `json:"safe_to_remove"`
	// Message is the sentence to show, e.g. "Saved arctic-install-….log to the USB stick
	// KINGSTON. You can unplug it now." or, without a stick, where the file is and that it is
	// lost when the computer restarts.
	Message string `json:"message"`
}

// ---- events ----

// Event names.
const (
	EventProgress  = "progress"
	EventModule    = "module"
	EventAttention = "attention"
	EventFailed    = "failed"
	EventDone      = "done"
	EventWizard    = "wizard" // wizard changed (sent after Start / done so a second UI stays in sync)
)

// Install phases.
const (
	PhaseDisk       = "disk"
	PhaseCopy       = "copy"
	PhaseConfigure  = "configure"
	PhaseBootloader = "bootloader"
	PhaseApps       = "apps"
	PhaseFinalize   = "finalize"
)

// Module statuses.
const (
	ModQueued      = "queued"
	ModDownloading = "downloading"
	ModInstalled   = "installed"
	ModFailed      = "failed"
	ModSkipped     = "skipped"
	ModDeferred    = "deferred"
	ModRemoved     = "removed"
)

type Substep struct {
	ID    string `json:"id"`
	Label string `json:"label"`
	State string `json:"state"` // done | active | todo | error
}

type ProgressEvent struct {
	Event       string    `json:"event"`
	Percent     int       `json:"percent"`
	Phase       string    `json:"phase"`
	Status      string    `json:"status"`
	ETASeconds  int       `json:"eta_seconds"`
	ETALabel    string    `json:"eta_label,omitempty"`
	AppsDone    int       `json:"apps_done"`
	AppsTotal   int       `json:"apps_total"`
	Substeps    []Substep `json:"substeps"`
	Paused      bool      `json:"paused,omitempty"`
	PausedLabel string    `json:"paused_label,omitempty"`
}

type ModuleEvent struct {
	Event   string `json:"event"`
	ID      string `json:"id"`
	Name    string `json:"name"`
	Status  string `json:"status"`
	Percent int    `json:"percent"`
}

type ModuleRef struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type AttentionEvent struct {
	Event    string    `json:"event"`
	Module   ModuleRef `json:"module"`
	Title    string    `json:"title"`   // "Steam couldn't be downloaded"
	Message  string    `json:"message"` // "The download server didn't answer."
	Help     string    `json:"help"`    // "Everything else is fine — Steam is optional …"
	Details  string    `json:"details,omitempty"`
	Optional bool      `json:"optional"`
	Retry    string    `json:"retry_label"` // "Try again"
	Skip     string    `json:"skip_label"`  // "Skip Steam"
}

type FailedEvent struct {
	Event   string `json:"event"`
	Title   string `json:"title"`
	Message string `json:"message"`
	Details string `json:"details,omitempty"`
	Fatal   bool   `json:"fatal"`
	// CanChange is true when Back / Goto may leave the failure to change answers (then
	// Start again). Start alone retries with the same answers.
	CanChange bool `json:"can_change,omitempty"`
}

type DoneEvent struct {
	Event         string   `json:"event"`
	AppsInstalled int      `json:"apps_installed"`
	FirstName     string   `json:"first_name"`
	Deferred      []string `json:"deferred,omitempty"`
	Title         string   `json:"title"`
	Help          string   `json:"help"`
	// Drivers are the drivers the install put on (or put off), with a sentence for each.
	Drivers []DriverResult `json:"drivers,omitempty"`
	// SecureBoot is set when a driver's signing key has to be enrolled after the restart
	// (Secure Boot is on): the one-time code and the steps of the firmware's MOK screen.
	SecureBoot *SecureBootInfo `json:"secure_boot,omitempty"`
	// Notes are sentences about an install that succeeded with a caveat (the new disk
	// couldn't be closed at the end, …).
	Notes []string `json:"notes,omitempty"`
}

// Driver statuses (DriverResult.Status).
const (
	DriverInstalled = "installed" // built and installed; starts after the restart
	DriverDeferred  = "deferred"  // installed at first boot, once online
	DriverSkipped   = "skipped"   // the person skipped it after a failure
)

// DriverResult is one driver of the Done screen.
type DriverResult struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Device string `json:"device"` // "NVIDIA GeForce RTX 4060 Max-Q / Mobile"
	Status string `json:"status"` // installed | deferred | skipped
	Text   string `json:"text"`   // "The NVIDIA driver for your … starts after you restart."
}

// SecureBootInfo tells the person how to enroll the driver signing key (a Machine Owner Key)
// in shim's MokManager on the first restart. Code is the one-time password MokManager asks
// for: digits only, typed with the number row (MokManager maps the keyboard as US QWERTY).
// Failed means the enrolment couldn't be requested: Title/Steps then say how to do it later.
type SecureBootInfo struct {
	Code   string   `json:"code,omitempty"`
	Title  string   `json:"title"`
	Intro  string   `json:"intro"`
	Steps  []string `json:"steps"`
	Note   string   `json:"note"`
	Failed bool     `json:"failed,omitempty"`
}

type WizardEvent struct {
	Event string `json:"event"`
	WizardResult
}
