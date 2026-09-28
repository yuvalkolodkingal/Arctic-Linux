package webapp

import (
	"crypto/sha256"
	"encoding/hex"
	"regexp"
	"strings"
	"unicode"
)

// idRE is the Arctic grammar. It is also a valid GApplication id (no '-': GLib discourages it
// and it breaks D-Bus object paths).
var idRE = regexp.MustCompile(`^org\.arcticlinux\.WebApp\.[A-Za-z][A-Za-z0-9]{0,31}_[0-9a-f]{6,8}$`)

// Valid reports whether id is a web-app id. Every path, Exec line and signal target is built
// from an id that passed this check.
func Valid(id string) bool {
	return idRE.MatchString(id) && ValidGApplicationID(id)
}

// ValidGApplicationID mirrors g_application_id_is_valid(): at most 255 bytes, at least two
// dot-separated elements, each non-empty, of [A-Za-z0-9_-], not starting with a digit.
func ValidGApplicationID(id string) bool {
	if len(id) == 0 || len(id) > 255 || id[0] == '.' {
		return false
	}
	parts := strings.Split(id, ".")
	if len(parts) < 2 {
		return false
	}
	for _, p := range parts {
		if p == "" || (p[0] >= '0' && p[0] <= '9') {
			return false
		}
		for i := 0; i < len(p); i++ {
			c := p[i]
			if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-') {
				return false
			}
		}
	}
	return true
}

// Slug is the id's readable part: the name's ASCII letters and digits in CamelCase ("YouTube
// Music" → "YouTubeMusic"); failing that the site label title-cased ("walla.co.il" → "Walla"),
// else "App". A leading digit gets the prefix "App"; at most 32 characters.
func Slug(name, site string) string {
	s := camel(name)
	if s == "" {
		label := site
		if i := strings.IndexByte(label, '.'); i > 0 {
			label = label[:i]
		}
		s = camel(label)
	}
	if s == "" {
		s = "App"
	}
	if s[0] >= '0' && s[0] <= '9' {
		s = "App" + s
	}
	if len(s) > 32 {
		s = s[:32]
	}
	return s
}

func camel(s string) string {
	var b strings.Builder
	upper := true
	for _, r := range s {
		switch {
		case r < 128 && (unicode.IsLetter(r) || unicode.IsDigit(r)):
			if upper && r >= 'a' && r <= 'z' {
				r -= 'a' - 'A'
			}
			b.WriteRune(r)
			upper = false
		default:
			upper = true
		}
	}
	return b.String()
}

// Hash is the first n hex digits of SHA-256 over the canonical identity.
func Hash(identity string, n int) string {
	sum := sha256.Sum256([]byte(identity))
	return hex.EncodeToString(sum[:])[:n]
}

// NewID builds the id for a site. owner reports which identity already holds an id (installed
// or kept), "" when it is free. The hash is deterministic, so reinstalling a site after
// `remove --keep-data` gets the same id and the same profile; if a different identity holds the
// 6-digit id, the id takes 8 digits. It returns "" when both are taken by other identities.
func NewID(name, site, identity string, owner func(id string) string) string {
	slug := Slug(name, site)
	for _, n := range []int{6, 8} {
		id := IDPrefix + slug + "_" + Hash(identity, n)
		if o := owner(id); o == "" || o == identity {
			return id
		}
	}
	return ""
}

// HashOf returns the hash part of a valid id.
func HashOf(id string) string {
	i := strings.LastIndexByte(id, '_')
	if i < 0 {
		return ""
	}
	return id[i+1:]
}
