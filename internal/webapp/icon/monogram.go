package icon

import (
	"fmt"
	"image"
	"image/color"
	"strings"
	"unicode"
)

// Letter icons (monograms) use the brand book's app-tile tints by category with an ink letter.
// No amber: amber means "here" and is never decoration (design/brand-book.md). monogram_test
// checks every value against design/tokens.json.
var monogramTints = map[string]string{
	"Network":     "#e2eefa", // info-soft (browser tile)
	"Office":      "#e1f2e9", // success-soft (office tile)
	"Calendar":    "#e1f2e9",
	"Education":   "#e1f2e9",
	"AudioVideo":  "#fbeadf", // warning-soft (video tile)
	"Game":        "#fbeadf",
	"Development": "#e8edf1", // surface-sunken (editor tile)
	"Utility":     "#e8edf1",
	"Graphics":    "#f0eae3", // warm-soft (shell tile)
}

// MonogramInk is the letter colour (ink, light).
const MonogramInk = "#151a21"

// MonogramTint returns the tile tint for a category (Network's for unknown ones).
func MonogramTint(category string) string {
	if t, ok := monogramTints[category]; ok {
		return t
	}
	return monogramTints["Network"]
}

// MonogramLetter is the first letter or digit of the name, uppercased ("" if none).
func MonogramLetter(name string) string {
	for _, r := range name {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return strings.ToUpper(string(r))
		}
	}
	return ""
}

// MonogramSVG is the letter icon's SVG source.
func MonogramSVG(name, category string) string {
	letter := MonogramLetter(name)
	var b strings.Builder
	fmt.Fprintf(&b, `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">`+"\n")
	fmt.Fprintf(&b, `  <rect width="512" height="512" rx="154" fill="%s"/>`+"\n", MonogramTint(category))
	if letter != "" {
		fmt.Fprintf(&b, `  <text x="256" y="256" dy="0.36em" text-anchor="middle" font-family="Figtree, Noto Sans, Noto Sans Hebrew, Noto Sans Arabic, Noto Sans CJK SC, sans-serif" font-weight="600" font-size="264" fill="%s">%s</text>`+"\n", MonogramInk, xmlEscape(letter))
	}
	b.WriteString("</svg>\n")
	return b.String()
}

func xmlEscape(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&apos;").Replace(s)
}

// Monogram renders the letter icon at 512 px. Without rsvg-convert (a development machine) it
// draws the tile without the letter rather than failing; the package requires librsvg2-tools.
func Monogram(name, category string) (image.Image, error) {
	img, err := RenderSVG([]byte(MonogramSVG(name, category)))
	if err == nil {
		return img, nil
	}
	if err != ErrNoRsvg {
		return nil, err
	}
	out := image.NewNRGBA(image.Rect(0, 0, 512, 512))
	fillRounded(out, parseHex(MonogramTint(category)))
	return out, nil
}

func parseHex(s string) color.NRGBA {
	var r, g, b uint8
	fmt.Sscanf(strings.TrimPrefix(s, "#"), "%02x%02x%02x", &r, &g, &b)
	return color.NRGBA{r, g, b, 0xff}
}
