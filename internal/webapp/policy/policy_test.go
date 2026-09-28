package policy

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var mail = Scope{Site: "google.com", Scheme: "https", Extra: []string{"accounts.example.org"}}

func TestScopeIn(t *testing.T) {
	for u, want := range map[string]bool{
		"https://mail.google.com/mail/u/0/":  true,
		"https://google.com/":                true,
		"https://accounts.google.com/signin": true,
		"http://mail.google.com/":            false, // https app: no downgrade
		"https://evilgoogle.com/":            false,
		"https://google.com.evil.org/":       false,
		"https://sso.accounts.example.org/":  true,
		"https://example.org/":               false,
		"ftp://google.com/":                  false,
		"not a url":                          false,
	} {
		if got := mail.In(u); got != want {
			t.Errorf("In(%q) = %v, want %v", u, got, want)
		}
	}
	ip := Scope{Site: "192.168.1.5:8123", Scheme: "http"}
	if !ip.In("http://192.168.1.5:8123/lovelace") || ip.In("http://192.168.1.5:9000/") || ip.In("http://192.168.1.50:8123/") {
		t.Error("IP apps match their exact host:port only")
	}
	if !(Scope{Site: "ha.lan", Scheme: "http"}).In("https://ha.lan:8123/") {
		t.Error("an http app may use https")
	}
}

// The navigation matrix (Epiphany's rule): only user link clicks and gesture-driven OTHER
// navigations leave the app; SSO redirect chains and cross-domain form posts stay.
func TestDecide(t *testing.T) {
	cases := []struct {
		name  string
		n     Nav
		links string
		want  int
	}{
		{"in-scope link", Nav{URI: "https://mail.google.com/x", Type: NavLinkClicked, UserGesture: true, MainFrame: true}, "browser", Use},
		{"out-of-scope link", Nav{URI: "https://example.com/", Type: NavLinkClicked, UserGesture: true, MainFrame: true}, "browser", External},
		{"out-of-scope link, links=app", Nav{URI: "https://example.com/", Type: NavLinkClicked, UserGesture: true, MainFrame: true}, "app", Use},
		{"ctrl-click in scope", Nav{URI: "https://mail.google.com/x", Type: NavLinkClicked, UserGesture: true, MainFrame: true, Modifiers: true}, "app", External},
		{"middle-click", Nav{URI: "https://mail.google.com/x", Type: NavLinkClicked, MainFrame: true, Middle: true}, "browser", External},
		{"server redirect to SSO", Nav{URI: "https://login.microsoftonline.com/", Type: NavOther, MainFrame: true}, "browser", Use},
		{"script navigation, no gesture", Nav{URI: "https://example.com/", Type: NavOther, MainFrame: true}, "browser", Use},
		{"OTHER with a gesture", Nav{URI: "https://example.com/", Type: NavOther, UserGesture: true, MainFrame: true}, "browser", External},
		{"cross-domain form post", Nav{URI: "https://idp.example.com/login", Type: NavFormSubmitted, UserGesture: true, MainFrame: true}, "browser", Use},
		{"back/forward out of scope", Nav{URI: "https://example.com/", Type: NavBackForward, MainFrame: true}, "browser", Use},
		{"subframe", Nav{URI: "https://ads.example/", Type: NavLinkClicked, UserGesture: true}, "browser", Use},
		{"mailto with gesture", Nav{URI: "mailto:a@b.c", Type: NavLinkClicked, UserGesture: true, MainFrame: true}, "browser", External},
		{"mailto without gesture", Nav{URI: "mailto:a@b.c", Type: NavOther, MainFrame: true}, "browser", Ignore},
		{"javascript: from a site", Nav{URI: "javascript:alert(1)", Type: NavLinkClicked, UserGesture: true, MainFrame: true}, "browser", Ignore},
		{"file:", Nav{URI: "file:///etc/passwd", Type: NavOther, MainFrame: true}, "browser", Ignore},
		{"about:blank", Nav{URI: "about:blank", MainFrame: true}, "browser", Use},
		{"target=_blank in scope", Nav{URI: "https://mail.google.com/y", Type: NavLinkClicked, UserGesture: true, NewWindow: true}, "browser", LoadInApp},
		{"target=_blank out of scope", Nav{URI: "https://example.com/", Type: NavLinkClicked, UserGesture: true, NewWindow: true}, "browser", External},
		{"window.open (OAuth)", Nav{URI: "https://accounts.example.net/oauth", Type: NavOther, UserGesture: true, NewWindow: true}, "browser", Popup},
		{"popup navigates anywhere", Nav{URI: "https://idp.example.net/", Type: NavLinkClicked, UserGesture: true, MainFrame: true, Popup: true}, "browser", Use},
	}
	for _, c := range cases {
		if got := Decide(c.n, mail, c.links); got != c.want {
			t.Errorf("%s: %d, want %d", c.name, got, c.want)
		}
	}
}

