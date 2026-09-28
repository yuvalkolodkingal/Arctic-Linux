// Package discover finds what a website offers to become a web app: its name, Web App
// Manifest, icons and theme colour. It reads the page's <head> with a small tokenizer (the
// standard library's html package only escapes, and x/net/html is not standard), follows the
// W3C manifest processing rules, and fetches with strict limits. Pages are never run: no
// JavaScript executes before you agree to install.
package discover

import (
	"html"
	"strings"
)

// Head is what the tokenizer collects from a page.
type Head struct {
	Base        string
	Title       string
	Links       []Link
	ThemeColors []ThemeColor
	AppName     string // <meta name=application-name>
	AppleTitle  string // <meta name=apple-mobile-web-app-title>
	OGSiteName  string // <meta property=og:site_name>
	Description string
	Refresh     string // <meta http-equiv=refresh content>
	Charset     string // <meta charset> or http-equiv content-type
}

// Link is a <link> with one of the rels discovery cares about.
type Link struct {
	Rel   string // manifest | icon | apple-touch-icon
	Href  string
	Sizes string
	Type  string
	Media string
}

// ThemeColor is one <meta name=theme-color>.
type ThemeColor struct {
	Content string
	Media   string
}

// Limits of the tokenizer: it stops at them rather than failing.
const (
	maxTags        = 4096
	maxAttrs       = 64
	maxValue       = 8 << 10
	afterHeadBytes = 64 << 10
)

var rawText = map[string]bool{"script": true, "style": true, "template": true, "noscript": true, "iframe": true, "xmp": true, "noembed": true, "noframes": true}

// ParseHead tokenizes an HTML document (already decoded to UTF-8) and collects the head
// elements discovery uses. It never fails: malformed input yields whatever was found.
func ParseHead(doc string) Head {
	var h Head
	t := tokenizer{s: doc}
	stopAt := -1
	for tags := 0; tags < maxTags; tags++ {
		if stopAt >= 0 && t.i >= stopAt {
			break
		}
		tok, ok := t.next()
		if !ok {
			break
		}
		if tok.end {
			if tok.name == "head" && stopAt < 0 {
				stopAt = t.i + afterHeadBytes
			}
			continue
		}
		switch tok.name {
		case "title":
			text := t.rcdata("title")
			if h.Title == "" {
				h.Title = strings.TrimSpace(html.UnescapeString(text))
			}
		case "textarea":
			t.rcdata("textarea")
		case "base":
			if h.Base == "" {
				h.Base = tok.attr("href")
			}
		case "link":
			collectLink(&h, tok)
		case "meta":
			collectMeta(&h, tok)
		case "body":
			if stopAt < 0 {
				stopAt = t.i + afterHeadBytes
			}
		default:
			if rawText[tok.name] && !tok.selfClosing {
				t.skipRaw(tok.name)
			}
		}
	}
	return h
}

func collectLink(h *Head, tok token) {
	href := strings.TrimSpace(tok.attr("href"))
	if href == "" {
		return
	}
	rels := strings.Fields(strings.ToLower(tok.attr("rel")))
	rel := ""
	for _, r := range rels {
		switch r {
		case "manifest":
			rel = "manifest"
		case "icon":
			if rel == "" {
				rel = "icon"
			}
		case "apple-touch-icon", "apple-touch-icon-precomposed":
			rel = "apple-touch-icon"
		case "mask-icon":
			return // a single-colour SVG mask, not an icon
		}
	}
	if rel == "" {
		return
	}
	h.Links = append(h.Links, Link{Rel: rel, Href: href, Sizes: strings.ToLower(tok.attr("sizes")), Type: strings.ToLower(tok.attr("type")), Media: tok.attr("media")})
}

func collectMeta(h *Head, tok token) {
	if cs := tok.attr("charset"); cs != "" && h.Charset == "" {
		h.Charset = strings.ToLower(strings.TrimSpace(cs))
	}
	content := strings.TrimSpace(tok.attr("content"))
	switch strings.ToLower(tok.attr("http-equiv")) {
	case "refresh":
		if h.Refresh == "" {
			h.Refresh = content
		}
	case "content-type":
		if cs := charsetParam(content); cs != "" && h.Charset == "" {
			h.Charset = cs
		}
	}
	switch strings.ToLower(strings.TrimSpace(tok.attr("name"))) {
	case "theme-color":
		if content != "" {
			h.ThemeColors = append(h.ThemeColors, ThemeColor{Content: content, Media: strings.TrimSpace(tok.attr("media"))})
		}
	case "application-name":
		if h.AppName == "" {
			h.AppName = content
		}
	case "apple-mobile-web-app-title":
		if h.AppleTitle == "" {
			h.AppleTitle = content
		}
	case "description":
		if h.Description == "" {
			h.Description = content
		}
	}
	if strings.ToLower(tok.attr("property")) == "og:site_name" && h.OGSiteName == "" {
		h.OGSiteName = content
	}
}

// ThemeColor picks the theme colour: one without media first, else the one for dark (or
// light) mode, else the first.
func (h Head) ThemeColor(dark bool) string {
	for _, c := range h.ThemeColors {
		if c.Media == "" {
			return c.Content
		}
	}
	want := "light"
	if dark {
		want = "dark"
	}
	for _, c := range h.ThemeColors {
		if strings.Contains(strings.ToLower(c.Media), want) {
			return c.Content
		}
	}
	if len(h.ThemeColors) > 0 {
		return h.ThemeColors[0].Content
	}
	return ""
}

