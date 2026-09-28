package discover

import (
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

// Manifest is a processed Web App Manifest (W3C processing: URLs resolved, start_url and
// scope checked). Members Arctic does not use (shortcuts, protocol_handlers, file_handlers,
// share_target) are ignored.
type Manifest struct {
	URL             string
	Name            string
	ShortName       string
	StartURL        string // resolved; "" when absent or not same-origin with the document
	Scope           string // resolved; always contains StartURL when both are set
	ID              string // resolved; defaults to StartURL
	Display         string
	ThemeColor      string
	BackgroundColor string
	Categories      []string
	Icons           []ManifestIcon
}

// ManifestIcon is one entry of icons[].
type ManifestIcon struct {
	Src     string // resolved against the manifest URL
	Sizes   []int  // largest side of each "WxH"; 0 for "any"
	Type    string
	Purpose []string // any | maskable (monochrome dropped)
}

type rawManifest struct {
	Name            json.RawMessage `json:"name"`
	ShortName       json.RawMessage `json:"short_name"`
	StartURL        json.RawMessage `json:"start_url"`
	Scope           json.RawMessage `json:"scope"`
	ID              json.RawMessage `json:"id"`
	Display         json.RawMessage `json:"display"`
	ThemeColor      json.RawMessage `json:"theme_color"`
	BackgroundColor json.RawMessage `json:"background_color"`
	Categories      json.RawMessage `json:"categories"`
	Icons           json.RawMessage `json:"icons"`
}

// str reads a member that should be a string; any other type counts as absent.
func str(m json.RawMessage) string {
	var s string
	if len(m) == 0 || json.Unmarshal(m, &s) != nil {
		return ""
	}
	return strings.TrimSpace(s)
}

// ParseManifest processes a manifest fetched from manifestURL for the page at docURL.
func ParseManifest(data []byte, manifestURL, docURL string) (*Manifest, error) {
	var raw rawManifest
	if err := json.Unmarshal(stripBOM(data), &raw); err != nil {
		return nil, fmt.Errorf("the app manifest isn’t valid JSON")
	}
	base, err := url.Parse(manifestURL)
	if err != nil {
		return nil, err
	}
	doc, err := url.Parse(docURL)
	if err != nil {
		return nil, err
	}
	m := &Manifest{
		URL:             manifestURL,
		Name:            str(raw.Name),
		ShortName:       str(raw.ShortName),
		Display:         strings.ToLower(str(raw.Display)),
		ThemeColor:      normalizeColor(str(raw.ThemeColor)),
		BackgroundColor: normalizeColor(str(raw.BackgroundColor)),
	}
	// start_url: resolved against the manifest URL, used only if same-origin with the document.
	start := doc
	if s := str(raw.StartURL); s != "" {
		if u, err := base.Parse(s); err == nil && sameOrigin(u, doc) && webScheme(u) {
			start = u
			m.StartURL = stripFragment(u)
		}
	}
	// scope: same-origin and containing start_url, else start_url minus file name, query and
	// fragment.
	defScope := *start
	defScope.RawQuery, defScope.Fragment = "", ""
	if i := strings.LastIndexByte(defScope.Path, '/'); i >= 0 {
		defScope.Path = defScope.Path[:i+1]
	} else {
		defScope.Path = "/"
	}
	defScope.RawPath = ""
	m.Scope = defScope.String()
	if s := str(raw.Scope); s != "" {
		if u, err := base.Parse(s); err == nil && sameOrigin(u, doc) {
			u.RawQuery, u.Fragment = "", ""
			if strings.HasPrefix(start.Path, u.Path) {
				m.Scope = u.String()
			}
		}
	}
	// id: resolved against start_url's origin; defaults to start_url.
	m.ID = stripFragment(start)
	if s := str(raw.ID); s != "" {
		if u, err := start.Parse(s); err == nil && sameOrigin(u, start) {
			m.ID = stripFragment(u)
		}
	}
	var cats []json.RawMessage
	if json.Unmarshal(raw.Categories, &cats) == nil {
		for _, c := range cats {
			if s := strings.ToLower(str(c)); s != "" {
				m.Categories = append(m.Categories, s)
			}
		}
	}
	var icons []map[string]json.RawMessage
	if json.Unmarshal(raw.Icons, &icons) == nil {
		for _, ic := range icons {
			src := str(ic["src"])
			if src == "" {
				continue
			}
			u, err := base.Parse(src)
			if err != nil || !webScheme(u) {
				continue
			}
			mi := ManifestIcon{Src: u.String(), Sizes: parseSizes(str(ic["sizes"])), Type: strings.ToLower(str(ic["type"]))}
			purposes := strings.Fields(strings.ToLower(str(ic["purpose"])))
			if len(purposes) == 0 {
				purposes = []string{"any"}
			}
			for _, p := range purposes {
				if p == "any" || p == "maskable" {
					mi.Purpose = append(mi.Purpose, p)
				}
			}
			if len(mi.Purpose) == 0 {
				continue // monochrome only
			}
			m.Icons = append(m.Icons, mi)
		}
	}
	return m, nil
}

// parseSizes reads "48x48 96x96 any" into the largest side of each size (0 for any).
func parseSizes(s string) []int {
	var out []int
	for _, f := range strings.Fields(strings.ToLower(s)) {
		if f == "any" {
			out = append(out, 0)
			continue
		}
		w, h, ok := strings.Cut(f, "x")
		if !ok {
			continue
		}
		wi, err1 := strconv.Atoi(w)
		hi, err2 := strconv.Atoi(h)
		if err1 != nil || err2 != nil || wi <= 0 || hi <= 0 || wi > 10000 || hi > 10000 {
			continue
		}
		out = append(out, max(wi, hi))
	}
	return out
}

func sameOrigin(a, b *url.URL) bool {
	return strings.EqualFold(a.Scheme, b.Scheme) && strings.EqualFold(a.Host, b.Host)
}

func webScheme(u *url.URL) bool { return u.Scheme == "https" || u.Scheme == "http" }

func stripFragment(u *url.URL) string {
	c := *u
	c.Fragment, c.RawFragment = "", ""
	return c.String()
}

// normalizeColor accepts #rgb/#rrggbb (and with alpha), rgb()/hsl() and CSS names as they are
// written; it only lowercases and trims. The colour is informational: the chrome stays Arctic.
func normalizeColor(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	if len(s) > 64 || strings.ContainsAny(s, "<>\"'\\;{}") {
		return ""
	}
	return s
}
