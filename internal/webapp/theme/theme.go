// Package theme reads the current Arctic theme (~/.config/arctic/current/theme.json, colours
// in QML's #AARRGGBB) for the web-app window: its own widgets (header, banners, find bar) and
// its error pages follow the theme, light or dark, and change live on a theme switch. Plain GTK
// widgets already get Arctic's colours from ~/.config/gtk-4.0/gtk.css.
package theme

import (
	"encoding/json"
	"fmt"
	"html/template"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Palette is the subset of theme colours the window uses, as CSS colours.
type Palette struct {
	Dark          bool
	Ground        string
	Surface       string
	SurfaceRaised string
	SurfaceSunken string
	Line          string
	Ink           string
	InkMuted      string
	Accent        string
	OnAccent      string
	Focus         string
	Warning       string
	Error         string
}

// Default is Winter (light), used when no theme file can be read.
var Default = Palette{
	Ground: "#eef2f5", Surface: "#fbfcfd", SurfaceRaised: "#ffffff", SurfaceSunken: "#e8edf1", Line: "#d5dde4",
	Ink: "#151a21", InkMuted: "#4a5663", Accent: "#efa637", OnAccent: "#151a21", Focus: "#a86812",
	Warning: "#9a4812", Error: "#b3261e",
}

// File is the current theme's JSON under the user's config directory.
func File(home string) string {
	cfg := os.Getenv("XDG_CONFIG_HOME")
	if !filepath.IsAbs(cfg) {
		cfg = filepath.Join(home, ".config")
	}
	return filepath.Join(cfg, "arctic", "current", "theme.json")
}

// Load reads a theme.json; missing colours keep Default's.
func Load(path string) (Palette, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Default, err
	}
	return Parse(data)
}

// Parse reads theme.json bytes.
func Parse(data []byte) (Palette, error) {
	var doc struct {
		Dark   bool              `json:"dark"`
		Colors map[string]string `json:"colors"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return Default, err
	}
	p := Default
	p.Dark = doc.Dark
	set := func(dst *string, key string) {
		if c, ok := CSSColor(doc.Colors[key]); ok {
			*dst = c
		}
	}
	set(&p.Ground, "ground")
	set(&p.Surface, "surface")
	set(&p.SurfaceRaised, "surfaceRaised")
	set(&p.SurfaceSunken, "surfaceSunken")
	set(&p.Line, "line")
	set(&p.Ink, "ink")
	set(&p.InkMuted, "inkMuted")
	set(&p.Accent, "accent")
	set(&p.OnAccent, "onAccent")
	set(&p.Focus, "focus")
	set(&p.Warning, "warning")
	set(&p.Error, "error")
	return p, nil
}

// CSSColor converts QML #RRGGBB or #AARRGGBB into a CSS colour.
func CSSColor(q string) (string, bool) {
	q = strings.TrimSpace(strings.ToLower(q))
	if !strings.HasPrefix(q, "#") {
		return "", false
	}
	h := q[1:]
	if _, err := strconv.ParseUint(h, 16, 64); err != nil {
		return "", false
	}
	switch len(h) {
	case 6:
		return "#" + h, true
	case 8:
		a, _ := strconv.ParseUint(h[0:2], 16, 8)
		if a == 255 {
			return "#" + h[2:], true
		}
		r, _ := strconv.ParseUint(h[2:4], 16, 8)
		g, _ := strconv.ParseUint(h[4:6], 16, 8)
		b, _ := strconv.ParseUint(h[6:8], 16, 8)
		return fmt.Sprintf("rgba(%d,%d,%d,%.3f)", r, g, b, float64(a)/255), true
	}
	return "", false
}

// HostCSS styles the window's own widgets (design/guidelines/10-platforms.md: buttons 10 px,
// popovers 14 px, focus 2 px solid in focus). Amber is only the banner's one primary action.
func HostCSS(p Palette) string {
	var b strings.Builder
	fmt.Fprintf(&b, "window.arctic-webapp { background: %s; }\n", p.Ground)
	fmt.Fprintf(&b, "window.arctic-webapp headerbar { background: %s; color: %s; box-shadow: inset 0 -1px %s; }\n", p.Surface, p.Ink, p.Line)
	fmt.Fprintf(&b, "window.arctic-webapp headerbar button { border-radius: 10px; }\n")
	fmt.Fprintf(&b, "window.arctic-webapp button:focus-visible { outline: 2px solid %s; outline-offset: 1px; }\n", p.Focus)
	fmt.Fprintf(&b, ".arctic-host { color: %s; font-size: 0.9em; }\n", p.InkMuted)
	fmt.Fprintf(&b, ".arctic-banner { background: %s; color: %s; border: 1px solid %s; border-radius: 14px; margin: 8px; padding: 8px 12px; }\n", p.SurfaceRaised, p.Ink, p.Line)
	fmt.Fprintf(&b, ".arctic-banner button.suggested-action { background: %s; color: %s; border-radius: 10px; }\n", p.Accent, p.OnAccent)
	fmt.Fprintf(&b, ".arctic-findbar { background: %s; border-bottom: 1px solid %s; }\n", p.SurfaceSunken, p.Line)
	return b.String()
}

var errorPage = template.Must(template.New("error").Parse(`<!doctype html>
<html><head><meta charset="utf-8"><title>{{.Title}}</title>
<style>
:root { color-scheme: {{if .P.Dark}}dark{{else}}light{{end}}; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: {{.P.Ground}}; color: {{.P.Ink}};
       font: 15px/1.5 Figtree, "Noto Sans", sans-serif; }
main { max-width: 34rem; padding: 2rem; background: {{.P.SurfaceRaised}}; border: 1px solid {{.P.Line}}; border-radius: 20px; }
h1 { font-size: 1.35rem; margin: 0 0 .5rem; }
p { color: {{.P.InkMuted}}; margin: 0 0 1rem; }
code { font-size: .85rem; word-break: break-all; }
a.button { display: inline-block; padding: .5rem 1rem; border-radius: 10px; background: {{.P.Accent}}; color: {{.P.OnAccent}}; text-decoration: none; }
a.button:focus-visible { outline: 2px solid {{.P.Focus}}; outline-offset: 2px; }
</style></head>
<body><main>
<h1>{{.Title}}</h1>
<p>{{.Message}}</p>
{{if .Detail}}<p><code>{{.Detail}}</code></p>{{end}}
{{if .Retry}}<a class="button" href="{{.Retry}}">Try again</a>{{end}}
</main></body></html>
`))

// ErrorPage renders an Arctic error page; every value is escaped by html/template.
func ErrorPage(p Palette, title, message, detail, retry string) string {
	var b strings.Builder
	if strings.HasPrefix(retry, "javascript:") {
		retry = ""
	}
	errorPage.Execute(&b, struct {
		P                             Palette
		Title, Message, Detail, Retry string
	}{p, title, message, detail, retry})
	return b.String()
}
