// Package daemon wires the engine for the binaries: catalog lookup, the engine log, the mock
// or real backend, the unix socket (with systemd socket activation) and the accept loop.
package daemon

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"sync"
	"syscall"

	"github.com/yuvalkolodkingal/o-tism/internal/backend"
	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/engine"
	"github.com/yuvalkolodkingal/o-tism/internal/host"
	"github.com/yuvalkolodkingal/o-tism/internal/mock"
	"github.com/yuvalkolodkingal/o-tism/modules"
)

// Defaults.
const (
	DefaultSocket  = "/run/arcticd.sock"
	DefaultLogPath = "/var/log/arctic-install/engine.log"
)

// LoadCatalog loads dir, else the packaged catalog, else the copy embedded in the binary.
func LoadCatalog(dir string) (*catalog.Catalog, string, error) {
	if dir != "" {
		c, err := catalog.LoadDir(dir)
		return c, dir, err
	}
	for _, d := range catalog.DefaultDirs {
		if _, err := os.Stat(filepath.Join(d, "catalog.toml")); err == nil {
			c, err := catalog.LoadDir(d)
			return c, d, err
		}
	}
	c, err := catalog.Load(modules.FS)
	return c, "(embedded)", err
}

// Config selects and configures a backend.
type Config struct {
	Mock        bool
	MockOptions mock.Options
	CatalogDir  string
	LogPath     string // "" = default for the mode; "-" = stderr
	Unattended  bool
	Target      string
}

// Env reads mock tuning from the environment: ARCTIC_MOCK_SPEED, ARCTIC_MOCK_FAIL
// (module id or "none"), ARCTIC_MOCK_FATAL=1, ARCTIC_MOCK_WIRED=1, ARCTIC_MOCK_FIRMWARE,
// ARCTIC_MOCK_HW (a hw.Fixtures name) and ARCTIC_MOCK_SECUREBOOT=0.
func (c *Config) Env() {
	if v, err := strconv.ParseFloat(os.Getenv("ARCTIC_MOCK_SPEED"), 64); err == nil && v > 0 {
		c.MockOptions.Speed = v
	}
	if v := os.Getenv("ARCTIC_MOCK_FAIL"); v != "" {
		c.MockOptions.FailModule = v
	}
	if os.Getenv("ARCTIC_MOCK_FATAL") == "1" {
		c.MockOptions.FailCore = true
	}
	if os.Getenv("ARCTIC_MOCK_WIRED") == "1" {
		c.MockOptions.Wired = true
	}
	if v := os.Getenv("ARCTIC_MOCK_FIRMWARE"); v == "uefi" || v == "bios" {
		c.MockOptions.Firmware = v
	}
	if v := os.Getenv("ARCTIC_MOCK_HW"); v != "" {
		c.MockOptions.Hardware = v
	}
	if os.Getenv("ARCTIC_MOCK_SECUREBOOT") == "0" {
		c.MockOptions.NoSecureBoot = true
	}
}

// OpenLog opens the engine log. Mock mode logs to $TMPDIR/arctic-install-mock/engine.log so
// it never needs root; if the log can't be opened the engine logs to stderr.
func OpenLog(path string, mockMode bool) (io.WriteCloser, string) {
	if path == "-" {
		return nopCloser{os.Stderr}, ""
	}
	if path == "" {
		path = DefaultLogPath
		if mockMode {
			path = filepath.Join(os.TempDir(), "arctic-install-mock", "engine.log")
		}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o750); err == nil {
		if f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o640); err == nil {
			return &lockedFile{f: f}, path
		}
	}
	return nopCloser{os.Stderr}, ""
}

type nopCloser struct{ io.Writer }

func (nopCloser) Close() error { return nil }

type lockedFile struct {
	mu sync.Mutex
	f  *os.File
}

func (l *lockedFile) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.f.Write(p)
}

func (l *lockedFile) Close() error { return l.f.Close() }

