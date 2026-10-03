package manage

import (
	"context"
	"os"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

func TestNativeOptionsMigrationAndAutostart(t *testing.T) {
	m := testManager(t)
	a := fixtureApp("Chat", "https://chat.example.org/")
	put(t, m, a)
	// Existing records have no new fields and must retain foreground-only behavior.
	old, err := m.Paths.Load(a.ID)
	if err != nil || old.Options.KeepRunning || old.Options.StartAtLogin || old.Options.AskDownload {
		t.Fatalf("migration: %+v %v", old, err)
	}
	res, err := m.Set(context.Background(), api.SetParams{ID: a.ID, KeepRunning: yes(), StartAtLogin: yes(), AskDownload: yes()})
	if err != nil || !res.App.KeepRunning || !res.App.StartAtLogin || !res.App.AskDownload {
		t.Fatalf("set: %+v %v", res, err)
	}
	data, err := os.ReadFile(m.Paths.AutostartFile(a.ID))
	if err != nil || !strings.Contains(string(data), "Exec=arctic-webapp run "+a.ID+" --startup\n") {
		t.Fatalf("entry: %s %v", data, err)
	}
	// Startup apps can disable the same entry. Rename/repair must preserve that choice.
	os.WriteFile(m.Paths.AutostartFile(a.ID), append(data, []byte("Hidden=true\n")...), 0600)
	res, err = m.Set(context.Background(), api.SetParams{ID: a.ID, Name: str("Other Chat")})
	if err != nil || res.App.StartAtLogin {
		t.Fatalf("external disable: %+v %v", res, err)
	}
	if _, err := m.Repair(); err != nil {
		t.Fatal(err)
	}
	if m.Paths.AutostartEnabled(a.ID) {
		t.Fatal("repair reenabled startup")
	}
	res, err = m.Set(context.Background(), api.SetParams{ID: a.ID, StartAtLogin: yes()})
	if err != nil || !res.App.StartAtLogin {
		t.Fatalf("explicit enable: %+v %v", res, err)
	}
	if _, err := m.Remove([]string{a.ID}, true); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(m.Paths.AutostartFile(a.ID)); !os.IsNotExist(err) {
		t.Fatalf("kept profile left startup entry: %v", err)
	}
	if _, err := m.Paths.LoadKept(a.ID); err != nil {
		t.Fatal("lost kept profile", err)
	}
}

func TestAutostartRejectsInvalidID(t *testing.T) {
	m := testManager(t)
	if err := m.Paths.WriteAutostart(&webapp.App{ID: "../../bad", Options: webapp.Options{StartAtLogin: true}}, true); err == nil {
		t.Fatal("accepted invalid id")
	}
	if err := m.Paths.RemoveAutostart("../../bad"); err == nil {
		t.Fatal("accepted invalid removal")
	}
}
