package catalog

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"
)

// shell/assets/featured.json must be what the catalog gives; regenerate it with
// `go run ./cmd/arctic-install catalog --featured > shell/assets/featured.json`.
func TestFeaturedFileIsCurrent(t *testing.T) {
	var want bytes.Buffer
	enc := json.NewEncoder(&want)
	enc.SetIndent("", " ")
	if err := enc.Encode(load(t).Featured()); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile("../../shell/assets/featured.json")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, want.Bytes()) {
		t.Fatal("shell/assets/featured.json is out of date: run go run ./cmd/arctic-install catalog --featured > shell/assets/featured.json")
	}
}

func TestFeaturedLeavesOutWhatGetAppsCantInstall(t *testing.T) {
	c := load(t)
	doc := c.Featured()
	if doc.Schema != 1 || len(doc.Apps) == 0 {
		t.Fatalf("featured: %+v", doc)
	}
	seen := map[string]bool{}
	for i, app := range doc.Apps {
		m := c.Modules[app.ID]
		if m == nil || m.Hidden || m.Always || m.IsHardware() {
			t.Errorf("%s: hidden, always-installed or a driver", app.ID)
		}
		if app.Flatpak == nil && app.DNF == nil {
			t.Errorf("%s: no method", app.ID)
		}
		if app.Flatpak != nil && (app.Flatpak.Remote != "flathub" || app.Flatpak.Ref == "") {
			t.Errorf("%s: flatpak %+v", app.ID, app.Flatpak)
		}
		if app.DNF != nil {
			for _, in := range m.Install {
				if in.Method == MethodDNF && len(in.Packages) > 0 && in.Packages[0] == app.DNF.Packages[0] &&
					(in.Copr != "" || len(in.Repos) > 0 || len(in.Swap) > 0) {
					t.Errorf("%s: dnf method needs COPR, repositories or swaps", app.ID)
				}
			}
		}
		if i > 0 && indexOf(c.Order, doc.Apps[i-1].ID) > indexOf(c.Order, app.ID) {
			t.Errorf("%s: not in catalog order", app.ID)
		}
		seen[app.ID] = true
	}
	// Every visible module with a usable method is there.
	for _, id := range c.Order {
		m := c.Modules[id]
		if m.Hidden || m.Always || m.IsHardware() {
			continue
		}
		usable := false
		for _, in := range m.Install {
			if (in.Method == MethodFlatpak && in.Remote == "flathub" && in.Ref != "") ||
				(in.Method == MethodDNF && len(in.Packages) > 0 && in.Copr == "" && len(in.Repos) == 0 && len(in.Swap) == 0) {
				usable = true
			}
		}
		if usable != seen[id] {
			t.Errorf("%s: usable %v, listed %v", id, usable, seen[id])
		}
	}
}

func indexOf(list []string, s string) int {
	for i, v := range list {
		if v == s {
			return i
		}
	}
	return -1
}
