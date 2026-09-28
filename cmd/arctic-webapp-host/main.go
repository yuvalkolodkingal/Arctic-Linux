//go:build cgo && webkit

// Command arctic-webapp-host is one web app's window (docs/BUILD-SPEC.md §11): a
// GtkApplication whose id is the app's id, an Arctic header bar and a WebKitWebView with the
// app's own network session. Only `arctic-webapp run` starts it:
//
//	arctic-webapp-host --app-id ID [--url URL] [--inspect] [--notice runtime-missing]
//	arctic-webapp-host --version
//
// Every decision is made in pure Go (internal/webapp/policy); the C shim in internal/webkit
// only reports facts and applies answers.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"runtime"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webkit"
)

// GTK and the GLib main loop run on the main thread.
func init() { runtime.LockOSThread() }

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	fs := flag.NewFlagSet("arctic-webapp-host", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	id := fs.String("app-id", "", "")
	openURL := fs.String("url", "", "")
	inspect := fs.Bool("inspect", false, "")
	notice := fs.String("notice", "", "")
	version := fs.Bool("version", false, "")
	if err := fs.Parse(args); err != nil || fs.NArg() > 0 {
		fmt.Fprintln(os.Stderr, "usage: arctic-webapp-host --app-id ID [--url URL] [--inspect] | --version")
		return 2
	}
	if *version {
		// Before any GTK call: without a display webkit_settings_new() would abort.
		fmt.Printf("arctic-webapp-host %s (WebKitGTK %s)\n", webapp.Version, webkit.Version())
		return 0
	}
	c, err := newController(*id, *openURL, *inspect, *notice)
	if err != nil {
		fmt.Fprintf(os.Stderr, "arctic-webapp-host: %v\n", err)
		return 1
	}
	return c.run()
}
