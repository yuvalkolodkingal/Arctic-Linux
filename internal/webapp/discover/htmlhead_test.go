package discover

import (
	"strings"
	"testing"
)

func TestParseHead(t *testing.T) {
	doc := `<!DOCTYPE html>
<?xml version="1.0"?>
<HTML><HEAD>
<meta charset=UTF-8>
<BASE HREF="/app/">
<title>Inbox (3) &amp; more – Example Mail</title>
<!-- <link rel="icon" href="/hidden.png"> -->
<script>var s = "</head><link rel=icon href=/fake.png>"; if (a < b) {}</script>
<style>link{}</style>
<link rel="shortcut icon" href='/favicon.ico'>
<link REL=apple-touch-icon href=/apple.png sizes=180x180>
<link rel="mask-icon" href="/mask.svg">
<link rel=manifest href="/manifest.webmanifest">
<link rel="icon" type="image/png" sizes="32x32 192x192" href="/i.png"/>
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000">
<meta name="theme-color" content="#FFF">
<meta name=application-name content="Example Mail">
<meta property="og:site_name" content="Example">
<meta http-equiv="refresh" content="0; url=/next">
<noscript><link rel=icon href=/noscript.png></noscript>
</head><body><link rel=icon href=/body.png></body></html>`
	h := ParseHead(doc)
	if h.Base != "/app/" || h.Title != "Inbox (3) & more – Example Mail" || h.Charset != "utf-8" {
		t.Fatalf("base/title/charset: %q %q %q", h.Base, h.Title, h.Charset)
	}
	var hrefs []string
	for _, l := range h.Links {
		hrefs = append(hrefs, l.Rel+":"+l.Href)
	}
	want := "icon:/favicon.ico apple-touch-icon:/apple.png manifest:/manifest.webmanifest icon:/i.png icon:/body.png"
	if got := strings.Join(hrefs, " "); got != want {
		t.Fatalf("links:\n got %s\nwant %s", got, want)
	}
	if h.ThemeColor(false) != "#FFF" || h.AppName != "Example Mail" || h.OGSiteName != "Example" || h.Refresh != "0; url=/next" {
		t.Fatalf("metas: %+v", h)
	}
	if h.Links[3].Sizes != "32x32 192x192" || h.Links[3].Type != "image/png" {
		t.Fatalf("attrs: %+v", h.Links[3])
	}
}

func TestThemeColorByMedia(t *testing.T) {
	h := Head{ThemeColors: []ThemeColor{{"#111", "(prefers-color-scheme: dark)"}, {"#eee", "(prefers-color-scheme: light)"}}}
	if h.ThemeColor(true) != "#111" || h.ThemeColor(false) != "#eee" {
		t.Fatal("media match")
	}
}

func TestTruncatedAndHostile(t *testing.T) {
	for _, doc := range []string{"", "<", "<title>", "<link rel=icon href=", "<!--", "<script>", "<a b='", "</", "<title>x</titl", strings.Repeat("<a ", 10000)} {
		ParseHead(doc) // must not panic or hang
	}
	h := ParseHead("<title>A</title><title>B</title>")
	if h.Title != "A" {
		t.Fatalf("first title wins: %q", h.Title)
	}
	h = ParseHead(`<link rel=icon href="/a.png" rel=manifest>`)
	if len(h.Links) != 1 || h.Links[0].Rel != "icon" {
		t.Fatalf("duplicate attributes: first wins: %+v", h.Links)
	}
}

func TestDecodeHTML(t *testing.T) {
	// windows-1252 bytes: “Café” with curly quotes (0x93, 0x94) and é (0xe9).
	raw := []byte("<meta charset=windows-1252><title>\x93Caf\xe9\x94</title>")
	if got := ParseHead(DecodeHTML(raw, "text/html")).Title; got != "“Café”" {
		t.Fatalf("1252 title %q", got)
	}
	if got := ParseHead(DecodeHTML([]byte("<title>Caf\xe9</title>"), "text/html; charset=ISO-8859-1")).Title; got != "Café" {
		t.Fatalf("latin1 title %q", got)
	}
	if got := ParseHead(DecodeHTML([]byte("\xef\xbb\xbf<title>\xd7\xa9\xd7\x9c\xd7\x95\xd7\x9d\r\n</title>"), "")).Title; got != "שלום" {
		t.Fatalf("BOM + CRLF title %q", got)
	}
	if got := DecodeHTML([]byte("a\xffb"), "text/html; charset=utf-8"); got != "a�b" {
		t.Fatalf("invalid utf-8: %q", got)
	}
}

func FuzzHead(f *testing.F) {
	for _, s := range []string{"<html><head><title>x</title><link rel=icon href=/a></head>", "<script></head>", "<!-- <link> -->", "<meta content='x", "<a/b/c>"} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, doc string) {
		h := ParseHead(doc)
		for _, l := range h.Links {
			if l.Href == "" {
				t.Fatal("empty href collected")
			}
		}
	})
}
