package discover

import (
	"strings"
	"unicode"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// PickName chooses the app's name, first non-empty of: the manifest name (short_name when
// name is over 30 characters), application-name, apple-mobile-web-app-title, og:site_name, the
// <title> segment most like the site label, and the site label title-cased. Behind a login wall
// head is empty, so the last steps use the typed host only. It returns the name and its source.
func PickName(m *Manifest, head Head, host, site string) (string, string) {
	if m != nil {
		n := m.Name
		if len([]rune(n)) > 30 && m.ShortName != "" {
			n = m.ShortName
		}
		if n = webapp.CleanName(n); n != "" {
			return n, "manifest"
		}
		if n = webapp.CleanName(m.ShortName); n != "" {
			return n, "manifest"
		}
	}
	for _, n := range []string{head.AppName, head.AppleTitle, head.OGSiteName} {
		if n = webapp.CleanName(n); n != "" {
			return n, "meta"
		}
	}
	if n := titleName(head.Title, site); n != "" {
		return n, "title"
	}
	return labelName(host, site), "host"
}

var titleSeps = []string{" | ", " - ", " – ", " — ", " · ", ": "}

// titleName splits a <title> on the usual separators and keeps the segment most like the site
// label, dropping "Home" and "Welcome".
func titleName(title, site string) string {
	title = webapp.CleanName(title)
	if title == "" {
		return ""
	}
	segs := []string{title}
	for _, sep := range titleSeps {
		var next []string
		for _, s := range segs {
			next = append(next, strings.Split(s, sep)...)
		}
		segs = next
	}
	label := strings.ToLower(siteLabel(site))
	best, bestScore := "", -1
	for _, s := range segs {
		s = strings.TrimSpace(s)
		ls := strings.ToLower(s)
		if s == "" || ls == "home" || ls == "welcome" || strings.HasPrefix(ls, "welcome to") {
			continue
		}
		score := 0
		compact := strings.ReplaceAll(ls, " ", "")
		switch {
		case label != "" && compact == label:
			score = 3
		case label != "" && strings.Contains(compact, label):
			score = 2
		case len(segs) == 1:
			score = 1
		}
		if score > bestScore {
			best, bestScore = s, score
		}
	}
	if bestScore < 0 {
		return ""
	}
	return webapp.CleanName(best)
}

// siteLabel is the registrable domain's first label ("walla" for walla.co.il).
func siteLabel(site string) string {
	if i := strings.IndexByte(site, '.'); i > 0 {
		return site[:i]
	}
	return site
}

// labelName title-cases the site label; for IP addresses and single-label hosts, the host.
func labelName(host, site string) string {
	label := siteLabel(site)
	if label == "" || strings.Trim(label, "0123456789[]:") == "" {
		return host
	}
	r := []rune(label)
	r[0] = unicode.ToUpper(r[0])
	return string(r)
}
