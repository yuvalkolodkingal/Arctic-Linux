package psl

import (
	"strings"
	"testing"
)

func fixture(t testing.TB) *List {
	l, err := Load("testdata/public_suffix_list.dat")
	if err != nil {
		t.Fatal(err)
	}
	return l
}

func TestSite(t *testing.T) {
	l := fixture(t)
	cases := map[string]string{
		"mail.google.com":        "google.com",
		"google.com":             "google.com",
		"MUSIC.YouTube.com.":     "youtube.com",
		"foo.bar.co.uk":          "bar.co.uk",
		"co.uk":                  "co.uk", // a public suffix is its own site
		"user.github.io":         "user.github.io",
		"a.b.user.github.io":     "user.github.io",
		"www.walla.co.il":        "walla.co.il",
		"x.y.kawasaki.jp":        "x.y.kawasaki.jp",
		"a.x.y.kawasaki.jp":      "x.y.kawasaki.jp",
		"city.kawasaki.jp":       "city.kawasaki.jp",
		"a.city.kawasaki.jp":     "city.kawasaki.jp",
		"www.ck":                 "www.ck",
		"a.www.ck":               "www.ck",
		"foo.bar.ck":             "foo.bar.ck",
		"app.example.unknowntld": "example.unknowntld", // the implicit * rule
		"ha.home.arpa":           "ha.home.arpa",
		"blog.blogspot.com":      "blog.blogspot.com",
		"192.168.1.10":           "192.168.1.10",
		"192.168.1.10:8123":      "192.168.1.10:8123",
		"[::1]:8080":             "[::1]:8080",
		"localhost:3000":         "localhost:3000",
		"nas":                    "nas",
		"app.example.com:8443":   "example.com",
	}
	for host, want := range cases {
		if got := l.Site(host); got != want {
			t.Errorf("Site(%q) = %q, want %q", host, got, want)
		}
	}
}

// Without the list, every host is its own site (narrow scope rather than a wrong wide one).
func TestMissingListFallsBack(t *testing.T) {
	l, err := Load("testdata/does-not-exist.dat")
	if err == nil {
		t.Fatal("want an error for a missing list")
	}
	if got := l.Site("mail.google.com"); got != "mail.google.com" {
		t.Fatalf("fallback Site = %q", got)
	}
}

func TestSameSite(t *testing.T) {
	for _, c := range []struct {
		host, site string
		want       bool
	}{
		{"mail.google.com", "google.com", true},
		{"google.com", "google.com", true},
		{"evilgoogle.com", "google.com", false},
		{"google.com.evil.org", "google.com", false},
	} {
		if SameSite(c.host, c.site) != c.want {
			t.Errorf("SameSite(%q, %q) != %v", c.host, c.site, c.want)
		}
	}
}

func FuzzPSL(f *testing.F) {
	l := fixture(f)
	for _, s := range []string{"a.b.co.uk", "www.ck", "..", ".", "[::1]", "a..b", strings.Repeat("a.", 100)} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, host string) {
		site := l.Site(host)
		h := strings.TrimSuffix(strings.ToLower(host), ".")
		if site != "" && !strings.HasSuffix(h, site) && !strings.Contains(host, ":") && !strings.HasPrefix(host, "[") {
			t.Fatalf("Site(%q) = %q is not a suffix of the host", host, site)
		}
	})
}
