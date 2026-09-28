package icon

import (
	"image"
	"image/color"
	"image/draw"
	"math"
)

// TileRadius is the app tile's corner radius as a fraction of its side (design/brand-book.md:
// app tiles have a 30% radius).
const TileRadius = 0.30

// SmallTint is the tile a tiny favicon sits on (surface-sunken, light).
var SmallTint = color.NRGBA{0xe8, 0xed, 0xf1, 0xff}

// MinSource is the smallest decoded icon used edge to edge; smaller ones sit in a tile.
const MinSource = 64

// Tile renders the launcher icon at size×size from the decoded source:
//   - maskable icons are cropped to their 80% safe zone and masked to the rounded tile;
//   - opaque full-bleed squares (apple-touch icons) get the same mask;
//   - icons with their own transparency stay as they are (centred if not square);
//   - icons under 64 px are drawn in the centre 55% of a surface-sunken tile.
//
// Every size is rendered from the source, never from another output size.
func Tile(src image.Image, purpose string, size int) *image.NRGBA {
	s := toNRGBA(src)
	w, h := s.Bounds().Dx(), s.Bounds().Dy()
	out := image.NewNRGBA(image.Rect(0, 0, size, size))
	if w == 0 || h == 0 {
		return out
	}
	if w < MinSource && h < MinSource {
		fillRounded(out, SmallTint)
		box := int(math.Round(float64(size) * 0.55))
		scale := float64(box) / float64(max(w, h))
		dw, dh := max(1, int(math.Round(float64(w)*scale))), max(1, int(math.Round(float64(h)*scale)))
		r := Resize(s, dw, dh)
		off := image.Pt((size-dw)/2, (size-dh)/2)
		draw.Draw(out, r.Bounds().Add(off), r, image.Point{}, draw.Over)
		return out
	}
	if purpose == "maskable" {
		// The safe zone is the centre circle of 80% diameter; crop the centre 80% square.
		cw, ch := int(float64(w)*0.8), int(float64(h)*0.8)
		crop := image.Rect((w-cw)/2, (h-ch)/2, (w-cw)/2+cw, (h-ch)/2+ch)
		sub := image.NewNRGBA(image.Rect(0, 0, cw, ch))
		draw.Draw(sub, sub.Bounds(), s, crop.Min, draw.Src)
		r := Resize(sub, size, size)
		maskRounded(r)
		return r
	}
	if w == h && opaqueCorners(s) {
		r := Resize(s, size, size)
		maskRounded(r)
		return r
	}
	// Transparent or non-square: fit inside the square, centred.
	scale := float64(size) / float64(max(w, h))
	dw, dh := max(1, int(math.Round(float64(w)*scale))), max(1, int(math.Round(float64(h)*scale)))
	r := Resize(s, dw, dh)
	off := image.Pt((size-dw)/2, (size-dh)/2)
	draw.Draw(out, r.Bounds().Add(off), r, image.Point{}, draw.Over)
	return out
}

// opaqueCorners: every corner pixel is fully opaque (a full-bleed square icon).
func opaqueCorners(s *image.NRGBA) bool {
	b := s.Bounds()
	for _, p := range []image.Point{{b.Min.X, b.Min.Y}, {b.Max.X - 1, b.Min.Y}, {b.Min.X, b.Max.Y - 1}, {b.Max.X - 1, b.Max.Y - 1}} {
		if s.NRGBAAt(p.X, p.Y).A != 0xff {
			return false
		}
	}
	return true
}

// coverage is how much of pixel (x, y) lies inside the rounded square of side n, from the
// signed distance to its edge (anti-aliased over one pixel).
func coverage(x, y, n int) float64 {
	fn := float64(n)
	r := fn * TileRadius
	px, py := float64(x)+0.5, float64(y)+0.5
	// Distance to the rounded rectangle (inigo quilez's box SDF with rounded corners).
	hx, hy := fn/2, fn/2
	qx := math.Abs(px-hx) - (hx - r)
	qy := math.Abs(py-hy) - (hy - r)
	outside := math.Hypot(math.Max(qx, 0), math.Max(qy, 0))
	inside := math.Min(math.Max(qx, qy), 0)
	d := outside + inside - r
	return math.Max(0, math.Min(1, 0.5-d))
}

func maskRounded(img *image.NRGBA) {
	n := img.Bounds().Dx()
	for y := 0; y < n; y++ {
		for x := 0; x < n; x++ {
			c := coverage(x, y, n)
			if c >= 1 {
				continue
			}
			i := img.PixOffset(x, y)
			img.Pix[i+3] = uint8(math.Round(float64(img.Pix[i+3]) * c))
		}
	}
}

func fillRounded(img *image.NRGBA, col color.NRGBA) {
	n := img.Bounds().Dx()
	for y := 0; y < n; y++ {
		for x := 0; x < n; x++ {
			c := coverage(x, y, n)
			if c <= 0 {
				continue
			}
			img.SetNRGBA(x, y, color.NRGBA{col.R, col.G, col.B, uint8(math.Round(float64(col.A) * c))})
		}
	}
}
