// Package api is the wire contract of `arctic-webapp serve` (JSON lines on stdin/stdout, the
// internal/protocol envelope) and of the one-line `--json` output (docs/BUILD-SPEC.md §11).
// Every name is snake_case; api_test pins them, because the shell's Get apps and Remove apps
// pages and Settings are written against exactly these shapes.
//
//	request  {"id": 1, "method": "Inspect", "params": {"url": "music.youtube.com"}}
//	response {"id": 1, "result": {...}}  or  {"id": 1, "error": {"code", "message", "fields"}}
//	event    {"event": "progress", "request": 1, "stage": "page", "message": "…"}
//	         {"event": "changed", "ids": ["org.arcticlinux.WebApp.…"]}
package api

import "encoding/json"

// Methods.
const (
	MethodHello     = "Hello"
	MethodRuntimes  = "Runtimes"
	MethodInspect   = "Inspect"
	MethodInstall   = "Install"
	MethodList      = "List"
	MethodGet       = "Get"
	MethodLaunch    = "Launch"
	MethodUpdate    = "Update"
	MethodSet       = "Set"
	MethodRemove    = "Remove"
	MethodForget    = "Forget"
	MethodClearData = "ClearData"
	MethodCancel    = "Cancel"
)

// Events.
const (
	EventProgress = "progress"
	EventChanged  = "changed"
)

// Progress stages.
const (
	StagePage     = "page"
	StageManifest = "manifest"
	StageIcons    = "icons"
	StageRender   = "render"
)

// ProgressEvent reports a long request's stage; request is the request's id.
type ProgressEvent struct {
	Event   string          `json:"event"`
	Request json.RawMessage `json:"request"`
	Stage   string          `json:"stage"`
	Message string          `json:"message"`
}

// ChangedEvent tells the shell to refresh these apps.
type ChangedEvent struct {
	Event string   `json:"event"`
	IDs   []string `json:"ids"`
}

// Runtime is one engine a web app can run in.
type Runtime struct {
	ID        string          `json:"id"` // webkit | chromium:<variant>
	Name      string          `json:"name"`
	Available bool            `json:"available"`
	DRM       bool            `json:"drm"`
	WebRTC    bool            `json:"webrtc"`
	Install   *RuntimeInstall `json:"install,omitempty"` // how to get it, when not available
}

// RuntimeInstall names the catalog module (and method) that installs a runtime.
type RuntimeInstall struct {
	Module string `json:"module"`
	Method string `json:"method"` // dnf | flatpak
	Ref    string `json:"ref,omitempty"`
}

// HelloResult answers Hello.
type HelloResult struct {
	EngineVersion   string    `json:"engine_version"`
	ProtocolVersion int       `json:"protocol_version"`
	Runtimes        []Runtime `json:"runtimes"`
}

// RuntimesResult answers Runtimes.
type RuntimesResult struct {
	Runtimes []Runtime `json:"runtimes"`
}

// ---- Inspect ----

type InspectParams struct {
	URL string `json:"url"`
}

type Scope struct {
	Site     string `json:"site"`
	Scheme   string `json:"scheme"`
	Manifest string `json:"manifest"`
}

// IconChoice is one icon the preview offers; path is a PNG rendered for the preview.
type IconChoice struct {
	Index   int    `json:"index"`
	Source  string `json:"source"`
	Purpose string `json:"purpose,omitempty"`
	Size    int    `json:"size"`
	Format  string `json:"format"`
	Path    string `json:"path"`
}

// Warning is a notice under the preview; it never blocks an install.
type Warning struct {
	Code    string `json:"code"` // drm_unsupported | calls_unsupported | login_wall | insecure
	Message string `json:"message"`
}

