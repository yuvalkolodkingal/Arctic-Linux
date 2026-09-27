package wizard

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

type fakeEnv struct {
	cat     *catalog.Catalog
	disks   []hw.Disk
	net     protocol.NetworkState
	secrets SecretsInfo
}

func (e *fakeEnv) Catalog() *catalog.Catalog      { return e.cat }
func (e *fakeEnv) Disks() []hw.Disk               { return e.disks }
func (e *fakeEnv) Network() protocol.NetworkState { return e.net }
func (e *fakeEnv) Secrets() SecretsInfo           { return e.secrets }
func (e *fakeEnv) Model() string                  { return "thinkpad" }
func (e *fakeEnv) DetectTimezone() Detected       { return Detected{"Asia/Jerusalem", "network"} }
func (e *fakeEnv) Now() time.Time                 { return time.Date(2026, 9, 27, 4, 42, 0, 0, time.UTC) }

func testDisks() []hw.Disk {
	return []hw.Disk{
		{Path: "/dev/nvme0n1", Model: "Samsung SSD 980", SizeBytes: 512 * hw.GB, PTType: "gpt", Transport: "nvme",
			ExistingOS: []string{"Windows 11"}, FreeRegions: []hw.Region{{StartByte: 332 * hw.GB, SizeBytes: 180 * hw.GB}}},
		{Path: "/dev/sda", Model: "WDC WD10EZEX", SizeBytes: 1 * hw.TB, Rotational: true, Transport: "sata", PTType: "gpt"},
		{Path: "/dev/sdb", Model: "SanDisk Ultra", SizeBytes: 32 * hw.GB, Removable: true, InstallMedia: true, Transport: "usb"},
	}
}

