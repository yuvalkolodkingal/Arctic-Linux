package catalog

import (
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/yuvalkolodkingal/o-tism/modules"
)

func load(t *testing.T) *Catalog {
	t.Helper()
	c, err := Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

// The repo's modules/ directory and the embedded copy must be the same catalog.
func TestLoadDirMatchesEmbedded(t *testing.T) {
	dir, err := filepath.Abs("../../modules")
	if err != nil {
		t.Fatal(err)
	}
	c, err := LoadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	e := load(t)
	if !reflect.DeepEqual(c.Order, e.Order) {
		t.Fatalf("order differs:\n dir %v\n emb %v", c.Order, e.Order)
	}
}

func TestDesignTiles(t *testing.T) {
	c := load(t)
	// Every real app tile of the design (bundle.js APPS minus "installer" and "settings"), plus
	// Btrfs Assistant (tile drawn in the same style, installer-ui/assets/tiles).
	want := strings.Fields("zen firefox chromium zed vscodium neovim helix kitty alacritty foot zsh fish bash yazi thunar nautilus collabora libreoffice onlyoffice vlc mpv celluloid flathub steam gimp inkscape signal obs btrfs-assistant")
	var got []string
	for _, m := range c.Modules {
		if !m.Hidden {
			got = append(got, m.ID)
		}
	}
	sort.Strings(got)
	sort.Strings(want)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("visible modules\n got %v\nwant %v", got, want)
	}
	var sys []string
	for _, m := range c.Modules {
		if m.Hidden {
			sys = append(sys, m.ID)
		}
	}
	sort.Strings(sys)
	if !reflect.DeepEqual(sys, []string{"adw-gtk3-dark-flatpak", "adw-gtk3-flatpak", "codecs", "desktop-base", "flatpak", "nix"}) {
		t.Fatalf("system modules %v", sys)
	}
	var cats []string
	for _, cat := range c.Categories {
		cats = append(cats, cat.ID+":"+cat.Choice)
	}
	if strings.Join(cats, " ") != "browser:one editor:any terminal:one shell:one files:any office:one video:any extras:any" {
		t.Fatalf("categories %v", cats)
	}
}

func TestDefaults(t *testing.T) {
	c := load(t)
	sel := c.DefaultSelection()
	want := Selection{
		"browser": {"zen"}, "editor": {"zed"}, "terminal": {"kitty"}, "shell": {"zsh"},
		"files": {"yazi", "thunar"}, "office": {"collabora"}, "video": {"vlc"}, "extras": {},
	}
	if !reflect.DeepEqual(sel, want) {
		t.Fatalf("defaults\n got %v\nwant %v", sel, want)
	}
	if f := c.Validate(sel); len(f) != 0 {
		t.Fatalf("defaults invalid: %v", f)
	}
	var ids []string
	for _, m := range c.Resolve(sel) {
		ids = append(ids, m.ID)
	}
	if strings.Join(ids, " ") != "zen zed kitty zsh bash yazi thunar collabora vlc adw-gtk3-dark-flatpak adw-gtk3-flatpak codecs desktop-base flatpak nix" {
		t.Fatalf("resolve = %v", ids)
	}
}

func TestLiveImageFlags(t *testing.T) {
	c := load(t)
	live := map[string]bool{}
	for id, m := range c.Modules {
		if m.InLiveImage {
			live[id] = true
		}
	}
	for _, id := range []string{"kitty", "zsh", "bash", "thunar", "vlc", "desktop-base", "flatpak", "nix"} {
		if !live[id] {
			t.Errorf("%s should be in the live image", id)
		}
	}
	for _, id := range []string{"zen", "zed", "collabora", "yazi", "codecs", "adw-gtk3-flatpak", "adw-gtk3-dark-flatpak"} {
		if live[id] {
			t.Errorf("%s should be downloaded", id)
		}
	}
}

