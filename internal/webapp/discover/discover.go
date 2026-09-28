package discover

import (
	"context"
	"mime"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/psl"
)

// Result is everything discovery found about a site.
type Result struct {
	Input       *url.URL // the normalised typed URL
	FinalURL    *url.URL // after redirects
	Name        string
	NameSource  string
	ShortName   string
	StartURL    string
	Site        string // registrable domain (scope)
	Scheme      string
	ScopeURL    string // the manifest's scope, informational
	ManifestURL string
	ManifestID  string
	Display     string
	ThemeColor  string
	Category    string
	Icons       []Icon
	LoginWall   bool
	Insecure    bool
}

// Options configure one discovery.
type Options struct {
	PSL      *psl.List
	Fetcher  *Fetcher // nil: a new one with the system roots
	Progress func(stage, message string)
	Timeout  time.Duration // default 30 s
}

// probes are asked for on the typed origin when a login wall hides the page.
var manifestProbes = []string{"/manifest.webmanifest", "/manifest.json", "/site.webmanifest"}

// Discover inspects a site: the page's head, its manifest and icons. The page's JavaScript
// never runs.
func Discover(ctx context.Context, input string, opt Options) (*Result, error) {
	typed, err := Normalize(input)
	if err != nil {
		return nil, err
	}
	if opt.Timeout == 0 {
		opt.Timeout = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, opt.Timeout)
	defer cancel()
	f := opt.Fetcher
	if f == nil {
		f = NewFetcher(nil)
	}
	list := opt.PSL
	if list == nil {
		list = &psl.List{}
	}
	progress := func(stage, msg string) {
		if opt.Progress != nil {
			opt.Progress(stage, msg)
		}
	}

	progress("page", "Opening "+typed.Host)
	resp, err := f.Get(ctx, typed, "text/html,application/xhtml+xml", MaxHTML, true)
	if err != nil {
		return nil, err
	}
	if !isHTML(resp) {
		return nil, webapp.Errorf(webapp.CodeNotHTML, "%s isn’t a web page.", typed.Host)
	}
	doc := DecodeHTML(resp.Body, resp.ContentType)
	head := ParseHead(doc)
	final := resp.URL
	// One <meta http-equiv=refresh> with a delay of at most 5 s is followed.
	if target := refreshTarget(head.Refresh, final); target != nil {
		if r2, err := f.Get(ctx, target, "text/html,application/xhtml+xml", MaxHTML, true); err == nil && isHTML(r2) {
			resp, final = r2, r2.URL
			head = ParseHead(DecodeHTML(r2.Body, r2.ContentType))
		}
	}
	f.PageDone()

	res := &Result{Input: typed, FinalURL: final}
	typedSite := list.Site(typed.Host)
	finalSite := list.Site(final.Host)
	origin := typed
	base := final
	if typedSite != finalSite {
		// A login wall (Gmail → accounts.google.com): the sign-in page's name and icons are not
		// the app's; ask the typed origin instead.
		res.LoginWall = true
		head = Head{}
	} else {
		origin = final
		if head.Base != "" {
			if b, err := final.Parse(head.Base); err == nil && (b.Scheme == "https" || b.Scheme == "http") {
				base = b
			}
		}
	}

	// Manifest.
	var man *Manifest
	docURL := final.String()
	if res.LoginWall {
		docURL = originOf(typed).String()
	}
	var manifestURLs []string
	for _, l := range head.Links {
		if l.Rel == "manifest" {
			if u, err := base.Parse(l.Href); err == nil && (u.Scheme == "https" || u.Scheme == "http") {
				manifestURLs = append(manifestURLs, u.String())
			}
			break
		}
	}
	if res.LoginWall {
		for _, p := range manifestProbes {
			u := originOf(typed)
			u.Path = p
			manifestURLs = append(manifestURLs, u.String())
		}
	}
	if len(manifestURLs) > 0 {
		progress("manifest", "Reading the app manifest")
	}
	for _, mu := range manifestURLs {
		u, _ := url.Parse(mu)
		r, err := f.Get(ctx, u, "application/manifest+json, application/json", MaxManifest, false)
		if err != nil {
			continue
		}
		m, err := ParseManifest(r.Body, r.URL.String(), docURL)
		if err != nil {
			continue
		}
		man = m
		res.ManifestURL = r.URL.String()
		break
	}

	// start_url: a typed deep URL inside the manifest scope wins (/mail/u/1/ keeps a second
	// account), then the manifest's, then the typed URL (upgraded to https when the site
	// redirected there on the same host). A sign-in page on another site never becomes it.
	start := typed
	if !res.LoginWall && final.Host == typed.Host && final.Scheme == "https" && typed.Scheme == "http" {
		up := *typed
		up.Scheme = "https"
		start = &up
	}
	deep := typed.Path != "/" || typed.RawQuery != ""
	switch {
	case deep && (man == nil || inScope(typed, man.Scope)):
		// keep the typed URL
	case man != nil && man.StartURL != "":
		if u, err := url.Parse(man.StartURL); err == nil {
			start = u
		}
	}
	res.StartURL = start.String()
	res.Site = list.Site(start.Host)
	res.Scheme = start.Scheme
	res.Insecure = start.Scheme == "http"
	if man != nil {
		res.ScopeURL = man.Scope
		res.ManifestID = man.ID
		res.Display = man.Display
		res.ShortName = man.ShortName
		res.ThemeColor = man.ThemeColor
		res.Category = Category(man.Categories)
	} else {
		res.Category = "Network"
	}
	if res.ThemeColor == "" {
		res.ThemeColor = normalizeColor(head.ThemeColor(false))
	}
	res.Name, res.NameSource = PickName(man, head, start.Hostname(), res.Site)

	// Icons.
	cands := Candidates(man, head, base, originOf(origin))
	if res.LoginWall {
		o := originOf(typed)
		for _, p := range []string{"/apple-touch-icon.png", "/favicon.ico"} {
			u := *o
			u.Path = p
			src, rank := "apple-touch", 2
			if p == "/favicon.ico" {
				src, rank = "favicon-ico", 5
			}
			cands = append(cands, Candidate{URL: u.String(), Source: src, Purpose: "any", Type: guessType("", p), rank: rank})
		}
	}
	if len(cands) > 0 {
		progress("icons", "Getting icons")
		res.Icons = FetchIcons(ctx, f, cands, func(msg string) { progress("icons", msg) })
	}
	return res, nil
}

