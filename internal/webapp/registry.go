package webapp

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"sort"
	"strings"
)

// Load reads and validates one app record. A missing record is a not_found error.
func (p Paths) Load(id string) (*App, error) {
	if !Valid(id) {
		return nil, Errorf(CodeNotFound, "There’s no web app called %q.", id)
	}
	return p.loadFile(id, p.AppFile(id))
}

// LoadKept reads the record `remove --keep-data` left behind.
func (p Paths) LoadKept(id string) (*App, error) {
	if !Valid(id) {
		return nil, Errorf(CodeNotFound, "There’s no saved sign-in data called %q.", id)
	}
	return p.loadFile(id, p.KeptFile(id))
}

func (p Paths) loadFile(id, path string) (*App, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, Errorf(CodeNotFound, "There’s no web app called %q.", id)
	}
	if err != nil {
		return nil, err
	}
	var a App
	if err := json.Unmarshal(data, &a); err != nil {
		return nil, fmt.Errorf("%s: %v", path, err)
	}
	a.Normalize()
	if a.ID != id {
		return nil, fmt.Errorf("%s: its id %q does not match its directory", path, a.ID)
	}
	if err := a.Validate(); err != nil {
		return nil, err
	}
	return &a, nil
}

// Save writes app.json atomically (dir 0700, file 0600). Callers hold the exclusive lock.
func (p Paths) Save(a *App) error {
	a.Normalize()
	if err := a.Validate(); err != nil {
		return err
	}
	return p.writeRecord(p.AppFile(a.ID), a)
}

// SaveKept writes the kept record.
func (p Paths) SaveKept(a *App) error {
	a.Normalize()
	if err := a.Validate(); err != nil {
		return err
	}
	return p.writeRecord(p.KeptFile(a.ID), a)
}

func (p Paths) writeRecord(path string, a *App) error {
	if err := os.MkdirAll(p.AppDir(a.ID), 0o700); err != nil {
		return err
	}
	if err := os.Chmod(p.AppDir(a.ID), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(a, "", "  ")
	if err != nil {
		return err
	}
	return WriteFileAtomic(path, append(data, '\n'), 0o600)
}

// IDs lists the valid app directories in the registry, sorted.
func (p Paths) IDs() ([]string, error) {
	entries, err := os.ReadDir(p.Root())
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, e := range entries {
		if e.IsDir() && Valid(e.Name()) {
			ids = append(ids, e.Name())
		}
	}
	sort.Strings(ids)
	return ids, nil
}

// List reads every installed app. Broken records are returned in bad (id → reason) so the
// Remove apps list can still offer to clean them up.
func (p Paths) List() (apps []*App, bad map[string]string, err error) {
	ids, err := p.IDs()
	if err != nil {
		return nil, nil, err
	}
	bad = map[string]string{}
	for _, id := range ids {
		if _, err := os.Stat(p.AppFile(id)); err != nil {
			continue // kept data only, or an empty directory
		}
		a, err := p.Load(id)
		if err != nil {
			bad[id] = err.Error()
			continue
		}
		apps = append(apps, a)
	}
	sort.SliceStable(apps, func(i, j int) bool {
		return strings.ToLower(apps[i].Name) < strings.ToLower(apps[j].Name)
	})
	return apps, bad, nil
}

// Kept lists apps removed with --keep-data whose sign-in data is still there.
func (p Paths) Kept() ([]*App, error) {
	ids, err := p.IDs()
	if err != nil {
		return nil, err
	}
	var kept []*App
	for _, id := range ids {
		if _, err := os.Stat(p.AppFile(id)); err == nil {
			continue
		}
		a, err := p.LoadKept(id)
		if err != nil {
			continue
		}
		kept = append(kept, a)
	}
	return kept, nil
}

// FindIdentity returns the installed or kept app with this identity, if any.
func (p Paths) FindIdentity(identity string) (a *App, kept bool) {
	apps, _, _ := p.List()
	for _, x := range apps {
		if x.Identity() == identity {
			return x, false
		}
	}
	ks, _ := p.Kept()
	for _, x := range ks {
		if x.Identity() == identity {
			return x, true
		}
	}
	return nil, false
}

// Owner returns the identity that holds id (installed or kept), "" when the id is free. It is
// the owner function NewID takes.
func (p Paths) Owner(id string) string {
	if a, err := p.Load(id); err == nil {
		return a.Identity()
	}
	if a, err := p.LoadKept(id); err == nil {
		return a.Identity()
	}
	if _, err := os.Stat(p.AppDir(id)); err == nil {
		return "\x00unknown" // a directory we can't read: never reuse it
	}
	return ""
}
