package discover

import (
	"bytes"
	"mime"
	"strings"
)

// charsetParam returns the charset parameter of a Content-Type value, lowercased.
func charsetParam(contentType string) string {
	_, params, err := mime.ParseMediaType(contentType)
	if err != nil {
		if i := strings.Index(strings.ToLower(contentType), "charset="); i >= 0 {
			v := contentType[i+len("charset="):]
			if j := strings.IndexAny(v, "; "); j >= 0 {
				v = v[:j]
			}
			return strings.ToLower(strings.Trim(v, `"'`))
		}
		return ""
	}
	return strings.ToLower(params["charset"])
}

// DecodeHTML turns a page's bytes into UTF-8: a UTF-8 BOM, then the Content-Type charset, then
// <meta charset>, else UTF-8. ISO-8859-1 and windows-1252 (which HTML treats as the same) are
// decoded by table; anything else is read as UTF-8 with invalid bytes replaced.
func DecodeHTML(raw []byte, contentType string) string {
	if bytes.HasPrefix(raw, []byte("\xef\xbb\xbf")) {
		return strings.ToValidUTF8(string(raw[3:]), "�")
	}
	cs := charsetParam(contentType)
	if cs == "" {
		// The tokenizer only needs ASCII to find <meta charset>.
		cs = ParseHead(string(raw)).Charset
	}
	switch cs {
	case "iso-8859-1", "latin1", "l1", "iso8859-1", "windows-1252", "cp1252", "us-ascii", "ascii", "iso_8859-1":
		return decode1252(raw)
	}
	return strings.ToValidUTF8(string(raw), "�")
}

// cp1252 maps 0x80–0x9f; the rest of windows-1252 equals ISO-8859-1 (U+0000–U+00FF).
var cp1252 = [32]rune{
	0x20AC, 0xFFFD, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0xFFFD, 0x017D, 0xFFFD,
	0xFFFD, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0xFFFD, 0x017E, 0x0178,
}

func decode1252(raw []byte) string {
	var b strings.Builder
	b.Grow(len(raw))
	for _, c := range raw {
		switch {
		case c < 0x80:
			b.WriteByte(c)
		case c < 0xa0:
			b.WriteRune(cp1252[c-0x80])
		default:
			b.WriteRune(rune(c))
		}
	}
	return b.String()
}

// stripBOM removes a UTF-8 byte order mark (manifests sometimes have one).
func stripBOM(b []byte) []byte {
	return bytes.TrimPrefix(b, []byte("\xef\xbb\xbf"))
}