// ---- tokenizer ----

type token struct {
	name        string
	end         bool
	selfClosing bool
	attrs       [][2]string
}

func (t token) attr(name string) string {
	for _, a := range t.attrs {
		if a[0] == name {
			return a[1]
		}
	}
	return ""
}

type tokenizer struct {
	s string
	i int
}

func isSpace(c byte) bool { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' }

func isAlpha(c byte) bool { return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' }

func lower(s string) string {
	b := []byte(s)
	for i, c := range b {
		if c >= 'A' && c <= 'Z' {
			b[i] = c + 32
		}
	}
	return string(b)
}

// next returns the next start or end tag, skipping text, comments, doctypes and processing
// instructions.
func (t *tokenizer) next() (token, bool) {
	for {
		j := strings.IndexByte(t.s[t.i:], '<')
		if j < 0 {
			t.i = len(t.s)
			return token{}, false
		}
		t.i += j
		rest := t.s[t.i:]
		switch {
		case strings.HasPrefix(rest, "<!--"):
			k := strings.Index(rest[4:], "-->")
			if k < 0 {
				t.i = len(t.s)
				return token{}, false
			}
			t.i += 4 + k + 3
		case strings.HasPrefix(rest, "<!") || strings.HasPrefix(rest, "<?"):
			t.skipTo('>')
		case strings.HasPrefix(rest, "</"):
			if len(rest) > 2 && isAlpha(rest[2]) {
				t.i += 2
				name := t.readName()
				t.skipTo('>')
				return token{name: name, end: true}, true
			}
			t.skipTo('>')
		case len(rest) > 1 && isAlpha(rest[1]):
			t.i++
			return t.readTag(), true
		default:
			t.i++
		}
	}
}

func (t *tokenizer) skipTo(c byte) {
	k := strings.IndexByte(t.s[t.i:], c)
	if k < 0 {
		t.i = len(t.s)
		return
	}
	t.i += k + 1
}

func (t *tokenizer) readName() string {
	start := t.i
	for t.i < len(t.s) && !isSpace(t.s[t.i]) && t.s[t.i] != '/' && t.s[t.i] != '>' {
		t.i++
	}
	return lower(t.s[start:t.i])
}

func (t *tokenizer) readTag() token {
	tok := token{name: t.readName()}
	for t.i < len(t.s) {
		c := t.s[t.i]
		switch {
		case isSpace(c):
			t.i++
			continue
		case c == '>':
			t.i++
			return tok
		case c == '/':
			t.i++
			if t.i < len(t.s) && t.s[t.i] == '>' {
				tok.selfClosing = true
			}
			continue
		}
		// Attribute name.
		start := t.i
		t.i++ // the first character may be '=' per the spec
		for t.i < len(t.s) && !isSpace(t.s[t.i]) && t.s[t.i] != '/' && t.s[t.i] != '>' && t.s[t.i] != '=' {
			t.i++
		}
		name := lower(t.s[start:t.i])
		for t.i < len(t.s) && isSpace(t.s[t.i]) {
			t.i++
		}
		value := ""
		if t.i < len(t.s) && t.s[t.i] == '=' {
			t.i++
			for t.i < len(t.s) && isSpace(t.s[t.i]) {
				t.i++
			}
			value = t.readValue()
		}
		if len(tok.attrs) < maxAttrs && tok.attr(name) == "" {
			if len(value) > maxValue {
				value = value[:maxValue]
			}
			tok.attrs = append(tok.attrs, [2]string{name, html.UnescapeString(value)})
		}
	}
	return tok
}

func (t *tokenizer) readValue() string {
	if t.i >= len(t.s) {
		return ""
	}
	if q := t.s[t.i]; q == '"' || q == '\'' {
		t.i++
		k := strings.IndexByte(t.s[t.i:], q)
		if k < 0 {
			v := t.s[t.i:]
			t.i = len(t.s)
			return v
		}
		v := t.s[t.i : t.i+k]
		t.i += k + 1
		return v
	}
	start := t.i
	for t.i < len(t.s) && !isSpace(t.s[t.i]) && t.s[t.i] != '>' {
		t.i++
	}
	return t.s[start:t.i]
}

// endTag finds the next "</name" (any case) at or after t.i followed by a delimiter; it
// returns its index or -1.
func (t *tokenizer) endTag(name string) int {
	low := len(t.s)
	pos := t.i
	for pos < low {
		k := strings.Index(t.s[pos:], "</")
		if k < 0 {
			return -1
		}
		at := pos + k
		end := at + 2 + len(name)
		if end <= len(t.s) && lower(t.s[at+2:end]) == name && (end == len(t.s) || isSpace(t.s[end]) || t.s[end] == '>' || t.s[end] == '/') {
			return at
		}
		pos = at + 2
	}
	return -1
}

// skipRaw skips raw text up to and including the matching end tag.
func (t *tokenizer) skipRaw(name string) {
	at := t.endTag(name)
	if at < 0 {
		t.i = len(t.s)
		return
	}
	t.i = at
	t.skipTo('>')
}

// rcdata returns the text up to the matching end tag and moves past it.
func (t *tokenizer) rcdata(name string) string {
	at := t.endTag(name)
	if at < 0 {
		text := t.s[t.i:]
		t.i = len(t.s)
		return text
	}
	text := t.s[t.i:at]
	t.i = at
	t.skipTo('>')
	return text
}
