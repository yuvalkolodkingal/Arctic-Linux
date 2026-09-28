package webapp

import (
	"flag"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

var update = flag.Bool("update", false, "rewrite golden files")

func golden(t *testing.T, name string, got []byte) {
	t.Helper()
	path := filepath.Join("testdata", name)
	if *update {
		if err := os.WriteFile(path, got, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	want, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(want) {
		t.Errorf("%s differs from its golden file:\n%s", name, got)
	}
}

func TestDesktopGoldens(t *testing.T) {
	webkit := sampleApp()

	chromium := sampleApp()
	chromium.ID = "org.arcticlinux.WebApp.Netflix_0a1b2c"
	chromium.Name, chromium.StartURL, chromium.Category = "Netflix", "https://www.netflix.com/browse", "AudioVideo"
	chromium.Runtime, chromium.WMClass = "chromium:brave", "brave-www.netflix.com__browse-Default"
	chromium.Normalize()

	mail := sampleApp()
	mail.ID = "org.arcticlinux.WebApp.Gmail_77aa01"
	mail.Name, mail.StartURL, mail.Category = "Gmail", "https://mail.google.com/mail/u/1/", "Office"
	mail.Handlers = []string{"mailto"}
	mail.Icon.Rev = 2
	mail.WMClass = mail.ID
	mail.Normalize()

	odd := sampleApp()
	odd.ID = "org.arcticlinux.WebApp.Walla_c0ffee"
	odd.Name = "וואלה!\nחדשות;\\ \u202eevil\u202c   news\t"
	odd.StartURL, odd.Category = "https://www.walla.co.il/", "Calendar"
	odd.WMClass = odd.ID
	odd.Normalize()

	for name, a := range map[string]*App{"desktop/webkit.desktop": webkit, "desktop/chromium.desktop": chromium, "desktop/mail.desktop": mail, "desktop/odd.desktop": odd} {
		got := DesktopEntry(a)
		golden(t, name, got)
		checkDesktopRules(t, a, string(got))
	}
}

// The launcher entry never carries a URL in Exec, a field code other than %u for a mail-link
// app, WebBrowser, NoDisplay or a MimeType other than the mailto opt-in.
func checkDesktopRules(t *testing.T, a *App, s string) {
	t.Helper()
	e := ParseEntry([]byte(s))
	wantExec := "arctic-webapp run " + a.ID
	if a.HasHandler("mailto") {
		wantExec += " %u"
		if e["MimeType"] != "x-scheme-handler/mailto;" {
			t.Errorf("%s: mailto MimeType missing", a.ID)
		}
	} else if _, ok := e["MimeType"]; ok {
		t.Errorf("%s: unexpected MimeType", a.ID)
	}
	if e["Exec"] != wantExec {
		t.Errorf("%s: Exec = %q", a.ID, e["Exec"])
	}
	if strings.Contains(s, "WebBrowser") || strings.Contains(s, "NoDisplay") {
		t.Errorf("%s: forbidden key", a.ID)
	}
	if strings.Count(s, "\n") != len(strings.Split(strings.TrimSpace(s), "\n")) {
		t.Errorf("%s: a value spans lines", a.ID)
	}
	if e["X-Arctic-WebApp-Id"] != a.ID || e["Icon"] != a.IconName() {
		t.Errorf("%s: id or icon keys wrong", a.ID)
	}
}

func TestCleanStripsControlAndBidi(t *testing.T) {
	cases := map[string]string{
		"  Hello \n  World ":    "Hello World",
		"a\u202eb\u2066c":       "abc",
		"x\x00y\x1bz":           "xyz",
		strings.Repeat("é", 70): strings.Repeat("é", 64),
		"one two three":         "one two three",
	}
	for in, want := range cases {
		if got := CleanName(in); got != want {
			t.Errorf("CleanName(%q) = %q, want %q", in, got, want)
		}
	}
}

func FuzzDesktopName(f *testing.F) {
	for _, s := range []string{"YouTube Music", "a\nb", "x;y\\z", "\u202e", ""} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, name string) {
		a := sampleApp()
		a.Name = name
		out := string(DesktopEntry(a))
		if !strings.HasPrefix(out, "[Desktop Entry]\n") {
			t.Fatal("no group header")
		}
		lines := strings.Split(strings.TrimSuffix(out, "\n"), "\n")
		if len(lines) != 18 {
			t.Fatalf("name %q produced %d lines", name, len(lines))
		}
		if e := ParseEntry([]byte(out)); e["Exec"] != "arctic-webapp run "+a.ID {
			t.Fatalf("Exec changed: %q", e["Exec"])
		}
	})
}
