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
//     every step in between is still done.
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

type SaveLogResult struct {
	Path string `json:"path"`
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
}

type DoneEvent struct {
	Event         string   `json:"event"`
	AppsInstalled int      `json:"apps_installed"`
	FirstName     string   `json:"first_name"`
	Deferred      []string `json:"deferred,omitempty"`
	Title         string   `json:"title"`
	Help          string   `json:"help"`
}

type WizardEvent struct {
	Event string `json:"event"`
	WizardResult
}
