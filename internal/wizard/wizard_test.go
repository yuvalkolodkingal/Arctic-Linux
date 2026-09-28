package wizard

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/hw"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

type fakeEnv struct {
	cat      *catalog.Catalog
	disks    []hw.Disk
	net      protocol.NetworkState
	secrets  SecretsInfo
	firmware string
	names    map[string]bool
	hw       hw.Hardware
}

func (e *fakeEnv) Catalog() *catalog.Catalog      { return e.cat }
func (e *fakeEnv) Disks() []hw.Disk               { return e.disks }
func (e *fakeEnv) Network() protocol.NetworkState { return e.net }
func (e *fakeEnv) Secrets() SecretsInfo           { return e.secrets }
func (e *fakeEnv) Model() string                  { return "thinkpad" }
func (e *fakeEnv) DetectTimezone() Detected       { return Detected{"Asia/Jerusalem", "network"} }
func (e *fakeEnv) Now() time.Time                 { return time.Date(2026, 9, 27, 4, 42, 0, 0, time.UTC) }
func (e *fakeEnv) Firmware() string               { return e.firmware }
func (e *fakeEnv) SystemNames() map[string]bool   { return e.names }
func (e *fakeEnv) Hardware() hw.Hardware          { return e.hw }

func testDisks() []hw.Disk {
	return []hw.Disk{
		{Path: "/dev/nvme0n1", Model: "Samsung SSD 980", SizeBytes: 512 * hw.GB, PTType: "gpt", Transport: "nvme",
			ExistingOS: []string{"Windows 11"}, FreeRegions: []hw.Region{{StartByte: 332 * hw.GB, SizeBytes: 180 * hw.GB}},
			Partitions: []hw.Partition{{Path: "/dev/nvme0n1p1", Number: 1, StartByte: hw.MiB, SizeBytes: 100 * hw.MiB, Type: hw.TypeESP, FSType: "vfat"}}},
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
	env := &fakeEnv{cat: cat, disks: testDisks(), firmware: "uefi", names: map[string]bool{"man": true, "video": true, "nixbld7": true}}
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
		"Language: English (US)",
		"Keyboard: English (US) layout",
		"Time zone: Jerusalem (UTC+3)",
		"Disk: Erase Samsung SSD 980 · 512 GB",
		"Encryption: On — you’ll type your passphrase each time the computer starts",
		"Account: Noa Levi (noa) on noa-thinkpad",
		"Apps: Zen, Zed, kitty, zsh, yazi, Thunar, Collabora, VLC",
	}
	// Every row's Change link reaches its step.
	for _, r := range s.Rows {
		if i := StepIndex(r.Step); i < 0 || i >= StepIndex(StepSummary) {
			t.Errorf("row %q links to %q", r.Label, r.Step)
		}
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
	if s.PrimaryLabel != "Install alongside Windows 11" || !strings.Contains(s.Rows[3].Value, "Next to Windows 11") {
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
	d, err := set(t, w, "apps", `{"selection":{"browser":["firefox"],"files":["thunar","yazi"],"gaming":["steam"]}}`)
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

func TestSummaryChangeReachesKeyboardAndEncryption(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	for _, id := range []string{StepKeyboard, StepEncryption} {
		if err := w.Goto(id); err != nil || w.Current() != id {
			t.Fatalf("Goto %s: %v (at %s)", id, err, w.Current())
		}
		mustNext(t, w)
		if w.Current() != StepSummary {
			t.Fatalf("Next after changing %s: at %s", id, w.Current())
		}
	}
	// Changing the language from Summary shows Keyboard (new suggestions), then Summary.
	if err := w.Goto(StepWelcome); err != nil {
		t.Fatal(err)
	}
	set(t, w, "welcome", `{"language":"de_DE.UTF-8"}`)
	mustNext(t, w)
	if w.Current() != StepKeyboard {
		t.Fatalf("after a language change: at %s, want keyboard", w.Current())
	}
	mustNext(t, w)
	if w.Current() != StepSummary {
		t.Fatalf("after keyboard: at %s, want summary", w.Current())
	}
	// Same language: straight back to Summary.
	w.Goto(StepWelcome)
	mustNext(t, w)
	if w.Current() != StepSummary {
		t.Fatalf("unchanged language: at %s, want summary", w.Current())
	}
}

func TestBackToWizardAfterFailure(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	mustNext(t, w) // summary → install
	w.BeginInstall()
	w.SetPhase(PhaseFailed)
	if _, err := set(t, w, "disk", `{"mode":"alongside"}`); err == nil || err.Code != protocol.CodeState || !strings.Contains(err.Message, "Disk step") {
		t.Errorf("SetStep while failed: %v", err)
	}
	// Change on the Summary: Goto a done step leaves the failure and returns to Summary after.
	if err := w.Goto(StepDisk); err != nil {
		t.Fatal(err)
	}
	if w.Phase() != PhaseWizard || w.Current() != StepDisk {
		t.Fatalf("after Goto: phase %s at %s", w.Phase(), w.Current())
	}
	if _, err := set(t, w, "disk", `{"disk":"/dev/sda"}`); err != nil {
		t.Fatal(err)
	}
	mustNext(t, w)
	if w.Current() != StepSummary {
		t.Fatalf("at %s, want summary", w.Current())
	}
	if st := w.Snapshot(); st.Steps[StepIndex(StepSummary)].State != "current" || st.Steps[StepIndex(StepInstall)].State != "todo" || st.State != PhaseWizard {
		t.Errorf("snapshot after reopening %+v", st)
	}
	if err := w.ReadyToInstall(); err != nil {
		t.Fatal(err)
	}
	// Back from a failure goes to Summary; Goto summary from the install screen too.
	mustNext(t, w)
	w.BeginInstall()
	w.SetPhase(PhaseFailed)
	if err := w.Back(); err != nil || w.Phase() != PhaseWizard || w.Current() != StepSummary {
		t.Fatalf("Back after failure: %v, %s at %s", err, w.Phase(), w.Current())
	}
	mustNext(t, w)
	w.BeginInstall()
	w.SetPhase(PhaseFailed)
	if err := w.Goto(StepSummary); err != nil || w.Phase() != PhaseWizard || w.Current() != StepSummary {
		t.Fatalf("Goto summary after failure: %v, %s at %s", err, w.Phase(), w.Current())
	}
	// While installing, nothing moves.
	mustNext(t, w)
	w.BeginInstall()
	if err := w.Back(); err == nil {
		t.Error("Back while installing must fail")
	}
	if err := w.Goto(StepDisk); err == nil {
		t.Error("Goto while installing must fail")
	}
}

func TestUsernameAvoidsSystemNames(t *testing.T) {
	w, env := newTest(t)
	walk(t, w, env)
	w.Goto("account")
	d, err := set(t, w, "account", `{"full_name":"Man Li","username":"","hostname":""}`)
	if a := d.(AccountData); err != nil || a.Username != "man1" {
		t.Errorf("suggestion for a taken group: %+v %v", a, err)
	}
	for _, u := range []string{"man", "video", "nixbld7", "tty", "kvm", "nixbld12"} {
		if _, err := set(t, w, "account", `{"username":"`+u+`"}`); err == nil || err.Fields["username"] != MsgNameTaken {
			t.Errorf("%s accepted: %v", u, err)
		}
	}
	if _, err := set(t, w, "account", `{"username":"mani"}`); err != nil {
		t.Errorf("mani: %v", err)
	}
	if got := SuggestUsernameAvoiding("Man Li", map[string]bool{"man1": true}); got != "man2" {
		t.Errorf("second suggestion %q", got)
	}
	if names := ReadAccountNames(strings.NewReader("root:x:0:0::/root:/bin/bash\n# comment\n\nman:x:15:\n")); strings.Join(names, ",") != "root,man" {
		t.Errorf("names %v", names)
	}
}

func TestAlongsideNeedsESPOnUEFI(t *testing.T) {
	w, env := newTest(t)
	env.disks[0].Partitions = nil // no ESP
	r, _ := w.Get("disk")
	if opts := r.Options.(map[string]any)["disks"].([]DiskOption); opts[0].AlongsidePossible {
		t.Errorf("UEFI alongside offered without an ESP: %+v", opts[0])
	}
	_, err := set(t, w, "disk", `{"disk":"/dev/nvme0n1","mode":"alongside"}`)
	if err == nil || !strings.Contains(err.Fields["mode"], "no EFI system partition") {
		t.Errorf("got %v", err)
	}
	env.firmware = "bios"
	if _, err := set(t, w, "disk", `{"disk":"/dev/nvme0n1","mode":"alongside"}`); err != nil {
		t.Errorf("BIOS alongside needs no ESP: %v", err)
	}
	// MBR ESP types are matched in any case; a full MBR table can't take two more partitions.
	env.firmware = "uefi"
	env.disks[0].PTType = "dos"
	env.disks[0].Partitions = []hw.Partition{{Number: 1, Type: "0xEF"}}
	if _, err := set(t, w, "disk", `{"disk":"/dev/nvme0n1","mode":"alongside"}`); err != nil {
		t.Errorf("MBR disk with an ESP: %v", err)
	}
	env.disks[0].Partitions = []hw.Partition{{Number: 1, Type: "0xef"}, {Number: 2, Type: "0x7"}, {Number: 3, Type: "0x27"}}
	if _, err := set(t, w, "disk", `{"disk":"/dev/nvme0n1","mode":"alongside"}`); err == nil || !strings.Contains(err.Fields["mode"], "no room") {
		t.Errorf("full MBR table: %v", err)
	}
}

func TestKeyboardConfig(t *testing.T) {
	cases := []struct {
		kb   KeyboardData
		want XKB
	}{
		{KeyboardData{"us", ""}, XKB{Layout: "us", Keymap: "us", Latin: true}},
		{KeyboardData{"de", "nodeadkeys"}, XKB{Layout: "de", Variant: "nodeadkeys", Keymap: "de-nodeadkeys", Latin: true}},
		{KeyboardData{"il", ""}, XKB{Layout: "us,il", Options: "grp:alt_shift_toggle", Keymap: "us"}},
		{KeyboardData{"ru", ""}, XKB{Layout: "us,ru", Options: "grp:alt_shift_toggle", Keymap: "ru"}},
		{KeyboardData{"ua", ""}, XKB{Layout: "us,ua", Options: "grp:alt_shift_toggle", Keymap: "ua-utf"}},
		{KeyboardData{"gr", ""}, XKB{Layout: "us,gr", Options: "grp:alt_shift_toggle", Keymap: "gr"}},
		{KeyboardData{"ara", ""}, XKB{Layout: "us,ara", Options: "grp:alt_shift_toggle", Keymap: "us"}},
	}
	for _, c := range cases {
		if got := KeyboardConfig(c.kb); got != c.want {
			t.Errorf("%+v: got %+v, want %+v", c.kb, got, c.want)
		}
	}
	// Every offered layout maps to something.
	for _, l := range Layouts {
		if x := KeyboardConfig(KeyboardData{l.Layout, l.Variant}); x.Layout == "" || x.Keymap == "" {
			t.Errorf("%s: %+v", l.Key(), x)
		}
	}
	w, _ := newTest(t)
	d, err := set(t, w, "keyboard", `{"layout":"il"}`)
	if v, ok := d.(KeyboardView); err != nil || !ok || v.XKB.Layout != "us,il" || v.Layout != "il" {
		t.Errorf("SetStep keyboard: %#v %v", d, err)
	}
	r, _ := w.Get("keyboard")
	b, _ := json.Marshal(r.Data)
	if string(b) != `{"layout":"il","variant":"","xkb":{"layout":"us,il","variant":"","options":"grp:alt_shift_toggle","keymap":"us","latin":false}}` {
		t.Errorf("GetStep keyboard data %s", b)
	}
	// The xkb object sent back is ignored.
	if _, err := set(t, w, "keyboard", string(b)); err != nil || w.Data.Keyboard != (KeyboardData{"il", ""}) {
		t.Errorf("round trip: %v %+v", err, w.Data.Keyboard)
	}
	s := w.Summary()
	if s.Rows[1].Value != "Hebrew layout, plus English (US) for passwords — Alt+Shift switches" {
		t.Errorf("summary keyboard row %q", s.Rows[1].Value)
	}
}

// The Summary doesn't scroll: a long pick lists the first names and how many more.
func TestSummaryAppsListIsCapped(t *testing.T) {
	names := make([]string, 0, 40)
	for i := 1; i <= 40; i++ {
		names = append(names, fmt.Sprintf("App%d", i))
	}
	if got := appList(names[:summaryApps]); got != strings.Join(names[:summaryApps], ", ") {
		t.Errorf("%d apps: %q", summaryApps, got)
	}
	got := appList(names)
	want := strings.Join(names[:summaryApps], ", ") + fmt.Sprintf(" and %d more", 40-summaryApps)
	if got != want {
		t.Errorf("40 apps: %q, want %q", got, want)
	}
}
