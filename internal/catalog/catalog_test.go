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
	// The design's app tiles (bundle.js APPS minus "installer" and "settings") and the curated
	// catalog that grew from them (docs/PLAN.md §4.2).
	want := strings.Fields(`zen firefox brave chrome librewolf chromium vivaldi
		zed vscode vscodium neovim helix kate emacs text-editor
		kitty ghostty alacritty foot konsole
		zsh fish bash
		yazi thunar nautilus dolphin nemo pcmanfm-qt
		collabora libreoffice onlyoffice
		vlc mpv celluloid haruna kodi jellyfin
		spotify strawberry tauon amberol rhythmbox shortwave easyeffects
		loupe gthumb shotwell digikam darktable rawtherapee
		gimp krita inkscape blender pinta freecad
		obs gpu-screen-recorder kooha audacity kdenlive shotcut handbrake
		signal discord telegram element slack zoom zapzap
		thunderbird evolution betterbird
		obsidian joplin logseq appflowy standard-notes xournalpp planify
		papers okular zathura foliate calibre pdfarranger
		steam heroic lutris bottles prism protonplus mangohud gamemode
		keepassxc bitwarden onepassword proton-pass authenticator protonvpn tor-browser
		qbittorrent transmission syncthing nextcloud localsend
		git lazygit meld dbeaver bruno
		podman podman-desktop distrobox gnome-boxes virt-manager waydroid
		flathub bazaar flatseal mission-center gnome-disks pika-backup file-roller btrfs-assistant`)
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
	wantCats := "browser:one editor:any terminal:one shell:one files:any office:one video:any " +
		"music:any photos:any graphics:any recording:any chat:any email:any notes:any reading:any " +
		"gaming:any security:any sync:any dev:any containers:any extras:any"
	if strings.Join(cats, " ") != wantCats {
		t.Fatalf("categories %v", cats)
	}
	// The design's seven sections stay open; the optional groups start folded and tick nothing.
	for i, cat := range c.Categories {
		if cat.Collapsed != (i >= 7) {
			t.Errorf("%s: collapsed = %v", cat.ID, cat.Collapsed)
		}
		if cat.Collapsed {
			for _, id := range cat.Modules {
				if c.Modules[id].Default {
					t.Errorf("%s is ticked by default in the collapsed %s section", id, cat.ID)
				}
			}
		}
	}
}

// Every visible module has its light and dark tile and a glyph the installer UI knows.
func TestTileAssets(t *testing.T) {
	assets := "../../installer-ui/assets"
	icons, err := os.ReadFile(filepath.Join(assets, "Icons.js"))
	if err != nil {
		t.Skip("installer-ui assets not available")
	}
	c := load(t)
	for _, id := range c.Order {
		m := c.Modules[id]
		if m.Hidden {
			continue
		}
		for _, theme := range []string{"light", "dark"} {
			if _, err := os.Stat(filepath.Join(assets, "tiles", m.Tile+"-"+theme+".svg")); err != nil {
				t.Errorf("%s: %v", id, err)
			}
		}
		if m.Icon == "" || !strings.Contains(string(icons), "\n \""+m.Icon+"\": ") {
			t.Errorf("%s: icon %q is not in Icons.js ICONS", id, m.Icon)
		}
		if !strings.Contains(string(icons), "\n \""+id+"\": {") {
			t.Errorf("%s: no APPS entry in Icons.js", id)
		}
	}
}

// Proprietary apps are tagged so the picker can say so (docs/PLAN.md §4.2 licence notes).
func TestProprietary(t *testing.T) {
	c := load(t)
	var got []string
	for _, id := range c.Order {
		if c.Modules[id].Proprietary {
			got = append(got, id)
		}
	}
	want := "chrome vivaldi vscode spotify discord slack zoom obsidian steam onepassword"
	if strings.Join(got, " ") != want {
		t.Fatalf("proprietary = %v, want %s", got, want)
	}
	for _, m := range c.Picker().Modules {
		if m.ID == "vscode" && !m.Proprietary {
			t.Errorf("picker does not tag VS Code")
		}
	}
}