// Preview is the Inspect result (and `inspect --json`'s "preview").
type Preview struct {
	Token             string       `json:"token"`
	URL               string       `json:"url"`
	FinalURL          string       `json:"final_url"`
	Host              string       `json:"host"`
	HostASCII         string       `json:"host_ascii"`
	Secure            bool         `json:"secure"`
	Name              string       `json:"name"`
	NameSource        string       `json:"name_source"`
	ShortName         string       `json:"short_name"`
	StartURL          string       `json:"start_url"`
	Scope             Scope        `json:"scope"`
	ManifestURL       string       `json:"manifest_url"`
	Display           string       `json:"display"`
	ThemeColor        string       `json:"theme_color"`
	Category          string       `json:"category"`
	SuggestedID       string       `json:"suggested_id"`
	Installed         []string     `json:"installed"` // ids of apps already made from this site
	Icons             []IconChoice `json:"icons"`
	RecommendedIcon   int          `json:"recommended_icon"`
	HandlersSupported []string     `json:"handlers_supported"`
	Warnings          []Warning    `json:"warnings"`
	SuggestedRuntime  string       `json:"suggested_runtime"`
}

// ---- Install ----

// InstallParams: a preview token (or a url, which inspects first) and your choices. Icon is an
// index into the preview's icons, or the string "monogram"; icon_file / icon_url pick another.
type InstallParams struct {
	Token         string          `json:"token,omitempty"`
	URL           string          `json:"url,omitempty"`
	Name          string          `json:"name,omitempty"`
	Icon          json.RawMessage `json:"icon,omitempty"`
	IconFile      string          `json:"icon_file,omitempty"`
	IconURL       string          `json:"icon_url,omitempty"`
	Category      string          `json:"category,omitempty"`
	Runtime       string          `json:"runtime,omitempty"`
	Links         string          `json:"links,omitempty"`
	Notifications string          `json:"notifications,omitempty"`
	MailLinks     bool            `json:"mail_links,omitempty"`
	NewCopy       bool            `json:"new_copy,omitempty"`
	Launch        bool            `json:"launch,omitempty"`
}

type InstallResult struct {
	App         AppInfo `json:"app"`
	DesktopFile string  `json:"desktop_file"`
	Launched    bool    `json:"launched"`
}

// ---- List / Get ----

type ListParams struct {
	Sizes bool `json:"sizes,omitempty"`
	Kept  bool `json:"kept,omitempty"`
}

// TLSExceptionInfo is a pinned certificate without its PEM.
type TLSExceptionInfo struct {
	Host   string `json:"host"`
	SHA256 string `json:"sha256"`
}

// AppInfo is one app in List, Get and results. Problem is "" | no-desktop-file | no-registry |
// runtime-missing: orphans are listed so Remove apps can clean them up.
type AppInfo struct {
	ID                string             `json:"id"`
	Name              string             `json:"name"`
	URL               string             `json:"url"`
	Host              string             `json:"host"`
	IconName          string             `json:"icon_name"`
	IconPath          string             `json:"icon_path"`
	Category          string             `json:"category"`
	Runtime           string             `json:"runtime"`
	RuntimeAvailable  bool               `json:"runtime_available"`
	Running           bool               `json:"running"`
	Links             string             `json:"links"`
	Notifications     string             `json:"notifications"`
	Devtools          bool               `json:"devtools"`
	Rendering         string             `json:"rendering"`
	ExtraDomains      []string           `json:"extra_domains"`
	Handlers          []string           `json:"handlers"`
	HandlersSupported []string           `json:"handlers_supported"`
	TLSExceptions     []TLSExceptionInfo `json:"tls_exceptions"`
	DataBytes         *int64             `json:"data_bytes"`
	Problem           string             `json:"problem"`
	Created           string             `json:"created"`
	Updated           string             `json:"updated"`
	KeepRunning       bool               `json:"keep_running"`
	StartAtLogin      bool               `json:"start_at_login"`
	AskDownload       bool               `json:"ask_download"`
}

// KeptInfo is sign-in data left by `remove --keep-data`.
type KeptInfo struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	URL       string `json:"url"`
	DataBytes *int64 `json:"data_bytes"`
}

// ListResult: kept is present (possibly []) exactly when it was asked for (a nil Kept leaves
// it out; plain omitempty would also drop an empty list).
type ListResult struct {
	Apps []AppInfo  `json:"apps"`
	Kept []KeptInfo `json:"kept,omitempty"`
}

