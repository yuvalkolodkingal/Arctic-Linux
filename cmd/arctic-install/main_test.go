package main

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"os"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/internal/profile"
	"github.com/yuvalkolodkingal/o-tism/modules"
	"github.com/yuvalkolodkingal/o-tism/profiles"
)

// `arctic-install plan` prints exactly the golden plan the installer tests pin down.
func TestPlanMatchesGolden(t *testing.T) {
	var out bytes.Buffer
	if code := cmdPlan([]string{"--profile", "../../profiles/defaults.toml", "--inventory", "mock"}, &out); code != 0 {
		t.Fatalf("exit %d", code)
	}
	golden, err := os.ReadFile("../../internal/installer/testdata/default-uefi-luks.plan")
	if err != nil {
		t.Fatal(err)
	}
	got := out.String()
	i := strings.Index(got, "# Arctic Linux install:")
	if i < 0 || got[i:] != string(golden) {
		t.Fatalf("plan output differs from the golden file:\n%s", got)
	}
	if !strings.HasPrefix(got, "# arctic-install plan — dry run") || strings.Contains(got, "dry-run\n") {
		t.Errorf("header or secret placeholder leaked:\n%s", got[:i])
	}
}

func TestPlanBIOS(t *testing.T) {
	var out bytes.Buffer
	if code := cmdPlan([]string{"--profile", "profiles/ci/alternative.toml", "--firmware", "bios", "--inventory", "mock"}, &out); code != 0 {
		t.Fatalf("exit %d", code)
	}
	golden, _ := os.ReadFile("../../internal/installer/testdata/alternative-bios-alongside.plan")
	if !strings.HasSuffix(out.String(), string(golden)) {
		t.Fatalf("alternative plan differs from its golden file")
	}
}

func TestCatalogJSON(t *testing.T) {
	var out bytes.Buffer
	if code := cmdCatalog([]string{"--json"}, &out); code != 0 {
		t.Fatalf("exit %d", code)
	}
	var doc struct {
		Categories []map[string]any `json:"categories"`
		Modules    []map[string]any `json:"modules"`
		Estimate   map[string]any   `json:"estimate"`
	}
	if err := json.Unmarshal(out.Bytes(), &doc); err != nil {
		t.Fatal(err)
	}
	if len(doc.Categories) != 8 || len(doc.Modules) != 33 || doc.Estimate["label"] != "8 apps · 2.1 GB download" {
		t.Fatalf("catalog json: %d categories, %d modules, %v", len(doc.Categories), len(doc.Modules), doc.Estimate)
	}
	if doc.Modules[0]["id"] != "zen" || doc.Modules[0]["install"].([]any)[0].(map[string]any)["ref"] != "app.zen_browser.zen" {
		t.Errorf("first module %v", doc.Modules[0])
	}
}

func TestAllProfilesValid(t *testing.T) {
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	n := 0
	fs.WalkDir(profiles.FS, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() || !strings.HasSuffix(path, ".toml") {
			return err
		}
		n++
		data, _ := profiles.FS.ReadFile(path)
		p, err := profile.Parse(data)
		if err != nil {
			t.Errorf("%s: %v", path, err)
			return nil
		}
		if _, _, err := p.Data(cat, mock.Inventory(), "thinkpad"); err != nil {
			t.Errorf("%s: %v", path, err)
		}
		return nil
	})
	if n != 4 { // defaults + ci/{default,alternative,offline}
		t.Errorf("found %d profiles, want 4", n)
	}
}

func TestUnattendedMock(t *testing.T) {
	t.Setenv("ARCTIC_LUKS_PASSPHRASE", "acid acorn acre aged")
	t.Setenv("ARCTIC_USER_PASSWORD", "winter-fox-2026")
	t.Setenv("ARCTIC_MOCK_SPEED", "200")
	var out bytes.Buffer
	code := cmdUnattended([]string{"--profile", "profiles/ci/default.toml", "--mock", "--log", t.TempDir() + "/engine.log"}, &out)
	if code != 0 {
		t.Fatalf("exit %d\n%s", code, out.String())
	}
	s := out.String()
	for _, want := range []string{"Account:               Arctic CI (ci) on arctic-ci", "[100%] Arctic Linux is installed.", "Done: Arctic Linux is ready"} {
		if !strings.Contains(s, want) {
			t.Errorf("output lacks %q:\n%s", want, s)
		}
	}
	if strings.Contains(s, "acid acorn") || strings.Contains(s, "winter-fox") {
		t.Error("secret printed")
	}
}
