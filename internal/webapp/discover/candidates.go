package discover

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"image"
	"net/url"
	"path"
	"sort"
	"strconv"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
)

// Candidate is an icon the site offers, before fetching.
type Candidate struct {
	URL      string
	Source   string // manifest | apple-touch | link | favicon-ico
	Purpose  string // any | maskable
	Declared int    // declared size (largest side), 0 if unknown or "any"
	Type     string // declared MIME type or guessed from the extension
	rank     int
}

// Icon is a fetched, decoded icon.
type Icon struct {
	Candidate
	Format string // png | jpeg | gif | ico | cur | bmp | svg
	Size   int    // decoded largest side
	Image  image.Image
	SHA256 string
}

const (
	maxCandidates = 16
	maxFetched    = 6
	wantDecoded   = 3
)

// Candidates lists the icons in preference order: manifest "any" ≥ 192 px, manifest maskable
// ≥ 192 px, apple-touch-icon, link icons ≥ 64 px or SVG, other link icons, and /favicon.ico only
// when nothing else was found. Never og:image (a wide share card) and never third-party
// favicon services (they would learn which sites you use). WebP, AVIF and JXL are dropped: the
// standard library can't decode them.
func Candidates(m *Manifest, head Head, base *url.URL, origin *url.URL) []Candidate {
	var out []Candidate
	seen := map[string]bool{}
	add := func(c Candidate) {
		if c.URL == "" || seen[c.URL] || unsupportedType(c.Type, c.URL) {
			return
		}
		seen[c.URL] = true
		out = append(out, c)
	}
	if m != nil {
		for _, ic := range m.Icons {
			size := 0
			for _, s := range ic.Sizes {
				size = max(size, s)
			}
			for _, p := range ic.Purpose {
				rank := 3
				switch {
				case p == "any" && (size >= 192 || size == 0 && isSVG(ic.Type, ic.Src)):
					rank = 0
				case p == "maskable" && size >= 192:
					rank = 1
				}
				add(Candidate{URL: ic.Src, Source: "manifest", Purpose: p, Declared: size, Type: guessType(ic.Type, ic.Src), rank: rank})
			}
		}
	}
	for _, l := range head.Links {
		u, err := base.Parse(l.Href)
		if err != nil || (u.Scheme != "https" && u.Scheme != "http") {
			continue
		}
		size := 0
		for _, s := range parseSizes(l.Sizes) {
			size = max(size, s)
		}
		c := Candidate{URL: u.String(), Purpose: "any", Declared: size, Type: guessType(l.Type, u.Path)}
		switch l.Rel {
		case "apple-touch-icon":
			c.Source, c.rank = "apple-touch", 2
			if c.Declared == 0 {
				c.Declared = 180
			}
		case "icon":
			c.Source, c.rank = "link", 4
			if size >= 64 || isSVG(c.Type, u.Path) {
				c.rank = 3
			}
		default:
			continue
		}
		add(c)
	}
	if len(out) == 0 && origin != nil {
		fav := *origin
		fav.Path, fav.RawQuery, fav.Fragment = "/favicon.ico", "", ""
		add(Candidate{URL: fav.String(), Source: "favicon-ico", Purpose: "any", Type: "image/x-icon", rank: 5})
	}
	sort.SliceStable(out, func(i, j int) bool { return score(out[i]) < score(out[j]) })
	if len(out) > maxCandidates {
		out = out[:maxCandidates]
	}
	return out
}

// score: source rank, then closeness to ≥ 256 px, then format (PNG > SVG > ICO > JPEG > GIF).
func score(c Candidate) int {
	s := c.rank * 10000
	switch {
	case c.Declared >= 256:
		s += (c.Declared - 256) / 64
	case c.Declared == 0:
		s += 300
	default:
		s += 256 - c.Declared
	}
	switch {
	case strings.Contains(c.Type, "png"):
	case strings.Contains(c.Type, "svg"):
		s += 5
	case strings.Contains(c.Type, "icon"):
		s += 10
	case strings.Contains(c.Type, "jpeg"):
		s += 15
	case strings.Contains(c.Type, "gif"):
		s += 20
	default:
		s += 8
	}
	return s
}

func guessType(declared, p string) string {
	if declared != "" {
		return strings.ToLower(declared)
	}
	switch strings.ToLower(path.Ext(strings.SplitN(p, "?", 2)[0])) {
	case ".png":
		return "image/png"
	case ".svg":
		return "image/svg+xml"
	case ".ico":
		return "image/x-icon"
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".gif":
		return "image/gif"
	case ".webp":
		return "image/webp"
	case ".avif":
		return "image/avif"
	case ".jxl":
		return "image/jxl"
	}
	return ""
}

func isSVG(t, p string) bool { return strings.Contains(guessType(t, p), "svg") }

func unsupportedType(t, p string) bool {
	g := guessType(t, p)
	return strings.Contains(g, "webp") || strings.Contains(g, "avif") || strings.Contains(g, "jxl")
}

// FetchIcons fetches candidates in order (at most 6) and decodes them with the bounded
// decoders, until three decode and one of them is at least 64 px.
func FetchIcons(ctx context.Context, f *Fetcher, cands []Candidate, progress func(string)) []Icon {
	var out []Icon
	big := false
	for i, c := range cands {
		if i >= maxFetched || (len(out) >= wantDecoded && big) || ctx.Err() != nil {
			break
		}
		if progress != nil {
			progress("Getting icons (" + strconv.Itoa(i+1) + " of " + strconv.Itoa(min(len(cands), maxFetched)) + ")")
		}
		u, err := url.Parse(c.URL)
		if err != nil {
			continue
		}
		limit := int64(MaxImage)
		if strings.Contains(c.Type, "icon") || strings.Contains(c.Type, "svg") {
			limit = MaxICO
		}
		resp, err := f.Get(ctx, u, "image/png,image/svg+xml,image/*;q=0.8", limit, false)
		if err != nil {
			continue
		}
		img, format, err := icon.Decode(resp.Body)
		if err != nil || img == nil {
			continue
		}
		b := img.Bounds()
		ic := Icon{Candidate: c, Format: format, Size: max(b.Dx(), b.Dy()), Image: img}
		if format == "svg" {
			ic.Source = map[bool]string{true: "svg", false: c.Source}[c.Source == "link"]
		}
		sum := sha256.Sum256(resp.Body)
		ic.SHA256 = hex.EncodeToString(sum[:])
		if ic.Size >= icon.MinSource {
			big = true
		}
		out = append(out, ic)
	}
	// Best first: large before small, keeping the preference order otherwise.
	sort.SliceStable(out, func(i, j int) bool {
		return (out[i].Size >= icon.MinSource) && !(out[j].Size >= icon.MinSource)
	})
	return out
}
