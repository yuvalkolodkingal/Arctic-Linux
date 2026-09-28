package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/manage"
)

// testCLI runs commands in-process over a temp HOME.
type testCLI struct {
	t    *testing.T
	home string
	m    *manage.Manager
}

func newTestCLI(t *testing.T) *testCLI {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_DATA_HOME", "")
	t.Setenv("XDG_CACHE_HOME", "")
	t.Setenv("XDG_STATE_HOME", "")
	t.Setenv("XDG_RUNTIME_DIR", filepath.Join(home, "run"))
	os.MkdirAll(filepath.Join(home, "run"), 0o700)
	host := filepath.Join(home, "fake-host")
	os.WriteFile(host, []byte("#!/bin/sh\necho 'arctic-webapp-host 0.2.0 (WebKitGTK 2.54.0)'\n"), 0o755)
	t.Setenv("ARCTIC_WEBAPP_HOST", host)
	m, err := manage.New()
	if err != nil {
		t.Fatal(err)
	}
	m.StopWait = 200 * time.Millisecond
	return &testCLI{t: t, home: home, m: m}
}

func (tc *testCLI) run(args ...string) (code int, stdout, stderr string) {
	var out, errb bytes.Buffer
	c := &cli{stdin: strings.NewReader(""), stdout: &out, stderr: &errb, newManager: func() (*manage.Manager, error) { return tc.m, nil }, euid: func() int { return 1000 }}
	code = c.main(args)
	return code, out.String(), errb.String()
}

// runJSON runs a --json command and checks the one-line contract: exactly one line on stdout,
// an ok field, a string error and code on failure, nothing on stderr.
func (tc *testCLI) runJSON(args ...string) (int, map[string]any) {
	tc.t.Helper()
	code, out, errs := tc.run(append(args, "--json")...)
	if errs != "" {
		tc.t.Errorf("%v: stderr in --json mode: %q", args, errs)
	}
	if strings.Count(out, "\n") != 1 || !strings.HasSuffix(out, "\n") {
		tc.t.Fatalf("%v: want exactly one line, got %q", args, out)
	}
	var m map[string]any
	if err := json.Unmarshal([]byte(out), &m); err != nil {
		tc.t.Fatalf("%v: %v: %q", args, err, out)
	}
	if !strings.HasPrefix(out, `{"ok":`) {
		tc.t.Errorf("%v: ok is not the first key: %q", args, out)
	}
	ok, isBool := m["ok"].(bool)
	if !isBool {
		tc.t.Fatalf("%v: no boolean ok: %q", args, out)
	}
	if !ok {
		if _, isStr := m["error"].(string); !isStr {
			tc.t.Errorf("%v: error is not a string: %q", args, out)
		}
		if _, isStr := m["code"].(string); !isStr {
			tc.t.Errorf("%v: code is not a string: %q", args, out)
		}
		if _, has := m["fields"]; has && m["code"] != "invalid" {
			tc.t.Errorf("%v: fields without code invalid", args)
		}
	}
	return code, m
}

func (tc *testCLI) put(name, start string) *webapp.App {
	tc.t.Helper()
	id := webapp.NewID(name, "", start, func(string) string { return "" })
	a := &webapp.App{
		Schema: webapp.Schema, Render: webapp.RenderVersion, EngineVersion: webapp.Version,
		ID: id, Name: name, StartURL: start, InputURL: start, NameSource: "title",
		Scope: webapp.Scope{Site: "example.org", Scheme: "https"}, Options: webapp.DefaultOptions(),
	}
	a.Normalize()
	if err := tc.m.Paths.Save(a); err != nil {
		tc.t.Fatal(err)
	}
	if err := tc.m.Paths.WriteDesktop(a); err != nil {
		tc.t.Fatal(err)
	}
	return a
}

func TestUsage(t *testing.T) {
	tc := newTestCLI(t)
	if code, _, errs := tc.run(); code != 2 || !strings.Contains(errs, "usage:") {
		t.Fatalf("no args: %d %q", code, errs)
	}
	if code, _, errs := tc.run("frobnicate"); code != 2 || !strings.Contains(errs, "unknown command") {
		t.Fatalf("unknown: %d %q", code, errs)
	}
	if code, _, _ := tc.run("show"); code != 2 {
		t.Fatalf("show without id: %d", code)
	}
	code, m := tc.runJSON("remove")
	if code != 2 || m["code"] != "bad_request" || m["error"] != "arctic-webapp remove needs one or more app ids." {
		t.Fatalf("remove --json without ids: %d %v", code, m)
	}
	code, m = tc.runJSON("list", "--bogus")
	if code != 2 || m["code"] != "bad_request" {
		t.Fatalf("bad flag: %d %v", code, m)
	}
}