func TestEstimateDownload(t *testing.T) {
	c := load(t)
	est := c.EstimateDownload(c.DefaultSelection())
	// zen 160 + Platform 25.08 259 + zed 132 + Sdk 26.08 656 + yazi 12 + collabora 454 + KDE 6.10 392 + codecs 40
	// + the adw-gtk3 themes for Flatpak apps 2 × 0.5
	if est.Apps != 8 {
		t.Errorf("apps = %d, want 8 (the ticked defaults; bash is installed but not counted)", est.Apps)
	}
	if est.Bytes != 2106*1000*1000 {
		t.Errorf("bytes = %d", est.Bytes)
	}
	if est.Label != "8 apps · 2.1 GB download" {
		t.Errorf("label = %q", est.Label)
	}

	// Shared runtimes count once: Firefox (dnf) + two Platform 25.08 flatpaks.
	sel := Selection{"browser": {"firefox"}, "terminal": {"kitty"}, "shell": {"zsh"}, "extras": {"obs"}, "office": {"libreoffice"}}
	est = c.EstimateDownload(sel)
	// firefox 100 + obs 199 + libreoffice 327 + Platform 25.08 259 (once) + codecs 40 + Flatpak themes 1
	if est.Bytes != 926*1000*1000 || est.Label != "5 apps · 926 MB download" {
		t.Errorf("got %+v", est)
	}

	// Only live-image apps: nothing but codecs and the Flatpak themes to download.
	sel = Selection{"browser": {"zen"}, "terminal": {"kitty"}, "shell": {"bash"}}
	est = c.EstimateDownload(sel)
	if est.Apps != 3 {
		t.Errorf("apps = %d", est.Apps)
	}
}

func TestValidate(t *testing.T) {
	c := load(t)
	base := func() Selection { return c.DefaultSelection() }
	cases := []struct {
		name  string
		edit  func(Selection)
		field string
		msg   string
	}{
		{"two browsers", func(s Selection) { s["browser"] = []string{"zen", "firefox"} }, "browser", "Pick just one browser."},
		{"no browser", func(s Selection) { s["browser"] = nil }, "browser", "Pick a browser."},
		{"no terminal", func(s Selection) { delete(s, "terminal") }, "terminal", "Pick a terminal."},
		{"unknown app", func(s Selection) { s["editor"] = []string{"emacs"} }, "editor", `We don't know an app called "emacs".`},
		{"wrong category", func(s Selection) { s["editor"] = []string{"vlc"} }, "editor", "VLC belongs under Video."},
		{"hidden module", func(s Selection) { s["extras"] = []string{"codecs"} }, "extras", `We don't know an app called "codecs".`},
		{"unknown category", func(s Selection) { s["games"] = []string{"steam"} }, "games", "This isn't one of the app groups."},
		{"two office", func(s Selection) { s["office"] = []string{"collabora", "onlyoffice"} }, "office", "Pick just one office."},
	}
	for _, tc := range cases {
		s := base()
		tc.edit(s)
		f := c.Validate(s)
		if f[tc.field] != tc.msg {
			t.Errorf("%s: fields = %v, want %s=%q", tc.name, f, tc.field, tc.msg)
		}
	}
	// Office is optional; many editors are fine.
	s := base()
	s["office"] = nil
	s["editor"] = []string{"zed", "neovim", "helix", "vscodium"}
	if f := c.Validate(s); len(f) != 0 {
		t.Fatalf("unexpected errors %v", f)
	}
}

func TestConflictsAndRequires(t *testing.T) {
	c := load(t)
	c.Modules["mpv"].Conflicts = []string{"celluloid"}
	c.Modules["neovim"].Requires = []string{"kitty"}
	s := c.DefaultSelection()
	s["video"] = []string{"mpv", "celluloid"}
	s["editor"] = []string{"neovim"}
	s["terminal"] = []string{"foot"}
	f := c.Validate(s)
	if f["video"] != "mpv and Celluloid can't be installed together." {
		t.Errorf("video: %q", f["video"])
	}
	if f["editor"] != "Neovim needs kitty. Tick it too." {
		t.Errorf("editor: %q", f["editor"])
	}
}

