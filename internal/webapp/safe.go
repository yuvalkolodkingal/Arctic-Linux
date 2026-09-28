package webapp

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// RemoveTree deletes root/<id> and everything below it. It refuses an invalid id, a path that
// is not directly under root after cleaning, and a symlinked directory (a tampered registry
// must not make remove delete somewhere else). A missing directory is not an error.
func RemoveTree(root, id string) error {
	if !Valid(id) {
		return fmt.Errorf("refusing to delete %q: not a web-app id", id)
	}
	root = filepath.Clean(root)
	dir := filepath.Join(root, id)
	if filepath.Dir(dir) != root || !strings.HasPrefix(dir, root+string(filepath.Separator)) {
		return fmt.Errorf("refusing to delete %s: not under %s", dir, root)
	}
	fi, err := os.Lstat(dir)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if fi.Mode()&os.ModeSymlink != 0 {
		// Remove the link itself, never what it points to.
		return os.Remove(dir)
	}
	if !fi.IsDir() {
		return os.Remove(dir)
	}
	return os.RemoveAll(dir)
}

// DirSize adds up the sizes of the regular files below dir (0 when it is missing).
func DirSize(dir string) int64 {
	var n int64
	filepath.WalkDir(dir, func(_ string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.Type().IsRegular() {
			if fi, err := d.Info(); err == nil {
				n += fi.Size()
			}
		}
		return nil
	})
	return n
}
