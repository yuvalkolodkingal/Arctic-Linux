//go:build cgo && webkit

package webkit

// The C → Go callbacks. Each one recovers a panic and returns the safe default: ignore a
// navigation, deny a permission, cancel a download, show WebKit's own error page.

/*
#include <stdint.h>
#include <stdlib.h>
*/
import "C"

import (
	"runtime/cgo"
	"strings"
)

func ctl(h C.uintptr_t) Controller { return cgo.Handle(h).Value().(Controller) }

func safe(def C.int, fn func() C.int) (r C.int) {
	defer func() {
		if recover() != nil {
			r = def
		}
	}()
	return fn()
}

func safeStr(fn func() string) (r *C.char) {
	defer func() {
		if recover() != nil {
			r = nil
		}
	}()
	s := fn()
	if s == "" {
		return nil
	}
	return C.CString(s) // freed by the C caller with free()
}

func safeDo(fn func()) {
	defer func() { recover() }()
	fn()
}

//export goDecidePolicy
func goDecidePolicy(h C.uintptr_t, uri *C.char, navType, gesture, newWindow, modifiers, middle, popup C.int) C.int {
	return safe(1, func() C.int {
		return C.int(ctl(h).DecidePolicy(C.GoString(uri), int(navType), gesture != 0, newWindow != 0, modifiers != 0, middle != 0, popup != 0))
	})
}

//export goDecideResponse
func goDecideResponse(h C.uintptr_t, mime *C.char, canShow, attachment C.int) C.int {
	return safe(0, func() C.int { return b2i(ctl(h).DecideResponse(C.GoString(mime), canShow != 0, attachment != 0)) })
}

//export goPermission
func goPermission(h C.uintptr_t, kind C.int, origin *C.char) C.int {
	return safe(0, func() C.int { return C.int(ctl(h).Permission(int(kind), C.GoString(origin))) })
}

//export goPermissionDecided
func goPermissionDecided(h C.uintptr_t, kind C.int, origin *C.char, allow C.int) {
	safeDo(func() { ctl(h).PermissionDecided(int(kind), C.GoString(origin), allow != 0) })
}

//export goNotificationOrigins
func goNotificationOrigins(h C.uintptr_t) *C.char {
	return safeStr(func() string { return strings.Join(ctl(h).NotificationOrigins(), "\n") })
}

//export goDownloadDestination
func goDownloadDestination(h C.uintptr_t, suggested, mime *C.char) *C.char {
	return safeStr(func() string { return ctl(h).DownloadDestination(C.GoString(suggested), C.GoString(mime)) })
}

//export goDownloadFinished
func goDownloadFinished(h C.uintptr_t, path *C.char) {
	safeDo(func() { ctl(h).DownloadFinished(C.GoString(path)) })
}

//export goURIChanged
func goURIChanged(h C.uintptr_t, uri *C.char) C.int {
	return safe(0, func() C.int { return C.int(ctl(h).URIChanged(C.GoString(uri))) })
}

//export goLoadFinished
func goLoadFinished(h C.uintptr_t, uri *C.char) {
	safeDo(func() { ctl(h).LoadFinished(C.GoString(uri)) })
}

//export goLoadFailed
func goLoadFailed(h C.uintptr_t, uri, message *C.char, tls C.int) *C.char {
	return safeStr(func() string { return ctl(h).LoadFailed(C.GoString(uri), C.GoString(message), tls != 0) })
}

//export goProcessTerminated
func goProcessTerminated(h C.uintptr_t, reason C.int) C.int {
	return safe(0, func() C.int { return b2i(ctl(h).ProcessTerminated(int(reason))) })
}

//export goCloseRequest
func goCloseRequest(h C.uintptr_t, w, hgt, maximized C.int, zoom C.double) {
	safeDo(func() { ctl(h).CloseRequest(int(w), int(hgt), maximized != 0, float64(zoom)) })
}

//export goStartup
func goStartup(h C.uintptr_t) { safeDo(func() { ctl(h).Startup() }) }

//export goShutdown
func goShutdown(h C.uintptr_t) { safeDo(func() { ctl(h).Shutdown() }) }

//export goOpen
func goOpen(h C.uintptr_t, uri *C.char) { safeDo(func() { ctl(h).Open(C.GoString(uri)) }) }

//export goSignal
func goSignal(h C.uintptr_t, signo C.int) { safeDo(func() { ctl(h).Signal(int(signo)) }) }

//export goThemeChanged
func goThemeChanged(h C.uintptr_t) { safeDo(func() { ctl(h).ThemeChanged() }) }

//export goIdle
func goIdle(h C.uintptr_t) { safeDo(func() { ctl(h).Idle() }) }
