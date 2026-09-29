package discover

import (
	"net/url"
	"reflect"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/policy"
)

func TestManifestW3CRules(t *testing.T) {
	data := []byte("\xef\xbb\xbf" + `{
	  "name": "YouTube Music", "short_name": "YT Music",
	  "start_url": "/?source=pwa", "scope": "/", "id": "/?source=pwa",
	  "display": "Standalone", "theme_color": "#0F0F0F",
	  "categories": ["music", 7],
	  "icons": [
	    {"src": "img/512.png", "sizes": "512x512", "type": "image/png"},
	    {"src": "img/mask.png", "sizes": "192x192 any", "purpose": "maskable monochrome"},
	    {"src": "img/mono.png", "sizes": "96x96", "purpose": "monochrome"},
	    {"src": "javascript:alert(1)"},
	    {"sizes": "1x1"}
	  ],
	  "shortcuts": [{"name": "ignored"}]
	}`)
	m, err := ParseManifest(data, "https://music.youtube.com/manifest.webmanifest", "https://music.youtube.com/")
	if err != nil {
		t.Fatal(err)
	}
	if m.Name != "YouTube Music" || m.StartURL != "https://music.youtube.com/?source=pwa" || m.Scope != "https://music.youtube.com/" || m.ID != "https://music.youtube.com/?source=pwa" {
		t.Fatalf("urls: %+v", m)
	}
	if m.Display != "standalone" || m.ThemeColor != "#0f0f0f" || !reflect.DeepEqual(m.Categories, []string{"music"}) {
		t.Fatalf("members: %+v", m)
	}
	if len(m.Icons) != 2 || m.Icons[0].Src != "https://music.youtube.com/img/512.png" || !reflect.DeepEqual(m.Icons[1].Sizes, []int{192, 0}) || !reflect.DeepEqual(m.Icons[1].Purpose, []string{"maskable"}) {
		t.Fatalf("icons: %+v", m.Icons)
	}
}

func TestManifestCrossOriginStartAndScope(t *testing.T) {
	m, err := ParseManifest([]byte(`{"start_url": "https://evil.example/", "scope": "/other/", "id": "https://evil.example/x"}`),
		"https://app.example.org/static/manifest.json", "https://app.example.org/mail/inbox?x=1")
	if err != nil {
		t.Fatal(err)
	}
	// start_url ignored (not same-origin); scope must contain the start URL: default scope.
	if m.StartURL != "" || m.Scope != "https://app.example.org/mail/" || m.ID != "https://app.example.org/mail/inbox?x=1" {
		t.Fatalf("%+v", m)
	}
}

func TestManifestWrongTypes(t *testing.T) {
	m, err := ParseManifest([]byte(`{"name": 5, "icons": "nope", "start_url": ["x"], "categories": {"a":1}}`), "https://a.org/m.json", "https://a.org/")
	if err != nil || m.Name != "" || len(m.Icons) != 0 || m.StartURL != "" {
		t.Fatalf("%+v %v", m, err)
	}
	if _, err := ParseManifest([]byte(`<html>`), "https://a.org/m.json", "https://a.org/"); err == nil {
		t.Fatal("HTML accepted as a manifest")
	}
}

func FuzzManifest(f *testing.F) {
	f.Add([]byte(`{"name":"x","icons":[{"src":"/a.png","sizes":"192x192"}]}`))
	f.Add([]byte(`{"start_url":"//evil/","scope":"../.."}`))
	f.Fuzz(func(t *testing.T, data []byte) {
		m, err := ParseManifest(data, "https://a.org/m.json", "https://a.org/")
		if err != nil {
			return
		}
		if m.StartURL != "" {
			u, err := url.Parse(m.StartURL)
			if err != nil || u.Host != "a.org" {
				t.Fatalf("start_url escaped the origin: %q", m.StartURL)
			}
		}
	})
}

func TestNormalize(t *testing.T) {
	ok := map[string]string{
		"music.youtube.com":            "https://music.youtube.com/",
		"  Music.YouTube.com/x#frag  ": "https://music.youtube.com/x",
		"http://ha.lan:8123":           "http://ha.lan:8123/",
		"ha.lan:8123/lovelace":         "https://ha.lan:8123/lovelace",
		"HTTPS://A.org/?q=1":           "https://a.org/?q=1",
		// Internationalised names in Punycode, as WebKit reports them.
		"münchen.de/rathaus":          "https://xn--mnchen-3ya.de/rathaus",
		"https://Bücher.example:8443": "https://xn--bcher-kva.example:8443/",
		"https://m%C3%BCnchen.de/":    "https://xn--mnchen-3ya.de/",
	}
	for in, want := range ok {
		u, err := Normalize(in)
		if err != nil || u.String() != want {
			t.Errorf("Normalize(%q) = %v, %v; want %s", in, u, err, want)
		}
	}
	for _, bad := range []string{"", "javascript:alert(1)", "mailto:a@b.c", "file:///etc/passwd", "ftp://a.org/", "https://user:pw@a.org/", "a b.org", "https://a.org/\x00", "https://", string(make([]byte, 3000))} {
		if _, err := Normalize(bad); err == nil {
			t.Errorf("Normalize(%q) accepted", bad)
		}
	}
}