func isHTML(r *Response) bool {
	ct := r.ContentType
	if ct == "" {
		ct = http.DetectContentType(r.Body)
	}
	mt, _, err := mime.ParseMediaType(ct)
	if err != nil {
		return false
	}
	return mt == "text/html" || mt == "application/xhtml+xml"
}

// refreshTarget parses "5; url=/next" (delay ≤ 5 s, http(s) only).
func refreshTarget(content string, base *url.URL) *url.URL {
	if content == "" {
		return nil
	}
	delay, rest, _ := strings.Cut(content, ";")
	if rest == "" {
		delay, rest, _ = strings.Cut(content, ",")
	}
	d, err := strconv.ParseFloat(strings.TrimSpace(delay), 64)
	if err != nil || d > 5 || d < 0 {
		return nil
	}
	rest = strings.TrimSpace(rest)
	low := strings.ToLower(rest)
	if !strings.HasPrefix(low, "url") {
		return nil
	}
	rest = strings.TrimSpace(rest[3:])
	rest = strings.TrimSpace(strings.TrimPrefix(rest, "="))
	rest = strings.Trim(rest, `"'`)
	u, err := base.Parse(rest)
	if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.User != nil {
		return nil
	}
	if base.Scheme == "https" && u.Scheme == "http" {
		return nil
	}
	return u
}

func originOf(u *url.URL) *url.URL {
	return &url.URL{Scheme: u.Scheme, Host: u.Host, Path: "/"}
}

// inScope reports whether u lies inside the manifest scope URL (same origin, path prefix).
func inScope(u *url.URL, scope string) bool {
	s, err := url.Parse(scope)
	if err != nil || scope == "" {
		return true
	}
	return sameOrigin(u, s) && strings.HasPrefix(u.Path, s.Path)
}