func TestListShowRemoveJSON(t *testing.T) {
	tc := newTestCLI(t)
	code, m := tc.runJSON("list")
	if code != 0 || m["ok"] != true {
		t.Fatalf("empty list: %v", m)
	}
	if apps, _ := m["apps"].([]any); apps == nil || len(apps) != 0 {
		t.Fatalf("apps must be [] not null: %v", m)
	}
	if _, has := m["kept"]; has {
		t.Fatal("kept only with --kept")
	}
	a := tc.put("Notes", "https://notes.example.org/")
	code, m = tc.runJSON("show", a.ID)
	app, _ := m["app"].(map[string]any)
	if code != 0 || app["id"] != a.ID || app["data_bytes"] != nil {
		t.Fatalf("show: %v", m)
	}
	for _, k := range []string{"id", "name", "url", "host", "icon_name", "icon_path", "category", "runtime", "runtime_available", "running", "links", "notifications", "devtools", "rendering", "extra_domains", "handlers", "handlers_supported", "tls_exceptions", "data_bytes", "problem", "created", "updated"} {
		if _, ok := app[k]; !ok {
			t.Errorf("app info lacks %q", k)
		}
	}
	code, m = tc.runJSON("remove", a.ID, "--keep-data")
	removed, _ := m["removed"].([]any)
	if code != 0 || len(removed) != 1 || removed[0].(map[string]any)["kept_data"] != true {
		t.Fatalf("remove --keep-data: %v", m)
	}
	code, m = tc.runJSON("list", "--kept", "--sizes")
	if kept, _ := m["kept"].([]any); code != 0 || len(kept) != 1 {
		t.Fatalf("kept: %v", m)
	}
	code, m = tc.runJSON("forget", a.ID)
	if code != 0 || len(m) != 1 {
		t.Fatalf("forget: %v", m)
	}
	code, m = tc.runJSON("show", a.ID)
	if code != 1 || m["code"] != "not_found" {
		t.Fatalf("show removed: %d %v", code, m)
	}
}

func TestRefusesRoot(t *testing.T) {
	tc := newTestCLI(t)
	var out bytes.Buffer
	c := &cli{stdout: &out, stderr: &out, newManager: func() (*manage.Manager, error) { return tc.m, nil }, euid: func() int { return 0 }}
	if code := c.main([]string{"list", "--json"}); code != 1 || !strings.Contains(out.String(), `"code":"state"`) {
		t.Fatalf("root: %d %q", code, out.String())
	}
}

func TestVersionJSON(t *testing.T) {
	tc := newTestCLI(t)
	code, m := tc.runJSON("version", "--webkit")
	if code != 0 || m["version"] != webapp.Version || m["host_present"] != true || m["webkit_version"] != "2.54.0" {
		t.Fatalf("version: %v", m)
	}
	if code, out, _ := tc.run("version"); code != 0 || out != "arctic-webapp "+webapp.Version+"\n" {
		t.Fatalf("plain version: %q", out)
	}
}

// run execs the host with the id and no shell.
func TestRunExecsHost(t *testing.T) {
	tc := newTestCLI(t)
	a := tc.put("Notes", "https://notes.example.org/")
	var gotPath string
	var gotArgv []string
	old := execFn
	execFn = func(path string, argv []string, env []string) error {
		gotPath, gotArgv = path, argv
		return os.ErrPermission
	}
	defer func() { execFn = old }()
	code, _, errs := tc.run("run", a.ID, "%u")
	if code != 1 || !strings.Contains(errs, "Couldn't start") {
		t.Fatalf("run: %d %q", code, errs)
	}
	if gotPath != os.Getenv("ARCTIC_WEBAPP_HOST") || strings.Join(gotArgv, " ") != "arctic-webapp-host --app-id "+a.ID {
		t.Fatalf("exec %s %q", gotPath, gotArgv)
	}
	if code, _, _ := tc.run("run", "org.arcticlinux.WebApp.X_000000; rm -rf ~"); code != 1 {
		t.Fatalf("bad id must fail: %d", code)
	}
}
