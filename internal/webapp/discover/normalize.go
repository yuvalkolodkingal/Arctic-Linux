package discover

import (
	"net/url"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// Normalize turns what you typed into a URL: https:// is added when there is no scheme; only
// http and https with a host are accepted; userinfo, whitespace, control characters and more
// than 2,048 bytes are refused; the fragment is dropped; the host is lowercase ASCII. http is
// allowed (self-hosted apps on your network) and gets the "insecure" warning.
func Normalize(input string) (*url.URL, error) {
	s := strings.TrimSpace(input)
	bad := webapp.Errorf(webapp.CodeInvalid, "That isn’t a web address. Try something like music.youtube.com.")
	if s == "" || len(s) > 2048 {
		return nil, bad
	}
	for _, r := range s {
		if r <= ' ' || r == 0x7f {
			return nil, bad
		}
	}
	if !strings.Contains(s, "://") {
		if strings.Contains(s, ":") && !looksLikeHostPort(s) {
			return nil, bad // mailto:, javascript: …
		}
		s = "https://" + s
	}
	u, err := url.Parse(s)
	if err != nil {
		return nil, bad
	}
	u.Scheme = strings.ToLower(u.Scheme)
	if (u.Scheme != "https" && u.Scheme != "http") || u.Hostname() == "" || u.User != nil || u.Opaque != "" {
		return nil, bad
	}
	// Lowercase, and Punycode for an internationalised name: the form WebKit reports pages in,
	// so the scope, start URL and identity match them.
	u.Host = webapp.ASCIIHost(strings.ToLower(u.Host))
	u.Fragment, u.RawFragment = "", ""
	if u.Path == "" {
		u.Path = "/"
	}
	return u, nil
}

// looksLikeHostPort tells "ha.lan:8123/x" (a host with a port) from "mailto:x".
func looksLikeHostPort(s string) bool {
	host, rest, _ := strings.Cut(s, ":")
	if host == "" {
		return false
	}
	port := rest
	if i := strings.IndexAny(port, "/?#"); i >= 0 {
		port = port[:i]
	}
	if port == "" {
		return false
	}
	for _, c := range port {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}
