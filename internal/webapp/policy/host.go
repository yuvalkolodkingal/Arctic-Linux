package policy

import (
	"encoding/json"
	"fmt"
	"mime"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// ---- downloads ----

// SafeName makes a download's suggested name safe to create in your Downloads folder: the base
// name only, no control characters, no leading dots (no hidden or dot-dot files), at most 200
// bytes, and an extension from the MIME type when it has none.
func SafeName(suggested, mimeType string) string {
	name := suggested
	if i := strings.LastIndexAny(name, `/\`); i >= 0 {
		name = name[i+1:]
	}
	name = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || r == 0x202e || r == 0x202d || r == 0x2066 || r == 0x2067 || r == 0x2068 || r == 0x2069 {
			return -1
		}
		return r
	}, name)
	name = strings.TrimLeft(strings.TrimSpace(name), ".")
	if name == "" {
		name = "download"
	}
	if filepath.Ext(name) == "" && mimeType != "" {
		if exts, _ := mime.ExtensionsByType(mimeType); len(exts) > 0 {
			name += exts[0]
		}
	}
	for len(name) > 200 {
		ext := filepath.Ext(name)
		if len(ext) > 20 {
			ext = ""
		}
		base := strings.TrimSuffix(name, ext)
		cut := 200 - len(ext)
		for cut > 0 && !utf8.RuneStart(base[cut]) {
			cut--
		}
		name = base[:cut] + ext
	}
	return name
}

// Unique returns dir/name, or dir/"name (1).ext", "name (2).ext" … when it exists.
func Unique(dir, name string) string {
	p := filepath.Join(dir, name)
	if _, err := os.Lstat(p); os.IsNotExist(err) {
		return p
	}
	ext := filepath.Ext(name)
	base := strings.TrimSuffix(name, ext)
	for i := 1; i < 10000; i++ {
		p = filepath.Join(dir, fmt.Sprintf("%s (%d)%s", base, i, ext))
		if _, err := os.Lstat(p); os.IsNotExist(err) {
			return p
		}
	}
	return filepath.Join(dir, fmt.Sprintf("%s (%d)%s", base, time.Now().UnixNano(), ext))
}

// DownloadDir is XDG's download directory (user-dirs.dirs), else ~/Downloads.
func DownloadDir(home string) string {
	cfg := os.Getenv("XDG_CONFIG_HOME")
	if !filepath.IsAbs(cfg) {
		cfg = filepath.Join(home, ".config")
	}
	if data, err := os.ReadFile(filepath.Join(cfg, "user-dirs.dirs")); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			v, ok := strings.CutPrefix(strings.TrimSpace(line), "XDG_DOWNLOAD_DIR=")
			if !ok {
				continue
			}
			v = strings.Trim(v, `"`)
			v = strings.Replace(v, "$HOME", home, 1)
			if filepath.IsAbs(v) && v != home {
				return v
			}
		}
	}
	return filepath.Join(home, "Downloads")
}

// ---- crashes ----

// Crashes decides what a web-process crash does: reload once within a minute, then a banner.
type Crashes struct {
	last time.Time
	Now  func() time.Time
}

// Crash reasons (WebKitWebProcessTerminationReason).
const (
	CrashCrashed       = 0
	CrashMemory        = 1
	CrashTerminatedAPI = 2
)

// OnCrash returns true to reload automatically, false to show "This page stopped working."
func (c *Crashes) OnCrash(reason int) bool {
	now := time.Now()
	if c.Now != nil {
		now = c.Now()
	}
	if reason != CrashCrashed {
		return false
	}
	if !c.last.IsZero() && now.Sub(c.last) < time.Minute {
		return false
	}
	c.last = now
	return true
}

// ---- permissions ----

// Permission kinds the shim reports.
const (
	PermNotifications = 0
	PermCamera        = 1
	PermMicrophone    = 2
	PermScreen        = 3
	PermGeolocation   = 4
	PermClipboard     = 5
	PermPointerLock   = 6
	PermDeviceInfo    = 7
	PermMediaKeys     = 8
	PermWebsiteData   = 9
	PermOther         = 10
)

// Answers.
const (
	Deny  = 0
	Allow = 1
	Ask   = 2
)

// Permissions are the per-origin decisions you made, in permissions.json.
type Permissions struct {
	Schema  int                          `json:"schema"`
	Origins map[string]map[string]string `json:"origins"`
}

