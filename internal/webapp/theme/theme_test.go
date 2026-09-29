package theme

import (
	"flag"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

var update = flag.Bool("update", false, "rewrite golden files")

// The shipped themes parse, and the window's CSS for each matches its golden file.
func TestShippedThemesGolden(t *testing.T) {
	for _, name := range []string{"winter", "polar-night"} {
		p, err := Load(filepath.Join("../../../dotfiles/.config/arctic/themes", name, "theme.json"))
		if err != nil {
			t.Fatal(err)
		}
		if p.Dark != (name == "polar-night") {
			t.Errorf("%s: dark = %v", name, p.Dark)
		}
		got := HostCSS(p)
		path := filepath.Join("testdata", name+".css")
		if *update {
			os.WriteFile(path, []byte(got), 0o644)
		}
		want, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if got != string(want) {
			t.Errorf("%s: HostCSS differs from %s:\n%s", name, path, got)
		}
	}
}

func TestCSSColor(t *testing.T) {
	for in, want := range map[string]string{"#eef2f5": "#eef2f5", "#FFEEF2F5": "#eef2f5", "#ccfbfcfd": "rgba(251,252,253,0.800)", "red": "", "#12": "", "#zzzzzz": ""} {
		got, _ := CSSColor(in)
		if got != want {
			t.Errorf("CSSColor(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestErrorPageEscapes(t *testing.T) {
	page := ErrorPage(Default, "Can’t open <b>", "The site <script>alert(1)</script> is down.", "https://a.org/?q=<x>", "javascript:alert(1)")
	if strings.Contains(page, "<script>alert") || strings.Contains(page, "<b>") || strings.Contains(page, "javascript:") {
		t.Fatalf("not escaped:\n%s", page)
	}
	if !strings.Contains(page, "background: #eef2f5") {
		t.Fatalf("palette not applied:\n%s", page)
	}
	page = ErrorPage(Default, "Offline", "m", "", "https://a.org/")
	if !strings.Contains(page, `href="https://a.org/"`) {
		t.Fatalf("retry link missing:\n%s", page)
	}
}