func TestNormalize(t *testing.T) {
	c := load(t)
	got := c.Normalize(Selection{"files": {"thunar", "yazi", "thunar"}, "extras": {"zzz", "obs", "steam"}})
	if !reflect.DeepEqual(got["files"], []string{"yazi", "thunar"}) {
		t.Errorf("files %v", got["files"])
	}
	if !reflect.DeepEqual(got["extras"], []string{"steam", "obs", "zzz"}) {
		t.Errorf("extras %v", got["extras"])
	}
	if got["browser"] == nil || len(got["browser"]) != 0 {
		t.Errorf("missing categories should become empty lists: %v", got)
	}
}

func TestPicker(t *testing.T) {
	c := load(t)
	p := c.Picker()
	if len(p.Categories) != 8 || len(p.Modules) != 29 {
		t.Fatalf("picker has %d categories, %d modules", len(p.Categories), len(p.Modules))
	}
	if p.Modules[0].ID != "zen" || p.Modules[0].Source != "Flathub" || p.Categories[0].Rule != "Pick one" {
		t.Fatalf("first module %+v", p.Modules[0])
	}
	for _, m := range p.Modules {
		if m.ID == "vlc" && m.Source != "RPM Fusion" {
			t.Errorf("vlc source %q", m.Source)
		}
		if m.ID == "yazi" && m.Source != "COPR" {
			t.Errorf("yazi source %q", m.Source)
		}
	}
}

func TestCatalogChecks(t *testing.T) {
	good := `nixpkgs = "x"
[[category]]
id = "browser"
name = "Browser"
choice = "one"
required = true
modules = ["a"]
`
	mod := `id = "a"
name = "A"
summary = "s"
category = "browser"
default = true
tile = "a"
gpu = true
[[install]]
method = "nix"
attr = "a"
`
	fsys := fstest.MapFS{
		"catalog.toml":          {Data: []byte(good)},
		"browser/a/module.toml": {Data: []byte(mod)},
	}
	_, err := Load(fsys)
	if err == nil || !strings.Contains(err.Error(), "nix is only allowed for CLI/TUI modules") {
		t.Fatalf("want gpu/nix error, got %v", err)
	}
	fsys["browser/a/module.toml"] = &fstest.MapFile{Data: []byte(strings.Replace(mod, `id = "a"`, `id = "b"`, 1))}
	if _, err := Load(fsys); err == nil || !strings.Contains(err.Error(), "does not match its directory") {
		t.Fatalf("want id/dir error, got %v", err)
	}
	fsys["browser/a/module.toml"] = &fstest.MapFile{Data: []byte(strings.Replace(mod, "method = \"nix\"\nattr = \"a\"", "method = \"flatpak\"\nref = \"x\"", 1))}
	if _, err := Load(fsys); err == nil || !strings.Contains(err.Error(), "must name their remote") {
		t.Fatalf("want remote error, got %v", err)
	}
}

func TestShippedManifestsHaveNoUnknownKeys(t *testing.T) {
	// Load is strict; this guards against a manifest edited without running the tests.
	if _, err := os.Stat("../../modules/catalog.toml"); err != nil {
		t.Skip("repo modules/ not available")
	}
	if _, err := LoadDir("../../modules"); err != nil {
		t.Fatal(err)
	}
}

func TestMarkPreinstalled(t *testing.T) {
	c, err := Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	before := c.EstimateDownload(c.DefaultSelection()).Bytes
	ids := c.MarkPreinstalled(func(ref string) bool { return ref == "app.zen_browser.zen" || ref == "org.mozilla.firefox" })
	// Firefox's primary method is dnf, so only Zen counts.
	if len(ids) != 1 || ids[0] != "zen" || !c.Modules["zen"].InLiveImage || c.Modules["firefox"].InLiveImage {
		t.Fatalf("marked %v", ids)
	}
	if after := c.EstimateDownload(c.DefaultSelection()).Bytes; after >= before {
		t.Errorf("estimate %d → %d: Zen's download should no longer count", before, after)
	}
}
