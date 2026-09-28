// Package policy makes the web-app window's decisions in pure Go: which navigations stay in the
// app, which go to your browser, what a permission request gets, where a download lands and
// what happens after a crash. The WebKit shim only reports facts and applies the answers, so
// every rule here is unit-tested without a display.
package policy

import (
	"net"
	"net/url"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/psl"
)

// Scope is what belongs to an app: its site (registrable domain, or exact host:port for IP
// and localhost apps), its scheme, and extra domains you added.
type Scope struct {
	Site   string
	Scheme string // https, or http when the app itself is http
	Extra  []string
}

// ScopeOf builds an app's scope.
func ScopeOf(a *webapp.App) Scope {
	return Scope{Site: a.Scope.Site, Scheme: a.Scope.Scheme, Extra: a.ExtraDomains}
}

// In reports whether a URL belongs to the app: http(s) in the app's scheme family (https, or
// http too for an http app), host equal to the site or a subdomain of it, or of an extra domain.
func (s Scope) In(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return false
	}
	switch u.Scheme {
	case "https":
	case "http":
		if s.Scheme != "http" {
			return false
		}
	default:
		return false
	}
	host := strings.ToLower(u.Host)
	if hostMatches(host, s.Site) {
		return true
	}
	for _, d := range s.Extra {
		if hostMatches(host, d) {
			return true
		}
	}
	return false
}

// hostMatches compares host[:port] with a site: an exact host:port site (IP literals,
// localhost) must match exactly; a domain matches itself and its subdomains on any port.
func hostMatches(hostport, site string) bool {
	site = strings.ToLower(site)
	if site == "" {
		return false
	}
	if hostport == site {
		return true
	}
	host := hostport
	if h, _, err := net.SplitHostPort(hostport); err == nil {
		host = h
	}
	if _, _, err := net.SplitHostPort(site); err == nil || net.ParseIP(strings.Trim(site, "[]")) != nil || site == "localhost" {
		return false // exact-host sites only match exactly
	}
	return psl.SameSite(host, site)
}

// Navigation types, as WebKit reports them (WebKitNavigationType).
const (
	NavLinkClicked   = 0
	NavFormSubmitted = 1
	NavBackForward   = 2
	NavReload        = 3
	NavFormResubmit  = 4
	NavOther         = 5
)

// Decisions.
const (
	Use       = 0 // let WebKit load it here
	Ignore    = 1 // drop it
	External  = 2 // drop it and open it in your browser (or the scheme's handler)
	Popup     = 3 // a new window: let WebKit create a popup (window.open, OAuth)
	LoadInApp = 4 // a new-window request for an in-scope page: load it in the main view
)

// Nav is a navigation as the shim reports it.
type Nav struct {
	URI         string
	Type        int  // Nav*
	UserGesture bool // started by a click or key press
	MainFrame   bool
	NewWindow   bool // NEW_WINDOW_ACTION (target=_blank or window.open)
	Modifiers   bool // Ctrl or Shift held
	Middle      bool // middle click
	Popup       bool // the view is a popup (not scope-policed except non-web schemes)
}

// Decide applies Epiphany's web-app rule: only user link clicks (and OTHER navigations with a
// user gesture) leave the app. Server redirects, script navigations and form posts stay, so
// single sign-on chains and cross-domain login forms finish in the app.
func Decide(n Nav, s Scope, links string) int {
	scheme := ""
	if u, err := url.Parse(n.URI); err == nil {
		scheme = strings.ToLower(u.Scheme)
	}
	switch scheme {
	case "about", "data", "blob":
		return Use
	case "javascript", "file":
		return Ignore
	case "http", "https":
	default:
		// mailto:, tel:, sms: and other schemes go to their handler, only on your gesture.
		if n.UserGesture {
			return External
		}
		return Ignore
	}
	if !n.MainFrame && !n.NewWindow {
		return Use // subframes
	}
	in := s.In(n.URI)
	userLink := n.Type == NavLinkClicked || (n.Type == NavOther && n.UserGesture)
	if n.NewWindow {
		switch {
		case n.Type == NavLinkClicked && (n.Modifiers || n.Middle):
			return External
		case n.Type == NavLinkClicked && in:
			return LoadInApp
		case n.Type == NavLinkClicked && links == "browser":
			return External
		case n.Type == NavLinkClicked:
			return LoadInApp
		default:
			return Popup // window.open: same session, window.opener kept (OAuth)
		}
	}
	if n.Popup {
		return Use
	}
	if n.Type == NavBackForward || n.Type == NavReload || n.Type == NavFormResubmit {
		return Use
	}
	if userLink && (n.Modifiers || n.Middle) {
		return External
	}
	if in || links == "app" {
		return Use
	}
	if userLink {
		return External
	}
	return Use // redirects, script navigations, form posts
}