// permNames are the kinds a decision is remembered for, per origin. Not website data: that
// request (an embedded site asking for its cookies) belongs to the pair of the embedded site
// and the page, which WebKit's own store keeps; remembering it for the page alone would let
// every other embedded site in too.
var permNames = map[int]string{PermNotifications: "notifications", PermCamera: "camera", PermMicrophone: "microphone", PermScreen: "screen",
	PermGeolocation: "geolocation", PermClipboard: "clipboard", PermPointerLock: "pointer-lock", PermDeviceInfo: "device-info"}

// LoadPermissions reads permissions.json (empty when missing or broken).
func LoadPermissions(path string) *Permissions {
	p := &Permissions{Schema: 1, Origins: map[string]map[string]string{}}
	if data, err := os.ReadFile(path); err == nil {
		json.Unmarshal(data, p)
	}
	if p.Origins == nil {
		p.Origins = map[string]map[string]string{}
	}
	return p
}

// Save writes permissions.json (0600).
func (p *Permissions) Save(path string) error {
	data, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		return err
	}
	return webapp.WriteFileAtomic(path, append(data, '\n'), 0o600)
}

// Remember stores a decision for an origin.
func (p *Permissions) Remember(origin string, kind int, allow bool) {
	name, ok := permNames[kind]
	if !ok {
		return
	}
	if p.Origins[origin] == nil {
		p.Origins[origin] = map[string]string{}
	}
	v := "deny"
	if allow {
		v = "allow"
	}
	p.Origins[origin][name] = v
}

// Decide answers a permission request: a stored decision first; notifications follow the
// app's option (allow: in-scope origins get them, as Epiphany's app mode does); EME and XR are
// denied; device info only for an origin that already has camera or microphone; everything else
// asks you (an in-window banner the page can't draw over).
func (p *Permissions) Decide(origin string, kind int, s Scope, notifications string) int {
	// A global block overrides earlier grants. Screen sharing always requires a fresh
	// choice; an explicit block remains respected.
	if kind == PermNotifications && notifications == "block" {
		return Deny
	}
	if kind == PermScreen && p.Origins[origin]["screen"] != "deny" {
		return Ask
	}
	if name, ok := permNames[kind]; ok {
		switch p.Origins[origin][name] {
		case "allow":
			return Allow
		case "deny":
			return Deny
		}
	}
	switch kind {
	case PermNotifications:
		switch notifications {
		case "allow":
			if s.In(origin + "/") {
				return Allow
			}
			return Ask
		case "block":
			return Deny
		}
		return Ask
	case PermMediaKeys, PermOther:
		return Deny
	case PermDeviceInfo:
		if p.Origins[origin]["camera"] == "allow" || p.Origins[origin]["microphone"] == "allow" {
			return Allow
		}
		return Deny
	}
	return Ask
}

// ---- window state ----

// State is the window's state.json.
type State struct {
	Schema    int       `json:"schema"`
	Width     int       `json:"width"`
	Height    int       `json:"height"`
	Maximized bool      `json:"maximized"`
	Zoom      float64   `json:"zoom"`
	LastURL   string    `json:"last_url"`
	LastUsed  time.Time `json:"last_used"`
}

// LoadState reads state.json with defaults (1200×800, zoom 1) and sane bounds.
func LoadState(path string) State {
	s := State{Schema: 1, Width: 1200, Height: 800, Zoom: 1}
	if data, err := os.ReadFile(path); err == nil {
		json.Unmarshal(data, &s)
	}
	if s.Width < 360 || s.Width > 10000 {
		s.Width = 1200
	}
	if s.Height < 300 || s.Height > 10000 {
		s.Height = 800
	}
	if s.Zoom < 0.3 || s.Zoom > 5 {
		s.Zoom = 1
	}
	return s
}

// Save writes state.json (0600).
func (s State) Save(path string) error {
	s.Schema = 1
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return webapp.WriteFileAtomic(path, append(data, '\n'), 0o600)
}

// RestoreURL is where a restarted app opens: the last page when it is in scope and was used
// in the last 30 days, else the start URL.
func RestoreURL(st State, start string, s Scope, now time.Time) string {
	if st.LastURL != "" && s.In(st.LastURL) && now.Sub(st.LastUsed) < 30*24*time.Hour {
		return st.LastURL
	}
	return start
}

// LogURL strips the query and fragment before a URL goes into the log.
func LogURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return "(unparseable)"
	}
	u.RawQuery, u.Fragment, u.User = "", "", nil
	return u.String()
}
