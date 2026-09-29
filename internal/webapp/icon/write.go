package icon

import (
	"bytes"
	"fmt"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
)

// EncodePNG encodes an image as PNG.
func EncodePNG(img image.Image) ([]byte, error) {
	var b bytes.Buffer
	enc := png.Encoder{CompressionLevel: png.BestCompression}
	if err := enc.Encode(&b, img); err != nil {
		return nil, err
	}
	return b.Bytes(), nil
}

// SaveSource keeps the decoded source (at most 512 px) in the app directory for re-rendering,
// with its purpose in the file name's sidecar-free form: maskable sources are stored cropped
// already, so a re-render needs no purpose.
func SaveSource(p webapp.Paths, id string, src image.Image, purpose string) error {
	img := Normalize(src, purpose)
	data, err := EncodePNG(img)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(p.AppDir(id), 0o700); err != nil {
		return err
	}
	return webapp.WriteFileAtomic(p.SourceIcon(id), data, 0o600)
}

// Normalize prepares a source for storage: maskable icons are rendered to the tile now, and
// anything over 512 px is scaled down.
func Normalize(src image.Image, purpose string) image.Image {
	if purpose == "maskable" {
		return Tile(src, "maskable", 512)
	}
	b := src.Bounds()
	if b.Dx() > 512 || b.Dy() > 512 {
		scale := 512 / float64(max(b.Dx(), b.Dy()))
		return Resize(src, max(1, int(float64(b.Dx())*scale)), max(1, int(float64(b.Dy())*scale)))
	}
	return src
}

// LoadSource reads the stored source icon.
func LoadSource(p webapp.Paths, id string) (image.Image, error) {
	data, err := os.ReadFile(p.SourceIcon(id))
	if err != nil {
		return nil, err
	}
	return png.Decode(bytes.NewReader(data))
}

// Install writes the launcher icon at every size under the given icon name (0644) and bumps
// the hicolor directories' times so icon caches notice.
func Install(p webapp.Paths, name string, src image.Image) error {
	for _, size := range webapp.IconSizes {
		data, err := EncodePNG(Tile(src, "any", size))
		if err != nil {
			return err
		}
		path := p.IconFile(name, size)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return err
		}
		if err := webapp.WriteFileAtomic(path, data, 0o644); err != nil {
			return err
		}
	}
	Touch(p)
	return nil
}

// Remove deletes every installed revision of an app's icon (<id>.png and <id>.r<N>.png), except
// keep (the current name) when it is not "".
func Remove(p webapp.Paths, id, keep string) {
	for _, size := range webapp.IconSizes {
		dir := filepath.Dir(p.IconFile(id, size))
		entries, err := os.ReadDir(dir)
		if err != nil {
			continue
		}
		for _, e := range entries {
			n := strings.TrimSuffix(e.Name(), ".png")
			if n == e.Name() || n == keep {
				continue
			}
			if n == id || (strings.HasPrefix(n, id+".r") && isDigits(n[len(id)+2:])) {
				os.Remove(filepath.Join(dir, e.Name()))
			}
		}
	}
}

func isDigits(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// Touch bumps the mtime of hicolor and each size directory, which is how icon theme caches
// (GTK's and Qt's) notice new files.
func Touch(p webapp.Paths) {
	now := time.Now()
	os.Chtimes(p.Hicolor(), now, now)
	for _, size := range webapp.IconSizes {
		os.Chtimes(filepath.Join(p.Hicolor(), fmt.Sprintf("%dx%d", size, size)), now, now)
		os.Chtimes(filepath.Dir(p.IconFile("x", size)), now, now)
	}
}
