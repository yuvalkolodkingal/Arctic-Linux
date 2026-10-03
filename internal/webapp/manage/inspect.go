package manage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/discover"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/psl"
)

// PreviewTTL is how long an inspect result can be installed from.
const PreviewTTL = time.Hour

// maxPreviewIcons is how many site icons the preview offers (the letter icon comes after).
const maxPreviewIcons = 4

var tokenRE = regexp.MustCompile(`^[0-9a-f]{16}$`)

// preview is what an inspect leaves in $XDG_RUNTIME_DIR/arctic-webapp/inspect-<token>/ so a
// later install (from serve or from the CLI's --preview) uses exactly what you saw.
type preview struct {
	Created    time.Time     `json:"created"`
	Preview    api.Preview   `json:"preview"`
	InputURL   string        `json:"input_url"`
	ManifestID string        `json:"manifest_id"`
	Icons      []previewIcon `json:"icons"`
}

type previewIcon struct {
	Source  string `json:"source"`
	Purpose string `json:"purpose"`
	URL     string `json:"url"`
	SHA256  string `json:"sha256"`
}

// PSLPath is the Public Suffix List file; tests use the fixture.
var PSLPath = psl.SystemPath

// NewFetcher builds the fetcher for one inspect; tests replace it to trust their servers.
var NewFetcher = func() *discover.Fetcher { return discover.NewFetcher(nil) }

func (m *Manager) psl() *psl.List {
	l, _ := psl.Load(PSLPath)
	return l
}

func (m *Manager) inspectDir(token string) string {
	return filepath.Join(m.Paths.RuntimeDir, "inspect-"+token)
}

// Inspect discovers a site and stores a preview you can install from within an hour.
func (m *Manager) Inspect(ctx context.Context, rawURL string) (api.Preview, error) {
	res, err := discover.Discover(ctx, rawURL, discover.Options{PSL: m.psl(), Fetcher: NewFetcher(), Progress: m.Progress, MetadataFallback: true})
	if err != nil {
		return api.Preview{}, err
	}
	return m.storePreview(rawURL, res)
}

// storePreview renders the icon choices and writes the preview directory.
func (m *Manager) storePreview(input string, res *discover.Result) (api.Preview, error) {
	m.cleanPreviews()
	tokBytes := make([]byte, 8)
	if _, err := rand.Read(tokBytes); err != nil {
		return api.Preview{}, err
	}
	token := hex.EncodeToString(tokBytes)
	dir := m.inspectDir(token)
	if err := m.Paths.EnsureRuntimeDir(); err != nil {
		return api.Preview{}, err
	}
	if err := os.Mkdir(dir, 0o700); err != nil {
		return api.Preview{}, err
	}
	p := api.Preview{
		Token: token, URL: res.Input.String(), FinalURL: res.FinalURL.String(),
		// host is for reading (Unicode); host_ascii is the name the page really has, a defence
		// against look-alike letters.
		Host: webapp.UnicodeHost(res.Input.Host), HostASCII: res.Input.Host, Secure: !res.Insecure,
		Name: res.Name, NameSource: res.NameSource, ShortName: res.ShortName, StartURL: res.StartURL,
		Scope:       api.Scope{Site: res.Site, Scheme: res.Scheme, Manifest: res.ScopeURL},
		ManifestURL: res.ManifestURL, Display: res.Display, ThemeColor: res.ThemeColor, Category: res.Category,
		Installed: []string{}, Icons: []api.IconChoice{}, HandlersSupported: []string{}, Warnings: []api.Warning{},
		SuggestedRuntime: "webkit",
	}
	identity := webapp.Identity(res.ManifestID, res.StartURL, 1)
	p.SuggestedID = webapp.NewID(res.Name, res.Site, identity, m.Paths.Owner)
	for _, a := range m.appsWithIdentityPrefix(identity) {
		p.Installed = append(p.Installed, a)
	}
	if MailTemplate(res.StartURL) != "" {
		p.HandlersSupported = []string{"mailto"}
	}
	pv := preview{Created: m.Now(), InputURL: strings.TrimSpace(input), ManifestID: res.ManifestID}
	for _, ic := range res.Icons {
		if len(p.Icons) >= maxPreviewIcons {
			break
		}
		idx := len(p.Icons)
		path := filepath.Join(dir, fmt.Sprintf("%d.png", idx))
		if err := writeSource(path, ic.Image, ic.Purpose); err != nil {
			continue
		}
		p.Icons = append(p.Icons, api.IconChoice{Index: idx, Source: ic.Source, Purpose: ic.Purpose, Size: ic.Size, Format: ic.Format, Path: path})
		pv.Icons = append(pv.Icons, previewIcon{Source: ic.Source, Purpose: ic.Purpose, URL: ic.URL, SHA256: ic.SHA256})
	}
	// The letter icon is always offered last.
	mono, err := icon.Monogram(res.Name, res.Category)
	if err == nil {
		idx := len(p.Icons)
		path := filepath.Join(dir, fmt.Sprintf("%d.png", idx))
		if writeSource(path, mono, "any") == nil {
			p.Icons = append(p.Icons, api.IconChoice{Index: idx, Source: "monogram", Size: 512, Format: "svg", Path: path})
			pv.Icons = append(pv.Icons, previewIcon{Source: "monogram"})
		}
	}
	p.RecommendedIcon = 0
	for i, ic := range p.Icons {
		if ic.Size >= icon.MinSource || ic.Source == "monogram" {
			p.RecommendedIcon = i
			break
		}
	}
	p.Warnings, p.SuggestedRuntime = m.warnings(res)
	pv.Preview = p
	data, err := json.Marshal(pv)
	if err != nil {
		return api.Preview{}, err
	}
	if err := webapp.WriteFileAtomic(filepath.Join(dir, "preview.json"), data, 0o600); err != nil {
		return api.Preview{}, err
	}
	return p, nil
}