func newTest(t *testing.T) (*Wizard, *fakeEnv) {
	t.Helper()
	cat, err := catalog.Load(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	env := &fakeEnv{cat: cat, disks: testDisks()}
	return New(env, "en_US.UTF-8"), env
}

func set(t *testing.T, w *Wizard, id, js string) (any, *protocol.Error) {
	t.Helper()
	return w.Set(id, json.RawMessage(js))
}

func mustNext(t *testing.T, w *Wizard) {
	t.Helper()
	if err := w.Next(); err != nil {
		t.Fatalf("Next from %s: %v", w.Current(), err)
	}
}

func TestDefaults(t *testing.T) {
	w, _ := newTest(t)
	d := w.Data
	if d.Welcome.Language != "en_US.UTF-8" || d.Keyboard.Layout != "us" || d.Keyboard.Variant != "" {
		t.Errorf("language/keyboard defaults: %+v %+v", d.Welcome, d.Keyboard)
	}
	if d.Timezone.Timezone != "Asia/Jerusalem" || !d.Timezone.AutoTime {
		t.Errorf("timezone: %+v", d.Timezone)
	}
	if d.Disk.Disk != "/dev/nvme0n1" || d.Disk.Mode != ModeErase || !d.Encryption.Enabled {
		t.Errorf("disk: %+v enc %+v", d.Disk, d.Encryption)
	}
	if d.Account.Autologin {
		t.Error("autologin must default to off")
	}
	snap := w.Snapshot()
	if len(snap.Steps) != 11 || snap.Current != "welcome" || snap.Steps[0].State != "current" || snap.Steps[1].State != "todo" || snap.Steps[10].ID != "done" {
		t.Errorf("snapshot %+v", snap)
	}
	if snap.Steps[3].Title != "Time zone" {
		t.Errorf("rail titles: %+v", snap.Steps[3])
	}
}

func TestStepCopy(t *testing.T) {
	w, _ := newTest(t)
	want := map[string]string{
		"welcome": "Welcome to Arctic Linux", "keyboard": "Choose your keyboard layout", "network": "Connect to the internet",
		"timezone": "Where are you?", "disk": "How should we install?", "encryption": "Create an encryption passphrase",
		"account": "Create your account", "apps": "Choose your apps", "summary": "Ready to install",
		"install": "Installing Arctic Linux", "done": "Arctic Linux is ready",
	}
	for id, title := range want {
		r, err := w.Get(id)
		if err != nil {
			t.Fatalf("%s: %v", id, err)
		}
		if r.Title != title {
			t.Errorf("%s title %q, want %q", id, r.Title, title)
		}
	}
	r, _ := w.Get("welcome")
	if r.Help != "This takes about 10 minutes. First, pick the language you’d like to use." || r.Note == "" {
		t.Errorf("welcome copy %+v", r)
	}
	if _, err := w.Get("nope"); err == nil || err.Code != protocol.CodeNotFound {
		t.Errorf("unknown step: %v", err)
	}
}

// walk drives the happy path up to Summary.
func walk(t *testing.T, w *Wizard, env *fakeEnv) {
	t.Helper()
	mustNext(t, w) // welcome
	mustNext(t, w) // keyboard
	if w.Current() == StepNetwork {
		env.net = protocol.NetworkState{Online: true, SSID: "Tundra-5G"}
		mustNext(t, w)
	}
	mustNext(t, w) // timezone
	mustNext(t, w) // disk
	env.secrets.LUKSSet, env.secrets.LUKS = true, CheckPassphrase("acid acorn acre aged")
	mustNext(t, w) // encryption
	if _, err := set(t, w, "account", `{"full_name":"Noa Levi"}`); err != nil {
		t.Fatal(err)
	}
	env.secrets.PasswordSet, env.secrets.Password = true, CheckPassphrase("winter fox 2026")
	mustNext(t, w) // account
	mustNext(t, w) // apps
	if w.Current() != StepSummary {
		t.Fatalf("at %s, want summary", w.Current())
	}
}

func TestHappyPathAndSummary(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	if a := w.Data.Account; a.Username != "noa" || a.Hostname != "noa-thinkpad" {
		t.Fatalf("account autofill %+v", a)
	}
	if err := w.ReadyToInstall(); err != nil {
		t.Fatal(err)
	}
	s := w.Summary()
	got := []string{}
	for _, r := range s.Rows {
		got = append(got, r.Label+": "+r.Value)
	}
	want := []string{
		"Language and keyboard: English (US) · English (US) layout",
		"Time zone: Jerusalem (UTC+3)",
		"Disk: Erase Samsung SSD 980 · 512 GB, encrypted",
		"Account: Noa Levi (noa) on noa-thinkpad",
		"Apps: Zen, Zed, kitty, zsh, yazi, Thunar, Collabora, VLC",
	}
	if strings.Join(got, "\n") != strings.Join(want, "\n") {
		t.Errorf("summary\n%s\nwant\n%s", strings.Join(got, "\n"), strings.Join(want, "\n"))
	}
	if s.Warning != "Installing will erase everything on Samsung SSD 980. This can’t be undone." || s.PrimaryLabel != "Erase disk and install" {
		t.Errorf("warning/primary %q %q", s.Warning, s.PrimaryLabel)
	}
	if err := w.Next(); err != nil || w.Current() != StepInstall {
		t.Errorf("Next at summary should move to install: %v %s", err, w.Current())
	}
	if err := w.ReadyToInstall(); err != nil {
		t.Errorf("ready from the install screen: %v", err)
	}
	if err := w.Next(); err == nil || err.Code != protocol.CodeState {
		t.Errorf("Next at install before Start should be a state error, got %v", err)
	}
	w.BeginInstall()
	if w.Current() != StepInstall || w.Snapshot().Steps[8].State != "done" {
		t.Errorf("after BeginInstall: %+v", w.Snapshot())
	}
	if _, err := set(t, w, "account", `{"username":"x"}`); err == nil {
		t.Error("SetStep during install must fail")
	}
	w.Finish(9)
	r, _ := w.Get("done")
	if r.Help != "Everything is installed, including 9 apps. Welcome aboard, Noa." {
		t.Errorf("done help %q", r.Help)
	}
	if w.Current() != StepDone {
		t.Errorf("current %s", w.Current())
	}
}

func TestNetworkAutoSkipAndBack(t *testing.T) {
	w, env := newTest(t)
	env.net = protocol.NetworkState{Online: true, Wired: true}
	mustNext(t, w)
	mustNext(t, w)
	if w.Current() != StepTimezone || !w.Done(StepNetwork) {
		t.Fatalf("wired+online should skip network; at %s", w.Current())
	}
	if err := w.Back(); err != nil {
		t.Fatal(err)
	}
	if w.Current() != StepKeyboard {
		t.Fatalf("Back should skip the auto-skipped network step, at %s", w.Current())
	}
}

func TestNetworkRequiresOnline(t *testing.T) {
	w, env := newTest(t)
	mustNext(t, w)
	mustNext(t, w)
	if w.Current() != StepNetwork {
		t.Fatalf("at %s", w.Current())
	}
	err := w.Next()
	if err == nil || err.Code != protocol.CodeOffline {
		t.Fatalf("want offline error, got %v", err)
	}
	env.net.Online = true
	mustNext(t, w)
}

func TestGotoOnlyDoneStepsAndReturnToSummary(t *testing.T) {
	w, env := newTest(t)
	if err := w.Goto("disk"); err == nil {
		t.Fatal("Goto to a todo step must fail")
	}
	walk(t, w, env)
	if err := w.Goto("disk"); err != nil {
		t.Fatal(err)
	}
	if _, err := set(t, w, "disk", `{"mode":"alongside"}`); err != nil {
		t.Fatal(err)
	}
	mustNext(t, w)
	if w.Current() != StepSummary {
		t.Fatalf("Next after Change should return to summary, at %s", w.Current())
	}
	s := w.Summary()
	if s.PrimaryLabel != "Install alongside Windows 11" || !strings.Contains(s.Rows[2].Value, "Next to Windows 11") {
		t.Errorf("alongside summary %+v", s)
	}
	if err := w.Goto("summary"); err != nil {
		t.Errorf("Goto current step should be a no-op: %v", err)
	}
	if err := w.Goto("install"); err == nil {
		t.Error("Goto install must fail")
	}
}

func TestAccountValidation(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	w.Goto("account")
	cases := []struct{ js, field, msg string }{
		{`{"username":"Noa"}`, "username", "Use lowercase letters, numbers, - and _."},
		{`{"username":"1noa"}`, "username", "Start with a lowercase letter."},
		{`{"username":"-noa"}`, "username", "Start with a lowercase letter."},
		{`{"username":"no a"}`, "username", "Use lowercase letters, numbers, - and _."},
		{`{"username":"root"}`, "username", "That name is taken by the system. Pick another one."},
		{`{"username":""}`, "username", "Pick a username."},
		{`{"username":"` + strings.Repeat("a", 33) + `"}`, "username", "Use 32 characters or fewer."},
		{`{"hostname":"-bad"}`, "hostname", "Start and end with a letter or number."},
		{`{"hostname":"My PC"}`, "hostname", "Use lowercase letters, numbers and -."},
		{`{"full_name":"a:b"}`, "full_name", "Your name can't contain : , or line breaks."},
	}
	for _, c := range cases {
		_, err := set(t, w, "account", c.js)
		if err == nil || err.Fields[c.field] != c.msg {
			t.Errorf("%s: got %v, want %s=%q", c.js, err, c.field, c.msg)
		}
		set(t, w, "account", `{"full_name":"Noa Levi","username":"noa","hostname":"noa-thinkpad"}`)
	}
	// Errors only for sent fields.
	set(t, w, "account", `{"username":"BAD"}`)
	_, err := set(t, w, "account", `{"autologin":true}`)
	if err != nil {
		t.Errorf("SetStep should only report sent fields, got %v", err)
	}
	// ...but Next reports all of them.
	if err := w.Next(); err == nil || err.Fields["username"] == "" {
		t.Errorf("Next must validate everything, got %v", err)
	}
	set(t, w, "account", `{"username":"noa"}`)
	env.secrets.PasswordSet, env.secrets.Password = true, CheckPassphrase("short")
	if err := w.Next(); err == nil || err.Fields["password"] != "Use at least 8 characters." {
		t.Errorf("weak password: %v", err)
	}
	env.secrets.PasswordSet = false
	if err := w.Next(); err == nil || err.Fields["password"] != "Type a password." {
		t.Errorf("missing password: %v", err)
	}
}

func TestAccountAutofill(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	w.Goto("account")
	d, _ := set(t, w, "account", `{"full_name":"Zoë Müller"}`)
	a := d.(AccountData)
	if a.Username != "zoe" || a.Hostname != "zoe-thinkpad" {
		t.Errorf("autofill %+v", a)
	}
	// A hand-edited username sticks; hostname follows it until edited itself.
	set(t, w, "account", `{"username":"zm"}`)
	d, _ = set(t, w, "account", `{"full_name":"Zoë Anna Müller"}`)
	a = d.(AccountData)
	if a.Username != "zm" || a.Hostname != "zm-thinkpad" {
		t.Errorf("after edit %+v", a)
	}
	set(t, w, "account", `{"hostname":"desk"}`)
	d, _ = set(t, w, "account", `{"username":"zoe"}`)
	if a = d.(AccountData); a.Hostname != "desk" {
		t.Errorf("hand-edited hostname replaced: %+v", a)
	}
}

func TestEncryptionValidation(t *testing.T) {
	w, env := newTest(t)
	env.net.Online = true
	for i := 0; i < 5; i++ {
		mustNext(t, w)
	}
	if w.Current() != StepEncryption {
		t.Fatalf("at %s", w.Current())
	}
	if err := w.Next(); err == nil || err.Fields["passphrase"] != "Type a passphrase." {
		t.Errorf("missing passphrase: %v", err)
	}
	env.secrets.LUKSSet, env.secrets.LUKS = true, CheckPassphrase("aaaaaaaaaa")
	if err := w.Next(); err == nil || !strings.HasPrefix(err.Fields["passphrase"], "Make it a bit longer") {
		t.Errorf("weak passphrase: %v", err)
	}
	set(t, w, "encryption", `{"enabled":false}`)
	mustNext(t, w)
}

func TestDiskValidation(t *testing.T) {
	w, env := newTest(t)
	env.net.Online = true
	for i := 0; i < 4; i++ {
		mustNext(t, w)
	}
	if w.Current() != StepDisk {
		t.Fatalf("at %s", w.Current())
	}
	r, _ := w.Get("disk")
	opts := r.Options.(map[string]any)["disks"].([]DiskOption)
	if len(opts) != 2 {
		t.Fatalf("install media must be hidden: %+v", opts)
	}
	if !opts[0].AlongsidePossible || opts[0].AlongsideLabel != "Uses 180 GB of free space" || opts[0].AlongsideTitle != "Install alongside Windows 11" {
		t.Errorf("nvme option %+v", opts[0])
	}
	if opts[1].AlongsidePossible {
		t.Errorf("sda has no free space: %+v", opts[1])
	}
	cases := []struct{ js, field, msg string }{
		{`{"disk":"/dev/sdb"}`, "disk", "Pick a disk from the list."},
		{`{"disk":"/dev/sda","mode":"alongside"}`, "mode", "There isn’t enough free space to install alongside. Arctic Linux needs 40 GB."},
		{`{"disk":"/dev/sda","mode":"shrink"}`, "mode", "Pick how to install."},
	}
	for _, c := range cases {
		_, err := set(t, w, "disk", c.js)
		if err == nil || err.Fields[c.field] != c.msg {
			t.Errorf("%s: %v", c.js, err)
		}
	}
	env.disks = append(env.disks, hw.Disk{Path: "/dev/sdc", Model: "Tiny", SizeBytes: 16 * hw.GB})
	if _, err := set(t, w, "disk", `{"disk":"/dev/sdc","mode":"erase"}`); err == nil || err.Fields["disk"] == "" {
		t.Errorf("too small disk accepted")
	}
	if _, err := set(t, w, "disk", `{"disk":"/dev/sda","mode":"erase"}`); err != nil {
		t.Error(err)
	}
}

func TestLanguageChangesSuggestedKeyboard(t *testing.T) {
	w, _ := newTest(t)
	set(t, w, "welcome", `{"language":"he_IL.UTF-8"}`)
	if w.Data.Keyboard.Layout != "il" {
		t.Errorf("keyboard not re-suggested: %+v", w.Data.Keyboard)
	}
	r, _ := w.Get("keyboard")
	layouts := r.Options.(map[string]any)["layouts"].([]Layout)
	if layouts[0].Layout != "il" || !layouts[0].Suggested || layouts[0].Description != "Suggested for your language" {
		t.Errorf("first layout %+v", layouts[0])
	}
	if _, err := set(t, w, "welcome", `{"language":"xx_XX.UTF-8"}`); err == nil {
		t.Error("unknown language accepted")
	}
}

func TestSetStepOrder(t *testing.T) {
	w, _ := newTest(t)
	if _, err := set(t, w, "account", `{"full_name":"Noa Levi"}`); err != nil || w.Current() != StepWelcome || w.Data.Account.Username != "noa" {
		t.Errorf("setting a later step stores a draft without moving: %v", err)
	}
	if _, err := set(t, w, "summary", `{}`); err == nil || err.Code != protocol.CodeState {
		t.Errorf("summary has nothing to set: %v", err)
	}
	if _, err := set(t, w, "welcome", `[1]`); err == nil || err.Code != protocol.CodeBadRequest {
		t.Errorf("bad data: %v", err)
	}
}

func TestAppsStep(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	w.Goto("apps")
	_, err := set(t, w, "apps", `{"selection":{"browser":["zen","firefox"]}}`)
	if err == nil || err.Fields["browser"] != "Pick just one browser." {
		t.Fatalf("got %v", err)
	}
	d, err := set(t, w, "apps", `{"selection":{"browser":["firefox"],"files":["thunar","yazi"],"extras":["steam"]}}`)
	if err != nil {
		t.Fatal(err)
	}
	sel := d.(AppsData).Selection
	if sel["files"][0] != "yazi" || sel["editor"] == nil {
		t.Errorf("normalized selection %v", sel)
	}
	r, _ := w.Get("apps")
	if !strings.HasPrefix(r.Note, "9 apps · ") {
		t.Errorf("apps footer %q", r.Note)
	}
}
