//go:build cgo && webkit

// Package webkit is the cgo boundary of the web-app window: a hand-written C shim (shim.c)
// over GTK 4 and WebKitGTK 6.0, and the Go side that turns its callbacks into calls on a
// Controller. Only C strings, ints and runtime/cgo handles cross; C never keeps a Go pointer.
// GTK runs on the main thread (the host locks it in init); nothing else calls into GTK.
// 2.54-only WebKit features are never called by symbol: the host is linked with -z now, so a
// newer symbol would stop it starting on an older WebKitGTK.
package webkit

/*
#cgo pkg-config: webkitgtk-6.0 gtk4 libsoup-3.0
#cgo CFLAGS: -std=gnu11 -Wall -Wno-deprecated-declarations
#include <stdlib.h>
#include "shim.h"
*/
import "C"

import (
	"runtime/cgo"
	"unsafe"
)

// Config is the window's start configuration.
type Config struct {
	AppID, AppName, IconName string
	StartURI, OpenURI        string
	DataDir, CacheDir        string
	Devtools, Software       bool
	Zoom                     float64
	Width, Height            int
	Maximized                bool
	Notice                   string // banner text shown at start ("" for none)
}

// Controller receives the shim's callbacks. Every method runs on the GTK main thread and must
// return quickly; panics are recovered and answered with the safe default.
type Controller interface {
	DecidePolicy(uri string, navType int, gesture, newWindow, modifiers, middle, popup bool) int
	DecideResponse(mime string, canShow, attachment bool) bool // true: download
	Permission(kind int, origin string) int
	PermissionDecided(kind int, origin string, allow bool)
	NotificationOrigins() []string
	DownloadDestination(suggested, mime string) string // "" cancels
	DownloadFinished(path string)
	URIChanged(uri string) int // bit 0: out of scope, bit 1: not secure
	LoadFinished(uri string)
	LoadFailed(uri, message string, tls bool) string // error page HTML, "" for WebKit's own
	ProcessTerminated(reason int) bool               // true: reload
	CloseRequest(width, height int, maximized bool, zoom float64)
	Startup()
	Shutdown()
	Open(uri string)
	Signal(signo int)
	ThemeChanged()
	Idle()
	// CertificateQuestion returns the banner text offering to trust a certificate for a
	// private-network host ("" for none); TrustCertificate acts on your yes.
	CertificateQuestion(uri, pem string) string
	TrustCertificate() bool
	// WantFavicon and Favicon upgrade a letter icon to the page's own icon.
	WantFavicon(width, height int) bool
	Favicon(png []byte) bool
}

func cstr(s string) *C.char {
	if s == "" {
		return nil
	}
	return C.CString(s)
}

func b2i(b bool) C.int {
	if b {
		return 1
	}
	return 0
}

// Run starts the GtkApplication and returns its exit status. args are passed to
// g_application_run (program name first; a URL there is opened like a second start's).
func Run(cfg Config, c Controller, args []string) int {
	h := cgo.NewHandle(c)
	defer h.Delete()
	var free []unsafe.Pointer
	s := func(v string) *C.char {
		p := cstr(v)
		if p != nil {
			free = append(free, unsafe.Pointer(p))
		}
		return p
	}
	cc := C.ArcticConfig{
		app_id: s(cfg.AppID), app_name: s(cfg.AppName), icon_name: s(cfg.IconName),
		start_uri: s(cfg.StartURI), open_uri: s(cfg.OpenURI),
		data_dir: s(cfg.DataDir), cache_dir: s(cfg.CacheDir),
		devtools: b2i(cfg.Devtools), software: b2i(cfg.Software), zoom: C.double(cfg.Zoom),
		width: C.int(cfg.Width), height: C.int(cfg.Height), maximized: b2i(cfg.Maximized),
		notice: s(cfg.Notice), handle: C.uintptr_t(h),
	}
	argv := make([]*C.char, len(args)+1)
	for i, a := range args {
		argv[i] = s(a)
	}
	defer func() {
		for _, p := range free {
			C.free(p)
		}
	}()
	return int(C.arctic_run(&cc, C.int(len(args)), (**C.char)(unsafe.Pointer(&argv[0]))))
}

// Version is the WebKitGTK version the host runs against; it needs no display.
func Version() string { return C.GoString(C.arctic_webkit_version()) }

// BaseDomain is libsoup's registrable domain for host ("" when it has none), for the tagged
// test that checks the pure-Go Public Suffix List against libsoup.
func BaseDomain(host string) string {
	p := C.CString(host)
	defer C.free(unsafe.Pointer(p))
	r := C.arctic_base_domain(p)
	if r == nil {
		return ""
	}
	defer C.free(unsafe.Pointer(r))
	return C.GoString(r)
}

func withC(s string, fn func(*C.char)) {
	p := C.CString(s)
	defer C.free(unsafe.Pointer(p))
	fn(p)
}

// Load navigates the main view.
func Load(uri string) { withC(uri, func(p *C.char) { C.arctic_load(p) }) }

// LoadHTML shows an Arctic page (error pages) in place of uri.
func LoadHTML(html, uri string) {
	withC(html, func(h *C.char) { withC(uri, func(u *C.char) { C.arctic_load_alternate_html(h, u) }) })
}

// OpenExternal opens a URI in your default browser (or the scheme's handler).
func OpenExternal(uri string) { withC(uri, func(p *C.char) { C.arctic_open_external(p) }) }

// SetTheme applies the window's CSS, colour scheme and page background.
func SetTheme(css string, dark bool, ground string) {
	withC(css, func(c *C.char) { withC(ground, func(g *C.char) { C.arctic_set_theme(c, b2i(dark), g) }) })
}

// AllowCertificate pins a certificate you confirmed for a private-network host.
func AllowCertificate(host, pem string) {
	withC(host, func(h *C.char) { withC(pem, func(p *C.char) { C.arctic_allow_certificate(h, p) }) })
}

// SetDevtools turns the inspector on or off live.
func SetDevtools(on bool) { C.arctic_set_devtools(b2i(on)) }

// Banner shows a notice under the header; primary is its one button ("" for none).
func Banner(text, primary string) {
	t := C.CString(text)
	defer C.free(unsafe.Pointer(t))
	var p *C.char
	if primary != "" {
		p = C.CString(primary)
		defer C.free(unsafe.Pointer(p))
	}
	C.arctic_banner(t, p)
}

// Present raises the window.
func Present() { C.arctic_present() }

// Quit ends the application (the window saves its state first).
func Quit() { C.arctic_quit() }

// PostIdle makes the main loop call c.Idle() once (from any goroutine).
func PostIdle(h cgo.Handle) { C.arctic_idle(C.uintptr_t(h)) }
