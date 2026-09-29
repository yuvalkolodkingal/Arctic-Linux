// Package manage is the manager's side of web apps: inspect, install, update, set, remove,
// launch and the runtime choice. Only the manager (cmd/arctic-webapp) imports it; every write
// happens under the registry's exclusive lock. docs/BUILD-SPEC.md §11 is the contract.
package manage

import (
	"errors"
	"io/fs"
	"os"
	"sort"
	"syscall"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

// Manager holds the paths and hooks every operation needs.
type Manager struct {
	Paths webapp.Paths
	Env   Env
	Now   func() time.Time
	// Progress reports a stage of a long operation (serve turns it into events; the CLI
	// prints it on a terminal's stderr, never in --json mode).
	Progress func(stage, message string)
	// StopWait is how long remove/clear-data/forget wait for a running app to quit.
	StopWait time.Duration
	// Environ is the environment runtimes start with (os.Environ() by default).
	Environ []string
}

// New returns a Manager for the current user.
func New() (*Manager, error) {
	p, err := webapp.PathsFromEnv()
	if err != nil {
		return nil, err
	}
	host := os.Getenv("ARCTIC_WEBAPP_HOST")
	if host == "" {
		host = webapp.HostPath
	}
	return &Manager{
		Paths:    p,
		Env:      Env{Home: p.Home, HostBin: host},
		Now:      func() time.Time { return time.Now().UTC().Truncate(time.Second) },
		StopWait: 3 * time.Second,
		Environ:  os.Environ(),
	}, nil
}

func (m *Manager) progress(stage, msg string) {
	if m.Progress != nil {
		m.Progress(stage, msg)
	}
}

// exclusive runs fn under the registry's exclusive lock.
func (m *Manager) exclusive(fn func() error) error {
	l, err := m.Paths.Acquire(true)
	if err != nil {
		return err
	}
	defer l.Release()
	return fn()
}

// shared runs fn under the shared lock (readers).
func (m *Manager) shared(fn func() error) error {
	l, err := m.Paths.Acquire(false)
	if err != nil {
		return err
	}
	defer l.Release()
	return fn()
}

// Info is the app as List, Get and results show it.
func (m *Manager) Info(a *webapp.App, sizes bool) api.AppInfo {
	info := api.AppInfo{
		ID: a.ID, Name: a.Name, URL: a.StartURL, Host: a.Host(),
		IconName: a.IconName(), Category: a.Category, Runtime: a.Runtime,
		RuntimeAvailable: m.Env.Available(a.Runtime),
		Running:          m.Paths.RunningPid(a.ID) != 0,
		Links:            a.Options.Links, Notifications: a.Options.Notifications,
		Devtools: a.Options.Devtools, Rendering: a.Options.Rendering,
		ExtraDomains:      append([]string{}, a.ExtraDomains...),
		Handlers:          append([]string{}, a.Handlers...),
		HandlersSupported: []string{},
		TLSExceptions:     []api.TLSExceptionInfo{},
		Created:           a.Created.UTC().Format(time.RFC3339),
		Updated:           a.Updated.UTC().Format(time.RFC3339),
	}
	if MailTemplate(a.StartURL) != "" {
		info.HandlersSupported = []string{"mailto"}
	}
	if p := m.Paths.IconFile(a.IconName(), 128); fileExists(p) {
		info.IconPath = p
	}
	for _, e := range a.TLSExceptions {
		info.TLSExceptions = append(info.TLSExceptions, api.TLSExceptionInfo{Host: e.Host, SHA256: e.SHA256})
	}
	if sizes {
		n := m.dataBytes(a)
		info.DataBytes = &n
	}
	switch {
	case !fileExists(m.Paths.DesktopFile(a.ID)):
		info.Problem = "no-desktop-file"
	case !info.RuntimeAvailable && a.Runtime != "webkit":
		info.Problem = "runtime-missing"
	}
	return info
}

func (m *Manager) dataBytes(a *webapp.App) int64 {
	n := webapp.DirSize(m.Paths.AppDir(a.ID)) + webapp.DirSize(m.Paths.Cache(a.ID))
	if b, ok := BrowserFor(a.Runtime); ok && b.Ref != "" {
		n += webapp.DirSize(m.Paths.FlatpakProfile(b.Ref, a.ID))
	}
	return n
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// List returns every app (and orphans: a launcher entry without a record, or a broken record)
// and, with kept, the sign-in data removed apps left behind.
func (m *Manager) List(sizes, kept bool) (api.ListResult, error) {
	res := api.ListResult{Apps: []api.AppInfo{}}
	var stale []*webapp.App
	err := m.shared(func() error {
		apps, bad, err := m.Paths.List()
		if err != nil {
			return err
		}
		seen := map[string]bool{}
		for _, a := range apps {
			seen[a.ID] = true
			if a.Render < webapp.RenderVersion {
				stale = append(stale, a)
			}
			res.Apps = append(res.Apps, m.Info(a, sizes))
		}
		// Orphans: a launcher entry with no (readable) record.
		for _, id := range m.Paths.DesktopIDs() {
			if seen[id] {
				continue
			}
			seen[id] = true
			res.Apps = append(res.Apps, m.orphan(id, sizes))
		}
		for id := range bad {
			if !seen[id] {
				res.Apps = append(res.Apps, m.orphan(id, sizes))
			}
		}
		if kept {
			res.Kept = []api.KeptInfo{}
			ks, err := m.Paths.Kept()
			if err != nil {
				return err
			}
			for _, a := range ks {
				n := m.dataBytes(a)
				k := api.KeptInfo{ID: a.ID, Name: a.Name, URL: a.StartURL}
				if sizes {
					k.DataBytes = &n
				}
				res.Kept = append(res.Kept, k)
			}
		}
		return nil
	})
	if err != nil {
		return res, err
	}
	if len(stale) > 0 {
		m.rerender(stale)
	}
	return res, nil
}

// orphan describes a launcher entry or directory without a usable record.
func (m *Manager) orphan(id string, sizes bool) api.AppInfo {
	info := api.AppInfo{
		ID: id, Name: id, IconName: id, Runtime: "webkit", Problem: "no-registry",
		ExtraDomains: []string{}, Handlers: []string{}, HandlersSupported: []string{},
		TLSExceptions: []api.TLSExceptionInfo{},
	}
	if data, err := os.ReadFile(m.Paths.DesktopFile(id)); err == nil {
		e := webapp.ParseEntry(data)
		if e["Name"] != "" {
			info.Name = e["Name"]
		}
		info.URL = e["X-Arctic-WebApp-URL"]
		if e["Icon"] != "" {
			info.IconName = e["Icon"]
		}
	}
	if sizes {
		n := webapp.DirSize(m.Paths.AppDir(id)) + webapp.DirSize(m.Paths.Cache(id))
		info.DataBytes = &n
	}
	return info
}

// Get returns one app.
func (m *Manager) Get(id string, sizes bool) (api.AppInfo, error) {
	var info api.AppInfo
	err := m.shared(func() error {
		a, err := m.Paths.Load(id)
		if err != nil {
			return err
		}
		info = m.Info(a, sizes)
		return nil
	})
	return info, err
}

// Remove deletes apps: the launcher entry, the icons and the record, and (unless keepData)
// the profile, cache and log. A running app is asked to quit first. With keepData the record
// becomes app.removed.json, listed under "Saved sign-in data", and reinstalling the site gets
// the same id and profile back.
func (m *Manager) Remove(ids []string, keepData bool) (api.RemoveResult, error) {
	res := api.RemoveResult{Removed: []api.Removed{}}
	if len(ids) == 0 {
		return res, webapp.Errorf(webapp.CodeBadRequest, "Say which web app to remove.")
	}
	for _, id := range ids {
		if !webapp.Valid(id) {
			return res, webapp.Errorf(webapp.CodeNotFound, "There’s no web app called %q.", id)
		}
	}
	err := m.exclusive(func() error {
		for _, id := range ids {
			a, loadErr := m.Paths.Load(id)
			known := loadErr == nil || fileExists(m.Paths.DesktopFile(id)) || fileExists(m.Paths.AppDir(id))
			if !known {
				return webapp.Errorf(webapp.CodeNotFound, "There’s no web app called %q.", id)
			}
			if keepData && a == nil && fileExists(m.Paths.AppDir(id)) {
				// Without a readable record there is nothing to keep the sign-in data under;
				// refuse rather than delete what you asked to keep.
				return webapp.Errorf(webapp.CodeState, "Arctic can’t read the record of %s, so it can’t keep its sign-in data. Remove it with its sign-in data instead.", m.orphan(id, false).Name)
			}
			stopped, err := m.Paths.Stop(id, m.StopWait)
			if err != nil {
				name := id
				if a != nil {
					name = a.Name
				}
				return webapp.Errorf(webapp.CodeState, "%s is still open. Close it and try again.", name)
			}
			m.removeFiles(id, a)
			kept := false
			if keepData && a != nil {
				if err := m.Paths.SaveKept(a); err != nil {
					return err
				}
				os.Remove(m.Paths.AppFile(id))
				os.Remove(m.Paths.SourceIcon(id))
				kept = true
			} else {
				if err := m.deleteData(id, a); err != nil {
					return err
				}
			}
			res.Removed = append(res.Removed, api.Removed{ID: id, Stopped: stopped, KeptData: kept})
		}
		return nil
	})
	return res, err
}

// removeFiles deletes the launcher entry and every installed icon revision.
func (m *Manager) removeFiles(id string, a *webapp.App) {
	os.Remove(m.Paths.DesktopFile(id))
	removeIcons(m.Paths, id)
	touchHicolor(m.Paths)
}

// deleteData deletes the app directory (record, profile, state), cache, log and a Flatpak
// browser's profile.
func (m *Manager) deleteData(id string, a *webapp.App) error {
	if err := webapp.RemoveTree(m.Paths.Root(), id); err != nil {
		return err
	}
	if err := webapp.RemoveTree(m.Paths.Cache(""), id); err != nil {
		return err
	}
	os.Remove(m.Paths.Log(id))
	os.Remove(m.Paths.Log(id) + ".1")
	for _, b := range Browsers {
		if b.Ref != "" {
			webapp.RemoveTree(m.Paths.FlatpakProfile(b.Ref, ""), id)
		}
	}
	return nil
}

// Forget deletes kept sign-in data.
func (m *Manager) Forget(ids []string) error {
	if len(ids) == 0 {
		return webapp.Errorf(webapp.CodeBadRequest, "Say which saved sign-in data to forget.")
	}
	return m.exclusive(func() error {
		for _, id := range ids {
			a, err := m.Paths.LoadKept(id)
			if err != nil {
				return err
			}
			if fileExists(m.Paths.AppFile(id)) {
				return webapp.Errorf(webapp.CodeState, "%s is installed. Remove it instead.", a.Name)
			}
			if _, err := m.Paths.Stop(id, m.StopWait); err != nil {
				return err
			}
			if err := m.deleteData(id, a); err != nil {
				return err
			}
		}
		return nil
	})
}

// ClearData signs you out: it deletes the profile, cache, permissions and window state but
// keeps the app.
func (m *Manager) ClearData(id string) error {
	return m.exclusive(func() error {
		a, err := m.Paths.Load(id)
		if err != nil {
			return err
		}
		if _, err := m.Paths.Stop(id, m.StopWait); err != nil {
			return webapp.Errorf(webapp.CodeState, "%s is still open. Close it and try again.", a.Name)
		}
		for _, p := range []string{m.Paths.Profile(id), m.Paths.ChromiumProfile(id)} {
			if err := os.RemoveAll(p); err != nil {
				return err
			}
		}
		for _, p := range []string{m.Paths.PermissionsFile(id), m.Paths.StateFile(id)} {
			if err := os.Remove(p); err != nil && !errors.Is(err, fs.ErrNotExist) {
				return err
			}
		}
		if err := webapp.RemoveTree(m.Paths.Cache(""), id); err != nil {
			return err
		}
		if b, ok := BrowserFor(a.Runtime); ok && b.Ref != "" {
			webapp.RemoveTree(m.Paths.FlatpakProfile(b.Ref, ""), id)
		}
		return nil
	})
}

// Repair rewrites every launcher entry and icon from the registry and removes launcher
// entries whose record is gone.
func (m *Manager) Repair() (api.RepairResult, error) {
	res := api.RepairResult{Repaired: []string{}, OrphansRemoved: []string{}}
	err := m.exclusive(func() error {
		apps, _, err := m.Paths.List()
		if err != nil {
			return err
		}
		have := map[string]bool{}
		for _, a := range apps {
			have[a.ID] = true
			if err := m.render(a); err != nil {
				return err
			}
			res.Repaired = append(res.Repaired, a.ID)
		}
		for _, id := range m.Paths.DesktopIDs() {
			if !have[id] {
				os.Remove(m.Paths.DesktopFile(id))
				removeIcons(m.Paths, id)
				res.OrphansRemoved = append(res.OrphansRemoved, id)
			}
		}
		touchHicolor(m.Paths)
		sort.Strings(res.OrphansRemoved)
		return nil
	})
	return res, err
}

// rerender brings apps rendered by an older engine up to date (best effort; under the lock).
func (m *Manager) rerender(apps []*webapp.App) {
	m.exclusive(func() error {
		for _, a := range apps {
			fresh, err := m.Paths.Load(a.ID)
			if err != nil || fresh.Render >= webapp.RenderVersion {
				continue
			}
			if m.render(fresh) == nil {
				fresh.Render = webapp.RenderVersion
				m.Paths.Save(fresh)
			}
		}
		return nil
	})
}

// Reload tells a running WebKit app to re-read app.json (SIGHUP); false when it isn't running.
func (m *Manager) Reload(id string) bool {
	return m.Paths.Signal(id, syscall.SIGHUP)
}
