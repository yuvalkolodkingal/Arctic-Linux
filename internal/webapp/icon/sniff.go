package icon

import (
	"bytes"
	"errors"
	"fmt"
	"image"
	"image/gif"
	"image/jpeg"
	"image/png"
)

// MaxPixels bounds decoded images: DecodeConfig is checked before any pixel is decoded.
const MaxPixels = 4096

// Sniff tells the format from the first bytes, never from a URL or Content-Type: png, jpeg,
// gif, ico, cur, bmp, svg, webp, avif, jxl, or "" (unknown).
func Sniff(b []byte) string {
	switch {
	case bytes.HasPrefix(b, []byte("\x89PNG\r\n\x1a\n")):
		return "png"
	case bytes.HasPrefix(b, []byte("\xff\xd8\xff")):
		return "jpeg"
	case bytes.HasPrefix(b, []byte("GIF87a")) || bytes.HasPrefix(b, []byte("GIF89a")):
		return "gif"
	case bytes.HasPrefix(b, []byte("\x00\x00\x01\x00")):
		return "ico"
	case bytes.HasPrefix(b, []byte("\x00\x00\x02\x00")):
		return "cur"
	case bytes.HasPrefix(b, []byte("BM")) && len(b) > 14:
		return "bmp"
	case len(b) > 12 && bytes.Equal(b[0:4], []byte("RIFF")) && bytes.Equal(b[8:12], []byte("WEBP")):
		return "webp"
	case len(b) > 12 && bytes.Equal(b[4:8], []byte("ftyp")) && (bytes.Equal(b[8:12], []byte("avif")) || bytes.Equal(b[8:12], []byte("avis"))):
		return "avif"
	case bytes.HasPrefix(b, []byte("\xff\x0a")) || bytes.HasPrefix(b, []byte("\x00\x00\x00\x0cJXL ")):
		return "jxl"
	}
	head := b
	if len(head) > 1024 {
		head = head[:1024]
	}
	head = bytes.TrimLeft(bytes.TrimPrefix(head, []byte("\xef\xbb\xbf")), " \t\r\n")
	if bytes.HasPrefix(head, []byte("<svg")) || ((bytes.HasPrefix(head, []byte("<?xml")) || bytes.HasPrefix(head, []byte("<!--")) || bytes.HasPrefix(head, []byte("<!DOCTYPE svg"))) && bytes.Contains(b, []byte("<svg"))) {
		return "svg"
	}
	return ""
}

// ErrUnsupported is an image format without a standard-library decoder (WebP, AVIF, JXL).
var ErrUnsupported = errors.New("unsupported image format")

// Decode decodes an icon of any supported format with bounds checks. SVG goes through
// rsvg-convert.
func Decode(b []byte) (image.Image, string, error) {
	format := Sniff(b)
	switch format {
	case "png", "jpeg", "gif":
		if len(b) > 2<<20 {
			return nil, format, errors.New("image too large")
		}
		cfg, _, err := image.DecodeConfig(bytes.NewReader(b))
		if err != nil {
			return nil, format, err
		}
		if cfg.Width <= 0 || cfg.Height <= 0 || cfg.Width > MaxPixels || cfg.Height > MaxPixels {
			return nil, format, fmt.Errorf("image is %dx%d", cfg.Width, cfg.Height)
		}
		var img image.Image
		switch format {
		case "png":
			img, err = png.Decode(bytes.NewReader(b))
		case "jpeg":
			img, err = jpeg.Decode(bytes.NewReader(b))
		case "gif":
			img, err = gif.Decode(bytes.NewReader(b)) // first frame
		}
		return img, format, err
	case "ico", "cur":
		img, err := DecodeICO(b)
		return img, format, err
	case "bmp":
		img, err := DecodeBMP(b)
		return img, format, err
	case "svg":
		img, err := RenderSVG(b)
		return img, format, err
	case "":
		return nil, format, errors.New("not an image")
	}
	return nil, format, ErrUnsupported
}
