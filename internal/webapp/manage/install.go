package manage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"image"
	"image/png"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/discover"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
)

// chosenIcon is the icon an install or set ends up with.
type chosenIcon struct {
	img     image.Image
	source  string
	purpose string
	url     string
	sha256  string
}

// Install makes a web app from a preview token (or a URL, which inspects first).
func (m *Manager) Install(ctx context.Context, p api.InstallParams) (api.InstallResult, error) {
	var res api.InstallResult
	token := p.Token
	if token == "" {
		if p.URL == "" {
			return res, webapp.Errorf(webapp.CodeBadRequest, "Say which site to add.")
		}
		pr, err := m.Inspect(ctx, p.URL)
		if err != nil && wantsMonogram(p) && unreachable(err) {
			// "Add with a letter icon" while offline: the typed address is all there is.
			pr, err = m.offlinePreview(p.URL)
		}
		if err != nil {
			return res, err
		}
		token = pr.Token
		defer m.DropPreviews([]string{token})
	}
	pv, dir, err := m.loadPreview(token)
	if err != nil {
		return res, err
	}
	pr := pv.Preview
	fields := map[string]string{}

	name := pr.Name
	if p.Name != "" {
		name = webapp.CleanName(p.Name)
		if name == "" {
			fields["name"] = "Give the app a name."
		}
	}
	category := pr.Category
	if p.Category != "" {
		category = p.Category
	}
	if !oneOf(category, webapp.Categories) {
		fields["category"] = "Choose a category from the list."
	}
	runtime := pr.SuggestedRuntime
	if runtime == "" {
		runtime = "webkit"
	}
	if p.Runtime != "" {
		runtime = p.Runtime
	}
	if msg := m.checkRuntime(runtime); msg != "" {
		fields["runtime"] = msg
	}
	opts := webapp.DefaultOptions()
	if p.Links != "" {
		opts.Links = p.Links
	}
	if p.Notifications != "" {
		opts.Notifications = p.Notifications
	}
	if !oneOf(opts.Links, webapp.LinkModes) {
		fields["links"] = "Choose browser or app."
	}
	if !oneOf(opts.Notifications, webapp.NotifyModes) {
		fields["notifications"] = "Choose allow, ask or block."
	}
	if p.MailLinks && MailTemplate(pr.StartURL) == "" {
		fields["mail_links"] = "This site can’t open email links."
	}
	ic, iconErr := m.pickIcon(ctx, p, pv, dir, name, category)
	if iconErr != "" {
		fields["icon"] = iconErr
	}
	if len(fields) > 0 {
		return res, fieldErrors(fields)
	}

	var app *webapp.App
	err = m.exclusive(func() error {
		base := webapp.Identity(pv.ManifestID, pr.StartURL, 1)
		copyN := 1
		if existing := m.appsWithIdentityPrefix(base); len(existing) > 0 {
			if !p.NewCopy {
				a, _ := m.Paths.Load(existing[0])
				shown := existing[0]
				if a != nil {
					shown = a.Name
				}
				return webapp.Errorf(webapp.CodeExists, "Already added: %s.", shown)
			}
			for copyN = 2; ; copyN++ {
				taken := false
				apps, _, _ := m.Paths.List()
				for _, a := range apps {
					if a.Identity() == webapp.Identity(pv.ManifestID, pr.StartURL, copyN) {
						taken = true
					}
				}
				if !taken {
					break
				}
			}
		}
		identity := webapp.Identity(pv.ManifestID, pr.StartURL, copyN)
		id := ""
		if kept, isKept := m.Paths.FindIdentity(identity); kept != nil && isKept {
			id = kept.ID // reinstall: the same id, so the same profile and sign-in
		} else {
			id = webapp.NewID(name, pr.Scope.Site, identity, m.Paths.Owner)
		}
		if id == "" {
			return webapp.Errorf(webapp.CodeInternal, "Couldn’t make an id for this app.")
		}
		now := m.Now()
		app = &webapp.App{
			Schema: webapp.Schema, Render: webapp.RenderVersion, EngineVersion: webapp.Version,
			ID: id, Copy: copyN, Name: name, NameSource: pr.NameSource, InputURL: pv.InputURL,
			StartURL: pr.StartURL, ManifestURL: pr.ManifestURL, ManifestID: pv.ManifestID,
			Scope:    webapp.Scope{Site: pr.Scope.Site, Scheme: pr.Scope.Scheme, Manifest: pr.Scope.Manifest},
			Category: category, ThemeColor: pr.ThemeColor,
			Icon:    webapp.Icon{Source: ic.source, URL: ic.url, SHA256: ic.sha256, Purpose: ic.purpose},
			Runtime: runtime, Options: opts, Created: now, Updated: now,
		}
		if p.Name != "" && name != pr.Name {
			app.NameSource = "user"
			app.MarkUserSet("name")
		}
		if ic.source == "user" || ic.source == "url" {
			app.MarkUserSet("icon")
		}
		if p.MailLinks {
			app.Handlers = []string{"mailto"}
		}
		m.setWMClass(app)
		app.Normalize()
		os.Remove(m.Paths.KeptFile(id))
		if err := m.Paths.Save(app); err != nil {
			return err
		}
		m.progress(api.StageRender, "Making the icon")
		if err := icon.SaveSource(m.Paths, id, ic.img, ic.purpose); err != nil {
			return err
		}
		return m.render(app)
	})
	if err != nil {
		return res, err
	}
	res.App = m.Info(app, false)
	res.DesktopFile = m.Paths.DesktopFile(app.ID)
	if p.Launch {
		if _, err := m.Launch(app.ID, ""); err == nil {
			res.Launched = true
		}
	}
	return res, nil
}

