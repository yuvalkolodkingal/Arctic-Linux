package webapp

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"time"
)

// LockTimeout is how long a caller waits for the registry lock before answering "busy".
var LockTimeout = 5 * time.Second

// Lock is a held registry lock.
type Lock struct{ f *os.File }

// Acquire takes the registry lock: shared for readers (run, list), exclusive for writers.
func (p Paths) Acquire(exclusive bool) (*Lock, error) {
	if err := os.MkdirAll(p.Root(), 0o700); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(p.LockFile(), os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		return nil, err
	}
	how := syscall.LOCK_SH
	if exclusive {
		how = syscall.LOCK_EX
	}
	deadline := time.Now().Add(LockTimeout)
	for {
		err := syscall.Flock(int(f.Fd()), how|syscall.LOCK_NB)
		if err == nil {
			return &Lock{f: f}, nil
		}
		if !errors.Is(err, syscall.EWOULDBLOCK) && !errors.Is(err, syscall.EINTR) {
			f.Close()
			return nil, err
		}
		if time.Now().After(deadline) {
			f.Close()
			return nil, Errorf(CodeBusy, "Web apps are busy with another change. Try again in a moment.")
		}
		time.Sleep(50 * time.Millisecond)
	}
}

// Release drops the lock.
func (l *Lock) Release() {
	if l != nil && l.f != nil {
		syscall.Flock(int(l.f.Fd()), syscall.LOCK_UN)
		l.f.Close()
		l.f = nil
	}
}

// WriteFileAtomic writes data to a temp file in the same directory, fsyncs it and renames it
// over path, so readers see the old or the new file, never half of one.
func WriteFileAtomic(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, "."+filepath.Base(path)+".tmp*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	ok := false
	defer func() {
		if !ok {
			tmp.Close()
			os.Remove(name)
		}
	}()
	if err := tmp.Chmod(perm); err != nil {
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(name, path); err != nil {
		return err
	}
	ok = true
	return nil
}