// NewEngine builds an engine for the config. The returned closer closes the log.
func NewEngine(cfg Config) (*engine.Engine, func(), error) {
	cat, where, err := LoadCatalog(cfg.CatalogDir)
	if err != nil {
		return nil, nil, fmt.Errorf("catalog %s: %w", where, err)
	}
	logw, logPath := OpenLog(cfg.LogPath, cfg.Mock)
	var b backend.Backend
	if cfg.Mock {
		b = mock.New(cfg.MockOptions)
	} else {
		b = host.New(host.Options{Log: logw, LogPath: logPath, Target: cfg.Target})
	}
	var preinstalled []string
	if !cfg.Mock && host.IsLive() {
		preinstalled = cat.MarkPreinstalled(host.ImageHasFlatpak)
	}
	e, err := engine.New(b, engine.Options{Catalog: cat, Log: logw, LogPath: logPath, Unattended: cfg.Unattended})
	if err != nil {
		logw.Close()
		return nil, nil, err
	}
	lg := log.New(logw, "arcticd: ", log.LstdFlags|log.Lmsgprefix)
	lg.Printf("catalog from %s (%d modules)", where, len(cat.Modules))
	if len(preinstalled) > 0 {
		lg.Printf("in the live image as Flatpaks: %v", preinstalled)
	}
	return e, func() { e.Close(); logw.Close() }, nil
}

// Listen returns the systemd-activated socket (LISTEN_FDS) or listens on path
// (mode 0660, group wheel when it exists).
func Listen(path string) (net.Listener, bool, error) {
	if l, err := activationListener(); err != nil || l != nil {
		return l, true, err
	}
	if fi, err := os.Lstat(path); err == nil && fi.Mode()&os.ModeSocket != 0 {
		if c, err := net.Dial("unix", path); err == nil {
			c.Close()
			return nil, false, fmt.Errorf("%s is already served by another engine", path)
		}
		os.Remove(path)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, false, err
	}
	l, err := net.Listen("unix", path)
	if err != nil {
		return nil, false, err
	}
	os.Chmod(path, 0o660)
	if g, err := user.LookupGroup("wheel"); err == nil && os.Geteuid() == 0 {
		if gid, err := strconv.Atoi(g.Gid); err == nil {
			os.Chown(path, 0, gid)
		}
	}
	return l, false, nil
}

// activationListener implements sd_listen_fds(3) with the standard library: fd 3 when
// LISTEN_PID is us and LISTEN_FDS ≥ 1.
func activationListener() (net.Listener, error) {
	pid, err := strconv.Atoi(os.Getenv("LISTEN_PID"))
	if err != nil || pid != os.Getpid() {
		return nil, nil
	}
	n, err := strconv.Atoi(os.Getenv("LISTEN_FDS"))
	if err != nil || n < 1 {
		return nil, nil
	}
	os.Unsetenv("LISTEN_PID")
	os.Unsetenv("LISTEN_FDS")
	os.Unsetenv("LISTEN_FDNAMES")
	const listenFDsStart = 3
	syscall.CloseOnExec(listenFDsStart)
	f := os.NewFile(uintptr(listenFDsStart), "arcticd.socket")
	l, err := net.FileListener(f)
	f.Close()
	if err != nil {
		return nil, fmt.Errorf("socket activation: %w", err)
	}
	return l, nil
}

// Serve accepts connections until ctx is done.
func Serve(ctx context.Context, l net.Listener, e *engine.Engine) error {
	go func() {
		<-ctx.Done()
		l.Close()
	}()
	var wg sync.WaitGroup
	defer wg.Wait()
	for {
		c, err := l.Accept()
		if err != nil {
			if ctx.Err() != nil || errors.Is(err, net.ErrClosed) {
				return nil
			}
			return err
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			stop := context.AfterFunc(ctx, func() { c.Close() })
			defer stop()
			defer c.Close()
			e.ServeConn(ctx, c, c)
		}()
	}
}