func fieldErrors(fields map[string]string) error {
	pe := webapp.Errorf(webapp.CodeInvalid, "Check the highlighted options.")
	pe.Fields = fields
	return pe
}

func oneOf(v string, list []string) bool {
	for _, x := range list {
		if v == x {
			return true
		}
	}
	return false
}

// checkRuntime returns a message when a runtime can't be used.
func (m *Manager) checkRuntime(rt string) string {
	if !webapp.ValidRuntime(rt) {
		return "Choose an engine from the list."
	}
	if rt == "webkit" || m.Env.Available(rt) {
		return ""
	}
	b, _ := BrowserFor(rt)
	return b.Name + " isn’t installed."
}

// setWMClass records the app id the window will have: the id itself for WebKit, Chromium's
// derived --app id otherwise.
func (m *Manager) setWMClass(a *webapp.App) {
	if b, ok := BrowserFor(a.Runtime); ok {
		a.WMClass = ChromiumWMClass(b, a.StartURL)
		return
	}
	a.WMClass = a.ID
}

// pickIcon resolves the install's icon choice. The message is "" on success.
func (m *Manager) pickIcon(ctx context.Context, p api.InstallParams, pv *preview, dir, name, category string) (chosenIcon, string) {
	switch {
	case p.IconFile != "":
		img, msg := decodeFile(p.IconFile)
		if msg != "" {
			return chosenIcon{}, msg
		}
		return chosenIcon{img: img, source: "user", purpose: "any"}, ""
	case p.IconURL != "":
		return m.fetchIcon(ctx, p.IconURL)
	}
	index := pv.Preview.RecommendedIcon
	if len(p.Icon) > 0 {
		var s string
		if json.Unmarshal(p.Icon, &s) == nil {
			if s == "monogram" {
				index = -1
			} else if n, err := strconv.Atoi(s); err == nil {
				index = n
			} else {
				return chosenIcon{}, "Choose one of the icons."
			}
		} else if json.Unmarshal(p.Icon, &index) != nil {
			return chosenIcon{}, "Choose one of the icons."
		}
	}
	if index >= 0 && index < len(pv.Icons) && pv.Icons[index].Source != "monogram" {
		data, err := os.ReadFile(filepath.Join(dir, fmt.Sprintf("%d.png", index)))
		if err == nil {
			if img, err := png.Decode(strings.NewReader(string(data))); err == nil {
				pi := pv.Icons[index]
				// The stored preview is already a tile for maskable icons.
				return chosenIcon{img: img, source: pi.Source, purpose: "any", url: pi.URL, sha256: pi.SHA256}, ""
			}
		}
		return chosenIcon{}, "That icon is no longer available. Look the site up again."
	}
	if index >= len(pv.Icons) {
		return chosenIcon{}, "Choose one of the icons."
	}
	img, err := icon.Monogram(name, category)
	if err != nil {
		return chosenIcon{}, "Couldn’t draw the letter icon."
	}
	return chosenIcon{img: img, source: "monogram", purpose: "any"}, ""
}

