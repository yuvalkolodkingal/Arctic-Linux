package manage

import (
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/api"
)

// Browser is one Chromium-family runtime: sites that need Widevine DRM or WebRTC calls, which
// Fedora's WebKitGTK does not have, run in it with a per-app --user-data-dir. catalog_test keeps
// this table in step with modules/browser/*/module.toml; the catalog itself is not read at run
// time (it belongs to arctic-installer, which is live-only).
type Browser struct {
	Variant string // chromium:<Variant>
	Name    string
	Module  string // catalog module id
	Command string // dnf: the binary; "" for Flatpak-only browsers
	Ref     string // Flatpak app id; "" for the dnf browser
	DRM     bool   // ships Widevine
}

// Browsers are the Chromium-family runtimes, in the order the preview offers them.
var Browsers = []Browser{
	{Variant: "brave", Name: "Brave", Module: "brave", Ref: "com.brave.Browser", DRM: true},
	{Variant: "chrome", Name: "Google Chrome", Module: "chrome", Ref: "com.google.Chrome", DRM: true},
	{Variant: "vivaldi", Name: "Vivaldi", Module: "vivaldi", Ref: "com.vivaldi.Vivaldi", DRM: true},
	{Variant: "chromium", Name: "Chromium", Module: "chromium", Command: "/usr/bin/chromium-browser"},
	{Variant: "ungoogled", Name: "Ungoogled Chromium", Module: "chromium", Ref: "io.github.ungoogled_software.ungoogled_chromium"},
}

// BrowserFor returns the table entry for "chromium:<variant>".
func BrowserFor(runtime string) (Browser, bool) {
	v, ok := strings.CutPrefix(runtime, "chromium:")
	if !ok {
		return Browser{}, false
	}
	for _, b := range Browsers {
		if b.Variant == v {
			return b, true
		}
	}
	return Browser{}, false
}

// Env is what runtime detection looks at; tests use a fake root.
type Env struct {
	Root    string // "" = /
	Home    string
	HostBin string // the WebKit host binary
}

func (e Env) path(p string) string {
	if e.Root == "" {
		return p
	}
	return filepath.Join(e.Root, p)
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// Available reports whether a runtime can run now.
func (e Env) Available(runtime string) bool {
	if runtime == "webkit" {
		return exists(e.HostBin)
	}
	b, ok := BrowserFor(runtime)
	if !ok {
		return false
	}
	if b.Command != "" {
		return exists(e.path(b.Command))
	}
	return e.flatpakInstalled(b.Ref)
}

func (e Env) flatpakInstalled(ref string) bool {
	if !exists(e.path("/usr/bin/flatpak")) {
		return false
	}
	for _, base := range []string{e.path("/var/lib/flatpak"), filepath.Join(e.Home, ".local/share/flatpak")} {
		if exists(filepath.Join(base, "app", ref, "current", "active")) {
			return true
		}
	}
	return false
}

// Runtimes lists every runtime and whether it is available (Hello, Runtimes).
func (e Env) Runtimes() []api.Runtime {
	rs := []api.Runtime{{ID: "webkit", Name: "Arctic", Available: e.Available("webkit")}}
	for _, b := range Browsers {
		r := api.Runtime{ID: "chromium:" + b.Variant, Name: b.Name, DRM: b.DRM, WebRTC: true}
		r.Available = e.Available(r.ID)
		if !r.Available {
			in := &api.RuntimeInstall{Module: b.Module, Method: "flatpak", Ref: b.Ref}
			if b.Command != "" {
				in = &api.RuntimeInstall{Module: b.Module, Method: "dnf"}
			}
			r.Install = in
		}
		rs = append(rs, r)
	}
	return rs
}

// Exec is a process to exec: path, argv and environment.
type Exec struct {
	Path string
	Argv []string
	Env  []string
}

// HostExec builds the WebKit host's command line and environment for `run`.
func HostExec(hostBin, id, openURL string, inspect bool, notice string, rendering string, environ []string, nvidia bool) Exec {
	argv := []string{"arctic-webapp-host", "--app-id", id}
	if openURL != "" {
		argv = append(argv, "--url", openURL)
	}
	if inspect {
		argv = append(argv, "--inspect")
	}
	if notice != "" {
		argv = append(argv, "--notice", notice)
	}
	return Exec{Path: hostBin, Argv: argv, Env: runtimeEnv(environ, rendering, nvidia)}
}

// runtimeEnv removes the WebKit sandbox kill switch (a web app always runs sandboxed), adds the
// NVIDIA workarounds unless you set them yourself, and software rendering when asked.
func runtimeEnv(environ []string, rendering string, nvidia bool) []string {
	var out []string
	set := map[string]bool{}
	for _, kv := range environ {
		k, _, _ := strings.Cut(kv, "=")
		if k == "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS" {
			continue
		}
		set[k] = true
		out = append(out, kv)
	}
	add := func(k, v string) {
		if !set[k] {
			out = append(out, k+"="+v)
			set[k] = true
		}
	}
	if nvidia {
		add("__NV_DISABLE_EXPLICIT_SYNC", "1")
		add("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
	}
	if rendering == "software" {
		add("WEBKIT_SKIA_ENABLE_CPU_RENDERING", "1")
		add("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
	}
	return out
}

// BrowserExec builds a Chromium-family --app command. The URL is always one argv element
// starting with http(s)://. Never --no-sandbox, --remote-debugging-port,
// --ignore-certificate-errors or --class (it does not set the Wayland app_id).
func BrowserExec(b Browser, p webapp.Paths, e Env, id, openURL string, environ []string) (Exec, bool) {
	u, err := url.Parse(openURL)
	if err != nil || (u.Scheme != "https" && u.Scheme != "http") || u.Host == "" {
		return Exec{}, false
	}
	common := []string{"--app=" + u.String(), "", "--no-first-run", "--no-default-browser-check"}
	env := runtimeEnv(environ, "auto", false)
	if b.Command != "" {
		common[1] = "--user-data-dir=" + p.ChromiumProfile(id)
		return Exec{Path: e.path(b.Command), Argv: append([]string{filepath.Base(b.Command)}, common...), Env: env}, true
	}
	common[1] = "--user-data-dir=" + p.FlatpakProfile(b.Ref, id)
	argv := append([]string{"flatpak", "run", "--branch=stable", b.Ref}, common...)
	return Exec{Path: e.path("/usr/bin/flatpak"), Argv: argv, Env: env}, true
}

// ChromiumWMClass is the app_id Chromium derives for an --app window:
// <prefix>-<host>__<path with / → _>-Default. The prefixes per brand and per Flatpak are the
// measured values; until measured the launcher entry uses the documented Chromium form.
func ChromiumWMClass(b Browser, startURL string) string {
	u, err := url.Parse(startURL)
	if err != nil {
		return ""
	}
	prefix := map[string]string{"brave": "brave", "chrome": "chrome", "vivaldi": "vivaldi", "chromium": "chromium", "ungoogled": "chromium"}[b.Variant]
	path := u.EscapedPath()
	if path == "" {
		path = "/"
	}
	return prefix + "-" + u.Host + "__" + strings.ReplaceAll(strings.TrimPrefix(path, "/"), "/", "_") + "-Default"
}

// NVIDIA reports the proprietary NVIDIA driver (its explicit sync and DMA-BUF renderer issues
// need the WebKit workarounds).
func NVIDIA() bool { return exists("/proc/driver/nvidia/version") }
