package manage

import (
	"context"
	"os"
	"strings"
	"syscall"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/discover"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
)

// Set changes an app. Options a running WebKit app can take live (links, notifications,
// devtools, extra sites, permissions) reach it through SIGHUP (applied "live"); the engine,
// rendering and a forgotten certificate apply at the next start ("next_start"); name, icon and
// category only rewrite files ("saved").
func (m *Manager) Set(ctx context.Context, p api.SetParams) (api.SetResult, error) {
	var res api.SetResult
	if p.ID == "" {
		return res, webapp.Errorf(webapp.CodeBadRequest, "arctic-webapp set needs an app id.")
	}
	cur, err := m.Paths.Load(p.ID)
	if err != nil {
		return res, err
	}
	fields := map[string]string{}
	var ic *chosenIcon
	if p.Icon != nil {
		switch {
		case p.Icon.File != "":
			img, msg := decodeFile(p.Icon.File)
			if msg != "" {
				fields["icon"] = msg
			} else {
				ic = &chosenIcon{img: img, source: "user", purpose: "any"}
			}
		case p.Icon.URL != "":
			c, msg := m.fetchIcon(ctx, p.Icon.URL)
			if msg != "" {
				fields["icon"] = msg
			} else {
				ic = &c
			}
		case p.Icon.Monogram:
			name, cat := cur.Name, cur.Category
			if p.Name != nil {
				name = *p.Name
			}
			if p.Category != nil {
				cat = *p.Category
			}
			img, err := icon.Monogram(name, cat)
			if err != nil {
				fields["icon"] = "Couldn’t draw the letter icon."
			} else {
				ic = &chosenIcon{img: img, source: "monogram", purpose: "any"}
			}
		default:
			// Get it from the site again.
			found, err := discover.Discover(ctx, cur.StartURL, discover.Options{PSL: m.psl(), Fetcher: NewFetcher(), Progress: m.Progress})
			if err != nil {
				return res, err
			}
			if len(found.Icons) == 0 {
				fields["icon"] = "The site has no icon Arctic can use."
			} else {
				b := found.Icons[0]
				ic = &chosenIcon{img: b.Image, source: b.Source, purpose: b.Purpose, url: b.URL, sha256: b.SHA256}
			}
		}
	}
	if p.Name != nil && webapp.CleanName(*p.Name) == "" {
		fields["name"] = "Give the app a name."
	}
	if p.Category != nil && !oneOf(*p.Category, webapp.Categories) {
		fields["category"] = "Choose a category from the list."
	}
	if p.Runtime != nil {
		if msg := m.checkRuntime(*p.Runtime); msg != "" {
			fields["runtime"] = msg
		}
	}
	if p.Links != nil && !oneOf(*p.Links, webapp.LinkModes) {
		fields["links"] = "Choose browser or app."
	}
	if p.Notifications != nil && !oneOf(*p.Notifications, webapp.NotifyModes) {
		fields["notifications"] = "Choose allow, ask or block."
	}
	if p.Rendering != nil && !oneOf(*p.Rendering, webapp.RenderModes) {
		fields["rendering"] = "Choose auto or software."
	}
	if p.MailLinks != nil && *p.MailLinks && MailTemplate(cur.StartURL) == "" {
		fields["mail_links"] = "This site can’t open email links."
	}
	domains := append([]string{}, cur.ExtraDomains...)
	if p.ExtraDomains != nil {
		domains = nil
		for _, d := range p.ExtraDomains {
			domains = append(domains, strings.ToLower(strings.TrimSpace(d)))
		}
	}
	if p.AddDomain != "" {
		domains = append(domains, strings.ToLower(strings.TrimSpace(p.AddDomain)))
	}
	if p.RemoveDomain != "" {
		var keep []string
		for _, d := range domains {
			if d != strings.ToLower(strings.TrimSpace(p.RemoveDomain)) {
				keep = append(keep, d)
			}
		}
		domains = keep
	}
	domains = dedupe(domains)
	for _, d := range domains {
		if !webapp.ValidDomain(d) {
			fields["extra_domains"] = d + " isn’t a site name, like accounts.example.com."
		}
	}
	if len(fields) > 0 {
		return res, fieldErrors(fields)
	}

	applied := "saved"
	live, next := false, false
	err = m.exclusive(func() error {
		a, err := m.Paths.Load(p.ID)
		if err != nil {
			return err
		}
		files := false
		if p.Name != nil {
			a.Name, a.NameSource = webapp.CleanName(*p.Name), "user"
			a.MarkUserSet("name")
			files = true
		}
		if p.Category != nil {
			a.Category = *p.Category
			a.MarkUserSet("category")
			files = true
		}
		if ic != nil {
			if err := icon.SaveSource(m.Paths, a.ID, ic.img, ic.purpose); err != nil {
				return err
			}
			a.Icon = webapp.Icon{Rev: a.Icon.Rev + 1, Source: ic.source, URL: ic.url, SHA256: ic.sha256, Purpose: ic.purpose}
			a.Icon.Name = a.IconName()
			if ic.source == "user" || ic.source == "url" || ic.source == "monogram" {
				a.MarkUserSet("icon")
			} else {
				a.UserSet = without(a.UserSet, "icon")
			}
			files = true
		}
		if p.Runtime != nil && *p.Runtime != a.Runtime {
			a.Runtime = *p.Runtime
			m.setWMClass(a)
			next, files = true, true
		}
		if p.Rendering != nil && *p.Rendering != a.Options.Rendering {
			a.Options.Rendering = *p.Rendering
			next = true
		}
		if p.MailLinks != nil {
			if *p.MailLinks {
				a.Handlers = []string{"mailto"}
			} else {
				a.Handlers = []string{}
			}
			files = true
		}
		if p.Links != nil {
			a.Options.Links, live = *p.Links, true
		}
		if p.Notifications != nil {
			a.Options.Notifications, live = *p.Notifications, true
		}
		if p.Devtools != nil {
			a.Options.Devtools, live = *p.Devtools, true
		}
		if p.ExtraDomains != nil || p.AddDomain != "" || p.RemoveDomain != "" {
			a.ExtraDomains, live = domains, true
		}
		if p.ForgetCertificate != "" {
			var keep []webapp.TLSException
			for _, e := range a.TLSExceptions {
				if e.Host != strings.ToLower(p.ForgetCertificate) {
					keep = append(keep, e)
				}
			}
			// WebKit can't take back a certificate it was told to allow: the open window
			// keeps accepting it until it closes.
			a.TLSExceptions, next = keep, true
		}
		if p.ResetPermissions {
			if err := os.Remove(m.Paths.PermissionsFile(a.ID)); err != nil && !os.IsNotExist(err) {
				return err
			}
			live = true
		}
		a.Updated = m.Now()
		if err := m.Paths.Save(a); err != nil {
			return err
		}
		if files {
			if err := m.render(a); err != nil {
				return err
			}
		}
		cur = a
		return nil
	})
	if err != nil {
		return res, err
	}
	running := m.Paths.RunningPid(cur.ID) != 0
	switch {
	case next && running:
		applied = "next_start"
	case live && running && cur.Runtime == "webkit":
		m.Paths.Signal(cur.ID, syscall.SIGHUP)
		applied = "live"
	case live && running:
		applied = "next_start"
	}
	res.App = m.Info(cur, false)
	res.Applied = applied
	return res, nil
}

func dedupe(list []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, s := range list {
		if s != "" && !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

func without(list []string, s string) []string {
	out := []string{}
	for _, x := range list {
		if x != s {
			out = append(out, x)
		}
	}
	return out
}
