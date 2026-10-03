package webapp

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// AutostartFile is owned by the web-app manager; the desktop Startup page may set Hidden.
func (p Paths) AutostartFile(id string) string {
	dir := p.ConfigHome
	if dir == "" {
		dir = filepath.Join(p.Home, ".config")
	}
	return filepath.Join(dir, "autostart", id+".desktop")
}

func (p Paths) AutostartEnabled(id string) bool {
	if !Valid(id) {
		return false
	}
	data, err := os.ReadFile(p.AutostartFile(id))
	if err != nil {
		return false
	}
	entry := ParseEntry(data)
	return entry["X-Arctic-WebApp-Id"] == id && entry["Hidden"] != "true"
}

func (p Paths) RemoveAutostart(id string) error {
	if !Valid(id) {
		return fmt.Errorf("invalid app id")
	}
	err := os.Remove(p.AutostartFile(id))
	if os.IsNotExist(err) {
		return nil
	}
	return err
}

// WriteAutostart preserves an external Startup-page disable on rename/repair.
// Explicit changes to Start at login override it.
func (p Paths) WriteAutostart(a *App, explicit bool) error {
	if !Valid(a.ID) {
		return fmt.Errorf("invalid app id")
	}
	if !a.Options.StartAtLogin {
		return p.RemoveAutostart(a.ID)
	}
	hidden := false
	if !explicit {
		if data, err := os.ReadFile(p.AutostartFile(a.ID)); err == nil {
			hidden = ParseEntry(data)["Hidden"] == "true"
		}
	}
	data := string(DesktopEntry(a))
	lines := strings.Split(data, "\n")
	for i, line := range lines {
		if strings.HasPrefix(line, "Exec=") {
			lines[i] = "Exec=arctic-webapp run " + a.ID + " --startup"
		}
	}
	data = strings.Join(lines, "\n")
	if hidden {
		data += "Hidden=true\n"
	}
	if err := os.MkdirAll(filepath.Dir(p.AutostartFile(a.ID)), 0o700); err != nil {
		return err
	}
	return WriteFileAtomic(p.AutostartFile(a.ID), []byte(data), 0o600)
}
