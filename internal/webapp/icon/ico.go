package icon

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
)

// ICO/CUR/BMP are decoded by hand (the standard library has no decoder): little-endian, every
// offset and length checked, at most 64 entries and 1 MiB. PNG entries go to image/png; the
// others are headerless DIBs (BITMAPINFOHEADER with a doubled height): 32 bpp BGRA, 24 bpp,
// and 8/4/1 bpp palettes, with the AND mask for transparency, bottom-up rows padded to 4
// bytes, BI_RGB only.

var errICO = errors.New("broken icon file")

type icoEntry struct {
	w, h   int
	bpp    int
	size   int
	offset int
}

// DecodeICO decodes the largest (then deepest) image of an ICO or CUR file.
func DecodeICO(b []byte) (image.Image, error) {
	if len(b) > 1<<20 || len(b) < 6 {
		return nil, errICO
	}
	typ := binary.LittleEndian.Uint16(b[2:4])
	count := int(binary.LittleEndian.Uint16(b[4:6]))
	if binary.LittleEndian.Uint16(b[0:2]) != 0 || (typ != 1 && typ != 2) || count == 0 || count > 64 {
		return nil, errICO
	}
	if len(b) < 6+16*count {
		return nil, errICO
	}
	var best *icoEntry
	for i := 0; i < count; i++ {
		e := b[6+16*i : 6+16*(i+1)]
		ent := icoEntry{w: int(e[0]), h: int(e[1]), size: int(binary.LittleEndian.Uint32(e[8:12])), offset: int(binary.LittleEndian.Uint32(e[12:16]))}
		if ent.w == 0 {
			ent.w = 256
		}
		if ent.h == 0 {
			ent.h = 256
		}
		if typ == 1 {
			ent.bpp = int(binary.LittleEndian.Uint16(e[6:8]))
		}
		if ent.offset < 6+16*count || ent.size <= 0 || ent.offset > len(b) || ent.size > len(b)-ent.offset {
			continue // out of bounds: skip this entry
		}
		if best == nil || ent.w*ent.h > best.w*best.h || (ent.w*ent.h == best.w*best.h && ent.bpp > best.bpp) {
			c := ent
			best = &c
		}
	}
	if best == nil {
		return nil, errICO
	}
	data := b[best.offset : best.offset+best.size]
	if bytes.HasPrefix(data, []byte("\x89PNG\r\n\x1a\n")) {
		cfg, err := png.DecodeConfig(bytes.NewReader(data))
		if err != nil || cfg.Width > MaxPixels || cfg.Height > MaxPixels {
			return nil, errICO
		}
		return png.Decode(bytes.NewReader(data))
	}
	return decodeDIB(data, true)
}

// DecodeBMP decodes a Windows bitmap file (14-byte header, then the same DIB decoder).
func DecodeBMP(b []byte) (image.Image, error) {
	if len(b) < 14+40 || len(b) > 2<<20 || b[0] != 'B' || b[1] != 'M' {
		return nil, errICO
	}
	off := int(binary.LittleEndian.Uint32(b[10:14]))
	if off < 14+40 || off > len(b) {
		return nil, errICO
	}
	// decodeDIB expects the pixels right after the header (and palette); BMP files say where
	// they start, so pass the header and the pixel array joined.
	hdrSize := int(binary.LittleEndian.Uint32(b[14:18]))
	if hdrSize < 40 || 14+hdrSize > len(b) {
		return nil, errICO
	}
	return decodeDIBAt(b[14:], off-14, false)
}

func decodeDIB(d []byte, icon bool) (image.Image, error) {
	if len(d) < 40 {
		return nil, errICO
	}
	hdr := int(binary.LittleEndian.Uint32(d[0:4]))
	if hdr < 40 || hdr > len(d) {
		return nil, errICO
	}
	bpp := int(binary.LittleEndian.Uint16(d[14:16]))
	colors := int(binary.LittleEndian.Uint32(d[32:36]))
	if bpp <= 8 && colors == 0 {
		colors = 1 << bpp
	}
	if bpp > 8 {
		colors = 0
	}
	return decodeDIBAt(d, hdr+4*colors, icon)
}