// writeSource stores a choice as the launcher will show it: the rounded tile at 512 px (install
// uses this file as the source, and a tile's transparent corners keep it from being masked twice).
func writeSource(path string, img image.Image, purpose string) error {
	data, err := icon.EncodePNG(icon.Tile(img, purpose, 512))
	if err != nil {
		return err
	}
	return webapp.WriteFileAtomic(path, data, 0o600)
}

// warnings explains what the Arctic engine can't do for this site and suggests an installed
// Chromium-family runtime that can (Brave, Chrome or Vivaldi for DRM; any for calls).
func (m *Manager) warnings(res *discover.Result) ([]api.Warning, string) {
	w := []api.Warning{}
	suggested := "webkit"
	pick := func(drm bool) (string, string) {
		for _, b := range Browsers {
			if drm && !b.DRM {
				continue
			}
			if m.Env.Available("chromium:" + b.Variant) {
				return "chromium:" + b.Variant, b.Name
			}
		}
		return "", "Brave"
	}
	switch discover.Needs(res.Input.Hostname()) {
	case "drm":
		rt, name := pick(true)
		if rt != "" {
			suggested = rt
		}
		w = append(w, api.Warning{Code: "drm_unsupported", Message: fmt.Sprintf("This site plays protected media, which the Arctic engine can’t play. %s can.", name)})
	case "calls":
		rt, name := pick(false)
		if rt != "" {
			suggested = rt
		}
		w = append(w, api.Warning{Code: "calls_unsupported", Message: fmt.Sprintf("Video and voice calls don’t work in the Arctic engine. %s can make them.", name)})
	}
	if res.LoginWall {
		w = append(w, api.Warning{Code: "login_wall", Message: fmt.Sprintf("The site asked you to sign in, so Arctic used the name and icon from %s.", res.Input.Host)})
	}
	if res.MetadataStatus != 0 {
		w = append(w, api.Warning{Code: "metadata_unavailable", Message: fmt.Sprintf("The site declined the preview request (HTTP %d). You can still add it with a letter icon and sign in when it opens.", res.MetadataStatus)})
	}
	if res.Insecure {
		w = append(w, api.Warning{Code: "insecure", Message: "This site doesn’t use a secure connection. Only add it if it’s on your own network."})
	}
	return w, suggested
}

// appsWithIdentityPrefix lists installed apps made from this site (any copy).
func (m *Manager) appsWithIdentityPrefix(identity string) []string {
	apps, _, _ := m.Paths.List()
	var ids []string
	for _, a := range apps {
		base := webapp.Identity(a.ManifestID, a.StartURL, 1)
		if base == identity {
			ids = append(ids, a.ID)
		}
	}
	return ids
}

// loadPreview reads a stored preview; expired or unknown tokens are not_found.
func (m *Manager) loadPreview(token string) (*preview, string, error) {
	if !tokenRE.MatchString(token) {
		return nil, "", webapp.Errorf(webapp.CodeNotFound, "That preview has expired. Look the site up again.")
	}
	dir := m.inspectDir(token)
	data, err := os.ReadFile(filepath.Join(dir, "preview.json"))
	if err != nil {
		return nil, "", webapp.Errorf(webapp.CodeNotFound, "That preview has expired. Look the site up again.")
	}
	var pv preview
	if err := json.Unmarshal(data, &pv); err != nil {
		return nil, "", err
	}
	if m.Now().Sub(pv.Created) > PreviewTTL {
		os.RemoveAll(dir)
		return nil, "", webapp.Errorf(webapp.CodeNotFound, "That preview has expired. Look the site up again.")
	}
	return &pv, dir, nil
}

// cleanPreviews deletes expired preview directories.
func (m *Manager) cleanPreviews() {
	entries, err := os.ReadDir(m.Paths.RuntimeDir)
	if err != nil {
		return
	}
	for _, e := range entries {
		tok, ok := strings.CutPrefix(e.Name(), "inspect-")
		if !ok || !tokenRE.MatchString(tok) {
			continue
		}
		fi, err := e.Info()
		if err == nil && time.Since(fi.ModTime()) > PreviewTTL {
			os.RemoveAll(filepath.Join(m.Paths.RuntimeDir, e.Name()))
		}
	}
}

// DropPreviews deletes the given preview directories (serve does on exit).
func (m *Manager) DropPreviews(tokens []string) {
	for _, t := range tokens {
		if tokenRE.MatchString(t) {
			if err := os.RemoveAll(m.inspectDir(t)); err != nil && !errors.Is(err, fs.ErrNotExist) {
				continue
			}
		}
	}
}
