package main

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/manage"
)

// cmdRenderSample renders two fixture apps offline into DIR (a plain app and a mail-link app,
// so both Exec forms are checked), with letter icons drawn by rsvg-convert. %check runs
// desktop-file-validate on DIR/*.desktop, so the check covers what this binary writes. Every
// file goes under DIR: it never reads or writes $HOME.
func (c *cli) cmdRenderSample(args []string) int {
	if len(args) != 1 || args[0] == "" || args[0][0] == '-' {
		return c.usageError(false, "arctic-webapp render-sample needs a directory.")
	}
	dir, err := filepath.Abs(args[0])
	if err != nil {
		return c.fail(false, err)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return c.fail(false, err)
	}
	root := filepath.Join(dir, "tree")
	p := webapp.Paths{Home: root, DataHome: root + "/data", CacheHome: root + "/cache", StateHome: root + "/state", RuntimeDir: root + "/run"}
	m := &manage.Manager{Paths: p, Env: manage.Env{Home: root, HostBin: webapp.HostPath}, Now: func() time.Time { return time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC) }}
	for _, a := range sampleApps() {
		if err := m.SaveAndRender(a); err != nil {
			return c.fail(false, fmt.Errorf("%s: %v", a.ID, err))
		}
		data, err := os.ReadFile(p.DesktopFile(a.ID))
		if err != nil {
			return c.fail(false, err)
		}
		if err := os.WriteFile(filepath.Join(dir, a.ID+".desktop"), data, 0o644); err != nil {
			return c.fail(false, err)
		}
		for _, size := range webapp.IconSizes {
			if _, err := os.Stat(p.IconFile(a.IconName(), size)); err != nil {
				return c.fail(false, fmt.Errorf("%s: no %d px icon", a.ID, size))
			}
		}
		fmt.Fprintln(c.stdout, filepath.Join(dir, a.ID+".desktop"))
	}
	return 0
}

func sampleApps() []*webapp.App {
	mk := func(name, start, site, category string, mail bool) *webapp.App {
		id := webapp.NewID(name, site, start, func(string) string { return "" })
		a := &webapp.App{
			Schema: webapp.Schema, Render: webapp.RenderVersion, EngineVersion: webapp.Version,
			ID: id, Copy: 1, Name: name, NameSource: "manifest", InputURL: start, StartURL: start,
			Scope:    webapp.Scope{Site: site, Scheme: "https"},
			Category: category, Icon: webapp.Icon{Source: "monogram", Purpose: "any"},
			Runtime: "webkit", Options: webapp.DefaultOptions(),
			Created: time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC), Updated: time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC),
		}
		if mail {
			a.Handlers = []string{"mailto"}
		}
		a.Normalize()
		return a
	}
	return []*webapp.App{
		mk("Excalidraw; sketches \\ notes", "https://excalidraw.com/", "excalidraw.com", "Graphics", false),
		mk("Gmail", "https://mail.google.com/mail/u/0/", "google.com", "Calendar", true),
	}
}
