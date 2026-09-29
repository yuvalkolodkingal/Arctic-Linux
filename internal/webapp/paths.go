package webapp

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
)

// Paths are the per-user directories web apps live in (XDG base directories with the usual
// $HOME fallbacks). Nothing is system-wide: no root, pkexec or polkit.
type Paths struct {
	Home       string
	DataHome   string // $XDG_DATA_HOME
	CacheHome  string // $XDG_CACHE_HOME
	StateHome  string // $XDG_STATE_HOME
	RuntimeDir string // $XDG_RUNTIME_DIR/arctic-webapp
}

// PathsFromEnv reads HOME and the XDG variables. Relative XDG values are ignored, as the XDG
// base directory specification says.
func PathsFromEnv() (Paths, error) {
	home := os.Getenv("HOME")
	if home == "" || !filepath.IsAbs(home) {
		h, err := os.UserHomeDir()
		if err != nil || !filepath.IsAbs(h) {
			return Paths{}, fmt.Errorf("HOME is not set")
		}
		home = h
	}
	xdg := func(key, def string) string {
		if v := os.Getenv(key); filepath.IsAbs(v) {
			return filepath.Clean(v)
		}
		return filepath.Join(home, def)
	}
	p := Paths{
		Home:      home,
		DataHome:  xdg("XDG_DATA_HOME", ".local/share"),
		CacheHome: xdg("XDG_CACHE_HOME", ".cache"),
		StateHome: xdg("XDG_STATE_HOME", ".local/state"),
	}
	if rt := os.Getenv("XDG_RUNTIME_DIR"); filepath.IsAbs(rt) {
		p.RuntimeDir = filepath.Join(rt, "arctic-webapp")
	} else {
		// No session runtime directory (a bare ssh login): a private directory in the cache.
		p.RuntimeDir = filepath.Join(p.CacheHome, "arctic", "webapp-run-"+strconv.Itoa(os.Getuid()))
	}
	return p, nil
}

// Root is the registry: one directory per app.
func (p Paths) Root() string { return filepath.Join(p.DataHome, "arctic", "webapps") }

// LockFile serialises every registry write.
func (p Paths) LockFile() string { return filepath.Join(p.Root(), ".lock") }

// AppDir holds app.json, the source icon, window state, permissions and the WebKit profile.
// id must be Valid.
func (p Paths) AppDir(id string) string { return filepath.Join(p.Root(), id) }

// AppFile is the app record.
func (p Paths) AppFile(id string) string { return filepath.Join(p.AppDir(id), "app.json") }

// KeptFile is the record left behind by `remove --keep-data`.
func (p Paths) KeptFile(id string) string { return filepath.Join(p.AppDir(id), "app.removed.json") }

// SourceIcon is the decoded source icon (≤ 512 px) kept for re-rendering.
func (p Paths) SourceIcon(id string) string { return filepath.Join(p.AppDir(id), "icon.png") }

// StateFile is the host's window state.
func (p Paths) StateFile(id string) string { return filepath.Join(p.AppDir(id), "state.json") }

// PermissionsFile is the host's per-origin permission decisions.
func (p Paths) PermissionsFile(id string) string {
	return filepath.Join(p.AppDir(id), "permissions.json")
}

// Profile is the WebKit data directory (cookies, local storage, IndexedDB, service workers).
func (p Paths) Profile(id string) string { return filepath.Join(p.AppDir(id), "profile") }

// ChromiumProfile is the --user-data-dir for the dnf Chromium runtime.
func (p Paths) ChromiumProfile(id string) string { return filepath.Join(p.AppDir(id), "chromium") }

// FlatpakProfile is the --user-data-dir for a Flatpak browser: the sandbox can write there.
func (p Paths) FlatpakProfile(ref, id string) string {
	return filepath.Join(p.Home, ".var", "app", ref, "data", "arctic-webapps", id)
}

// Cache is the WebKit cache directory.
func (p Paths) Cache(id string) string { return filepath.Join(p.CacheHome, "arctic", "webapps", id) }

// Log is the host's log (1 MiB, one rotation).
func (p Paths) Log(id string) string {
	return filepath.Join(p.StateHome, "arctic", "webapps", id+".log")
}

// PidFile records the running app's primary process.
func (p Paths) PidFile(id string) string { return filepath.Join(p.RuntimeDir, id+".pid") }

// Applications is where launcher entries go.
func (p Paths) Applications() string { return filepath.Join(p.DataHome, "applications") }

// DesktopFile is the app's launcher entry.
func (p Paths) DesktopFile(id string) string { return filepath.Join(p.Applications(), id+".desktop") }

// Hicolor is the user's hicolor icon theme.
func (p Paths) Hicolor() string { return filepath.Join(p.DataHome, "icons", "hicolor") }

// IconSizes are the PNG sizes installed for every app.
var IconSizes = []int{48, 64, 128, 256, 512}

// IconFile is one installed icon size.
func (p Paths) IconFile(name string, size int) string {
	return filepath.Join(p.Hicolor(), fmt.Sprintf("%dx%d", size, size), "apps", name+".png")
}

// EnsureRuntimeDir creates the private runtime directory.
func (p Paths) EnsureRuntimeDir() error {
	if err := os.MkdirAll(p.RuntimeDir, 0o700); err != nil {
		return err
	}
	return os.Chmod(p.RuntimeDir, 0o700)
}