func TestDefaults(t *testing.T) {
	c := load(t)
	sel := c.DefaultSelection()
	want := Selection{
		"browser": {"zen"}, "editor": {"zed"}, "terminal": {"kitty"}, "shell": {"zsh"},
		"files": {"yazi", "thunar"}, "office": {"collabora"}, "video": {"vlc"},
		"music": {}, "photos": {}, "graphics": {}, "recording": {}, "chat": {}, "email": {}, "notes": {},
		"reading": {}, "gaming": {}, "security": {}, "sync": {}, "dev": {}, "containers": {}, "extras": {},
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
	// zen 160 + Platform 25.08 259 + zed 132 + Sdk 26.08 656 + yazi 45 + collabora 454 + KDE 6.10 392 + codecs 40
	// + the adw-gtk3 themes for Flatpak apps 2 × 0.5
	if est.Apps != 8 {
		t.Errorf("apps = %d, want 8 (the ticked defaults; bash is installed but not counted)", est.Apps)
	}
	if est.Bytes != 2139*1000*1000 {
		t.Errorf("bytes = %d", est.Bytes)
	}
	if est.Label != "8 apps · 2.1 GB download" {
		t.Errorf("label = %q", est.Label)
	}

	// Shared runtimes count once: Firefox (dnf) + two Platform 25.08 flatpaks.
	sel := Selection{"browser": {"firefox"}, "terminal": {"kitty"}, "shell": {"zsh"}, "recording": {"obs"}, "office": {"libreoffice"}}
	est = c.EstimateDownload(sel)
	// firefox 109 + obs 199 + libreoffice 327 + Platform 25.08 259 (once) + codecs 40
	if est.Bytes != 935*1000*1000 || est.Label != "5 apps · 935 MB download" {
		t.Errorf("got %+v", est)
	}

	// A new runtime is paid for once however many apps use it: Shortwave, Pinta and Kooha all
	// run on GNOME 50 (6 + 57 + 1 + 420), on top of the defaults.
	sel = c.DefaultSelection()
	sel["music"] = []string{"shortwave"}
	sel["graphics"] = []string{"pinta"}
	sel["recording"] = []string{"kooha"}
	est = c.EstimateDownload(sel)
	if est.Apps != 11 || est.Bytes != (2139+6+57+1+420)*1000*1000 {
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
		{"unknown app", func(s Selection) { s["editor"] = []string{"sublime"} }, "editor", `We don't know an app called "sublime".`},
		{"wrong category", func(s Selection) { s["editor"] = []string{"vlc"} }, "editor", "VLC belongs under Video."},
		{"hidden module", func(s Selection) { s["extras"] = []string{"codecs"} }, "extras", `We don't know an app called "codecs".`},
		{"unknown category", func(s Selection) { s["games"] = []string{"steam"} }, "games", "This isn't one of the app groups."},
		{"moved app", func(s Selection) { s["extras"] = []string{"steam"} }, "extras", "Steam belongs under Games."},
		{"needs podman", func(s Selection) { s["containers"] = []string{"podman-desktop"} }, "containers", "Podman Desktop needs Podman. Tick it too."},
		{"needs git", func(s Selection) { s["dev"] = []string{"lazygit"} }, "dev", "lazygit needs Git. Tick it too."},
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
	s["containers"] = []string{"podman", "podman-desktop"}
	s["dev"] = []string{"git", "lazygit"}
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
	got := c.Normalize(Selection{"files": {"thunar", "yazi", "thunar"}, "gaming": {"zzz", "protonplus", "steam"}})
	if !reflect.DeepEqual(got["files"], []string{"yazi", "thunar"}) {
		t.Errorf("files %v", got["files"])
	}
	if !reflect.DeepEqual(got["gaming"], []string{"steam", "protonplus", "zzz"}) {
		t.Errorf("gaming %v", got["gaming"])
	}
	if got["browser"] == nil || len(got["browser"]) != 0 {
		t.Errorf("missing categories should become empty lists: %v", got)
	}
}

func TestPicker(t *testing.T) {
	c := load(t)
	p := c.Picker()
	if len(p.Categories) != 21 || len(p.Modules) != 126 {
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
		if m.ID == "steam" && (m.Source != "RPM Fusion" || m.Method != "dnf") {
			t.Errorf("steam source %q/%q", m.Source, m.Method)
		}
		if m.ID == "lazygit" && m.Source != "Nix" {
			t.Errorf("lazygit source %q", m.Source)
		}
	}
	for _, cat := range p.Categories {
		if cat.Collapsed != (cat.ID != "browser" && cat.ID != "editor" && cat.ID != "terminal" && cat.ID != "shell" &&
			cat.ID != "files" && cat.ID != "office" && cat.ID != "video") {
			t.Errorf("picker %s collapsed = %v", cat.ID, cat.Collapsed)
		}
	}
}

// Modules that fall back to another method keep a working default app entry: a per-method
// desktop_id or command only makes sense on a module that declares [defaults].
func TestMethodOverridesNeedDefaults(t *testing.T) {
	c := load(t)
	for _, id := range c.Order {
		m := c.Modules[id]
		for i, in := range m.Install {
			if (in.DesktopID != "" || in.Command != "") && m.Defaults.DesktopID == "" && m.Defaults.Command == "" {
				t.Errorf("%s install[%d]: desktop_id/command override without [defaults]", id, i)
			}
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
	fsys["browser/a/module.toml"] = &fstest.MapFile{Data: []byte(strings.Replace(mod, "gpu = true", "gpu = false", 1))}
	if _, err := Load(fsys); err != nil {
		t.Fatalf("valid catalog: %v", err)
	}
	fsys["catalog.toml"] = &fstest.MapFile{Data: []byte(good + "collapsed = true\n")}
	if _, err := Load(fsys); err == nil || !strings.Contains(err.Error(), "a required category can't start collapsed") {
		t.Fatalf("want collapsed error, got %v", err)
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

// freedesktop runtimes get two years of updates: a new branch each August, and the one
// before the previous goes end-of-life. A module on an older branch makes flatpak warn and
// pulls a runtime nothing else needs. Such a module has to be listed here, with the reason,
// until Flathub moves the app on.
var staleRuntimeOK = map[string]string{
	"gpu-screen-recorder": "Flathub's com.dec05eba.gpu_screen_recorder is still on 24.08 (2026-09-28)",
	"kodi":                "Flatpak fallback only; Flathub's tv.kodi.Kodi is still on 24.08 (2026-09-28)",
}

func TestFlatpakRuntimesAreCurrent(t *testing.T) {
	c := load(t)
	// Newest two branches of each org.freedesktop.* runtime named in [runtimes].
	branches := map[string][]string{}
	for ref := range c.Runtimes {
		name, branch, ok := strings.Cut(ref, "//")
		if ok && strings.HasPrefix(name, "org.freedesktop.") {
			branches[name] = append(branches[name], branch)
		}
	}
	current := map[string]bool{}
	for name, bs := range branches {
		sort.Sort(sort.Reverse(sort.StringSlice(bs))) // YY.MM sorts as text
		for i, b := range bs {
			if i < 2 {
				current[name+"//"+b] = true
			}
		}
	}
	stale := map[string]bool{}
	for _, id := range c.Order {
		for _, in := range c.Modules[id].Install {
			name, _, _ := strings.Cut(in.Runtime, "//")
			if in.Runtime == "" || !strings.HasPrefix(name, "org.freedesktop.") || current[in.Runtime] {
				continue
			}
			stale[id] = true
			if _, ok := staleRuntimeOK[id]; !ok {
				t.Errorf("%s: runtime %s is older than the newest two branches (end-of-life); use a newer one or list it in staleRuntimeOK", id, in.Runtime)
			} else {
				t.Logf("warning: %s still uses end-of-life %s: %s", id, in.Runtime, staleRuntimeOK[id])
			}
		}
	}
	for id := range staleRuntimeOK {
		if !stale[id] {
			t.Errorf("%s is in staleRuntimeOK but no longer uses an old runtime: drop it from the list", id)
		}
	}
}
