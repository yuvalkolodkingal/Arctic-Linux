package webapp

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

func TestSaveLoadModes(t *testing.T) {
	p := testPaths(t)
	a := sampleApp()
	if err := p.Save(a); err != nil {
		t.Fatal(err)
	}
	got, err := p.Load(a.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Name != a.Name || got.Identity() != a.Identity() || got.ExtraDomains == nil {
		t.Fatalf("round trip lost data: %+v", got)
	}
	for path, want := range map[string]os.FileMode{p.AppDir(a.ID): 0o700, p.AppFile(a.ID): 0o600} {
		fi, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if fi.Mode().Perm() != want {
			t.Errorf("%s mode %v, want %v", path, fi.Mode().Perm(), want)
		}
	}
	// No temp files left behind.
	entries, _ := os.ReadDir(p.AppDir(a.ID))
	for _, e := range entries {
		if strings.Contains(e.Name(), ".tmp") {
			t.Errorf("temp file left: %s", e.Name())
		}
	}
	var raw map[string]any
	data, _ := os.ReadFile(p.AppFile(a.ID))
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{"schema", "render", "engine_version", "name_source", "input_url", "start_url", "manifest_url", "manifest_id", "extra_domains", "theme_color", "wm_class", "tls_exceptions", "user_set"} {
		if _, ok := raw[k]; !ok {
			t.Errorf("app.json lacks %q", k)
		}
	}
}

// A tampered record can't inject Exec arguments or reach outside its directory.
func TestValidateRejects(t *testing.T) {
	cases := map[string]func(a *App){
		"bad id":          func(a *App) { a.ID = "org.arcticlinux.WebApp.X_1234567/../x" },
		"javascript url":  func(a *App) { a.StartURL = "javascript:alert(1)" },
		"file url":        func(a *App) { a.StartURL = "file:///etc/passwd" },
		"userinfo":        func(a *App) { a.StartURL = "https://u:p@a.org/" },
		"space in url":    func(a *App) { a.StartURL = "https://a.org/ --no-sandbox" },
		"runtime":         func(a *App) { a.Runtime = "chromium:../../bin/sh" },
		"category":        func(a *App) { a.Category = "WebBrowser" },
		"handler":         func(a *App) { a.Handlers = []string{"https"} },
		"links":           func(a *App) { a.Options.Links = "sometimes" },
		"public tls host": func(a *App) { a.TLSExceptions = []TLSException{{Host: "example.com", SHA256: "x"}} },
		"extra domain":    func(a *App) { a.ExtraDomains = []string{"a.org/x"} },
		"empty name":      func(a *App) { a.Name = "  " },
		"icon name":       func(a *App) { a.Icon.Name = "../../evil" },
		"schema":          func(a *App) { a.Schema = 9 },
	}
	for name, mutate := range cases {
		a := sampleApp()
		mutate(a)
		if err := a.Validate(); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	ok := sampleApp()
	ok.TLSExceptions = []TLSException{{Host: "ha.lan:8123", SHA256: "ab"}, {Host: "192.168.1.5", SHA256: "cd"}}
	ok.ExtraDomains = []string{"accounts.google.com", "sso.example.org:8443"}
	if err := ok.Validate(); err != nil {
		t.Errorf("valid record rejected: %v", err)
	}
}

func TestLoadMismatchedDirectory(t *testing.T) {
	p := testPaths(t)
	a := sampleApp()
	if err := p.Save(a); err != nil {
		t.Fatal(err)
	}
	other := "org.arcticlinux.WebApp.Other_abcdef"
	os.MkdirAll(p.AppDir(other), 0o700)
	data, _ := os.ReadFile(p.AppFile(a.ID))
	os.WriteFile(p.AppFile(other), data, 0o600)
	if _, err := p.Load(other); err == nil {
		t.Fatal("a record in another app's directory must be refused")
	}
	apps, bad, err := p.List()
	if err != nil || len(apps) != 1 || bad[other] == "" {
		t.Fatalf("List: %d apps, bad %v, err %v", len(apps), bad, err)
	}
	var pe *protocol.Error
	if _, err := p.Load("org.arcticlinux.WebApp.Nope_000000"); !errors.As(err, &pe) || pe.Code != CodeNotFound {
		t.Fatalf("missing app: %v", err)
	}
}

func TestKeptAndOwner(t *testing.T) {
	p := testPaths(t)
	a := sampleApp()
	if err := p.SaveKept(a); err != nil {
		t.Fatal(err)
	}
	kept, err := p.Kept()
	if err != nil || len(kept) != 1 || kept[0].ID != a.ID {
		t.Fatalf("Kept: %v %v", kept, err)
	}
	if got := p.Owner(a.ID); got != a.Identity() {
		t.Fatalf("Owner = %q", got)
	}
	if found, isKept := p.FindIdentity(a.Identity()); found == nil || !isKept {
		t.Fatal("FindIdentity should find the kept record")
	}
	if p.Owner("org.arcticlinux.WebApp.Free_000000") != "" {
		t.Fatal("free id has an owner")
	}
}

func TestLockBusyAndShared(t *testing.T) {
	p := testPaths(t)
	old := LockTimeout
	LockTimeout = 200 * time.Millisecond
	defer func() { LockTimeout = old }()
	r1, err := p.Acquire(false)
	if err != nil {
		t.Fatal(err)
	}
	r2, err := p.Acquire(false)
	if err != nil {
		t.Fatal("two readers must share the lock:", err)
	}
	_, err = p.Acquire(true)
	var pe *protocol.Error
	if !errors.As(err, &pe) || pe.Code != CodeBusy {
		t.Fatalf("writer during readers: %v, want busy", err)
	}
	r1.Release()
	r2.Release()
	w, err := p.Acquire(true)
	if err != nil {
		t.Fatal(err)
	}
	w.Release()
	if fi, _ := os.Stat(p.LockFile()); fi.Mode().Perm() != 0o600 {
		t.Errorf("lock mode %v", fi.Mode().Perm())
	}
}

// Concurrent writers under the lock never lose an update.
func TestConcurrentWriters(t *testing.T) {
	p := testPaths(t)
	a := sampleApp()
	p.Save(a)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			l, err := p.Acquire(true)
			if err != nil {
				t.Error(err)
				return
			}
			defer l.Release()
			cur, err := p.Load(a.ID)
			if err != nil {
				t.Error(err)
				return
			}
			cur.ExtraDomains = append(cur.ExtraDomains, "d"+strconv.Itoa(len(cur.ExtraDomains))+".org")
			if err := p.Save(cur); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	got, _ := p.Load(a.ID)
	if len(got.ExtraDomains) != 8 {
		t.Fatalf("lost updates: %v", got.ExtraDomains)
	}
}

func TestRemoveTree(t *testing.T) {
	root := t.TempDir()
	id := "org.arcticlinux.WebApp.X_abcdef"
	os.MkdirAll(filepath.Join(root, id, "profile"), 0o700)
	os.WriteFile(filepath.Join(root, id, "profile", "c"), []byte("x"), 0o600)
	if err := RemoveTree(root, id); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, id)); !os.IsNotExist(err) {
		t.Fatal("not removed")
	}
	if err := RemoveTree(root, id); err != nil {
		t.Fatal("missing directory should be fine:", err)
	}
	for _, bad := range []string{"..", "../x", "", "org.arcticlinux.WebApp.X_abcdef/..", "/etc"} {
		if err := RemoveTree(root, bad); err == nil {
			t.Errorf("RemoveTree accepted %q", bad)
		}
	}
	// A symlinked app directory: the link goes, its target stays.
	target := t.TempDir()
	os.WriteFile(filepath.Join(target, "keep"), []byte("x"), 0o600)
	os.Symlink(target, filepath.Join(root, id))
	if err := RemoveTree(root, id); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(target, "keep")); err != nil {
		t.Fatal("followed a symlink")
	}
}

