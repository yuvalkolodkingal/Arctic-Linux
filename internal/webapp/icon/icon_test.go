package icon

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"math"
	"os"
	"strings"
	"testing"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

func solid(w, h int, c color.NRGBA) *image.NRGBA {
	img := image.NewNRGBA(image.Rect(0, 0, w, h))
	for i := 0; i < len(img.Pix); i += 4 {
		img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = c.R, c.G, c.B, c.A
	}
	return img
}

func pngOf(img image.Image) []byte {
	var b bytes.Buffer
	png.Encode(&b, img)
	return b.Bytes()
}

// ico builds an ICO file with the given entries (w, h, bpp, data).
func ico(entries ...[4]any) []byte {
	var b bytes.Buffer
	binary.Write(&b, binary.LittleEndian, []uint16{0, 1, uint16(len(entries))})
	off := 6 + 16*len(entries)
	for _, e := range entries {
		data := e[3].([]byte)
		b.Write([]byte{byte(e[0].(int)), byte(e[1].(int)), 0, 0})
		binary.Write(&b, binary.LittleEndian, []uint16{1, uint16(e[2].(int))})
		binary.Write(&b, binary.LittleEndian, []uint32{uint32(len(data)), uint32(off)})
		off += len(data)
	}
	for _, e := range entries {
		b.Write(e[3].([]byte))
	}
	return b.Bytes()
}

// dib builds a BITMAPINFOHEADER image: pixels bottom-up, rows padded, then the AND mask.
func dib(w, h, bpp int, palette []color.NRGBA, pixel func(x, y int) []byte, mask func(x, y int) bool) []byte {
	var b bytes.Buffer
	binary.Write(&b, binary.LittleEndian, []uint32{40, uint32(w), uint32(2 * h)})
	binary.Write(&b, binary.LittleEndian, []uint16{1, uint16(bpp)})
	binary.Write(&b, binary.LittleEndian, []uint32{0, 0, 0, 0, uint32(len(palette)), 0})
	for _, c := range palette {
		b.Write([]byte{c.B, c.G, c.R, 0})
	}
	stride := ((w*bpp + 31) / 32) * 4
	for y := h - 1; y >= 0; y-- {
		row := make([]byte, stride)
		if bpp >= 24 {
			for x := 0; x < w; x++ {
				copy(row[x*bpp/8:], pixel(x, y))
			}
		} else {
			for x := 0; x < w; x++ {
				v := pixel(x, y)[0]
				bit := x * bpp
				row[bit/8] |= v << (8 - bpp - bit%8)
			}
		}
		b.Write(row)
	}
	mstride := ((w + 31) / 32) * 4
	for y := h - 1; y >= 0; y-- {
		row := make([]byte, mstride)
		for x := 0; x < w; x++ {
			if mask(x, y) {
				row[x/8] |= 1 << (7 - x%8)
			}
		}
		b.Write(row)
	}
	return b.Bytes()
}

