package webapp

import (
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

// App is one web app's record, app.json schema 1 (docs/BUILD-SPEC.md §11). Only the manager
// writes it, always under the registry lock; the host reads it.
type App struct {
	Schema        int            `json:"schema"`
	Render        int            `json:"render"`
	EngineVersion string         `json:"engine_version"`
	ID            string         `json:"id"`
	Copy          int            `json:"copy"`
	Name          string         `json:"name"`
	NameSource    string         `json:"name_source"`
	InputURL      string         `json:"input_url"`
	StartURL      string         `json:"start_url"`
	ManifestURL   string         `json:"manifest_url"`
	ManifestID    string         `json:"manifest_id"`
	Scope         Scope          `json:"scope"`
	ExtraDomains  []string       `json:"extra_domains"`
	Category      string         `json:"category"`
	ThemeColor    string         `json:"theme_color"` // informational only: the chrome stays Arctic
	Icon          Icon           `json:"icon"`
	Runtime       string         `json:"runtime"`
	WMClass       string         `json:"wm_class"`
	Handlers      []string       `json:"handlers"`
	Options       Options        `json:"options"`
	TLSExceptions []TLSException `json:"tls_exceptions"`
	UserSet       []string       `json:"user_set"`
	Created       time.Time      `json:"created"`
	Updated       time.Time      `json:"updated"`
}

// Scope decides which pages belong to the app: Site is the registrable domain (eTLD+1, or the
// exact host:port for IP literals and localhost). Manifest is informational.
type Scope struct {
	Site     string `json:"site"`
	Scheme   string `json:"scheme"`
	Manifest string `json:"manifest"`
}

// Icon records where the app's icon came from. Name changes to <id>.r<Rev> after each change.
type Icon struct {
	Name    string `json:"name"`
	Rev     int    `json:"rev"`
	Source  string `json:"source"`
	URL     string `json:"url,omitempty"`
	SHA256  string `json:"sha256,omitempty"`
	Purpose string `json:"purpose,omitempty"`
}

// Options are the settings you can change while the app runs (SIGHUP applies them live).
type Options struct {
	Links         string `json:"links"`         // browser | app
	Notifications string `json:"notifications"` // allow | ask | block
	Devtools      bool   `json:"devtools"`
	Rendering     string `json:"rendering"` // auto | software
}

// TLSException pins one certificate for one private-network host (docs/BUILD-SPEC.md §11).
type TLSException struct {
	Host   string `json:"host"`
	SHA256 string `json:"sha256"`
	PEM    string `json:"pem"`
}

// Accepted values.
var (
	Categories    = []string{"Network", "AudioVideo", "Game", "Office", "Development", "Education", "Graphics", "Utility", "Calendar"}
	LinkModes     = []string{"browser", "app"}
	NotifyModes   = []string{"allow", "ask", "block"}
	RenderModes   = []string{"auto", "software"}
	ChromiumTypes = []string{"chromium", "ungoogled", "brave", "chrome", "vivaldi"}
	IconSources   = []string{"manifest", "apple-touch", "link", "favicon-ico", "svg", "host-favicon", "monogram", "user", "url"}
	NameSources   = []string{"manifest", "title", "meta", "host", "user"}
)

// DefaultOptions are a new app's options.
func DefaultOptions() Options {
	return Options{Links: "browser", Notifications: "allow", Rendering: "auto"}
}

func oneOf(v string, list []string) bool {
	for _, x := range list {
		if v == x {
			return true
		}
	}
	return false
}

// ValidRuntime accepts "webkit" and "chromium:<variant>".
func ValidRuntime(r string) bool {
	if r == "webkit" {
		return true
	}
	v, ok := strings.CutPrefix(r, "chromium:")
	return ok && oneOf(v, ChromiumTypes)
}

// Identity is what the id's hash is computed from: the manifest id when there is one, else the
// start URL without its fragment; later copies append #N.
func (a *App) Identity() string {
	return Identity(a.ManifestID, a.StartURL, a.Copy)
}

// Identity builds the canonical identity of a site (see App.Identity).
func Identity(manifestID, startURL string, copyN int) string {
	s := manifestID
	if s == "" {
		s = startURL
	}
	if i := strings.IndexByte(s, '#'); i >= 0 {
		s = s[:i]
	}
	if copyN > 1 {
		s += fmt.Sprintf("#%d", copyN)
	}
	return s
}

// IconName is the current icon name (<id>, then <id>.r<N> after each change).
func (a *App) IconName() string {
	if a.Icon.Rev == 0 {
		return a.ID
	}
	return fmt.Sprintf("%s.r%d", a.ID, a.Icon.Rev)
}

// Host is the start URL's host (with port), for the launcher's second line.
func (a *App) Host() string {
	u, err := url.Parse(a.StartURL)
	if err != nil {
		return ""
	}
	return u.Host
}

// HasHandler reports whether the app opens links of this scheme (only "mailto" exists).
func (a *App) HasHandler(h string) bool { return oneOf(h, a.Handlers) }

// IsUserSet reports whether you changed this field yourself (update never overwrites it).
func (a *App) IsUserSet(field string) bool { return oneOf(field, a.UserSet) }

// MarkUserSet records a field you changed.
func (a *App) MarkUserSet(field string) {
	if !a.IsUserSet(field) {
		a.UserSet = append(a.UserSet, field)
	}
}

// Normalize fills defaults for fields an older or hand-written record left empty, so readers
// never see nil lists.
func (a *App) Normalize() {
	if a.Copy == 0 {
		a.Copy = 1
	}
	if a.Runtime == "" {
		a.Runtime = "webkit"
	}
	if a.Category == "" {
		a.Category = "Network"
	}
	d := DefaultOptions()
	if a.Options.Links == "" {
		a.Options.Links = d.Links
	}
	if a.Options.Notifications == "" {
		a.Options.Notifications = d.Notifications
	}
	if a.Options.Rendering == "" {
		a.Options.Rendering = d.Rendering
	}
	if a.Icon.Name == "" {
		a.Icon.Name = a.IconName()
	}
	if a.WMClass == "" && a.Runtime == "webkit" {
		a.WMClass = a.ID
	}
	for _, p := range []*[]string{&a.ExtraDomains, &a.Handlers, &a.UserSet} {
		if *p == nil {
			*p = []string{}
		}
	}
	if a.TLSExceptions == nil {
		a.TLSExceptions = []TLSException{}
	}
}

// Validate rejects a record that could inject Exec arguments or reach outside its directory:
// a bad id, a URL that is not http(s), an unknown value, a TLS exception for a public host.
func (a *App) Validate() error {
	if !Valid(a.ID) {
		return fmt.Errorf("%q is not a web-app id", a.ID)
	}
	if a.Schema != Schema {
		return fmt.Errorf("%s: unknown schema %d", a.ID, a.Schema)
	}
	if err := checkWebURL(a.StartURL); err != nil {
		return fmt.Errorf("%s: start_url: %v", a.ID, err)
	}
	if a.ManifestURL != "" {
		if err := checkWebURL(a.ManifestURL); err != nil {
			return fmt.Errorf("%s: manifest_url: %v", a.ID, err)
		}
	}
	if strings.TrimSpace(a.Name) == "" || len([]rune(a.Name)) > 64 {
		return fmt.Errorf("%s: the name must have 1 to 64 characters", a.ID)
	}
	if a.Scope.Site == "" || strings.ContainsAny(a.Scope.Site, "/\\ \t\n") {
		return fmt.Errorf("%s: bad scope site %q", a.ID, a.Scope.Site)
	}
	if a.Scope.Scheme != "https" && a.Scope.Scheme != "http" {
		return fmt.Errorf("%s: bad scope scheme %q", a.ID, a.Scope.Scheme)
	}
	for _, d := range a.ExtraDomains {
		if !ValidDomain(d) {
			return fmt.Errorf("%s: bad extra domain %q", a.ID, d)
		}
	}
	if !oneOf(a.Category, Categories) {
		return fmt.Errorf("%s: unknown category %q", a.ID, a.Category)
	}
	if !ValidRuntime(a.Runtime) {
		return fmt.Errorf("%s: unknown runtime %q", a.ID, a.Runtime)
	}
	for _, h := range a.Handlers {
		if h != "mailto" {
			return fmt.Errorf("%s: unknown handler %q", a.ID, h)
		}
	}
	if !oneOf(a.Options.Links, LinkModes) || !oneOf(a.Options.Notifications, NotifyModes) || !oneOf(a.Options.Rendering, RenderModes) {
		return fmt.Errorf("%s: unknown option value", a.ID)
	}
	if a.Icon.Name != a.IconName() {
		return fmt.Errorf("%s: icon name %q does not match its revision", a.ID, a.Icon.Name)
	}
	for _, e := range a.TLSExceptions {
		if !PrivateHostLiteral(e.Host) {
			return fmt.Errorf("%s: a certificate exception names a public host (%s)", a.ID, e.Host)
		}
	}
	return nil
}

func checkWebURL(s string) error {
	u, err := url.Parse(s)
	if err != nil {
		return err
	}
	if (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" || u.User != nil {
		return fmt.Errorf("%q is not an http(s) address", s)
	}
	if strings.ContainsAny(s, " \t\r\n\x00") {
		return fmt.Errorf("%q has spaces or control characters", s)
	}
	return nil
}

// ValidDomain accepts a lowercase DNS name (optionally with a port) for extra_domains.
func ValidDomain(d string) bool {
	host := d
	if h, p, err := net.SplitHostPort(d); err == nil {
		host = h
		if p == "" || strings.Trim(p, "0123456789") != "" {
			return false
		}
	}
	if host == "" || len(host) > 253 || strings.HasPrefix(host, ".") || strings.HasSuffix(host, ".") {
		return false
	}
	if net.ParseIP(host) != nil {
		return true
	}
	for _, label := range strings.Split(host, ".") {
		if label == "" || len(label) > 63 || strings.HasPrefix(label, "-") || strings.HasSuffix(label, "-") {
			return false
		}
		for _, r := range label {
			if !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '-') {
				return false
			}
		}
	}
	return true
}

// PrivateHostLiteral reports whether a host[:port] names a private-network host by its text
// alone: loopback, RFC 1918, ULA or link-local IP literals, localhost, and names ending .local,
// .lan, .home.arpa or .internal. (For names, the manager also checks every resolved address.)
func PrivateHostLiteral(hostport string) bool {
	host := hostport
	if h, _, err := net.SplitHostPort(hostport); err == nil {
		host = h
	}
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	if ip := net.ParseIP(host); ip != nil {
		return PrivateIP(ip)
	}
	if host == "localhost" || strings.HasSuffix(host, ".localhost") {
		return true
	}
	for _, suf := range []string{".local", ".lan", ".home.arpa", ".internal"} {
		if strings.HasSuffix(host, suf) && len(host) > len(suf) {
			return true
		}
	}
	return false
}

// PrivateIP reports loopback, private (RFC 1918, ULA), link-local and unspecified addresses.
func PrivateIP(ip net.IP) bool {
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsUnspecified() || ip.IsInterfaceLocalMulticast()
}
