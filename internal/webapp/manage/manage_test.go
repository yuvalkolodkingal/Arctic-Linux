package manage

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// testManager is a Manager over a temp tree with a fake host binary.
func testManager(t *testing.T) *Manager {
	t.Helper()
	d := t.TempDir()
	p := webapp.Paths{Home: d, DataHome: d + "/data", CacheHome: d + "/cache", StateHome: d + "/state", RuntimeDir: d + "/run"}
	host := filepath.Join(d, "host")
	os.WriteFile(host, []byte("#!/bin/sh\n"), 0o755)
	return &Manager{
		Paths: p, Env: Env{Root: filepath.Join(d, "root"), Home: d, HostBin: host},
		Now:      func() time.Time { return time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC) },
		StopWait: 200 * time.Millisecond,
		Environ:  []string{"PATH=/usr/bin", "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1"},
	}
}

func fixtureApp(name, start string) *webapp.App {
	id := webapp.NewID(name, "", start, func(string) string { return "" })
	a := &webapp.App{
		Schema: webapp.Schema, Render: webapp.RenderVersion, EngineVersion: webapp.Version,
		ID: id, Name: name, NameSource: "manifest", InputURL: start, StartURL: start,
		Scope: webapp.Scope{Site: "example.org", Scheme: "https"}, Runtime: "webkit",
		Options: webapp.DefaultOptions(),
	}
	a.Normalize()
	return a
}

// put installs an app record and its files as install would.
func put(t *testing.T, m *Manager, a *webapp.App) {
	t.Helper()
	if err := m.Paths.Save(a); err != nil {
		t.Fatal(err)
	}
	if err := m.render(a); err != nil {
		t.Fatal(err)
	}
	os.MkdirAll(m.Paths.Profile(a.ID), 0o700)
	os.WriteFile(filepath.Join(m.Paths.Profile(a.ID), "cookies.sqlite"), []byte("cookies"), 0o600)
	os.MkdirAll(m.Paths.Cache(a.ID), 0o700)
}

func code(err error) string {
	var pe *protocol.Error
	if errors.As(err, &pe) {
		return pe.Code
	}
	return ""
}

func TestListAndOrphans(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	// A launcher entry whose record is gone is listed as an orphan.
	orphan := fixtureApp("Gone", "https://gone.example.org/")
	m.Paths.WriteDesktop(orphan)

	res, err := m.List(true, true)
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Apps) != 2 {
		t.Fatalf("apps: %+v", res.Apps)
	}
	got := map[string]string{}
	for _, x := range res.Apps {
		got[x.ID] = x.Problem
		if x.DataBytes == nil {
			t.Errorf("%s: sizes asked but data_bytes is null", x.ID)
		}
	}
	if got[a.ID] != "" || got[orphan.ID] != "no-registry" {
		t.Fatalf("problems: %v", got)
	}
	if res.Kept == nil {
		t.Fatal("kept asked: must be a list")
	}
	info := res.Apps[0]
	if info.ID == orphan.ID {
		info = res.Apps[1]
	}
	if info.IconPath == "" || !strings.HasSuffix(info.IconPath, "/128x128/apps/"+a.ID+".png") {
		t.Errorf("icon_path %q", info.IconPath)
	}
	if !info.RuntimeAvailable || info.Running {
		t.Errorf("runtime/running: %+v", info)
	}
}

func TestRemoveDeletesEverything(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	res, err := m.Remove([]string{a.ID}, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Removed) != 1 || res.Removed[0].KeptData || res.Removed[0].Stopped {
		t.Fatalf("result %+v", res)
	}
	for _, p := range []string{m.Paths.AppDir(a.ID), m.Paths.DesktopFile(a.ID), m.Paths.IconFile(a.ID, 48), m.Paths.Cache(a.ID)} {
		if _, err := os.Stat(p); !os.IsNotExist(err) {
			t.Errorf("%s still exists", p)
		}
	}
	if _, err := m.Remove([]string{a.ID}, false); code(err) != webapp.CodeNotFound {
		t.Fatalf("second remove: %v", err)
	}
	if _, err := m.Remove([]string{"../../etc"}, false); code(err) != webapp.CodeNotFound {
		t.Fatalf("bad id: %v", err)
	}
}

// remove --keep-data keeps the profile and lists it under kept; forget deletes it.
func TestRemoveKeepDataThenForget(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	if _, err := m.Remove([]string{a.ID}, true); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(m.Paths.Profile(a.ID), "cookies.sqlite")); err != nil {
		t.Fatal("profile deleted despite --keep-data")
	}
	for _, p := range []string{m.Paths.AppFile(a.ID), m.Paths.DesktopFile(a.ID), m.Paths.IconFile(a.ID, 48)} {
		if _, err := os.Stat(p); !os.IsNotExist(err) {
			t.Errorf("%s still exists", p)
		}
	}
	res, _ := m.List(false, true)
	if len(res.Apps) != 0 || len(res.Kept) != 1 || res.Kept[0].ID != a.ID {
		t.Fatalf("list after keep: %+v", res)
	}
	if err := m.Forget([]string{a.ID}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(m.Paths.AppDir(a.ID)); !os.IsNotExist(err) {
		t.Fatal("forget left the app directory")
	}
	if err := m.Forget([]string{a.ID}); code(err) != webapp.CodeNotFound {
		t.Fatalf("forget twice: %v", err)
	}
}

