//go:build cgo && webkit

package main

import (
	"fmt"
	"log"
	"net"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/policy"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/theme"
	"github.com/yuvalkolodkingal/o-tism/internal/webkit"
)

// controller is the window's Go side: it answers the shim's callbacks with the pure-Go
// policies and keeps the window state, permissions and log.
type controller struct {
	paths    webapp.Paths
	app      *webapp.App
	scope    policy.Scope
	state    policy.State
	perms    *policy.Permissions
	crashes  policy.Crashes
	palette  theme.Palette
	openURI  string
	explicit bool // openURI came from --url
	inspect  bool
	notice   string
	log      *log.Logger
	logFile  *os.File
	pidDone  bool
	// pendingCert is the certificate the trust banner offers; faviconSent stops a second
	// favicon upgrade in one session.
	pendingCert *pendingCert
	faviconSent bool
}

func newController(id, openURL string, inspect bool, notice string) (*controller, error) {
	if !webapp.Valid(id) {
		return nil, fmt.Errorf("%q is not a web-app id", id)
	}
	p, err := webapp.PathsFromEnv()
	if err != nil {
		return nil, err
	}
	a, err := p.Load(id)
	if err != nil {
		return nil, err
	}
	c := &controller{paths: p, app: a, scope: policy.ScopeOf(a), inspect: inspect}
	c.state = policy.LoadState(p.StateFile(id))
	c.perms = policy.LoadPermissions(p.PermissionsFile(id))
	c.openURI = policy.RestoreURL(c.state, a.StartURL, c.scope, time.Now())
	if openURL != "" {
		if c.scope.In(openURL) {
			c.openURI, c.explicit = openURL, true
		} else {
			// Not this app's page: your browser opens it, the app opens as usual.
			exec.Command("xdg-open", openURL).Start()
		}
	}
	if notice == "runtime-missing" {
		c.notice = fmt.Sprintf("The browser %s used is no longer installed, so it opened in the Arctic engine.", a.Name)
	}
	c.openLog()
	return c, nil
}

// openLog starts the app's log (1 MiB, one rotation; URLs without query or fragment).
func (c *controller) openLog() {
	path := c.paths.Log(c.app.ID)
	os.MkdirAll(filepath.Dir(path), 0o700)
	if fi, err := os.Stat(path); err == nil && fi.Size() > 1<<20 {
		os.Rename(path, path+".1")
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		c.log = log.New(os.Stderr, "arctic-webapp-host: ", log.LstdFlags)
		return
	}
	c.logFile = f
	c.log = log.New(f, "", log.LstdFlags)
}

func (c *controller) run() int {
	for _, d := range []string{c.paths.Profile(c.app.ID), c.paths.Cache(c.app.ID)} {
		if err := os.MkdirAll(d, 0o700); err != nil {
			fmt.Fprintf(os.Stderr, "arctic-webapp-host: %v\n", err)
			return 1
		}
	}
	c.log.Printf("start %s (WebKitGTK %s) at %s", c.app.ID, webkit.Version(), policy.LogURL(c.openURI))
	cfg := webkit.Config{
		AppID: c.app.ID, AppName: c.app.Name, IconName: c.app.IconName(),
		StartURI: c.app.StartURL, OpenURI: c.openURI,
		DataDir: c.paths.Profile(c.app.ID), CacheDir: c.paths.Cache(c.app.ID),
		Devtools: c.app.Options.Devtools || c.inspect, Software: c.app.Options.Rendering == "software",
		Zoom: c.state.Zoom, Width: c.state.Width, Height: c.state.Height, Maximized: c.state.Maximized,
		Notice: c.notice,
	}
	args := []string{"arctic-webapp-host"}
	if c.explicit {
		// A URL to open: a running instance receives it as an "open" and navigates.
		args = append(args, c.openURI)
	}
	status := webkit.Run(cfg, c, args)
	if c.logFile != nil {
		c.logFile.Close()
	}
	return status
}

// ---- webkit.Controller ----

func (c *controller) DecidePolicy(uri string, navType int, gesture, newWindow, modifiers, middle, popup bool) int {
	d := policy.Decide(policy.Nav{URI: uri, Type: navType, UserGesture: gesture, MainFrame: true, NewWindow: newWindow,
		Modifiers: modifiers, Middle: middle, Popup: popup}, c.scope, c.app.Options.Links)
	if d == policy.External {
		c.log.Printf("open outside the app: %s", policy.LogURL(uri))
	}
	return d
}

func (c *controller) DecideResponse(mime string, canShow, attachment bool) bool {
	return attachment || !canShow
}

func (c *controller) Permission(kind int, origin string) int {
	return c.perms.Decide(origin, kind, c.scope, c.app.Options.Notifications)
}

func (c *controller) PermissionDecided(kind int, origin string, allow bool) {
	c.perms.Remember(origin, kind, allow)
	if err := c.perms.Save(c.paths.PermissionsFile(c.app.ID)); err != nil {
		c.log.Printf("permissions: %v", err)
	}
}

