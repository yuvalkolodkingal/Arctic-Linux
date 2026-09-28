// Package psl finds a host's registrable domain (eTLD+1) with the Public Suffix List that
// Fedora ships in publicsuffix-list. A web app's scope is its site: mail.google.com belongs to
// google.com, foo.bar.co.uk to bar.co.uk, and user.github.io stays user.github.io. The WebKit
// host's tagged test checks the answers against libsoup's soup_tld_get_base_domain.
package psl

import (
	"bufio"
	"io"
	"net"
	"os"
	"strings"
)

// SystemPath is Fedora's copy of the list.
const SystemPath = "/usr/share/publicsuffix/public_suffix_list.dat"

// List is a parsed Public Suffix List. The zero value (no rules) treats every host as its own
// site, the safe fallback when the list is missing.
type List struct {
	rules      map[string]bool // "co.uk", "*.ck"
	exceptions map[string]bool // "www.ck" (from "!www.ck")
}

// Load reads a list file; a missing file gives an empty List and the error.
func Load(path string) (*List, error) {
	f, err := os.Open(path)
	if err != nil {
		return &List{}, err
	}
	defer f.Close()
	return Parse(f)
}

// Parse reads the list format: one rule per line, // comments, "*." wildcards, "!" exceptions.
// Only the first whitespace-separated word of a line counts.
func Parse(r io.Reader) (*List, error) {
	l := &List{rules: map[string]bool{}, exceptions: map[string]bool{}}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "//") {
			continue
		}
		if i := strings.IndexAny(line, " \t"); i >= 0 {
			line = line[:i]
		}
		line = strings.ToLower(line)
		if ex, ok := strings.CutPrefix(line, "!"); ok {
			l.exceptions[ex] = true
			continue
		}
		l.rules[line] = true
	}
	return l, sc.Err()
}

// Empty reports a list without rules (the file was missing).
func (l *List) Empty() bool { return l == nil || len(l.rules) == 0 }

// Site returns the registrable domain of host (lowercase ASCII, no trailing dot). IP literals,
// localhost and single-label hosts are their own site, with the port kept when hostport has one.
// A host that is itself a public suffix is its own site. Without rules, the exact host.
func (l *List) Site(hostport string) string {
	host, port := hostport, ""
	if h, p, err := net.SplitHostPort(hostport); err == nil {
		host, port = h, p
	}
	host = strings.TrimSuffix(strings.ToLower(host), ".")
	withPort := func(h string) string {
		if port == "" {
			return h
		}
		return net.JoinHostPort(h, port)
	}
	if net.ParseIP(strings.Trim(host, "[]")) != nil || host == "localhost" || !strings.Contains(host, ".") || l.Empty() {
		return withPort(host)
	}
	labels := strings.Split(host, ".")
	n := l.suffixLabels(labels)
	if n >= len(labels) {
		return host
	}
	return strings.Join(labels[len(labels)-n-1:], ".")
}

// suffixLabels is the number of labels in the public suffix of labels (the prevailing rule;
// the implicit "*" rule gives 1).
func (l *List) suffixLabels(labels []string) int {
	best := 1
	for i := range labels {
		cand := strings.Join(labels[i:], ".")
		n := len(labels) - i
		if l.exceptions[cand] {
			// An exception rule wins and its suffix is one label shorter.
			return n - 1
		}
		if l.rules[cand] && n > best {
			best = n
		}
		if i+1 < len(labels) {
			wild := "*." + strings.Join(labels[i+1:], ".")
			if l.rules[wild] && n > best {
				best = n
			}
		}
	}
	return best
}

// SameSite reports whether host is site or one of its subdomains.
func SameSite(host, site string) bool {
	host = strings.TrimSuffix(strings.ToLower(host), ".")
	site = strings.ToLower(site)
	return host == site || strings.HasSuffix(host, "."+site)
}
