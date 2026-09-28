package webapp

import "github.com/yuvalkolodkingal/o-tism/internal/protocol"

// Error codes shared by `serve` errors and the `code` of --json failures. The first group is
// internal/protocol's; the rest are the web-app engine's own.
const (
	CodeInvalid     = protocol.CodeInvalid
	CodeBadRequest  = protocol.CodeBadRequest
	CodeUnknown     = protocol.CodeUnknown
	CodeNotFound    = protocol.CodeNotFound
	CodeState       = protocol.CodeState
	CodeOffline     = protocol.CodeOffline
	CodeTimeout     = protocol.CodeTimeout
	CodeInternal    = protocol.CodeInternal
	CodeExists      = "exists"      // the site is already an app (use a second copy)
	CodeFetch       = "fetch"       // DNS or connect failed
	CodeHTTP        = "http"        // status >= 400
	CodeTLS         = "tls"         // certificate not trusted
	CodeTooLarge    = "too_large"   // a response went over its size limit
	CodeNotHTML     = "not_html"    // the address is not a web page
	CodeBusy        = "busy"        // the registry lock was held for more than 5 s
	CodeUnsupported = "unsupported" // runtime missing
)

// Errorf builds an engine error; every message is a sentence the UI can show as is.
func Errorf(code, format string, a ...any) *protocol.Error {
	return protocol.Errorf(code, format, a...)
}

// AsError turns any error into a *protocol.Error (internal when it is not one already).
func AsError(err error) *protocol.Error {
	if err == nil {
		return nil
	}
	if pe, ok := err.(*protocol.Error); ok {
		return pe
	}
	return &protocol.Error{Code: CodeInternal, Message: sentence(err.Error())}
}

// sentence makes a Go error readable in the UI: capital first letter, final full stop.
func sentence(s string) string {
	if s == "" {
		return "Something went wrong."
	}
	r := []rune(s)
	if r[0] >= 'a' && r[0] <= 'z' {
		r[0] -= 'a' - 'A'
	}
	s = string(r)
	switch s[len(s)-1] {
	case '.', '!', '?':
		return s
	}
	return s + "."
}
