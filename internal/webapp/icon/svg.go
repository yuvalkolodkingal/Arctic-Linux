package icon

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"image"
	"image/png"
	"io"
	"os"
	"os/exec"
	"time"
)

// RsvgConvert is the SVG renderer (librsvg2-tools); tests may point it elsewhere.
var RsvgConvert = "/usr/bin/rsvg-convert"

// ErrNoRsvg means rsvg-convert is not installed.
var ErrNoRsvg = errors.New("rsvg-convert is not installed")

const (
	maxSVG     = 1 << 20
	maxSVGPNG  = 4 << 20
	svgTimeout = 5 * time.Second
)

// RenderSVG renders an SVG to a 512×512 PNG image with rsvg-convert: the SVG goes in on stdin
// (so relative references resolve to nothing), argv only, 5 s, an empty working directory, a
// minimal environment, output capped at 4 MiB and decoded with image/png. The SVG itself is
// never installed or handed to Qt or GTK.
func RenderSVG(svg []byte) (image.Image, error) {
	if len(svg) > maxSVG {
		return nil, fmt.Errorf("the SVG icon is too large")
	}
	if _, err := os.Stat(RsvgConvert); err != nil {
		return nil, ErrNoRsvg
	}
	dir, err := os.MkdirTemp("", "arctic-webapp-svg")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(dir)
	ctx, cancel := context.WithTimeout(context.Background(), svgTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, RsvgConvert, "-w", "512", "-h", "512", "--keep-aspect-ratio", "-f", "png")
	cmd.Dir = dir
	cmd.Env = []string{"PATH=/usr/bin", "LANG=C.UTF-8", "HOME=" + dir}
	cmd.Stdin = bytes.NewReader(svg)
	var out bytes.Buffer
	cmd.Stdout = &limitWriter{w: &out, n: maxSVGPNG}
	cmd.Stderr = io.Discard
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("the SVG icon could not be drawn: %v", err)
	}
	img, err := png.Decode(&out)
	if err != nil {
		return nil, fmt.Errorf("the SVG icon could not be drawn: %v", err)
	}
	return img, nil
}

type limitWriter struct {
	w io.Writer
	n int
}

func (l *limitWriter) Write(p []byte) (int, error) {
	if len(p) > l.n {
		return 0, errors.New("output too large")
	}
	l.n -= len(p)
	return l.w.Write(p)
}