func TestICOFormats(t *testing.T) {
	red := color.NRGBA{255, 0, 0, 255}
	leftHalf := func(x, y int) bool { return x < 8 } // masked out = transparent
	none := func(x, y int) bool { return false }
	cases := map[string]struct {
		file    []byte
		w       int
		at      image.Point
		want    color.NRGBA
		clearAt image.Point
	}{
		"png entry wins by size": {ico([4]any{16, 16, 32, dib(16, 16, 32, nil, func(x, y int) []byte { return []byte{0, 0, 255, 255} }, none)},
			[4]any{0, 0, 32, pngOf(solid(256, 256, red))}), 256, image.Pt(5, 5), red, image.Pt(-1, -1)},
		"32bpp alpha": {ico([4]any{16, 16, 32, dib(16, 16, 32, nil, func(x, y int) []byte { return []byte{0, 0, 255, byte(x * 16)} }, none)}),
			16, image.Pt(15, 3), color.NRGBA{255, 0, 0, 240}, image.Pt(0, 0)},
		"32bpp zero alpha uses the mask": {ico([4]any{16, 16, 32, dib(16, 16, 32, nil, func(x, y int) []byte { return []byte{0, 255, 0, 0} }, leftHalf)}),
			16, image.Pt(12, 12), color.NRGBA{0, 255, 0, 255}, image.Pt(2, 2)},
		"24bpp + mask": {ico([4]any{16, 16, 24, dib(16, 16, 24, nil, func(x, y int) []byte { return []byte{255, 0, 0} }, leftHalf)}),
			16, image.Pt(9, 0), color.NRGBA{0, 0, 255, 255}, image.Pt(0, 15)},
		"8bpp palette": {ico([4]any{16, 16, 8, dib(16, 16, 8, []color.NRGBA{{0, 0, 0, 0}, red}, func(x, y int) []byte { return []byte{1} }, none)}),
			16, image.Pt(4, 4), red, image.Pt(-1, -1)},
		"4bpp palette": {ico([4]any{16, 16, 4, dib(16, 16, 4, []color.NRGBA{{1, 2, 3, 0}, {9, 9, 9, 0}}, func(x, y int) []byte { return []byte{byte(x % 2)} }, none)}),
			16, image.Pt(3, 7), color.NRGBA{9, 9, 9, 255}, image.Pt(-1, -1)},
		"1bpp": {ico([4]any{16, 16, 1, dib(16, 16, 1, []color.NRGBA{{0, 0, 0, 0}, {255, 255, 255, 0}}, func(x, y int) []byte { return []byte{byte(y % 2)} }, none)}),
			16, image.Pt(0, 1), color.NRGBA{255, 255, 255, 255}, image.Pt(-1, -1)},
	}
	for name, c := range cases {
		img, format, err := Decode(c.file)
		if err != nil || format != "ico" {
			t.Errorf("%s: %v %s", name, err, format)
			continue
		}
		if img.Bounds().Dx() != c.w {
			t.Errorf("%s: width %d", name, img.Bounds().Dx())
		}
		got := color.NRGBAModel.Convert(img.At(c.at.X, c.at.Y)).(color.NRGBA)
		if got != c.want {
			t.Errorf("%s: pixel %v = %v, want %v", name, c.at, got, c.want)
		}
		if c.clearAt.X >= 0 {
			if a := color.NRGBAModel.Convert(img.At(c.clearAt.X, c.clearAt.Y)).(color.NRGBA).A; a != 0 {
				t.Errorf("%s: %v should be transparent, alpha %d", name, c.clearAt, a)
			}
		}
	}
}

func TestICORejectsBroken(t *testing.T) {
	good := ico([4]any{16, 16, 32, dib(16, 16, 32, nil, func(x, y int) []byte { return []byte{1, 2, 3, 4} }, func(int, int) bool { return false })})
	truncated := good[:len(good)-200]
	count65 := append([]byte{0, 0, 1, 0, 65, 0}, make([]byte, 16*65)...)
	overlapping := append([]byte{}, good...)
	binary.LittleEndian.PutUint32(overlapping[6+12:], 2) // offset inside the directory
	huge := append([]byte{}, good...)
	binary.LittleEndian.PutUint32(huge[6+8:], 1<<30)
	for name, b := range map[string][]byte{"truncated": truncated, "count 65": count65, "overlapping": overlapping, "huge size": huge, "empty": {0, 0, 1, 0, 0, 0}, "short": {0, 0, 1}} {
		if img, err := DecodeICO(b); err == nil && name != "truncated" {
			t.Errorf("%s: accepted (%v)", name, img.Bounds())
		}
	}
}

func FuzzICO(f *testing.F) {
	f.Add(ico([4]any{16, 16, 32, dib(16, 16, 32, nil, func(x, y int) []byte { return []byte{1, 2, 3, 4} }, func(int, int) bool { return false })}))
	f.Add(ico([4]any{0, 0, 32, pngOf(solid(4, 4, color.NRGBA{1, 1, 1, 1}))}))
	f.Fuzz(func(t *testing.T, b []byte) {
		DecodeICO(b) // must never panic
		DecodeBMP(b)
	})
}

func TestSniff(t *testing.T) {
	for want, b := range map[string][]byte{
		"png": pngOf(solid(1, 1, color.NRGBA{})), "gif": []byte("GIF89a..."), "jpeg": {0xff, 0xd8, 0xff, 0xe0},
		"ico": {0, 0, 1, 0, 1, 0}, "svg": []byte("\n  <?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>"),
		"webp": []byte("RIFF\x00\x00\x00\x00WEBPVP8 "), "avif": []byte("\x00\x00\x00\x1cftypavif\x00\x00"), "": []byte("<html>"),
	} {
		if got := Sniff(b); got != want {
			t.Errorf("Sniff = %q, want %q", got, want)
		}
	}
	if _, _, err := Decode([]byte("RIFF\x00\x00\x00\x00WEBPVP8 ")); err != ErrUnsupported {
		t.Errorf("webp: %v", err)
	}
	// A PNG claiming to be 5000 px wide is refused before decoding.
	var b bytes.Buffer
	png.Encode(&b, solid(1, 1, color.NRGBA{}))
	raw := b.Bytes()
	binary.BigEndian.PutUint32(raw[16:], 5000)
	if _, _, err := Decode(raw); err == nil {
		t.Error("5000 px PNG accepted")
	}
}