func TestSafeNameAndUnique(t *testing.T) {
	for in, want := range map[[2]string]string{
		{"../../x", ""}:                         "x",
		{".bashrc", ""}:                         "bashrc",
		{"a\x00b\nc.pdf", ""}:                   "abc.pdf",
		{"report", "application/pdf"}:           "report.pdf",
		{"evil\u202egpj.exe", ""}:               "evilgpj.exe",
		{"", ""}:                                "download",
		{strings.Repeat("é", 150) + ".pdf", ""}: strings.Repeat("é", 98) + ".pdf",
	} {
		if got := SafeName(in[0], in[1]); got != want {
			t.Errorf("SafeName(%q, %q) = %q, want %q", in[0], in[1], got, want)
		}
	}
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "file.pdf"), nil, 0o600)
	os.WriteFile(filepath.Join(dir, "file (1).pdf"), nil, 0o600)
	if got := Unique(dir, "file.pdf"); got != filepath.Join(dir, "file (2).pdf") {
		t.Fatalf("Unique = %s", got)
	}
}

func TestCrashes(t *testing.T) {
	now := time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC)
	c := &Crashes{Now: func() time.Time { return now }}
	if !c.OnCrash(CrashCrashed) {
		t.Fatal("first crash reloads")
	}
	now = now.Add(30 * time.Second)
	if c.OnCrash(CrashCrashed) {
		t.Fatal("second crash within a minute shows the banner")
	}
	now = now.Add(2 * time.Minute)
	if !c.OnCrash(CrashCrashed) || c.OnCrash(CrashMemory) {
		t.Fatal("later crash reloads; memory limit shows the banner")
	}
}

func TestPermissions(t *testing.T) {
	dir := t.TempDir()
	p := LoadPermissions(filepath.Join(dir, "permissions.json"))
	origin := "https://mail.google.com"
	if p.Decide(origin, PermNotifications, mail, "allow") != Allow || p.Decide("https://other.org", PermNotifications, mail, "allow") != Ask {
		t.Fatal("notifications allow: in-scope only")
	}
	if p.Decide(origin, PermNotifications, mail, "block") != Deny || p.Decide(origin, PermNotifications, mail, "ask") != Ask {
		t.Fatal("block / ask")
	}
	if p.Decide(origin, PermCamera, mail, "allow") != Ask || p.Decide(origin, PermMediaKeys, mail, "allow") != Deny || p.Decide(origin, PermDeviceInfo, mail, "allow") != Deny {
		t.Fatal("defaults")
	}
	p.Remember(origin, PermCamera, true)
	p.Remember(origin, PermNotifications, false)
	if err := p.Save(filepath.Join(dir, "permissions.json")); err != nil {
		t.Fatal(err)
	}
	p = LoadPermissions(filepath.Join(dir, "permissions.json"))
	if p.Decide(origin, PermCamera, mail, "allow") != Allow || p.Decide(origin, PermNotifications, mail, "allow") != Deny || p.Decide(origin, PermDeviceInfo, mail, "allow") != Allow {
		t.Fatal("stored decisions")
	}
}

func TestStateAndRestore(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	s := LoadState(path)
	if s.Width != 1200 || s.Height != 800 || s.Zoom != 1 {
		t.Fatalf("defaults %+v", s)
	}
	now := time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC)
	s.LastURL, s.LastUsed, s.Zoom = "https://mail.google.com/mail/u/0/#inbox", now, 1.25
	s.Save(path)
	s = LoadState(path)
	if s.Zoom != 1.25 || RestoreURL(s, "https://mail.google.com/", mail, now.Add(time.Hour)) != s.LastURL {
		t.Fatal("restore last URL")
	}
	if RestoreURL(s, "https://mail.google.com/", mail, now.Add(40*24*time.Hour)) != "https://mail.google.com/" {
		t.Fatal("stale last URL")
	}
	s.LastURL = "https://evil.example/"
	if RestoreURL(s, "https://mail.google.com/", mail, now) != "https://mail.google.com/" {
		t.Fatal("out-of-scope last URL")
	}
	if LogURL("https://u:p@a.org/x?token=1#y") != "https://a.org/x" {
		t.Fatal("log url")
	}
}