// decodeDIBAt decodes a DIB whose header starts at d[0] and whose pixel array starts at pix.
func decodeDIBAt(d []byte, pix int, icon bool) (image.Image, error) {
	hdr := int(binary.LittleEndian.Uint32(d[0:4]))
	w := int(int32(binary.LittleEndian.Uint32(d[4:8])))
	h := int(int32(binary.LittleEndian.Uint32(d[8:12])))
	bpp := int(binary.LittleEndian.Uint16(d[14:16]))
	comp := binary.LittleEndian.Uint32(d[16:20])
	colors := int(binary.LittleEndian.Uint32(d[32:36]))
	topDown := false
	if h < 0 {
		h, topDown = -h, true
	}
	if icon {
		h /= 2 // XOR image + AND mask
	}
	if comp != 0 || w <= 0 || h <= 0 || w > MaxPixels || h > MaxPixels {
		return nil, fmt.Errorf("unsupported bitmap (%dx%d, compression %d)", w, h, comp)
	}
	switch bpp {
	case 1, 4, 8, 24, 32:
	default:
		return nil, fmt.Errorf("unsupported bitmap depth %d", bpp)
	}
	if bpp <= 8 && colors == 0 {
		colors = 1 << bpp
	}
	var palette []color.NRGBA
	if bpp <= 8 {
		if colors > 256 || hdr+4*colors > len(d) {
			return nil, errICO
		}
		for i := 0; i < colors; i++ {
			p := d[hdr+4*i:]
			palette = append(palette, color.NRGBA{p[2], p[1], p[0], 0xff})
		}
	}
	stride := ((w*bpp + 31) / 32) * 4
	maskStride := ((w + 31) / 32) * 4
	need := pix + stride*h
	if pix < 0 || need > len(d) || need < 0 {
		return nil, errICO
	}
	hasMask := icon && pix+stride*h+maskStride*h <= len(d)
	img := image.NewNRGBA(image.Rect(0, 0, w, h))
	allZeroAlpha := true
	for y := 0; y < h; y++ {
		row := y
		if !topDown {
			row = h - 1 - y
		}
		line := d[pix+row*stride : pix+(row+1)*stride]
		for x := 0; x < w; x++ {
			var c color.NRGBA
			switch bpp {
			case 32:
				p := line[4*x:]
				c = color.NRGBA{p[2], p[1], p[0], p[3]}
				if p[3] != 0 {
					allZeroAlpha = false
				}
			case 24:
				p := line[3*x:]
				c = color.NRGBA{p[2], p[1], p[0], 0xff}
			default:
				bit := x * bpp
				v := int(line[bit/8]>>(8-bpp-bit%8)) & (1<<bpp - 1)
				if v >= len(palette) {
					return nil, errICO
				}
				c = palette[v]
			}
			img.SetNRGBA(x, y, c)
		}
	}
	// The AND mask gives transparency, except for 32 bpp icons that have real alpha.
	if hasMask && (bpp != 32 || allZeroAlpha) {
		mask := pix + stride*h
		for y := 0; y < h; y++ {
			row := y
			if !topDown {
				row = h - 1 - y
			}
			line := d[mask+row*maskStride : mask+(row+1)*maskStride]
			for x := 0; x < w; x++ {
				i := img.PixOffset(x, y)
				if line[x/8]>>(7-x%8)&1 == 1 {
					img.Pix[i+3] = 0
				} else {
					img.Pix[i+3] = 0xff
				}
			}
		}
	} else if bpp == 32 && allZeroAlpha {
		for i := 3; i < len(img.Pix); i += 4 {
			img.Pix[i] = 0xff
		}
	}
	return img, nil
}