func TestResize(t *testing.T) {
	c := color.NRGBA{10, 200, 30, 255}
	down := Resize(solid(300, 300, c), 48, 48)
	if down.NRGBAAt(20, 20) != c || down.Bounds().Dx() != 48 {
		t.Fatalf("solid down: %v", down.NRGBAAt(20, 20))
	}
	up := Resize(solid(32, 32, c), 64, 64)
	if up.NRGBAAt(63, 63) != c {
		t.Fatalf("solid up: %v", up.NRGBAAt(63, 63))
	}
	// Premultiplied: a red pixel next to transparent black does not darken.
	half := image.NewNRGBA(image.Rect(0, 0, 2, 1))
	half.SetNRGBA(0, 0, color.NRGBA{255, 0, 0, 255})
	one := Resize(half, 1, 1).NRGBAAt(0, 0)
	if one.R != 255 || one.A < 126 || one.A > 129 {
		t.Fatalf("fringe: %v", one)
	}
}

func TestTileShapes(t *testing.T) {
	opaque := Tile(solid(180, 180, color.NRGBA{0, 0, 255, 255}), "any", 128)
	if opaque.NRGBAAt(0, 0).A != 0 || opaque.NRGBAAt(64, 64).A != 255 || opaque.NRGBAAt(64, 0).A != 255 {
		t.Fatalf("full-bleed square: corner %v centre %v edge %v", opaque.NRGBAAt(0, 0), opaque.NRGBAAt(64, 64), opaque.NRGBAAt(64, 0))
	}
	// An icon with its own transparency stays as it is (corner pixel transparent → no mask).
	trans := solid(128, 128, color.NRGBA{0, 0, 255, 255})
	trans.SetNRGBA(0, 0, color.NRGBA{})
	kept := Tile(trans, "any", 128)
	if kept.NRGBAAt(1, 1).A != 255 {
		t.Fatalf("transparent icon was masked")
	}
	// Maskable: the centre 80% fills the tile.
	m := solid(100, 100, color.NRGBA{255, 0, 0, 255})
	for y := 0; y < 100; y++ {
		for x := 0; x < 100; x++ {
			if x < 10 || x >= 90 || y < 10 || y >= 90 {
				m.SetNRGBA(x, y, color.NRGBA{0, 255, 0, 255})
			}
		}
	}
	mt := Tile(m, "maskable", 64)
	if c := mt.NRGBAAt(32, 1); c.R != 255 || c.G != 0 {
		t.Fatalf("maskable safe zone not cropped: %v", c)
	}
	// Tiny favicons sit on a surface-sunken tile.
	small := Tile(solid(16, 16, color.NRGBA{0, 0, 0, 255}), "any", 128)
	if small.NRGBAAt(10, 64) != SmallTint || small.NRGBAAt(64, 64) != (color.NRGBA{0, 0, 0, 255}) {
		t.Fatalf("small icon: edge %v centre %v", small.NRGBAAt(10, 64), small.NRGBAAt(64, 64))
	}
	// Non-square: centred, transparent bars.
	wide := Tile(solid(200, 100, color.NRGBA{9, 9, 9, 255}), "any", 64)
	if wide.NRGBAAt(32, 2).A != 0 || wide.NRGBAAt(32, 32).A != 255 {
		t.Fatal("non-square not centred")
	}
}

// ---- monograms: tokens only, no amber, readable ----

type tokenFile struct {
	Color struct {
		Tokens []struct {
			Name  string          `json:"name"`
			Value json.RawMessage `json:"value"`
		} `json:"tokens"`
	} `json:"color"`
}

func tokenValues(t *testing.T) map[string]string {
	data, err := os.ReadFile("../../../design/tokens.json")
	if err != nil {
		t.Fatal(err)
	}
	var tf tokenFile
	if err := json.Unmarshal(data, &tf); err != nil {
		t.Fatal(err)
	}
	out := map[string]string{}
	for _, tok := range tf.Color.Tokens {
		var v struct{ Light string }
		if json.Unmarshal(tok.Value, &v) == nil && v.Light != "" {
			out[tok.Name] = strings.ToLower(v.Light)
			continue
		}
		var s string
		if json.Unmarshal(tok.Value, &s) == nil {
			out[tok.Name] = strings.ToLower(s)
		}
	}
	return out
}