// decodeFile reads a local icon file you chose, with the same bounded decoders as discovery.
func decodeFile(path string) (image.Image, string) {
	if !filepath.IsAbs(path) {
		return nil, "Choose the icon file with its full path."
	}
	fi, err := os.Stat(path)
	if err != nil || !fi.Mode().IsRegular() {
		return nil, "That icon file can’t be read."
	}
	if fi.Size() > discover.MaxImage {
		return nil, "That icon file is too large (2 MB at most)."
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, "That icon file can’t be read."
	}
	img, _, err := icon.Decode(data)
	if err != nil {
		return nil, "That file isn’t an image Arctic can use (PNG, JPEG, GIF, ICO or SVG)."
	}
	return img, ""
}

// fetchIcon downloads an icon you pointed at ("Use an icon from the web").
func (m *Manager) fetchIcon(ctx context.Context, raw string) (chosenIcon, string) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" || u.User != nil {
		return chosenIcon{}, "That isn’t an image address."
	}
	f := NewFetcher()
	f.PageDone() // the address is yours: no page to compare with, public addresses only
	resp, err := f.Get(ctx, u, "image/png,image/svg+xml,image/*;q=0.8", discover.MaxImage, false)
	if err != nil {
		return chosenIcon{}, webapp.AsError(err).Message
	}
	img, _, err := icon.Decode(resp.Body)
	if err != nil {
		return chosenIcon{}, "That address isn’t an image Arctic can use (PNG, JPEG, GIF, ICO or SVG)."
	}
	sum := sha256.Sum256(resp.Body)
	return chosenIcon{img: img, source: "url", purpose: "any", url: u.String(), sha256: hex.EncodeToString(sum[:])}, ""
}

func wantsMonogram(p api.InstallParams) bool {
	var s string
	return p.IconFile == "" && p.IconURL == "" && json.Unmarshal(p.Icon, &s) == nil && s == "monogram"
}

// unreachable: the site couldn't be read at all (offline, no answer, DNS), as opposed to an
// answer Arctic refuses (not a web page, too large, TLS).
func unreachable(err error) bool {
	switch webapp.AsError(err).Code {
	case webapp.CodeOffline, webapp.CodeFetch, webapp.CodeTimeout:
		return true
	}
	return false
}

// offlinePreview builds a preview from the typed address alone: its host's site as the scope,
// the site label as the name and a letter icon.
func (m *Manager) offlinePreview(raw string) (api.Preview, error) {
	u, err := discover.Normalize(raw)
	if err != nil {
		return api.Preview{}, err
	}
	site := m.psl().Site(u.Host)
	name, source := discover.PickName(nil, discover.Head{}, u.Host, site)
	res := &discover.Result{
		Input: u, FinalURL: u, Name: name, NameSource: source, StartURL: u.String(),
		Site: site, Scheme: u.Scheme, Category: "Network", Insecure: u.Scheme == "http",
	}
	return m.storePreview(raw, res)
}
