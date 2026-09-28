// Package icon turns whatever a site offers (PNG, JPEG, GIF, ICO/CUR/BMP, SVG through
// rsvg-convert) into the app's launcher icons: a rounded tile at 48–512 px in the user's
// hicolor theme, or a letter icon (monogram) from the design tokens. Every decoder is bounded;
// nothing a site sends reaches Qt or GTK undecoded.
package icon

import (
	"image"
	"image/color"
	"image/draw"
	"math"
)

// toNRGBA copies any image into a fresh NRGBA with its origin at 0,0.
func toNRGBA(src image.Image) *image.NRGBA {
	b := src.Bounds()
	dst := image.NewNRGBA(image.Rect(0, 0, b.Dx(), b.Dy()))
	draw.Draw(dst, dst.Bounds(), src, b.Min, draw.Src)
	return dst
}

// Resize scales src to w×h: a premultiplied box filter when shrinking (no dark fringes around
// transparent edges), bilinear when growing. image/draw has no scaler.
func Resize(src image.Image, w, h int) *image.NRGBA {
	s := toNRGBA(src)
	sw, sh := s.Bounds().Dx(), s.Bounds().Dy()
	dst := image.NewNRGBA(image.Rect(0, 0, w, h))
	if sw == 0 || sh == 0 || w <= 0 || h <= 0 {
		return dst
	}
	if w <= sw && h <= sh {
		boxDown(s, dst)
	} else {
		bilinear(s, dst)
	}
	return dst
}

func boxDown(s, dst *image.NRGBA) {
	sw, sh := s.Bounds().Dx(), s.Bounds().Dy()
	w, h := dst.Bounds().Dx(), dst.Bounds().Dy()
	fx, fy := float64(sw)/float64(w), float64(sh)/float64(h)
	for y := 0; y < h; y++ {
		y0, y1 := float64(y)*fy, float64(y+1)*fy
		for x := 0; x < w; x++ {
			x0, x1 := float64(x)*fx, float64(x+1)*fx
			var r, g, b, a, area float64
			for sy := int(y0); sy < int(math.Ceil(y1)) && sy < sh; sy++ {
				wy := math.Min(y1, float64(sy+1)) - math.Max(y0, float64(sy))
				for sx := int(x0); sx < int(math.Ceil(x1)) && sx < sw; sx++ {
					wx := math.Min(x1, float64(sx+1)) - math.Max(x0, float64(sx))
					wgt := wx * wy
					i := s.PixOffset(sx, sy)
					pa := float64(s.Pix[i+3]) / 255
					r += float64(s.Pix[i]) * pa * wgt
					g += float64(s.Pix[i+1]) * pa * wgt
					b += float64(s.Pix[i+2]) * pa * wgt
					a += pa * wgt
					area += wgt
				}
			}
			setPremul(dst, x, y, r, g, b, a, area)
		}
	}
}

func bilinear(s, dst *image.NRGBA) {
	sw, sh := s.Bounds().Dx(), s.Bounds().Dy()
	w, h := dst.Bounds().Dx(), dst.Bounds().Dy()
	at := func(x, y int) (float64, float64, float64, float64) {
		x = clampInt(x, 0, sw-1)
		y = clampInt(y, 0, sh-1)
		i := s.PixOffset(x, y)
		pa := float64(s.Pix[i+3]) / 255
		return float64(s.Pix[i]) * pa, float64(s.Pix[i+1]) * pa, float64(s.Pix[i+2]) * pa, pa
	}
	for y := 0; y < h; y++ {
		sy := (float64(y)+0.5)*float64(sh)/float64(h) - 0.5
		y0 := int(math.Floor(sy))
		ty := sy - float64(y0)
		for x := 0; x < w; x++ {
			sx := (float64(x)+0.5)*float64(sw)/float64(w) - 0.5
			x0 := int(math.Floor(sx))
			tx := sx - float64(x0)
			var acc [4]float64
			for _, c := range [4]struct {
				dx, dy int
				wgt    float64
			}{{0, 0, (1 - tx) * (1 - ty)}, {1, 0, tx * (1 - ty)}, {0, 1, (1 - tx) * ty}, {1, 1, tx * ty}} {
				r, g, b, a := at(x0+c.dx, y0+c.dy)
				acc[0] += r * c.wgt
				acc[1] += g * c.wgt
				acc[2] += b * c.wgt
				acc[3] += a * c.wgt
			}
			setPremul(dst, x, y, acc[0], acc[1], acc[2], acc[3], 1)
		}
	}
}

// setPremul stores a premultiplied sum (divided by area) as a straight-alpha pixel.
func setPremul(dst *image.NRGBA, x, y int, r, g, b, a, area float64) {
	if area <= 0 {
		return
	}
	r, g, b, a = r/area, g/area, b/area, a/area
	var c color.NRGBA
	if a > 0 {
		c = color.NRGBA{R: clamp8(r / a), G: clamp8(g / a), B: clamp8(b / a), A: clamp8(a * 255)}
	}
	dst.SetNRGBA(x, y, c)
}

func clamp8(v float64) uint8 {
	v = math.Round(v)
	if v < 0 {
		return 0
	}
	if v > 255 {
		return 255
	}
	return uint8(v)
}

func clampInt(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}