func luminance(hex string) float64 {
	c := parseHex(hex)
	lin := func(v uint8) float64 {
		f := float64(v) / 255
		if f <= 0.03928 {
			return f / 12.92
		}
		return math.Pow((f+0.055)/1.055, 2.4)
	}
	return 0.2126*lin(c.R) + 0.7152*lin(c.G) + 0.0722*lin(c.B)
}

func TestMonogramPalette(t *testing.T) {
	tokens := tokenValues(t)
	values := map[string]bool{}
	amber := map[string]bool{}
	for name, v := range tokens {
		values[v] = true
		if strings.HasPrefix(name, "amber") || strings.HasPrefix(name, "accent") || name == "focus" || name == "selection" || name == "term-cursor" {
			amber[v] = true
		}
	}
	if len(amber) == 0 {
		t.Fatal("no amber tokens found; tokens.json layout changed?")
	}
	ink := MonogramInk
	if !values[ink] || amber[ink] {
		t.Fatalf("ink %s is not a token or is amber", ink)
	}
	for _, cat := range webapp.Categories {
		tint := MonogramTint(cat)
		if !values[tint] {
			t.Errorf("%s: tint %s is not a token value", cat, tint)
		}
		if amber[tint] {
			t.Errorf("%s: tint %s is amber", cat, tint)
		}
		l1, l2 := luminance(tint), luminance(ink)
		if ratio := (math.Max(l1, l2) + 0.05) / (math.Min(l1, l2) + 0.05); ratio < 4.5 {
			t.Errorf("%s: contrast %.2f < 4.5", cat, ratio)
		}
	}
}

func TestMonogramSVG(t *testing.T) {
	got := MonogramSVG("<script>", "Graphics")
	if !strings.Contains(got, `fill="#f0eae3"`) || !strings.Contains(got, ">S</text>") || strings.Contains(got, "<script") {
		t.Fatalf("svg:\n%s", got)
	}
	if MonogramLetter("  ☺ 9lives") != "9" || MonogramLetter("שלום") != "ש" || MonogramLetter("") != "" {
		t.Fatal("letters")
	}
	if strings.Contains(MonogramSVG("", "Network"), "<text") {
		t.Fatal("no letter: no text element")
	}
}

func TestSVGWithRsvg(t *testing.T) {
	if _, err := os.Stat(RsvgConvert); err != nil {
		t.Skip("rsvg-convert not installed")
	}
	img, err := Monogram("YouTube", "AudioVideo")
	if err != nil {
		t.Fatal(err)
	}
	if img.Bounds().Dx() != 512 {
		t.Fatalf("size %v", img.Bounds())
	}
	if c := color.NRGBAModel.Convert(img.At(256, 40)).(color.NRGBA); c != parseHex("#fbeadf") {
		t.Fatalf("tint %v", c)
	}
	if _, err := RenderSVG([]byte("<svg><image href='file:///etc/passwd'/></svg>")); err != nil {
		t.Logf("external reference refused: %v", err)
	}
	if _, err := RenderSVG([]byte("not svg")); err == nil {
		t.Fatal("garbage rendered")
	}
}

func TestInstallAndRemove(t *testing.T) {
	d := t.TempDir()
	p := webapp.Paths{Home: d, DataHome: d + "/data"}
	id := "org.arcticlinux.WebApp.X_abcdef"
	src := solid(300, 300, color.NRGBA{1, 2, 3, 255})
	if err := Install(p, id, src); err != nil {
		t.Fatal(err)
	}
	if err := Install(p, id+".r1", src); err != nil {
		t.Fatal(err)
	}
	for _, size := range webapp.IconSizes {
		data, err := os.ReadFile(p.IconFile(id+".r1", size))
		if err != nil {
			t.Fatal(err)
		}
		cfg, err := png.DecodeConfig(bytes.NewReader(data))
		if err != nil || cfg.Width != size {
			t.Fatalf("%d: %v %v", size, cfg, err)
		}
		fi, _ := os.Stat(p.IconFile(id+".r1", size))
		if fi.Mode().Perm() != 0o644 {
			t.Fatalf("icon mode %v", fi.Mode().Perm())
		}
	}
	Remove(p, id, id+".r1")
	if _, err := os.Stat(p.IconFile(id, 48)); !os.IsNotExist(err) {
		t.Fatal("old revision kept")
	}
	if _, err := os.Stat(p.IconFile(id+".r1", 48)); err != nil {
		t.Fatal("current revision removed")
	}
	Remove(p, id, "")
	if _, err := os.Stat(p.IconFile(id+".r1", 48)); !os.IsNotExist(err) {
		t.Fatal("remove all left a file")
	}
}