// An app whose record can't be read (Settings lists it as "Record missing") is never removed
// with its sign-in data when you asked to keep it: there is nothing to keep it under.
func TestRemoveKeepDataRefusesABrokenRecord(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	os.WriteFile(m.Paths.AppFile(a.ID), []byte(`{"schema":1,"id":"`+a.ID+`","start_url":"javascript:alert(1)"}`), 0o600)
	cookies := filepath.Join(m.Paths.Profile(a.ID), "cookies.sqlite")
	if _, err := m.Remove([]string{a.ID}, true); code(err) != webapp.CodeState || !strings.Contains(webapp.AsError(err).Message, "Notes") {
		t.Fatalf("keep-data on a broken record: %v", err)
	}
	if _, err := os.Stat(cookies); err != nil {
		t.Fatal("sign-in data deleted despite --keep-data")
	}
	if _, err := os.Stat(m.Paths.DesktopFile(a.ID)); err != nil {
		t.Fatal("the refused remove took the launcher entry")
	}
	// Removing it with its sign-in data still works.
	if _, err := m.Remove([]string{a.ID}, false); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(m.Paths.AppDir(a.ID)); !os.IsNotExist(err) {
		t.Fatal("the app directory is still there")
	}
}

func TestClearDataKeepsApp(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	os.WriteFile(m.Paths.PermissionsFile(a.ID), []byte("{}"), 0o600)
	if err := m.ClearData(a.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(m.Paths.Profile(a.ID)); !os.IsNotExist(err) {
		t.Fatal("profile kept")
	}
	if _, err := os.Stat(m.Paths.PermissionsFile(a.ID)); !os.IsNotExist(err) {
		t.Fatal("permissions kept")
	}
	if _, err := m.Paths.Load(a.ID); err != nil {
		t.Fatal("app gone:", err)
	}
}

func TestRepairRewritesAndRemovesOrphans(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Notes", "https://notes.example.org/")
	put(t, m, a)
	os.Remove(m.Paths.DesktopFile(a.ID))
	orphan := fixtureApp("Gone", "https://gone.example.org/")
	m.Paths.WriteDesktop(orphan)
	res, err := m.Repair()
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Repaired) != 1 || len(res.OrphansRemoved) != 1 || res.OrphansRemoved[0] != orphan.ID {
		t.Fatalf("repair: %+v", res)
	}
	if _, err := os.Stat(m.Paths.DesktopFile(a.ID)); err != nil {
		t.Fatal("desktop file not rewritten")
	}
}

func TestPlanRunWebKit(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Mail", "https://mail.google.com/mail/u/0/")
	a.Handlers = []string{"mailto"}
	a.Options.Rendering = "software"
	put(t, m, a)
	plan, err := m.PlanRun(a.ID, "mailto:someone@example.org?subject=Hi%20there", "", false)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"arctic-webapp-host", "--app-id", a.ID, "--url", "https://mail.google.com/mail/?extsrc=mailto&url=mailto%3Asomeone%40example.org%3Fsubject%3DHi%2520there"}
	if strings.Join(plan.Exec.Argv, " ") != strings.Join(want, " ") {
		t.Fatalf("argv %q", plan.Exec.Argv)
	}
	env := strings.Join(plan.Exec.Env, "\n")
	if strings.Contains(env, "WEBKIT_DISABLE_SANDBOX") || !strings.Contains(env, "WEBKIT_SKIA_ENABLE_CPU_RENDERING=1") {
		t.Fatalf("env %q", plan.Exec.Env)
	}
	// A literal %u from a launcher, or a non-mailto URI, opens nothing.
	for _, uri := range []string{"%u", "https://evil.example/", "mailto:x\ny"} {
		plan, err := m.PlanRun(a.ID, uri, "", false)
		if err != nil || len(plan.Exec.Argv) != 3 {
			t.Errorf("%q: %v %q", uri, err, plan.Exec.Argv)
		}
	}
	if _, err := m.PlanRun("org.arcticlinux.WebApp.Nope_000000", "", "", false); code(err) != webapp.CodeNotFound {
		t.Fatalf("unknown app: %v", err)
	}
}