// NotificationOrigins seeds WebKit with the origins that may notify without asking, so
// Notification.permission reads "granted" for them.
func (c *controller) NotificationOrigins() []string {
	var out []string
	if c.app.Options.Notifications == "allow" {
		if u, err := url.Parse(c.app.StartURL); err == nil {
			out = append(out, u.Scheme+"://"+u.Host)
		}
	}
	for origin, m := range c.perms.Origins {
		if m["notifications"] == "allow" {
			out = append(out, origin)
		}
	}
	return out
}

func (c *controller) DownloadDestination(suggested, mime string) string {
	dir := policy.DownloadDir(c.paths.Home)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		c.log.Printf("downloads: %v", err)
		return ""
	}
	path := policy.Unique(dir, policy.SafeName(suggested, mime))
	c.log.Printf("download to %s", path)
	return path
}

func (c *controller) DownloadFinished(path string) {
	c.log.Printf("downloaded %s", path)
}

func (c *controller) URIChanged(uri string) int {
	if !strings.HasPrefix(uri, "http://") && !strings.HasPrefix(uri, "https://") {
		return 0
	}
	bits := 0
	if !c.scope.In(uri) {
		bits |= 1
	}
	if strings.HasPrefix(uri, "http://") {
		bits |= 2
	}
	return bits
}

func (c *controller) LoadFinished(uri string) {
	if c.scope.In(uri) {
		c.state.LastURL = uri
		c.state.LastUsed = time.Now().UTC()
	}
}

func (c *controller) LoadFailed(uri, message string, tls bool) string {
	host := uri
	if u, err := url.Parse(uri); err == nil && u.Host != "" {
		host = u.Host
	}
	c.log.Printf("load failed: %s: %s (tls %v)", policy.LogURL(uri), message, tls)
	if tls {
		return theme.ErrorPage(c.palette, "This connection isn’t private",
			fmt.Sprintf("%s sent a certificate that isn’t trusted, so %s didn’t open it.", host, c.app.Name), "", "")
	}
	return theme.ErrorPage(c.palette, "Can’t open this page",
		fmt.Sprintf("%s couldn’t reach %s. Check your connection.", c.app.Name, host), message, uri)
}

func (c *controller) ProcessTerminated(reason int) bool {
	c.log.Printf("web process ended (reason %d)", reason)
	return c.crashes.OnCrash(reason)
}

func (c *controller) CloseRequest(width, height int, maximized bool, zoom float64) {
	if !maximized && width > 0 && height > 0 {
		c.state.Width, c.state.Height = width, height
	}
	c.state.Maximized = maximized
	c.state.Zoom = zoom
	c.saveState()
}

func (c *controller) saveState() {
	if c.state.LastUsed.IsZero() {
		c.state.LastUsed = time.Now().UTC()
	}
	if err := c.state.Save(c.paths.StateFile(c.app.ID)); err != nil {
		c.log.Printf("state: %v", err)
	}
}

func (c *controller) Startup() {
	// The primary instance only (D-5): a second start forwards to it and exits.
	if err := c.paths.WritePid(c.app.ID, os.Getpid()); err == nil {
		c.pidDone = true
	}
	c.applyCertificates()
}

func (c *controller) Shutdown() {
	if c.pidDone {
		c.paths.RemovePid(c.app.ID, os.Getpid())
	}
	c.log.Printf("stop %s", c.app.ID)
}

func (c *controller) Open(uri string) {
	webkit.Present()
	if c.scope.In(uri) {
		webkit.Load(uri)
		return
	}
	webkit.OpenExternal(uri)
}

func (c *controller) Signal(signo int) {
	switch syscall.Signal(signo) {
	case syscall.SIGHUP:
		c.reload()
	case syscall.SIGTERM, syscall.SIGINT:
		webkit.Quit()
	}
}

// reload re-reads app.json after `arctic-webapp set` (SIGHUP): links, extra domains,
// notifications, developer tools and certificates apply now.
func (c *controller) reload() {
	a, err := c.paths.Load(c.app.ID)
	if err != nil {
		c.log.Printf("reload: %v", err)
		return
	}
	c.app = a
	c.scope = policy.ScopeOf(a)
	c.perms = policy.LoadPermissions(c.paths.PermissionsFile(a.ID))
	webkit.SetDevtools(a.Options.Devtools || c.inspect)
	c.applyCertificates()
	c.log.Printf("options reloaded")
}

func (c *controller) applyCertificates() {
	for _, e := range c.app.TLSExceptions {
		host := e.Host
		if h, _, err := net.SplitHostPort(host); err == nil {
			host = h
		}
		webkit.AllowCertificate(host, e.PEM)
	}
}

func (c *controller) ThemeChanged() {
	p, err := theme.Load(theme.File(c.paths.Home))
	if err != nil {
		p = theme.Default
	}
	c.palette = p
	webkit.SetTheme(theme.HostCSS(p), p.Dark, p.Ground)
}

func (c *controller) Idle() {}