func TestPathsFromEnv(t *testing.T) {
	t.Setenv("HOME", "/home/u")
	t.Setenv("XDG_DATA_HOME", "relative/ignored")
	t.Setenv("XDG_CACHE_HOME", "/c")
	t.Setenv("XDG_STATE_HOME", "")
	t.Setenv("XDG_RUNTIME_DIR", "/run/user/1000")
	p, err := PathsFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	id := "org.arcticlinux.WebApp.X_abcdef"
	checks := map[string]string{
		p.AppFile(id):       "/home/u/.local/share/arctic/webapps/" + id + "/app.json",
		p.Cache(id):         "/c/arctic/webapps/" + id,
		p.Log(id):           "/home/u/.local/state/arctic/webapps/" + id + ".log",
		p.PidFile(id):       "/run/user/1000/arctic-webapp/" + id + ".pid",
		p.DesktopFile(id):   "/home/u/.local/share/applications/" + id + ".desktop",
		p.IconFile(id, 128): "/home/u/.local/share/icons/hicolor/128x128/apps/" + id + ".png",
		p.FlatpakProfile("com.brave.Browser", id): "/home/u/.var/app/com.brave.Browser/data/arctic-webapps/" + id,
	}
	for got, want := range checks {
		if got != want {
			t.Errorf("got %s, want %s", got, want)
		}
	}
}

func TestRunningPid(t *testing.T) {
	p := testPaths(t)
	proc := t.TempDir()
	old := ProcRoot
	ProcRoot = proc
	defer func() { ProcRoot = old }()
	id := "org.arcticlinux.WebApp.X_abcdef"
	if p.RunningPid(id) != 0 {
		t.Fatal("no pid file: not running")
	}
	p.WritePid(id, 4242)
	os.MkdirAll(filepath.Join(proc, "4242"), 0o755)
	os.WriteFile(filepath.Join(proc, "4242", "cmdline"), []byte("arctic-webapp-host\x00--app-id\x00"+id+"\x00"), 0o644)
	if p.RunningPid(id) != 4242 {
		t.Fatal("host with our id should count")
	}
	// A recycled pid running something else never counts.
	os.WriteFile(filepath.Join(proc, "4242", "cmdline"), []byte("bash\x00"), 0o644)
	if p.RunningPid(id) != 0 {
		t.Fatal("recycled pid counted")
	}
	// A browser with this app's profile directory counts.
	os.WriteFile(filepath.Join(proc, "4242", "cmdline"), []byte("chromium-browser\x00--app=https://x/\x00--user-data-dir=/home/u/.local/share/arctic/webapps/"+id+"/chromium\x00"), 0o644)
	if p.RunningPid(id) != 4242 {
		t.Fatal("dnf browser with our profile should count")
	}
	os.WriteFile(filepath.Join(proc, "4242", "cmdline"), []byte("flatpak\x00run\x00--user-data-dir=/home/u/.var/app/com.brave.Browser/data/arctic-webapps/"+id+"\x00"), 0o644)
	if p.RunningPid(id) != 4242 {
		t.Fatal("flatpak browser with our profile should count")
	}
	if fi, _ := os.Stat(p.RuntimeDir); fi.Mode().Perm() != 0o700 {
		t.Errorf("runtime dir mode %v", fi.Mode().Perm())
	}
}