func TestPlanRunBrowserMissingRequiresSelection(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Flix", "https://www.netflix.com/")
	a.Runtime = "chromium:brave"
	a.WMClass = "brave-www.netflix.com__-Default"
	put(t, m, a)
	plan, err := m.PlanRun(a.ID, "", "", false)
	if code(err) != webapp.CodeUnsupported || plan.Exec.Path != "" {
		t.Fatalf("missing runtime must not switch profiles: %+v %v", plan, err)
	}
	// With the Flatpak installed: flatpak run with a per-app profile in the sandbox's data dir.
	os.MkdirAll(filepath.Join(m.Env.Root, "usr/bin"), 0o755)
	os.WriteFile(filepath.Join(m.Env.Root, "usr/bin/flatpak"), nil, 0o755)
	os.MkdirAll(filepath.Join(m.Env.Root, "var/lib/flatpak/app/com.brave.Browser/current/active"), 0o755)
	plan, err = m.PlanRun(a.ID, "", "", false)
	if err != nil {
		t.Fatal(err)
	}
	want := "flatpak run --branch=stable com.brave.Browser --app=https://www.netflix.com/ --user-data-dir=" +
		m.Paths.FlatpakProfile("com.brave.Browser", a.ID) + " --no-first-run --no-default-browser-check"
	if !plan.Browser || strings.Join(plan.Exec.Argv, " ") != want {
		t.Fatalf("argv %q", plan.Exec.Argv)
	}
	for _, arg := range plan.Exec.Argv {
		for _, bad := range []string{"--no-sandbox", "--class", "--remote-debugging", "--ignore-certificate"} {
			if strings.HasPrefix(arg, bad) {
				t.Fatalf("forbidden flag %s", arg)
			}
		}
	}
}

func TestRuntimeEnv(t *testing.T) {
	env := runtimeEnv([]string{"A=1", "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1", "WEBKIT_DISABLE_DMABUF_RENDERER=0"}, "auto")
	got := strings.Join(env, " ")
	if got != "A=1 WEBKIT_DISABLE_DMABUF_RENDERER=0" {
		t.Fatalf("env %q", got)
	}
	if got := strings.Join(runtimeEnv([]string{"PATH=/usr/bin"}, "auto"), " "); got != "PATH=/usr/bin" {
		t.Fatalf("automatic rendering disables acceleration: %q", got)
	}
	software := strings.Join(runtimeEnv(nil, "software"), " ")
	if !strings.Contains(software, "WEBKIT_SKIA_ENABLE_CPU_RENDERING=1") || !strings.Contains(software, "WEBKIT_DISABLE_COMPOSITING_MODE=1") {
		t.Fatalf("software rendering no longer opts out: %q", software)
	}
}

func TestFindClient(t *testing.T) {
	cases := []struct {
		out  string
		want string
		ok   bool
	}{
		{`{"clients":[{"id":7,"appid":"brave-x__-Default","title":"X"}]}`, "7", true},
		{`[{"id":"9","app_id":"brave-x__-Default"}]`, "9", true},
		{`{"clients":[{"id":7,"appid":"other"}]}`, "", false},
		{`not json`, "", false},
	}
	for _, c := range cases {
		got, ok := findClient([]byte(c.out), "brave-x__-Default")
		if got != c.want || ok != c.ok {
			t.Errorf("%s: %q %v", c.out, got, ok)
		}
	}
}

// Launch-or-focus with a fake mmsg on PATH: a running window is focused, else nothing.
func TestFocusRunningFakeMmsg(t *testing.T) {
	dir := t.TempDir()
	log := filepath.Join(dir, "log")
	script := "#!/bin/sh\necho \"$@\" >> " + log + "\nif [ \"$1\" = get ]; then echo '{\"clients\":[{\"id\":12,\"appid\":\"brave-a__-Default\"}]}'; fi\n"
	os.WriteFile(filepath.Join(dir, "mmsg"), []byte(script), 0o755)
	t.Setenv("PATH", dir)
	if !FocusRunning("brave-a__-Default") {
		t.Fatal("should focus")
	}
	data, _ := os.ReadFile(log)
	if !strings.Contains(string(data), "dispatch focusid client,12") {
		t.Fatalf("mmsg calls: %s", data)
	}
	if FocusRunning("brave-b__-Default") {
		t.Fatal("no such window")
	}
	t.Setenv("PATH", t.TempDir())
	if FocusRunning("brave-a__-Default") {
		t.Fatal("no mmsg: launch instead")
	}
}

func TestMailtoURL(t *testing.T) {
	if got := MailtoURL("https://mail.google.com/mail/u/0/", "mailto:a@b.c"); got != "https://mail.google.com/mail/?extsrc=mailto&url=mailto%3Aa%40b.c" {
		t.Errorf("gmail: %q", got)
	}
	for _, bad := range []string{"https://a.b/", "MAILTO", "mailto:" + strings.Repeat("a", 2050), "%u"} {
		if MailtoURL("https://mail.google.com/", bad) != "" {
			t.Errorf("accepted %q", bad)
		}
	}
	if MailtoURL("https://example.org/", "mailto:a@b.c") != "" {
		t.Error("non-mail site")
	}
	if MailTemplate("http://mail.google.com/") != "" {
		t.Error("http must not count")
	}
}