// An app added as münchen.de keeps the pages WebKit reports (xn--mnchen-3ya.de) in scope.
func TestInternationalNameScope(t *testing.T) {
	typed, err := Normalize("münchen.de/rathaus")
	if err != nil {
		t.Fatal(err)
	}
	s := policy.Scope{Site: testPSL(t).Site(typed.Host), Scheme: typed.Scheme}
	if s.Site != "xn--mnchen-3ya.de" || !s.In("https://xn--mnchen-3ya.de/foo") || !s.In("https://www.xn--mnchen-3ya.de/") {
		t.Fatalf("scope %+v", s)
	}
	if id := webapp.Identity("", typed.String(), 1); id != "https://xn--mnchen-3ya.de/rathaus" {
		t.Fatalf("identity %q", id)
	}
}

func TestPickName(t *testing.T) {
	cases := []struct {
		m          *Manifest
		head       Head
		host, site string
		want, src  string
	}{
		{&Manifest{Name: "YouTube Music"}, Head{}, "music.youtube.com", "youtube.com", "YouTube Music", "manifest"},
		{&Manifest{Name: "A very long progressive web app name here", ShortName: "Short"}, Head{}, "a.org", "a.org", "Short", "manifest"},
		{nil, Head{AppName: "Notion"}, "www.notion.so", "notion.so", "Notion", "meta"},
		{nil, Head{Title: "Home | GitHub"}, "github.com", "github.com", "GitHub", "title"},
		{nil, Head{Title: "Inbox (3) - user@gmail.com - Gmail"}, "mail.google.com", "google.com", "Inbox (3)", "title"},
		{nil, Head{Title: "Welcome"}, "www.walla.co.il", "walla.co.il", "Walla", "host"},
		{nil, Head{}, "192.168.1.5:8123", "192.168.1.5:8123", "192.168.1.5:8123", "host"},
		// The site label of an internationalised name, decoded.
		{nil, Head{}, "www.xn--mnchen-3ya.de", "xn--mnchen-3ya.de", "München", "host"},
		{nil, Head{Title: "Stadtportal – München"}, "www.xn--mnchen-3ya.de", "xn--mnchen-3ya.de", "München", "title"},
	}
	for _, c := range cases {
		n, s := PickName(c.m, c.head, c.host, c.site)
		if n != c.want || s != c.src {
			t.Errorf("PickName(%v, %q) = %q/%q, want %q/%q", c.m, c.head.Title, n, s, c.want, c.src)
		}
	}
}

func TestCategoryAndNeeds(t *testing.T) {
	if Category([]string{"news", "music"}) != "AudioVideo" || Category(nil) != "Network" || Category([]string{"productivity"}) != "Office" {
		t.Fatal("category mapping")
	}
	for host, want := range map[string]string{"www.netflix.com": "drm", "open.spotify.com": "drm", "spotify.com": "", "meet.google.com": "calls", "app.slack.com": "calls", "example.org": ""} {
		if got := Needs(host); got != want {
			t.Errorf("Needs(%q) = %q, want %q", host, got, want)
		}
	}
}

func TestCandidatesOrder(t *testing.T) {
	base, _ := url.Parse("https://a.org/app/")
	m := &Manifest{Icons: []ManifestIcon{
		{Src: "https://a.org/small.png", Sizes: []int{48}, Purpose: []string{"any"}},
		{Src: "https://a.org/mask.png", Sizes: []int{512}, Purpose: []string{"maskable"}},
		{Src: "https://a.org/big.png", Sizes: []int{512}, Purpose: []string{"any"}},
		{Src: "https://a.org/pic.webp", Sizes: []int{512}, Type: "image/webp", Purpose: []string{"any"}},
	}}
	head := Head{Links: []Link{{Rel: "apple-touch-icon", Href: "/apple.png"}, {Rel: "icon", Href: "favicon.ico"}, {Rel: "icon", Href: "https://www.google.com/s2/favicons?domain=a.org", Type: "image/png"}}}
	cs := Candidates(m, head, base, base)
	var got []string
	for _, c := range cs {
		got = append(got, c.Source+":"+c.URL)
	}
	want := []string{"manifest:https://a.org/big.png", "manifest:https://a.org/mask.png", "apple-touch:https://a.org/apple.png",
		"manifest:https://a.org/small.png", "link:https://www.google.com/s2/favicons?domain=a.org", "link:https://a.org/app/favicon.ico"}
	if len(got) != len(want) {
		t.Fatalf("got %v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("order:\n got %v\nwant %v", got, want)
		}
	}
	// Only /favicon.ico when nothing else is offered.
	cs = Candidates(nil, Head{}, base, base)
	if len(cs) != 1 || cs[0].URL != "https://a.org/favicon.ico" || cs[0].Source != "favicon-ico" {
		t.Fatalf("fallback %+v", cs)
	}
}

func TestRefreshTarget(t *testing.T) {
	base, _ := url.Parse("https://a.org/")
	for in, want := range map[string]string{"0; url=/next": "https://a.org/next", "3;URL='https://a.org/x'": "https://a.org/x", "10; url=/slow": "", "0; url=http://a.org/": "", "0; url=javascript:x": "", "5": ""} {
		got := ""
		if u := refreshTarget(in, base); u != nil {
			got = u.String()
		}
		if got != want {
			t.Errorf("refreshTarget(%q) = %q, want %q", in, got, want)
		}
	}
}
