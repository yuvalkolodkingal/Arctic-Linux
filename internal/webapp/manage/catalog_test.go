package manage

import (
	"path/filepath"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

// The Chromium-runtime table names the same Flatpak refs, dnf package and command as the app
// catalog's browser modules (modules/browser/*/module.toml), so "Install Brave" in Get apps
// installs what the engine then finds.
func TestRuntimeTableMatchesCatalog(t *testing.T) {
	c, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	for _, b := range Browsers {
		mod, ok := c.Modules[b.Module]
		if !ok {
			t.Errorf("%s: no catalog module %q", b.Variant, b.Module)
			continue
		}
		found := false
		for _, in := range mod.Install {
			switch {
			case b.Ref != "" && in.Method == "flatpak" && in.Ref == b.Ref:
				found = true
			case b.Command != "" && in.Method == "dnf":
				for _, p := range in.Packages {
					if p == "chromium" && mod.Defaults.Command == filepath.Base(b.Command) {
						found = true
					}
				}
			}
		}
		if !found {
			t.Errorf("%s: module %s has no matching install (ref %q, command %q)", b.Variant, b.Module, b.Ref, b.Command)
		}
	}
}

func TestChromiumWMClass(t *testing.T) {
	b, _ := BrowserFor("chromium:brave")
	if got := ChromiumWMClass(b, "https://www.netflix.com/browse/x"); got != "brave-www.netflix.com__browse_x-Default" {
		t.Fatalf("%q", got)
	}
	u, _ := BrowserFor("chromium:ungoogled")
	if got := ChromiumWMClass(u, "https://meet.google.com/"); got != "chromium-meet.google.com__-Default" {
		t.Fatalf("%q", got)
	}
}