func (r ListResult) MarshalJSON() ([]byte, error) {
	out := struct {
		Apps []AppInfo   `json:"apps"`
		Kept *[]KeptInfo `json:"kept,omitempty"`
	}{Apps: r.Apps}
	if r.Kept != nil {
		out.Kept = &r.Kept
	}
	return json.Marshal(out)
}

type GetParams struct {
	ID    string `json:"id"`
	Sizes bool   `json:"sizes,omitempty"`
}

type AppResult struct {
	App AppInfo `json:"app"`
}

// ---- Launch ----

type LaunchParams struct {
	ID  string `json:"id"`
	URL string `json:"url,omitempty"`
}

// LaunchResult: pid of the started process, or focused when a running app was raised.
type LaunchResult struct {
	Pid     int  `json:"pid,omitempty"`
	Focused bool `json:"focused,omitempty"`
}

// ---- Update ----

type UpdateParams struct {
	IDs []string `json:"ids"`
	All bool     `json:"all,omitempty"`
}

// Updated reports what update changed and which of your own edits it kept.
type Updated struct {
	ID      string   `json:"id"`
	Changed []string `json:"changed"`
	Kept    []string `json:"kept"`
}

type UpdateResult struct {
	Updated []Updated `json:"updated"`
}

// ---- Set ----

// SetIcon changes the icon: a file, "monogram" (letter icon), a URL, or refresh from the site.
type SetIcon struct {
	File     string `json:"file,omitempty"`
	Monogram bool   `json:"monogram,omitempty"`
	URL      string `json:"url,omitempty"`
}

// SetParams: only the fields present change. Pointer fields tell "absent" from "off".
type SetParams struct {
	KeepRunning       *bool    `json:"keep_running,omitempty"`
	StartAtLogin      *bool    `json:"start_at_login,omitempty"`
	AskDownload       *bool    `json:"ask_download,omitempty"`
	ID                string   `json:"id"`
	Name              *string  `json:"name,omitempty"`
	Icon              *SetIcon `json:"icon,omitempty"`
	Category          *string  `json:"category,omitempty"`
	Runtime           *string  `json:"runtime,omitempty"`
	Links             *string  `json:"links,omitempty"`
	ExtraDomains      []string `json:"extra_domains,omitempty"` // replaces the list
	AddDomain         string   `json:"add_domain,omitempty"`
	RemoveDomain      string   `json:"remove_domain,omitempty"`
	Notifications     *string  `json:"notifications,omitempty"`
	MailLinks         *bool    `json:"mail_links,omitempty"`
	Devtools          *bool    `json:"devtools,omitempty"`
	Rendering         *string  `json:"rendering,omitempty"`
	ResetPermissions  bool     `json:"reset_permissions,omitempty"`
	ForgetCertificate string   `json:"forget_certificate,omitempty"`
}

// SetResult: applied is live (the running app took it), next_start or saved (files only).
type SetResult struct {
	App     AppInfo `json:"app"`
	Applied string  `json:"applied"`
}

// ---- Remove / Forget / ClearData / Cancel ----

type RemoveParams struct {
	IDs      []string `json:"ids"`
	KeepData bool     `json:"keep_data,omitempty"`
}

type Removed struct {
	ID       string `json:"id"`
	Stopped  bool   `json:"stopped"`
	KeptData bool   `json:"kept_data"`
}

type RemoveResult struct {
	Removed []Removed `json:"removed"`
}

type IDsParams struct {
	IDs []string `json:"ids"`
}

type IDParams struct {
	ID string `json:"id"`
}

type CancelParams struct {
	Request json.RawMessage `json:"request"`
}

// Empty is the {} result.
type Empty struct{}

// ---- CLI-only results ----

type RepairResult struct {
	Repaired       []string `json:"repaired"`
	OrphansRemoved []string `json:"orphans_removed"`
}

type VersionResult struct {
	Version       string `json:"version"`
	Host          string `json:"host"`
	HostPresent   bool   `json:"host_present"`
	WebKitVersion string `json:"webkit_version,omitempty"`
}
