# Arctic Linux 0.3 — Web app engine (Go)

Part of the [0.3 plan](../PLAN-0.3.md).

Request #2: "we code a custom engine in Go to make any website into a web app". This section
also covers the web-app parts of #1 (Get apps → Web apps), #4 (Remove apps → Web apps), the
launcher, and the gap items `chromium-theme-policy`, `launch-or-focus` and `default-app-roles`
where they touch web apps. It ships in Arctic Linux 0.3.0 (D1) as the new subpackage
`arctic-webapps` (D4).

The design is the judged split engine in `research/engine-design.md` with every correction in
`research/engine-verdict.json` applied (listed in 3.1). Where this plan departs from
engine-design.md it says so in 3.2, with the reason.

🔍 marks a claim that still needs a hands-on check; each one names what proves it.

### 1. What ships

A **web app** is a website with its own launcher entry, icon, window, Wayland app_id and
signed-in profile, kept separate from your browser.

| Piece | Build | Job |
|---|---|---|
| `/usr/bin/arctic-webapp` (manager) | Go, standard library only, `CGO_ENABLED=0`, built in the existing `for cmd in …` loop | URL checks, discovery (HTML head, manifest, icons), icon rendering, registry, `.desktop` files, install / update / set / remove, the JSON-lines API `serve` for the shell, one-line `--json` output for Settings, and `run` (the `.desktop` Exec, which `syscall.Exec`s the right runtime). It never loads GTK or WebKit. |
| `/usr/libexec/arctic/arctic-webapp-host` (window) | Go + a hand-written C shim, cgo against Fedora's WebKitGTK 6.0, GTK 4 and libsoup 3. Every file starts with `//go:build cgo && webkit`. | One web app: a GtkApplication whose id is the app id, an Arctic header bar, a WebKitWebView with its own WebKitNetworkSession, and the navigation, popup, permission, notification, download, theme and crash hooks. Every decision is made in pure-Go policy packages. |
| Chromium-family runtime (per-app fallback) | none: an installed browser | `chromium-browser --app=…` or `flatpak run <ref> --app=…` with a per-app `--user-data-dir`, for sites that need Widevine DRM or WebRTC calls, which Fedora 44's WebKitGTK 2.54 does not have. |

Not in 0.3.0 (said on the wiki page and in the preview): background push while the window is
closed, manifest `shortcuts`/`protocol_handlers`/`file_handlers`/`share_target`, saved
passwords, a page ↔ native JavaScript bridge, Firefox/Zen/LibreWolf as runtimes (no `--app`
mode), preinstalled web apps (gap-list skipped them).

### 2. Current state

Nothing web-app related exists: `grep -rli 'webapp\|--app=' cmd internal shell settings
dotfiles packaging` finds nothing, and `research/arctic-inventory.json` lists "Web apps:
missing". The facts the design builds on:

**Go and build policy**
- `go.mod:1-3`: `module github.com/yuvalkolodkingal/o-tism`, `go 1.22`, no `require`. The
  language level is 1.22, so no range-over-func, no `os.Root`, no `encoding/json` `omitzero`,
  no `testing.T.Context`/`t.Chdir` (all ≥ 1.23/1.24), even though Fedora 44 builds with
  golang 1.26.8.
- Standard library only: `docs/wiki/Contributing.md:33`, `docs/BUILD-SPEC.md:72`,
  `docs/wiki/Architecture.md:30`, `README.md:50`, `docs/wiki/Building-from-Source.md:206`.
  Offline builds: `GOPROXY=off` at `packaging/arctic-linux.spec:496` and
  `.github/workflows/ci.yml:22`.
- No Go file has a build constraint or `import "C"` today (`grep -rln '//go:build\|import "C"'
  --include=*.go .` is empty).
- Two binaries: `cmd/arcticd`, `cmd/arctic-install`. CLI conventions in
  `cmd/arctic-install/main.go:1-81`: usage in the doc comment, subcommand switch, `fail()`
  prints `arctic-install: …` on stderr and returns 1, usage errors exit 2, `version` prints
  `backend.EngineVersion`.
- `backend.EngineVersion = "0.2.1"` (`internal/backend/backend.go:18`). `internal/backend`
  imports catalog, hw, protocol and wizard (`backend.go:6-15`), so the manager must not import
  it; a test keeps a separate constant in step.
- Wire protocol `internal/protocol/protocol.go`: envelope in the doc comment (`:1-11`),
  `Version = 1` (`:31`), `SecretMethods` (`:61`), error codes (`:68-78`), `Request`/`Response`/
  `Error` (`:81-100`), `Errorf`/`FieldErrors` (`:110-117`), snake_case wire names
  (`HelloResult`, `:126-128`). It imports only `encoding/json` and `fmt`, so the web-app API
  reuses its types.
- Test conventions: table-driven `testing`, goldens in `testdata/`
  (`cmd/arctic-install/main_test.go`), environment-gated tests (`ARCTIC_E2E_DEVICE`,
  `internal/installer/realdisk_test.go:17-28`). Embedded data: `modules/embed.go`
  (`//go:embed catalog.toml */*/module.toml`), loaded by `catalog.Load(fs.FS)`
  (`internal/catalog/catalog.go:315`) with the repo's own TOML parser (`internal/toml`).

**Spec, CI, ISO**
- `packaging/arctic-linux.spec`: header list `:7-27`; `:32` "Go binaries are built with the Go
  linker (CGO_ENABLED=0); no separate debuginfo." and `:33` `%global debug_package %{nil}`;
  `ExclusiveArch: x86_64` `:45`; `BuildRequires: golang >= 1.22` `:47`, `librsvg2-tools` `:48`,
  `desktop-file-utils` `:52`; no gcc or pkgconfig BuildRequires.
- `mangowm >= 0.17.1` at `:160` (arctic-desktop-config), `:338` (sddm-wayland-mango), `:417`
  (arctic-desktop). `packaging/mangowm.spec:12` builds 0.17.3.
- arctic-shell `:240-257` (noarch); arctic-installer `:290-330` (the only x86_64 subpackage);
  arctic-desktop `:402-482` (already Requires `xdg-desktop-portal-gtk` `:444`, `xdg-utils`
  `:446`, `librsvg2-tools` `:448`).
- `%build` `:493-507`: `export GOTOOLCHAIN=local CGO_ENABLED=0 GOPROXY=off
  GOFLAGS="-buildmode=pie -trimpath"`, loop `for cmd in arcticd arctic-install` at `:501-503`.
- `%install` `:744`: `install -pm 0755 _build/bin/arcticd _build/bin/arctic-install …`.
- `%check` `:825-832` loops over `%{buildroot}%{_libexecdir}/arctic/*` and runs `bash -n` on
  every file whose first line is not python. `bash -n` on an ELF file exits 126 and `%check`
  runs under `sh -e`, so **an ELF binary in `/usr/libexec/arctic` fails every build** until the
  loop skips ELF files. `mango -c … -p` validates the skel config only when mango is installed
  in the build root (`:884-897`).
- `%files` arctic-shell `:1124-1130`, arctic-installer `:1141-1153`, arctic-desktop `:1185`;
  `%changelog` `:1188`.
- `tools/build-rpms.sh:232` runs `dnf -y builddep`, so new BuildRequires install themselves.
- `.github/workflows/ci.yml`: job `go` `:16-39` (fedora:44 container, `CGO_ENABLED: "0"` at
  `:24`, installs `git golang`, runs `go vet ./...` and `go test ./...`); `shellcheck` `:41-63`
  (file list `:52-54`); `shell-tests` `:65-97` (runs every `shell/tests/*.cjs`); `qml`
  `:129-148` (qmllint over every `*.qml`); `settings-headless` `:150-168`; `specs` `:170-183`;
  `rpms` `:185-212`.
- `iso/kiwi/config.kiwi:58` `patternType="plusRecommended"`; `:65` arctic-desktop; `:66-72`
  arctic-settings "named so it is never left out" plus its tools. `LiveOnlyPackages`
  (`internal/installer/installer.go:39`) does not list any new package, so `arctic-webapps`
  stays on installed systems. The ISO must stay within GitHub's 2 GiB asset limit or
  `--zen auto` drops preinstalled Zen (`docs/wiki/Building-from-Source.md:109-111`).

**Desktop pieces the engine plugs into**
- Launcher: `shell/Launcher.qml:57-61` maps every `DesktopEntries.applications` entry, so a new
  `~/.local/share/applications/*.desktop` shows up by itself; the second line is
  `e.genericName || e.comment` (`:59`); `tile: Icons.tileFor(e.id, e.name)` (`:61`).
  `Icons.tileFor` (`shell/assets/Icons.js:73-77`) lowercases `id + ' ' + name` and tests it
  against `TILE_MATCH` (`:61-71`: `/settings/`, `/signal/`, `/steam/`, `/chromium/` …), so a
  web app named "Signal" or "Steam" would get that app's design tile. `AppTile.qml:16` resolves
  other icons with `Quickshell.iconPath(iconName, true)` and draws them at 67% inside a
  30%-radius tile (`AppTile.qml:18-39`).
- Get apps: `Launcher.qml:131-137` embeds `InstallConsole.qml` directly; its description is
  "Install apps with dnf or Flatpak" (`Launcher.qml:51`). The console drives
  `shell/scripts/install-terminal.py` with `Process{stdinEnabled:true, stdout: SplitParser}`
  (`InstallConsole.qml:81-105`), the pattern the web-app page reuses.
- Settings: `settings/Backend.qml:95` always runs `python3 arctic_settings.py <args>`, reads the
  whole stdout with one `StdioCollector` and `JSON.parse`, and treats any result whose `ok` is
  not true as a failure, showing `result.error` as a sentence (`:111-127`). Default-app roles
  are `ROLES` at `settings/scripts/arctic_settings.py:1790-1804` (browser `keys='Super + W'`
  at `:1793`; no mailto role); `desktop_dirs` (`:1734-1741`) includes
  `~/.local/share/applications`; tool detection is `TOOLS` (`:2519-2524`) + `cmd_caps`.
- Mango: `dotfiles/.config/mango/arctic/rules.conf` (43 lines) has no web-app rule.
  `activation_bypass` is a key Mango 0.17.3 parses (`settings/tests/mango-0.17.3-keys.txt:6`;
  the list is generated from `src/config/parse_config.c` and includes window-rule keys such as
  `appid` `:28` and `isfloating` `:135`).
- Launch-or-focus precedent: `dotfiles/.local/bin/arctic-settings:48-59` uses
  `mmsg get all-clients` and `mmsg dispatch focusid "client,$id"`.
- Browser keys: `dotfiles/.config/mango/arctic/apps.conf:7` `bind=SUPER,w,spawn,arctic-open
  browser` (D7 moves it to Super+B); screenshots `binds.conf:82-84`.
- Theme: `~/.config/arctic/current` → `themes/<name>`; `theme.json` colours are QML
  `#AARRGGBB`; `shell/Theme.qml:140-157` watches `~/.config/arctic/theme`, which `arctic-theme`
  rewrites after every switch. GTK 4 apps already get Arctic radii, focus ring and
  `@arctic_*` colours from `dotfiles/.config/gtk-4.0/gtk.css` (imports `arctic-colors.css`),
  and `dotfiles/.config/gtk-4.0/settings.ini:5-6` sets `gtk-font-name=Figtree 11` and
  `gtk-decoration-layout=:`.
- Browser modules: `modules/browser/chromium/module.toml` (dnf `chromium`, command
  `chromium-browser`; Flatpak `io.github.ungoogled_software.ungoogled_chromium`),
  `brave` (`com.brave.Browser`), `chrome` (`com.google.Chrome`), `vivaldi`
  (`com.vivaldi.Vivaldi`), all Flatpak only.
- Design: `design/brand-book.md:7` "Amber means 'here' … never decoration, never a category
  colour"; `:46` the amber allow-list; `:103` app tiles (30% radius, category tint, one `ink`
  glyph); `design/tokens.json` marks `aurora-1..3` "Welcome, splash, wallpapers only";
  `shell/assets/design-data.js:269` `TINTS`.

### 3. Decisions applied

#### 3.1 engine-verdict.json corrections, and where each lands

| # | Correction | Applied in |
|---|---|---|
| C1 | `activation_bypass` is verified for Mango 0.17.3; raise `mangowm >= 0.17.3` where the rule ships | 7.3, 11.1 (spec `:160`, `:417`; `:338` too for consistency), rules.conf line in 10.5 |
| C2 | snake_case on the wire, never camelCase | every JSON shape in 5 and 6 (`final_url`, `manifest_url`, `name_source`, `keep_data`, `extra_domains` …); `api_test.go` pins the names |
| C3 | `--json` prints `{"ok":true,…}` or `{"ok":false,"code":…,"error":"<sentence>","fields":{…}}` | 6.2 |
| C4 | No progress lines in `--json` mode; progress events only in `serve` | 6.2, 6.3 |
| C5 | No amber in monograms (brand-book.md:7, :46) | 7.9; `monogram_test` asserts no amber-family value |
| C6 | The manager is a dynamically linked PIE with zero DT_NEEDED, not "static" | 11.1 `%check` asserts `! readelf -d … \| grep -q NEEDED` on `arctic-webapp` |
| C7 | Untagged `.c`/`.h`/`doc.go` are silently accepted by Go 1.24+; the real hazard is an untagged Go file in `cmd/arctic-webapp-host` | 4.3 rule + `buildtag_test.go` source scan (13.1) |
| C8 | Scope is enforced only on `LINK_CLICKED` and on `OTHER` with a user gesture (Epiphany); redirects, script navigations and form posts stay in the app | 8.5 navigation table; `navigate_test.go` |
| C9 | `tileFor` skip prefix: lowercase inside `Icons.js`, exact case on `e.id` in `Launcher.qml` | 10.3 |
| C10 | Never copy a WebKit user-agent literal; pin `FetchUserAgent` from `webkit_settings_get_user_agent()` in the smoke test | 7.2, 13.4 |
| C11 | Favicon APIs are deprecated in 2.54: `-Wno-deprecated-declarations`, or a `webkit_get_minor_version() >= 54` branch for `page-icons` | 4.3 (`#cgo CFLAGS`), 8.11 (both; see D-4 for the link-time trap) |
| C12 | `webkit_network_session_set_memory_pressure_settings` is a type function: global, called once before any session | 8.4 |
| C13 | `--class` does not set the Wayland app_id; never pass it; measure `StartupWMClass` | 8.14 |
| C14 | Do not Recommend gstreamer plugins again (webkitgtk6.0 already Recommends them) | 11.1 subpackage has no such line |

Also from the grafts, kept as designed: deterministic 6-hex SHA-256 id (reinstall keeps
sign-in), private-address guard in `net.Dialer.Control`, pinned TLS exceptions for private
hosts only, SIGHUP live reload, PSL matcher over Fedora's `publicsuffix-list`, login-wall
probes, typed deep URL as start_url, `render-sample` in `%check`, the catalog cross-check test,
never `flatpak kill`.

#### 3.2 Where this plan departs from engine-design.md

| # | Change | Reason |
|---|---|---|
| D-1 | `webapp.Version = "0.3.0"` (design: 0.2.1) | D1. `version_test.go` keeps it equal to `backend.EngineVersion`, which the 0.3.0 bump raises. |
| D-2 | Monograms use the brand book's app-tile tints by category with an `ink` letter (7.9), not aurora/slate/info/success fills and not the site's theme colour | D9 (colours only from tokens, used as the tokens say): `tokens.json` limits `aurora-*` to welcome, splash and wallpapers; `brand-book.md:103` defines app tiles. Still no amber (C5). |
| D-3 | The `site_colour` option (tint the header from the page's `theme-color`) is dropped; `theme_color` is stored for information only | D9: a site colour in Arctic chrome is not a token. |
| D-4 | `Requires: webkitgtk6.0 >= <version compiled against>` instead of a fixed `>= 2.50`; 2.54-only features reached by GObject property name, never by a new symbol | The host links with `-z now` (BIND_NOW, verified in the prototype). A direct call to a 2.54-only symbol makes the host fail to start on 2.52, whatever runtime check guards it. Reaching new features by property name keeps the same source building and running against 2.50–2.52 (F44 shipped 2.52.x earlier), so the floor can be lowered later without code changes. |
| D-5 | The pid file is written only by the primary instance (GApplication `startup`), or by `run` for a Chromium runtime only when no live pid is recorded | With the design's "host writes `<id>.pid`", a second start (which forwards `activate` and exits) would overwrite the running app's pid. |
| D-6 | Web apps may handle `mailto:` links, but only by explicit user choice and only for sites in an Arctic table (8.15) | Gap item `default-app-roles` asks for mail web apps as the email role; the design's rule "nothing a site declares becomes a handler" still holds, since the table is Arctic's and the user opts in. |
| D-7 | Settings calls go through new `arctic_settings.py` subcommands, not straight argv | `Backend.qml:95` always runs the Python helper. The helper passes the one-line JSON through. |
| D-8 | Chromium-runtime apps get launch-or-focus through `mmsg` (8.3) | Gap item `launch-or-focus`; Chromium opens a second `--app` window on every start. |
| D-9 | New `--icon-url URL` (and "Use an icon from the web" in the preview) | Omarchy parity: Omarchy asks for an icon URL when discovery fails. |
| D-10 | The smoke test checks notifications with `dbus-monitor`, not `makoctl` | D6: the Quickshell session's notification server replaces mako, so the test must not depend on which daemon runs. |
| D-11 | Host chrome uses Adwaita symbolic icon names; no new drawn icons | GTK apps on Arctic use Adwaita icons (BUILD-SPEC §3.1 "Icons"). D9's "draw new icons in the design-data.js style" does not apply; the shell pages use existing glyphs (`globe`, `trash`, `alert`, `lock`, `external`, `refresh`). |
| D-12 | Category choice "Calendar" writes `Categories=Office;Calendar;X-Arctic-WebApp;` | Gap item `default-app-roles` adds a calendar role (Categories=Calendar). |
| D-13 | The Remove apps sheet keeps sign-in data unless you tick "Also delete sign-in data" | Same default as the Flatpak tab's "Also delete this app's settings and data" (off). The CLI keeps the design's default (`remove` deletes; `--keep-data` keeps). Kept data is always listed under "Saved sign-in data". |

### 4. Components

#### 4.1 Installed files

| Path | Package | Notes |
|---|---|---|
| `/usr/bin/arctic-webapp` | arctic-webapps | Pure-Go PIE, `-trimpath`, `-B gobuildid`, no DT_NEEDED. On `PATH`: Exec/TryExec, the shell and Settings call it. |
| `/usr/libexec/arctic/arctic-webapp-host` | arctic-webapps | cgo PIE, BIND_NOW, linked externally with `%{build_ldflags}`. Only `arctic-webapp run` executes it. Dev override: `ARCTIC_WEBAPP_HOST=/path` (read by `run` only). |
| `/usr/libexec/webkitgtk-6.0/WebKit{Web,Network,GPU}Process` | webkitgtk6.0 | Spawned by WebKit inside bubblewrap; never exec'd by us. |
| `/usr/bin/rsvg-convert` | librsvg2-tools | SVG icons and monograms → PNG; argv only, SVG on stdin, 5 s timeout. |
| `/usr/share/publicsuffix/public_suffix_list.dat` | publicsuffix-list | eTLD+1 data for the pure-Go PSL matcher. |
| `/usr/bin/chromium-browser`, `/usr/bin/flatpak` | chromium, flatpak | Only for apps whose runtime is `chromium:<variant>`. |
| `rules.conf` line `windowrule=activation_bypass:1,appid:^org\.arcticlinux\.WebApp\.` | arctic-desktop-config | 10.5 |

No file in `dotfiles/.local/bin`, so the `grep -vxE` exclusion at spec `:702` does not change.

#### 4.2 Processes

```
Get apps / Remove apps (QML) ── WebAppService: Process{['arctic-webapp','serve']} JSON lines ─┐
Arctic Settings ── python3 arctic_settings.py webapp-* ── argv: arctic-webapp … --json ────────┤
Launcher row Delete ── app-owner.py → WebAppService.remove ────────────────────────────────────┤
                                                                                                ▼
                     arctic-webapp (pure Go; never loads GTK/WebKit)
                     discover → icon → registry (flock) → .desktop + hicolor icons
                                                                                                │
Launcher: DesktopEntry.execute() → Exec=arctic-webapp run <id> [%u for mail apps]
   validate id, shared lock, read app.json, build env, syscall.Exec (same PID, no shell)
   ├─ runtime "webkit":    /usr/libexec/arctic/arctic-webapp-host --app-id <id> [--url U]
   │     GtkApplication(<id>) → xdg_toplevel app_id <id>; second start → D-Bus activate → present
   │     └─ WebKitWebProcess / NetworkProcess / GPUProcess (bubblewrap)
   └─ runtime "chromium:<v>": running? → mmsg focus : chromium-browser --app=… | flatpak run <ref> --app=…
```

- Only the manager writes `app.json`, `.desktop` files and icons, always under the registry
  lock. The host reads `app.json` and writes only `state.json`, `permissions.json`, its log
  and `<id>.pid`.
- For a favicon upgrade or a trusted certificate the host execs `arctic-webapp icon …` or
  `arctic-webapp trust-certificate …` with an argv; "Web app settings…" in the host menu
  spawns `arctic-settings webapps` (argv, detached). The host runs nothing else.

#### 4.3 The cgo boundary

- cgo lives only in `internal/webkit/` and `cmd/arctic-webapp-host/`. **Every** file there,
  `shim.c`, `shim.h` and tests included, starts with `//go:build cgo && webkit`. There is no
  untagged `doc.go`: in `cmd/` it would make a `package main` with no `main` (C7).
- `webkit.go`: `#cgo pkg-config: webkitgtk-6.0 gtk4 libsoup-3.0` and
  `#cgo CFLAGS: -std=gnu11 -Wall -Wno-deprecated-declarations` (C11).
- A plain `go build ./cmd/arctic-webapp-host` without `-tags webkit` fails with "build
  constraints exclude all Go files", so no stub binary can ship; `%check` also asserts the
  NEEDED entry (11.1).
- `./...` skips the tagged packages under `CGO_ENABLED=0`, and under `CGO_ENABLED=1` without
  the tag, so developer machines without WebKit headers still run `go test ./...` (verified
  with Go 1.24.7 and 1.26.8).

Go → C (main thread only):

| C function | Does |
|---|---|
| `int arctic_run(const ArcticConfig *cfg, int argc, char **argv)` | `gtk_application_new(id, G_APPLICATION_HANDLES_OPEN)`, `g_set_application_name`, `g_application_run` (argv stripped of our own flags) |
| `const char *arctic_webkit_version(void)` | `webkit_get_{major,minor,micro}_version`; display-free |
| `char *arctic_base_domain(const char *host)` | `soup_tld_get_base_domain`; used only by the tagged PSL parity test |
| `void arctic_set_theme(const char *css, int dark, const char *ground)` | `gtk_css_provider_load_from_string` (GTK ≥ 4.12) at APPLICATION priority; GtkSettings `gtk-interface-color-scheme` set by property name (GTK ≥ 4.20; F44 has 4.22.5); `webkit_web_view_set_background_color` |
| `void arctic_banner(uintptr_t win, int kind, const char *text, const char *primary, const char *secondary, uintptr_t token)` | In-window banner (GtkRevealer under the header) |
| `void arctic_open_external(uintptr_t win, const char *uri)` | `gtk_uri_launcher_launch` (GTK ≥ 4.10) |
| `void arctic_load(uintptr_t view, const char *uri)`, `void arctic_load_alternate_html(uintptr_t view, const char *html, const char *uri)` | Navigation and Arctic error pages |
| `void arctic_permission_reply(uintptr_t req, int allow)`, `void arctic_download_set(uintptr_t dl, const char *path)` | Finish async decisions; the shim holds a ref until then |
| `void arctic_send_notification(const char *tag, const char *title, const char *body, const char *icon, uintptr_t wknotif)` | `GNotification` + `g_application_send_notification` |
| `void arctic_allow_certificate(const char *host, const char *pem)` | `webkit_network_session_allow_tls_certificate_for_host`, only for a stored, confirmed exception |
| `void arctic_reload_config(const ArcticConfig *cfg)` | Applies options live (zoom, devtools, links, notification seeds, TLS exceptions) |
| `void arctic_idle(uintptr_t handle)` | `g_idle_add` trampoline back to `goIdle` |

C → Go (`//export` in `internal/webkit/exports.go`; the preamble has declarations only):
`goDecidePolicy(h, decisionType, uri, navType, userGesture, mainFrame, modifiers, button) int`
(USE / IGNORE / EXTERNAL / POPUP), `goDecideResponse(h, uri, mime, canShow, attachment) int`,
`goPermission(h, win, kind, origin, req) int` (ALLOW / DENY / ASK),
`goQueryPermission(h, origin, kind) int`, `goNotification(h, title, body, origin, id)`,
`goDownloadDestination(h, suggested, mime) *C.char`, `goDownloadFinished(h, path, ok)`,
`goTitle`, `goURI`, `goLoad`, `goLoadFailed(h, win, uri, domain, code, tls) *C.char` (escaped
error-page HTML), `goProcessTerminated(h, win, reason)`, `goFavicon(h, png, len)`,
`goThemeFileChanged(h)`, `goSignal(h, signo)`,
`goCloseRequest(h, win, w, hgt, maximized, zoom)`, `goIdle(h)`.

Rules:
- Only C strings (freed by whoever allocated them), ints and `uintptr_t` from
  `runtime/cgo.Handle` cross. C never keeps a Go pointer.
- Every export recovers panics and returns the safe default (deny, ignore, error page).
- `init(){ runtime.LockOSThread() }` in the host: `main` and the GLib loop run on the main
  thread. Goroutines (file I/O, PNG work) never call GTK; they post back with `arctic_idle`.
  Timers are GLib timeouts.
- SIGTERM, SIGINT, SIGHUP go through `g_unix_signal_add`, never `os/signal`. JavaScriptCore
  uses SIGUSR1; Go must never touch it.
- Only `arctic_run` initialises GTK. `--version` runs before any GTK call (without a display
  `webkit_settings_new` asserts and crashes).
- The shim holds no policy.
- 2.54-only features (the `page-icons` property, `WebKitImage`) are reached by property name
  through `g_object_get`/`g_signal_connect(… "notify::page-icons" …)` and the GIO
  `GLoadableIcon` interface, never by calling a symbol that 2.50/2.52 lack (D-4). A tagged test
  lists the host's undefined `webkit_*` symbols (`nm -D --undefined-only`) and compares them
  with a checked-in allowlist, so a new WebKit symbol is a deliberate change.

### 5. Go package layout

```
cmd/arctic-webapp/                  pure Go CLI (CGO_ENABLED=0)
  main.go        doc comment with usage; subcommand switch; flag.NewFlagSet(ContinueOnError);
                 "arctic-webapp: …" on stderr; exit 0/1/2; refuses root (os.Geteuid()==0 → 1)
  run.go         run (Exec target: syscall.Exec runtime), launch (Setsid-detached run)
  serve.go       JSON-lines server (internal/protocol envelope)
  sample.go      render-sample DIR (offline fixture render for %check)
  main_test.go   golden CLI tests; testdata/*.json
internal/webapp/                    core, no network (manager AND host import it)
  doc.go         package doc citing BUILD-SPEC §11 "Web apps"
  version.go     Version = "0.3.0"; version_test.go asserts == backend.EngineVersion
  app.go         App (app.json schema 1), Options, Icon, TLSException, Validate, Migrate, RenderVersion
  id.go          NewID(name, identity, copyN, taken) · Valid (GLib rules + Arctic grammar)
  paths.go       XDG_DATA/CACHE/STATE_HOME, XDG_RUNTIME_DIR (HOME fallbacks); per-app paths from a valid id
  registry.go    Load/Save (temp + fsync + rename, 0600), List, Kept, migration
  lock.go        syscall.Flock on $XDG_DATA_HOME/arctic/webapps/.lock (shared read / exclusive write; 5 s → busy)
  desktop.go     Entry.Marshal (exact key order, escaping) + ParseEntry (repair, orphans)
  running.go     $XDG_RUNTIME_DIR/arctic-webapp/<id>.pid + /proc/<pid>/cmdline check; Signal(id, sig); Stop(id, 3 s)
  safe.go        RemoveTree(root, id): valid id, path under root after Clean, Lstat (no symlinked dir)
  buildtag_test.go  every .go/.c/.h under internal/webkit and cmd/arctic-webapp-host starts with the tag (C7)
  rules_test.go  rules.conf has the activation_bypass line and its regex matches NewID output
  testdata/desktop/*.desktop
internal/webapp/psl/                pure Go Public Suffix List matcher (rules, wildcards, exceptions; ASCII hosts)
  psl.go         Load(path) · Site(host) (eTLD+1; IP / localhost → exact host)
  testdata/public_suffix_list.dat   fixture; tests never need the system file
internal/webapp/discover/           manager only
  normalize.go fetch.go htmlhead.go charset.go manifest.go name.go loginwall.go candidates.go
  compat.go (+ compat.json via go:embed) category.go fuzz_test.go testdata/sites/<name>/…
internal/webapp/icon/               manager only
  sniff.go ico.go svg.go resample.go tile.go monogram.go write.go (+ tests, testdata)
internal/webapp/manage/             manager only
  inspect.go (preview tokens, 1 h expiry) install.go update.go set.go remove.go runtime.go launch.go
  focus.go (mmsg launch-or-focus) handlers.go (+ handlers.json via go:embed)
  catalog_test.go (runtime table ↔ modules/browser/*/module.toml through modules.FS + catalog.Load)
internal/webapp/policy/             host decisions (pure Go)
  scope.go navigate.go permissions.go downloads.go crash.go tls.go (private-host check)
internal/webapp/theme/              theme.json (QML #AARRGGBB) → Palette; HostCSS (golden)
internal/webapp/api/                serve methods, params/results, events, error codes; api_test pins wire names
internal/webkit/                    //go:build cgo && webkit (every file)
  shim.h shim.c (≈1,000–1,500 lines C) webkit.go exports.go idle.go webkit_test.go symbols.allow
cmd/arctic-webapp-host/             //go:build cgo && webkit (every file)
  main.go controller.go smoke_test.go testdata/site/ dev/smoke.sh
```

`internal/webapp/**` and `cmd/arctic-webapp` need no cgo and run in the unchanged `go` job.
`internal/webkit` and `cmd/arctic-webapp-host` run only in the new `go-webkit` job (12).
`go.mod` does not change.

### 6. Data formats and commands

#### 6.1 On-disk data

All of it is per user. Nothing needs root, pkexec or polkit.

**App id** (GApplication id = Wayland app_id = `.desktop` basename = `StartupWMClass` for
the WebKit runtime = D-Bus name = first icon name):
- `org.arcticlinux.WebApp.<Slug>_<hash>`, grammar
  `^org\.arcticlinux\.WebApp\.[A-Za-z][A-Za-z0-9]{0,31}_[0-9a-f]{6,8}$`. It passes
  `g_application_id_is_valid`; no `-` (GLib discourages it and it breaks object paths).
- Slug: ASCII letters and digits of the name in CamelCase (`YouTube Music` → `YouTubeMusic`);
  if empty, the site label title-cased (`walla.co.il` → `Walla`), else `App`; a leading digit
  gets the prefix `App`.
- Hash: first 6 hex digits of SHA-256 over the canonical identity (manifest `id` if present,
  else start_url without its fragment). `--new-copy` appends `#2`, `#3`, … for a second
  account. If a different identity holds that id, 8 digits. Deterministic, so reinstalling a
  site after `remove --keep-data` gets the same id and the same profile.
- Icon names: `<id>` on install, `<id>.r<N>` after each icon change (sidesteps Qt's per-name
  QIcon cache and stale caches). Old files are deleted, `Icon=` is rewritten atomically, and the
  manager `Chtimes` the `hicolor` directory and each size directory.

**Paths**

| What | Path | Mode | Writer |
|---|---|---|---|
| Registry lock | `$XDG_DATA_HOME/arctic/webapps/.lock` | 0600 | manager |
| App record | `…/webapps/<id>/app.json` | dir 0700, file 0600 | manager |
| Kept record | `…/webapps/<id>/app.removed.json` (after `remove --keep-data`) | 0600 | manager |
| Source icon | `…/webapps/<id>/icon.png` (≤ 512 px, for re-rendering) | 0600 | manager |
| Window state | `…/webapps/<id>/state.json` | 0600 | host |
| Permissions | `…/webapps/<id>/permissions.json` | 0600 | host (manager deletes it on `--reset-permissions`) |
| WebKit profile | `…/webapps/<id>/profile/` (cookies.sqlite, localStorage, IndexedDB, service workers, favicons) | 0700 | WebKit |
| WebKit cache | `$XDG_CACHE_HOME/arctic/webapps/<id>/` | 0700 | WebKit |
| Chromium profile, dnf browser | `…/webapps/<id>/chromium/` | 0700 | browser |
| Chromium profile, Flatpak browser | `~/.var/app/<ref>/data/arctic-webapps/<id>/` (the sandbox's writable place) | 0700 | browser |
| Launcher entry | `$XDG_DATA_HOME/applications/<id>.desktop` | 0644 | manager |
| Icons | `$XDG_DATA_HOME/icons/hicolor/{48x48,64x64,128x128,256x256,512x512}/apps/<icon>.png` | 0644 | manager |
| Log | `$XDG_STATE_HOME/arctic/webapps/<id>.log` (1 MiB, one rotation; URLs without query or fragment) | 0600 | host |
| Runtime files | `$XDG_RUNTIME_DIR/arctic-webapp/` (0700): `<id>.pid`, `inspect-<token>/`, `<id>-favicon.png`, `<id>-cert.pem` | 0700 | host / manager |

Writes are atomic (temp file in the same directory, fsync, rename). No `scalable/` SVG is ever
installed.

**`app.json` (schema 1)**

```json
{
  "schema": 1, "render": 1, "engine_version": "0.3.0",
  "id": "org.arcticlinux.WebApp.YouTubeMusic_4c1a9e", "copy": 1,
  "name": "YouTube Music", "name_source": "manifest",
  "input_url": "music.youtube.com",
  "start_url": "https://music.youtube.com/?source=pwa",
  "manifest_url": "https://music.youtube.com/manifest.webmanifest",
  "manifest_id": "https://music.youtube.com/?source=pwa",
  "scope": { "site": "youtube.com", "scheme": "https", "manifest": "https://music.youtube.com/" },
  "extra_domains": [],
  "category": "AudioVideo",
  "theme_color": "#0f0f0f",
  "icon": { "name": "org.arcticlinux.WebApp.YouTubeMusic_4c1a9e", "rev": 0, "source": "manifest",
            "url": "https://music.youtube.com/img/favicon_512.png", "sha256": "…", "purpose": "any" },
  "runtime": "webkit",
  "wm_class": "org.arcticlinux.WebApp.YouTubeMusic_4c1a9e",
  "handlers": [],
  "options": { "links": "browser", "notifications": "allow", "devtools": false, "rendering": "auto" },
  "tls_exceptions": [],
  "user_set": [],
  "created": "2026-09-28T12:00:00Z", "updated": "2026-09-28T12:00:00Z"
}
```

- `name_source` / `icon.source`: `manifest | apple-touch | link | favicon-ico | svg |
  host-favicon | monogram | title | meta | host | user | url`.
- `category`: one of `Network AudioVideo Game Office Development Education Graphics Utility
  Calendar` (`Calendar` is written as `Office;Calendar`, D-12).
- `runtime`: `webkit | chromium:<variant>`; `wm_class` is the id for `webkit` and the measured
  Chromium app_id otherwise (8.14).
- `handlers`: `[] | ["mailto"]` (8.15).
- `options.links`: `browser | app`; `options.notifications`: `allow | ask | block`;
  `options.rendering`: `auto | software`.
- `tls_exceptions[]`: `{"host":"ha.lan:8123","sha256":"…","pem":"-----BEGIN…"}`, private-network
  hosts only (8.12).
- `user_set` lists fields you edited; `update` never overwrites them.
- `Validate` rejects the file if `id` does not match its directory, a URL is not http(s), a
  value is unknown, or a TLS exception names a public host. A tampered registry cannot inject
  Exec arguments or reach outside its directory.
- When `render` is older than `webapp.RenderVersion`, the next `run` re-renders that app's
  `.desktop` and icons, and `list`/`serve` re-render all of them under the exclusive lock. RPM
  scriptlets never touch home directories.

`state.json`: `{"schema":1,"width":1200,"height":800,"maximized":false,"zoom":1.0,"last_url":"https://…","last_used":"2026-09-28T12:00:00Z"}`.

`permissions.json`: `{"schema":1,"origins":{"https://music.youtube.com":{"notifications":"allow","camera":"deny","microphone":"deny","geolocation":"deny","clipboard":"allow"}}}`.

**`.desktop` (exact keys, in this order)**

```ini
[Desktop Entry]
Type=Application
Version=1.5
Name=YouTube Music
Comment=Web app · music.youtube.com
Exec=arctic-webapp run org.arcticlinux.WebApp.YouTubeMusic_4c1a9e
TryExec=arctic-webapp
Icon=org.arcticlinux.WebApp.YouTubeMusic_4c1a9e
Terminal=false
StartupNotify=true
StartupWMClass=org.arcticlinux.WebApp.YouTubeMusic_4c1a9e
SingleMainWindow=true
Categories=AudioVideo;X-Arctic-WebApp;
Keywords=web;app;music.youtube.com;
X-Arctic-WebApp-Id=org.arcticlinux.WebApp.YouTubeMusic_4c1a9e
X-Arctic-WebApp-URL=https://music.youtube.com/?source=pwa
X-Arctic-WebApp-Runtime=webkit
X-Arctic-WebApp-Schema=1
```

- `Exec` holds only the validated id. With `handlers:["mailto"]` it is
  `Exec=arctic-webapp run <id> %u` and `MimeType=x-scheme-handler/mailto;` follows `Keywords`
  (8.15). No other field code and never a URL.
- `Comment` is the launcher's second line (`Launcher.qml:59`), so there is no `GenericName`.
- Categories: one main category plus `X-Arctic-WebApp`. Manifest categories map music,
  entertainment, photo, video → AudioVideo; games → Game; productivity, business, finance →
  Office; developer → Development; education → Education; design → Graphics; utilities →
  Utility; anything else → Network.
- Never written: `WebBrowser` (Settings' browser role picks by it, `arctic_settings.py:1791`),
  `NoDisplay`, any `MimeType` other than the mailto opt-in.
- Values: control and bidi characters stripped, whitespace collapsed, `Name` ≤ 64 runes,
  `Comment` ≤ 160, `\` → `\\`, `;` → `\;` in list values.
- A Chromium-runtime app changes only `StartupWMClass` and `X-Arctic-WebApp-Runtime`.

#### 6.2 CLI

```
arctic-webapp inspect URL [--json]
arctic-webapp install (URL | --preview TOKEN) [--name NAME] [--icon INDEX|monogram|FILE] [--icon-url URL]
                      [--category CAT] [--runtime webkit|chromium:VARIANT] [--links browser|app]
                      [--notifications allow|ask|block] [--mail-links on|off] [--new-copy] [--launch] [--json]
arctic-webapp list [--sizes] [--kept] [--json]
arctic-webapp show ID [--sizes] [--json]
arctic-webapp run ID [URI] [--url URL] [--inspect]   the .desktop Exec: execs the runtime (same PID)
arctic-webapp launch ID [--url URL] [--json]        run, detached with Setsid (shell and Settings)
arctic-webapp update (ID… | --all) [--json]         re-discover name/manifest/icon; never touches user_set fields
arctic-webapp set ID [--name N] [--icon FILE|monogram] [--icon-url URL] [--category C] [--runtime R]
                  [--links browser|app] [--add-domain HOST] [--remove-domain HOST]
                  [--notifications allow|ask|block] [--mail-links on|off] [--devtools on|off]
                  [--rendering auto|software] [--reset-permissions] [--forget-certificate HOST] [--json]
arctic-webapp clear-data ID [--json]                sign out: delete profile + cache, keep the app
arctic-webapp remove ID… [--keep-data] [--json]
arctic-webapp forget ID… [--json]                   delete kept sign-in data
arctic-webapp icon ID --from-file FILE --source host-favicon          (called by the host)
arctic-webapp trust-certificate ID --host HOST --pem FILE             (called by the host after you confirm)
arctic-webapp repair [--json]                       rewrite .desktop files and icons from the registry
arctic-webapp runtimes [--json]
arctic-webapp serve                                 JSON lines on stdin/stdout
arctic-webapp render-sample DIR                     offline fixture render (%check)
arctic-webapp version [--webkit] [--json]
```

- Messages on stderr start with `arctic-webapp: `. Exit codes: 0 ok, 1 error, 2 usage.
- It refuses to run as root.
- Without `--json`, `inspect` and `install` may print progress on **stderr** only when stderr
  is a terminal.
- `run` accepts one optional positional `URI` from `%u`: a `mailto:` URI for a mail-handler app
  (8.15); a literal `%u`/`%U` (a launcher that passes field codes through) is ignored 🔍 (prove
  what Quickshell 0.2.1's `DesktopEntry.execute()` does with `%u`; the test in 13.1 covers both).

**`--json` output (C3, C4)**: exactly one line on stdout, nothing else on stdout, nothing on
stderr unless the program crashes. `fields` appears only with `code:"invalid"`.

```json
{"ok":true,"app":{"id":"org.arcticlinux.WebApp.YouTubeMusic_4c1a9e","name":"YouTube Music"}}
{"ok":false,"code":"state","error":"YouTube Music is still open. Close it and try again."}
{"ok":false,"code":"invalid","error":"Check the highlighted options.","fields":{"runtime":"Brave isn’t installed."}}
{"ok":false,"code":"bad_request","error":"arctic-webapp set needs an app id."}
```

Shapes per command:

| Command | Success line |
|---|---|
| `inspect --json` | `{"ok":true,"preview":{…same as serve Inspect result…}}` |
| `install --json` | `{"ok":true,"app":{…},"desktop_file":"…","launched":false}` |
| `list --json` | `{"ok":true,"apps":[…],"kept":[…]}` (`kept` only with `--kept`) |
| `show --json` | `{"ok":true,"app":{…}}` |
| `launch --json` | `{"ok":true,"pid":41234}` or `{"ok":true,"focused":true}` |
| `update --json` | `{"ok":true,"updated":[{"id":"…","changed":["icon"],"kept":["name"]}]}` |
| `set --json` | `{"ok":true,"app":{…},"applied":"live"}` (`live` \| `next_start` \| `saved`) |
| `clear-data --json`, `forget --json` | `{"ok":true}` |
| `remove --json` | `{"ok":true,"removed":[{"id":"…","stopped":true,"kept_data":false}]}` |
| `repair --json` | `{"ok":true,"repaired":["…"],"orphans_removed":["…"]}` |
| `runtimes --json` | `{"ok":true,"runtimes":[…same as Hello…]}` |
| `version --json` | `{"ok":true,"version":"0.3.0","host":"/usr/libexec/arctic/arctic-webapp-host","host_present":true}`; `--webkit` adds `"webkit_version":"2.54.0"` (runs `arctic-webapp-host --version`) |

App info object (`list`, `show`, results): `id`, `name`, `url` (start_url), `host`,
`icon_name`, `icon_path` (128 px file), `category`, `runtime`, `runtime_available`, `running`,
`links`, `notifications`, `devtools`, `rendering`, `extra_domains`, `handlers`,
`handlers_supported` (e.g. `["mailto"]` when the site is in the table), `tls_exceptions`
(`host` + `sha256` only, never the PEM), `data_bytes` (`null` unless `--sizes`), `problem`
(`"" | "no-desktop-file" | "no-registry" | "runtime-missing"`: orphans are listed so Remove
apps can clean them up), `created`, `updated`.

#### 6.3 `serve` (JSON lines, internal/protocol envelope, snake_case)

- Request `{"id","method","params"}`; response `{"id","result"}` or
  `{"id","error":{"code","message","fields"}}`; events `{"event",…}`, told apart by the `event`
  key (as `protocol.go:9-10` says). It reuses `protocol.Request`, `protocol.Response`,
  `protocol.Error`, `protocol.Errorf`, `protocol.FieldErrors` and the `protocol.Code*`
  constants. `SecretMethods` is empty.
- `Inspect` runs in a goroutine; a new `Inspect` cancels the previous one (the shell debounces
  typing by ~600 ms) and `Cancel` stops it. Every write is serialised under the registry lock.
  `serve` exits on stdin EOF and deletes its `inspect-*` directories.
- Methods: `Hello`, `Runtimes`, `Inspect`, `Install`, `List`, `Get`, `Launch`, `Update`,
  `Set`, `Remove`, `Forget`, `ClearData`, `Cancel`.
- Error codes: from internal/protocol `invalid` (with `fields`), `bad_request`,
  `unknown_method`, `not_found`, `state`, `offline`, `timeout`, `internal`; new `exists`,
  `fetch` (DNS or connect), `http` (status ≥ 400), `tls`, `too_large`, `not_html`, `busy` (lock
  held > 5 s), `unsupported` (runtime missing). The same codes appear in `--json` `code`.

```
→ {"id":0,"method":"Hello"}
← {"id":0,"result":{"engine_version":"0.3.0","protocol_version":1,"runtimes":[
     {"id":"webkit","name":"Arctic","available":true,"drm":false,"webrtc":false},
     {"id":"chromium:brave","name":"Brave","available":true,"drm":true,"webrtc":true},
     {"id":"chromium:chromium","name":"Chromium","available":false,"drm":false,"webrtc":true,
      "install":{"module":"chromium","method":"dnf"}}]}}

→ {"id":1,"method":"Inspect","params":{"url":"music.youtube.com"}}
← {"event":"progress","request":1,"stage":"page","message":"Opening music.youtube.com"}
← {"event":"progress","request":1,"stage":"manifest","message":"Reading the app manifest"}
← {"event":"progress","request":1,"stage":"icons","message":"Getting icons (2 of 4)"}
← {"id":1,"result":{
     "token":"b3f1c29a0d4c55a1","url":"https://music.youtube.com/","final_url":"https://music.youtube.com/",
     "host":"music.youtube.com","host_ascii":"music.youtube.com","secure":true,
     "name":"YouTube Music","name_source":"manifest","short_name":"YT Music",
     "start_url":"https://music.youtube.com/?source=pwa",
     "scope":{"site":"youtube.com","scheme":"https","manifest":"https://music.youtube.com/"},
     "manifest_url":"https://music.youtube.com/manifest.webmanifest","display":"standalone",
     "theme_color":"#0f0f0f","category":"AudioVideo",
     "suggested_id":"org.arcticlinux.WebApp.YouTubeMusic_4c1a9e","installed":[],
     "icons":[
       {"index":0,"source":"manifest","purpose":"any","size":512,"format":"png","path":"/run/user/1000/arctic-webapp/inspect-b3f1c29a0d4c55a1/0.png"},
       {"index":1,"source":"apple-touch","size":180,"format":"png","path":"…/1.png"},
       {"index":2,"source":"monogram","size":512,"format":"svg","path":"…/2.png"}],
     "recommended_icon":0,
     "handlers_supported":[],
     "warnings":[],
     "suggested_runtime":"webkit"}}
   DRM site:   "warnings":[{"code":"drm_unsupported","message":"This site plays protected media, which the Arctic engine can’t play. Brave can."}],
               "suggested_runtime":"chromium:brave"
   Calls:      "warnings":[{"code":"calls_unsupported","message":"Video and voice calls don’t work in the Arctic engine. Brave can make them."}]
   Login wall: "warnings":[{"code":"login_wall","message":"The site asked you to sign in, so Arctic used the name and icon from music.youtube.com."}]
   http:       "warnings":[{"code":"insecure","message":"This site doesn’t use a secure connection. Only add it if it’s on your own network."}]
   Offline:    {"id":1,"error":{"code":"offline","message":"You’re offline. You can still add the app with a letter icon."}}

→ {"id":2,"method":"Install","params":{"token":"b3f1c29a0d4c55a1","name":"YouTube Music","icon":0,
     "category":"AudioVideo","runtime":"webkit","links":"browser","notifications":"allow",
     "mail_links":false,"launch":true}}
   (or {"url":"https://…"} without a token, which inspects first; {"icon":"monogram"};
    {"icon_file":"/path.png"}; {"icon_url":"https://…/icon.png"}; {"new_copy":true})
← {"event":"progress","request":2,"stage":"render","message":"Making the icon"}
← {"id":2,"result":{"app":{…},"desktop_file":"/home/u/.local/share/applications/org.arcticlinux.WebApp.YouTubeMusic_4c1a9e.desktop","launched":true}}
← {"event":"changed","ids":["org.arcticlinux.WebApp.YouTubeMusic_4c1a9e"]}

→ {"id":3,"method":"List","params":{"sizes":false,"kept":true}}
← {"id":3,"result":{"apps":[{…app info…}],
     "kept":[{"id":"org.arcticlinux.WebApp.Slack_09ab3c","name":"Slack","url":"https://app.slack.com/","data_bytes":48213504}]}}
→ {"id":4,"method":"Get","params":{"id":"…","sizes":true}}           ← {"id":4,"result":{"app":{…,"data_bytes":48213504}}}
→ {"id":5,"method":"Launch","params":{"id":"…","url":"https://music.youtube.com/library"}}
← {"id":5,"result":{"pid":41234}}                                    (or {"focused":true})
→ {"id":6,"method":"Update","params":{"ids":["…"]}}                  ← {"id":6,"result":{"updated":[…]}}
→ {"id":7,"method":"Set","params":{"id":"…","name":"YT Music","links":"app","extra_domains":["accounts.google.com"],"notifications":"ask","icon":{"file":"/home/u/Pictures/ytm.png"}}}
← {"id":7,"result":{"app":{…},"applied":"live"}}
← {"id":7,"error":{"code":"invalid","message":"Check the highlighted options.","fields":{"runtime":"Brave isn’t installed."}}}
→ {"id":8,"method":"Remove","params":{"ids":["…"],"keep_data":true}}
← {"id":8,"result":{"removed":[{"id":"…","stopped":true,"kept_data":true}]}}
→ {"id":9,"method":"Forget","params":{"ids":["org.arcticlinux.WebApp.Slack_09ab3c"]}}   ← {"id":9,"result":{}}
→ {"id":10,"method":"ClearData","params":{"id":"…"}}                ← {"id":10,"result":{}}
→ {"id":11,"method":"Cancel","params":{"request":1}}                 ← {"id":11,"result":{}}
```

Events: `progress` (`request`, `stage` ∈ `page manifest icons render`, `message`) and
`changed` (`ids`), also sent after a host-triggered favicon upgrade is seen on the next
`List`. `api_test.go` pins every wire name in the style of `protocol_test.go`.

### 7. Discovery pipeline (pure Go, standard library only)

#### 7.1 Normalise (`discover/normalize.go`)
- Trim; add `https://` when there is no scheme; `url.Parse`. Accept only `http`/`https` with a
  host. Reject userinfo, whitespace, control characters, anything over 2,048 bytes. Drop the
  fragment.
- `http` is allowed with the `insecure` warning (self-hosted apps on a LAN).
- The preview shows the ASCII host under the name (homograph defence).

#### 7.2 Fetch (`discover/fetch.go`)
- Transport: `Proxy: http.ProxyFromEnvironment`; dial 5 s, TLS handshake 5 s, response headers
  10 s; `MaxResponseHeaderBytes` 64 KiB; `tls.Config{MinVersion: tls.VersionTLS12}`, never
  `InsecureSkipVerify`; no cookie jar; GET only; one 30 s context per inspect.
- Redirects: at most 5 hops, http(s) only, no userinfo, https → http refused. One
  `<meta http-equiv=refresh>` with delay ≤ 5 s is followed inside the same budget.
- Headers: `User-Agent: webapp.FetchUserAgent` (WebKitGTK's own default UA; the constant is
  pinned by the smoke test against `webkit_settings_get_user_agent()` and never copied from a
  document, C10); `Accept: text/html,application/xhtml+xml`; `Accept-Language` from
  `LANG`/`LANGUAGE`.
- Private-address guard: a `net.Dialer.Control` check refuses loopback, RFC 1918, link-local,
  ULA and unspecified addresses for the manifest and icons **when the page itself resolved to
  a public address**. It runs at connect time, so DNS rebinding cannot get around it. A page on
  a private address (Home Assistant) may load its own sub-resources.
- Limits: HTML 1 MiB read, tokenising stops 64 KiB after `</head>`, must be `text/html` or
  `application/xhtml+xml` (else `not_html`); manifest 256 KiB
  (`Accept: application/manifest+json, application/json`); PNG/JPEG/GIF 2 MiB with
  `image.DecodeConfig` ≤ 4096×4096 first; ICO/CUR 1 MiB, ≤ 64 entries; SVG 1 MiB; 16
  candidates collected, ≤ 6 fetched, 3 at once; 8 MiB total.

#### 7.3 Login wall and start_url (`discover/loginwall.go`)
- If the final URL's site (`psl.Site`) differs from the typed URL's site (Gmail →
  accounts.google.com): ignore names and icons from that page; probe the typed origin for
  `/manifest.webmanifest`, `/manifest.json`, `/site.webmanifest`, then `/apple-touch-icon.png`
  and `/favicon.ico`; keep the typed URL as start_url; set `login_wall`.
- start_url, in order: the manifest `start_url` when valid; the typed URL when it has a path
  beyond `/` inside the manifest scope (so `/mail/u/1/` keeps a second account); the normalised
  typed URL, upgraded to https if the site redirected to https on the same host. A sign-in page
  on another site never becomes start_url.

#### 7.4 HTML head tokenizer (`discover/htmlhead.go`, ~300 lines, fuzzed)
- The stdlib `html` package only escapes; `x/net/html` is not stdlib.
- States: data; tag open / end tag / tag name; attribute name, double-, single- or unquoted
  value; self-closing; `<!-- -->` and bogus comments (`<!DOCTYPE`, `<?…>`). Raw text skipped to
  the matching end tag (case-insensitive): `script`, `style`, `template`, `noscript`, `iframe`.
  RCDATA kept: `title`, `textarea`.
- Names ASCII-lowercased; entities through `html.UnescapeString`. Charset from Content-Type,
  then `<meta charset>`, else UTF-8; ISO-8859-1 and windows-1252 by hand-written tables;
  anything else decoded as UTF-8 with `strings.ToValidUTF8`.
- Caps: 4,096 tags, 64 attributes per tag, 8 KiB per value.
- Collects `<base href>`, `<title>`, `<link rel~=manifest|icon|shortcut icon|apple-touch-icon(-precomposed)>`
  (`href`, `sizes`, `type`, `media`; `mask-icon` ignored), and `<meta>` `theme-color` (prefer
  no `media`, then the one matching the current mode), `application-name`,
  `apple-mobile-web-app-title`, `og:site_name`, `description`.
- Parsing inside WebKit is rejected for inspect: it needs a display, runs untrusted JavaScript
  before you agreed to install, and is slow. Sites that add head tags from script get the
  favicon upgrade (8.11).

#### 7.5 Manifest (`discover/manifest.go`, W3C processing)
- `encoding/json` after stripping a BOM; `json.RawMessage` for members whose type varies.
- `start_url` resolved against the manifest URL and used only if same-origin with the
  document; `scope` must be same-origin and contain start_url, else start_url minus
  filename/query/fragment; `id` defaults to start_url.
- Informational: `display`, `theme_color`, `background_color` (hex, `rgb()`, `hsl()`, named),
  `categories`. `icons`: `src`, `sizes` (`any` or `WxH`), `type`, `purpose` (`any`,
  `maskable`; `monochrome` ignored).
- Ignored: `shortcuts`, `protocol_handlers`, `file_handlers`, `share_target`.

#### 7.6 Name (`discover/name.go`)
First non-empty of: manifest `name` (`short_name` when `name` > 30 chars); `application-name`;
`apple-mobile-web-app-title`; `og:site_name`; `<title>` split on ` | `, ` - `, ` – `, ` · `,
`: ` keeping the segment most like the site label and dropping "Home"/"Welcome"; the site label
title-cased. ≤ 64 characters, trimmed, bidi controls removed. Behind a login wall, the last
two steps use the typed host only.

#### 7.7 Scope (`psl/`, `policy/scope.go`)
- `psl.Site(host)` over `/usr/share/publicsuffix/public_suffix_list.dat` with rules,
  wildcards and exceptions: `mail.google.com` → `google.com`, `foo.bar.co.uk` → `bar.co.uk`,
  `user.github.io` → `user.github.io`. IP literals and `localhost` → exact `host:port`. If the
  list file is missing: exact host, logged.
- In scope = same scheme family (https, or http when the app itself is http) and a host equal
  to the site or a subdomain, or an `extra_domains` entry or its subdomain. The manifest scope
  is kept for information and the header cue.
- A tagged test checks `psl.Site` against `soup_tld_get_base_domain` over a host table.

#### 7.8 Icon candidates (`discover/candidates.go`)
- Preference: manifest `any` ≥ 192 px; manifest `maskable` ≥ 192 px; `apple-touch-icon`;
  `link rel=icon` ≥ 64 px or SVG; other `link rel=icon`; `/favicon.ico` only when nothing
  else was found.
- Score = source rank + closeness to ≥ 256 px (declared, then decoded) + format
  (PNG > SVG > ICO > JPEG > GIF). Formats sniffed from magic bytes. WebP, AVIF and JXL dropped
  (no stdlib decoder). Fetched in score order until one decodes to ≥ 64 px.
- Never `og:image` (a wide share card) and never third-party favicon services (Google s2 and
  similar leak which sites you visit).

#### 7.9 Decode and render (`icon/`)
- PNG/JPEG/GIF (first frame) with `image/*` after a `DecodeConfig` bound.
- ICO/CUR/BMP by hand, little-endian: 6-byte ICONDIR (type 1 or 2, count ≤ 64), 16-byte
  entries (0 = 256), largest then deepest entry wins, every offset/length checked. `\x89PNG`
  entries → `image/png`; others are headerless DIBs (BITMAPINFOHEADER, doubled height): 32 bpp
  BGRA (AND mask only if every alpha is 0), 24 bpp + mask, 8/4/1 bpp palette + mask, bottom-up
  rows padded to 4 bytes, BI_RGB only. BMP uses the same decoder after its 14-byte header.
  Fuzzed (`FuzzICO`).
- SVG: `rsvg-convert -w 512 -h 512 --keep-aspect-ratio -f png` with the SVG on stdin (no base
  file, relative references resolve to nothing), `exec.CommandContext` 5 s, empty working
  directory, `PATH=/usr/bin LANG=C.UTF-8`, stdout capped at 4 MiB, output validated with
  `image/png`. The SVG itself is never installed or handed to Qt/GTK.
- Resampling: premultiplied box filter down, bilinear up to 2× (`image/draw` has no scaler).
- Tile shape: rounded square, 30% radius (brand-book.md:103), anti-aliased from a signed
  distance. `maskable` icons are cropped to the 80% safe zone then masked; opaque full-bleed
  squares (apple-touch) get the same mask; icons with their own transparency stay as they are.
  Under 64 px after decoding: drawn at ≤ 2× in the centre 55% of a `surface-sunken` tile.
  Non-square: centred on a transparent square.
- Output 48/64/128/256/512 px PNGs, each from the source, never from another output size.

**Monogram (D-2, C5)**

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="154" fill="{tint}"/>
  <text x="256" y="256" dy="0.36em" text-anchor="middle"
        font-family="Figtree, Noto Sans, Noto Sans Hebrew, Noto Sans Arabic, Noto Sans CJK SC, sans-serif"
        font-weight="600" font-size="264" fill="{ink}">{letter}</text>
</svg>
```

- `{letter}`: the first letter or digit of the name, uppercased, XML-escaped.
- `{tint}` by category, the brand book's app-tile tints (`design-data.js:269` `TINTS`), light
  values from `design/tokens.json`:

  | Category | Tile tint (token) | Value |
  |---|---|---|
  | Network (default) | `info-soft` (browser tile) | `#e2eefa` |
  | Office, Calendar, Education | `success-soft` (office tile) | `#e1f2e9` |
  | AudioVideo, Game | `warning-soft` (video tile) | `#fbeadf` |
  | Development, Utility | `surface-sunken` (editor/extras tile) | `#e8edf1` |
  | Graphics | `warm-soft` (shell tile) | `#f0eae3` |

  `accent-soft` (the files tint) is excluded: amber is never decoration.
- `{ink}`: `ink` light `#151a21`.
- The launcher frames every icon in a live-themed tile (`AppTile.qml:18-39`), so a fixed light
  monogram reads like any upstream icon in both themes; icons are not re-rendered on a theme
  switch (that would rename every icon to `.rN` on each switch).
- `monogram_test` reads `design/tokens.json` and asserts: every palette value is a token value,
  none is from `amber-*`, `accent*`, `focus`, `selection`, `term-cursor`, and every pair
  reaches ≥ 4.5:1.
- Rendered with rsvg-convert; Figtree comes from arctic-fonts.

#### 7.10 Compatibility warnings (`discover/compat.json`, embedded)
- `calls_unsupported`: meet.google.com, teams.microsoft.com, teams.live.com, app.zoom.us,
  discord.com, app.slack.com (huddles), whereby.com, meet.jit.si.
- `drm_unsupported`: netflix.com, open.spotify.com, primevideo.com, tidal.com, disneyplus.com,
  max.com, music.apple.com, tv.apple.com, deezer.com, hulu.com (🔍 for the ones not named in
  research: Disney+, Max, Apple Music, Deezer, Hulu; confirm in M8).
- They set `suggested_runtime` to an installed Chromium variant that fits (Brave, Chrome or
  Vivaldi for DRM, since only they ship Widevine; any for calls) and never block an install.

### 8. Runtime behaviour

#### 8.1 `arctic-webapp run <id>`
1. Validate the id, take the shared lock, read `app.json`, re-render if `render` is old.
2. Build the environment: **remove** `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS`; if
   `/proc/driver/nvidia/version` exists, add `__NV_DISABLE_EXPLICIT_SYNC=1` and
   `WEBKIT_DISABLE_DMABUF_RENDERER=1` unless already set; `rendering=software` adds
   `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` and `WEBKIT_DISABLE_COMPOSITING_MODE=1`.
3. WebKit: `syscall.Exec("/usr/libexec/arctic/arctic-webapp-host",
   ["arctic-webapp-host","--app-id",id,(--url U),(--inspect),(--notice runtime-missing)], env)`.
4. Chromium: 8.3, then 8.14.

#### 8.2 Window and chrome
- One `GtkApplicationWindow`; size and maximized state from `state.json` (default 1200×800,
  clamped to the monitor). `GtkHeaderBar` titlebar; skel's `gtk-decoration-layout=:`
  (`dotfiles/.config/gtk-4.0/settings.ini:6`) hides window buttons.
- Header, left to right: back, forward, reload/stop; the page title (fallback: app name); a
  subtitle only when the page is **out of scope or not https** (host, `changes-prevent-symbolic`
  lock or `dialog-warning-symbolic` glyph, and a **Back to <App>** button); an audio indicator
  (`is-playing-audio`) that mutes on click (`webkit_web_view_set_is_muted`); a downloads button
  while downloads are active; the menu: zoom row, Find…, Print…, Copy link, Open in browser,
  Reload without cache, Clear site data…, Web app settings…, About this app. Icons are Adwaita
  symbolic names (D-11).
- The chrome stays Arctic (no site tint, D-3).

#### 8.3 Identity, single instance, launch-or-focus
- GTK 4 sets `xdg_toplevel.set_app_id` from the GApplication id; the smoke test checks it with
  `swaymsg -t get_tree`.
- Second start (WebKit): the unique GApplication forwards `activate` (or `open` with the URL)
  to the running instance and exits; the primary calls `gtk_window_present` and navigates to
  `--url` only if in scope, else opens it externally. So `arctic-webapp run <id>` is already
  launch-or-focus for WebKit apps, from the launcher, a user bind or `arctic-open --focus`.
- Mango focuses on activation only for a token from a focused surface, so the
  `activation_bypass` rule (10.5) is required (C1).
- Chromium runtime (D-8): before exec, `manage/focus.go` runs `mmsg get all-clients` (argv,
  2 s timeout), looks for a client whose app id equals `wm_class`, and if found runs
  `mmsg dispatch focusid client,<id>` and exits 0 (`launch` returns `{"focused":true}`). No
  `mmsg` (e.g. under sway) → launch. 🔍 the JSON key holding the app id in
  `mmsg get all-clients` (`appid` or `app_id`); the parser accepts both; prove on Mango 0.17.3
  in M7. `arctic-settings:53-59` shows the `id` and `title` keys.
- Pid file (D-5): the WebKit host writes `<id>.pid` in its GApplication `startup` handler, which
  runs only in the primary instance, and removes it on exit. For a Chromium runtime `run` writes
  it (its own pid, which becomes the browser's after exec) only when no live pid is recorded.
  The manager uses it for `running` in `List`, SIGTERM to stop on `remove`, `clear-data` and
  `forget` (wait 3 s, then `state`), and SIGHUP to reload options. Liveness =
  `/proc/<pid>/cmdline` still names the host (or the browser with this app's
  `--user-data-dir`). For Flatpak browsers the recorded pid is the host-side `flatpak`/`bwrap`
  process 🔍 (whether SIGTERM to it closes the browser; if not, `remove` answers `state`
  "Close <App> first."). The manager never runs `flatpak kill` (it would close your own
  browser too).

#### 8.4 Profile, session and settings (Epiphany's order)
- If memory limits are used: `webkit_network_session_set_memory_pressure_settings` once,
  before any session exists (a type function, global; C12). v1 sets none; per-app memory is
  measured in M8.
- `webkit_network_session_new(<id>/profile, $XDG_CACHE_HOME/arctic/webapps/<id>)`;
  `webkit_cookie_manager_set_persistent_storage(<profile>/cookies.sqlite,
  WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE)`; `webkit_network_session_set_itp_enabled(TRUE)`;
  `set_persistent_credential_storage_enabled(FALSE)` (no saved passwords in v1);
  `webkit_website_data_manager_set_favicons_enabled(TRUE)`; spell checking on with
  `g_get_language_names()`; stored notification decisions seeded through
  `initialize-notification-permissions`.
- View: `g_object_new(WEBKIT_TYPE_WEB_VIEW, "network-session", s, "settings", st,
  "user-content-manager", ucm, NULL)` (the `new_with_*` constructors do not exist in 6.0).
- WebKitSettings: user agent unchanged; `hardware-acceleration-policy` ALWAYS unless
  `rendering=software`; `enable-developer-extras` only with `devtools` or `--inspect`;
  `enable-media-stream` TRUE; `enable-webrtc` and `enable-encrypted-media` FALSE (defaults;
  Fedora does not build them); `javascript-can-open-windows-automatically` FALSE; site quirks
  and back/forward gestures on. No user scripts, no script message handlers, no custom URI
  schemes: no bridge from pages to the host.

#### 8.5 Navigation (`policy/navigate.go`; the shim only reports facts; C8)

| Case (main frame, `NAVIGATION_ACTION`) | Decision |
|---|---|
| `about:blank`, `data:`, `blob:` | use (WebKit's own restrictions apply) |
| `javascript:` or `file:` started by a site | ignore |
| `mailto:`, `tel:`, `sms:`, other non-web schemes | open externally with a user gesture; else ignore |
| http(s) in scope, back/forward, reload | use |
| Out of scope and `LINK_CLICKED`, or `OTHER` with a user gesture, with `links=browser` (default) | ignore + `arctic_open_external`; Ctrl-click and middle-click always go external |
| Out of scope with no gesture (server redirects, script navigations) or `FORM_SUBMITTED` | use, so SSO chains and cross-domain login posts finish in the app; the header shows the host and **Back to <App>** |
| Anything with `links=app` | use |

Other decision types: subframes use; `NEW_WINDOW_ACTION`: a user-clicked `target=_blank`
link in scope → load in the main view, out of scope → your browser, script `window.open` →
`create` (8.6); `RESPONSE`: a MIME type WebKit cannot show, or `Content-Disposition:
attachment`, becomes a download.

"Open in browser" and external links use the `x-scheme-handler/https` default through
`GtkUriLauncher`, which Settings' browser role sets (`arctic_settings.py:1792`). It does not
call `arctic-open browser` (that exits 2 when given a URL, `arctic-open:28-29`).

#### 8.6 Popups and OAuth
- On `create` the shim returns `g_object_new(WEBKIT_TYPE_WEB_VIEW, "related-view", parent,
  "settings", st, "user-content-manager", ucm, NULL)`: same session, `window.opener` kept, so
  OAuth `postMessage` handshakes work (avoids Epiphany #1752).
- The popup window is transient for the opener, sized from `WebKitWindowProperties` clamped to
  480–1200 × 400–900, shown on `ready-to-show`, destroyed on `close`, always shows origin and
  TLS state in its header, titled `Pop-up: <page title>`. Not scope-policed except non-web
  schemes.
- 🔍 whether Mango floats transient windows; if not, add
  `windowrule=isfloating:1,title:^Pop-up: ` to rules.conf (M5 decides).

#### 8.7 Permissions
`permission-request` and `query-permission-state` are answered from `permissions.json` plus:

| Request | Default |
|---|---|
| Notifications | `allow` (option default): allowed for in-scope origins (Epiphany's app-mode precedent); `ask`: prompt; `block`: deny |
| UserMedia (camera, microphone, screen; told apart by `webkit_user_media_permission_is_for_{audio,video,display}_device`), Geolocation, Clipboard read, WebsiteDataAccess | prompt |
| PointerLock | allowed in scope while full screen; otherwise prompt |
| DeviceInfo | allowed only when the origin already has camera or microphone |
| MediaKeySystem (EME), XR | denied |

The prompt is an in-window banner (GtkRevealer under the header, outside page content, so a
page cannot fake it): `surface-raised`, 1 px `line`, 14 px radius, one `accent` **Allow**
button (the view's one primary action) and a plain **Block**; copy "music.youtube.com wants to
use your camera."; "Remember for this site" on by default. The origin comes from
`webkit_security_origin_new_for_uri(webkit_web_view_get_uri())`, never from page text.
Navigating away or dismissing denies; requests queue.

#### 8.8 Notifications
- `show-notification` → Go → `GNotification`: title and body from the page, icon
  `g_themed_icon_new(<current icon name>)`, default action `app.notification-clicked(<tag>)`.
  A click presents the window and calls `webkit_notification_clicked`.
- GLib's freedesktop backend sends `desktop-entry=<app id>` and `app_name=<Name>`, so the
  shell's notification centre (D6) groups them under the web app and resolves the icon from the
  desktop entry, and Do not disturb applies. 🔍 which GNotification backend GLib picks on a
  Mango session with xdg-desktop-portal-gtk running (freedesktop vs portal); the smoke test
  asserts the hints with `dbus-monitor` (D-10).
- No background push: in v1 the host exits with its last window.

#### 8.9 Downloads
`download-started` (network session) → `decide-destination` → `policy.SafeName` (basename
only, no control characters, no leading dots, ≤ 200 bytes, MIME-derived extension when
missing) → `policy.Unique` in `G_USER_DIRECTORY_DOWNLOAD` (`file (1).pdf`),
`set_allow_overwrite(FALSE)`, `set_destination`. Progress in a header popover (amber progress
fill is allowed by brand-book.md:46). When done, a GNotification offers **Open** and **Show in
folder** (GtkFileLauncher). Never opened automatically; the executable bit is never set.

#### 8.10 Theme
- The host reads `~/.config/arctic/current/theme.json` (QML `#AARRGGBB`, converted).
  `theme.HostCSS` generates CSS for the host's own widgets (header, banners, find bar, error
  page) following design/guidelines/10-platforms.md: buttons 10 px, popovers 14 px, dialogs
  20 px, focus `2px solid` in `focus`. Plain GTK widgets already get Arctic colours and radii
  from `~/.config/gtk-4.0/gtk.css`.
- A `GFileMonitor` on `~/.config/arctic/` fires when `theme` (rewritten by `arctic-theme`) or
  the `current` link changes, the trigger `Theme.qml:140-157` uses; CSS, colour scheme and view
  background update live. 🔍 whether GTK 4.22 re-reads `~/.config/gtk-4.0/gtk.css` after a
  switch; if not, the host also loads `current/gtk.css` as its own provider at
  `GTK_STYLE_PROVIDER_PRIORITY_USER + 1` and reloads it on the same trigger.
- 🔍 whether page `prefers-color-scheme` follows GTK's colour scheme in 2.54; the smoke test
  logs `matchMedia` in both themes. Pages are never forced dark.

#### 8.11 Favicon upgrade (C11, D-4)
- Applies when `icon.source` is `monogram` (or a favicon ≤ 32 px) and not user-set.
- After the first successful load: on WebKitGTK < 2.54, `webkit_web_view_get_favicon`
  (deprecated in 2.54, present from 2.50) → `gdk_texture_save_to_png_bytes` (WebKit's decoded
  pixels, never `gdk_texture_new_from_bytes` on untrusted bytes). On ≥ 2.54
  (`webkit_get_minor_version()`), the `page-icons` property by name: the largest `WebKitImage`
  is loaded through `g_loadable_icon_load` and its bytes are written unchanged.
- The host writes `$XDG_RUNTIME_DIR/arctic-webapp/<id>-favicon.png` (any format) and execs
  `arctic-webapp icon <id> --from-file … --source host-favicon`; the manager sniffs and decodes
  it with the same bounded decoders as discovery, requires ≥ 64 px, renders the sizes and bumps
  `icon.rev` and `Icon=`.

#### 8.12 Crashes, offline pages and TLS
- `web-process-terminated`: `CRASHED` → reload once within 60 s, then a banner "This page
  stopped working." with **Reload**; `EXCEEDED_MEMORY_LIMIT` → banner with **Reload**; repeated
  crashes right after a WebKitGTK update → "WebKit was updated. Restart this app."
- `load-failed` (offline, DNS): an Arctic error page through
  `webkit_web_view_load_alternate_html` (embedded `html/template`, every value escaped) with
  **Try again**; retries when `GNetworkMonitor` reports the network is back.
- `load-failed-with-tls-errors`: blocking page "This connection isn’t private", no "continue
  anyway". Exception only for private-network hosts (IP literals in loopback, RFC 1918, ULA or
  link-local; `localhost`; names ending `.local`, `.lan`, `.home.arpa`, `.internal` whose every
  resolved address is private, re-checked by the manager): the page shows the SHA-256
  fingerprint and **Trust this certificate for <host>**; on confirmation the host writes the PEM
  to the runtime directory and execs `arctic-webapp trust-certificate <id> --host H --pem F`;
  the manager validates, stores it in `tls_exceptions` and sends SIGHUP; the host calls
  `webkit_network_session_allow_tls_certificate_for_host` for that host and that exact
  certificate, and reloads. `set --forget-certificate HOST` removes it.
- If the host dies, the next start restores `last_url` when in scope and used in the last 30
  days. Logs strip query and fragment.

#### 8.13 Live options
`set` on a running app sends SIGHUP; the host re-reads `app.json` and applies zoom, links,
notifications, devtools and TLS exceptions (`applied:"live"`). A runtime change applies at the
next start (`next_start`); a name/icon/category change only rewrites files (`saved`).

#### 8.14 Chromium-family runtime (fallback)
A built-in table in `manage/runtime.go`; `catalog_test.go` cross-checks refs, dnf package and
command against `modules/browser/*/module.toml` through `modules.FS` and `catalog.Load`. The
catalog is not read at run time (it belongs to arctic-installer, which is live-only).

| Variant | Detect | argv |
|---|---|---|
| `chromium` | `/usr/bin/chromium-browser` (dnf `chromium`) | `chromium-browser --app=<url> --user-data-dir=<id>/chromium --no-first-run --no-default-browser-check` |
| `ungoogled` | `{/var/lib,~/.local/share}/flatpak/app/io.github.ungoogled_software.ungoogled_chromium/current/active` | `flatpak run --branch=stable <ref> --app=<url> --user-data-dir=~/.var/app/<ref>/data/arctic-webapps/<id> --no-first-run --no-default-browser-check` |
| `brave` (DRM) | `com.brave.Browser` | as `ungoogled` |
| `chrome` (DRM) | `com.google.Chrome` | as `ungoogled` |
| `vivaldi` (DRM) | `com.vivaldi.Vivaldi` | as `ungoogled` |

- The URL is always one argv element starting with `https://` or `http://`. Never
  `--no-sandbox`, `--remote-debugging-port`, `--ignore-certificate-errors`, `--class` (C13).
- `wm_class`/`StartupWMClass`: Chromium derives `<prefix>-<host>__<path with / → _>-Default`
  itself. 🔍 the prefix per brand and per Flatpak; measured in M7 and pinned in
  `runtime_test.go`.
- Notifications, permissions, downloads and link handling belong to the browser; the profile
  is still per app.
- Browser removed later: `run` falls back to the WebKit host with `--notice runtime-missing`
  (a banner), and Remove apps shows "runtime missing".
- Theme (gap `chromium-theme-policy`): the WebKit host follows the Arctic theme itself (8.10).
  Chromium-runtime windows take their colours from the managed `BrowserThemeColor` /
  `BrowserColorScheme` policy that the theming section's new hook
  `packaging/theme-hooks.d/50-chromium` writes. Managed policies are machine-wide, so the
  per-app `--user-data-dir` profiles get them too. 🔍 whether Flatpak Brave/Chrome/Vivaldi read
  host `/etc/…/policies/managed` or need their Flathub `*.Policy` extension points; that is the
  hook's open issue, not the engine's. The engine adds no browser flags for theming.

#### 8.15 Email links (gap `default-app-roles`, D-6)
- `manage/handlers.json` (embedded) lists mail sites and compose templates, e.g.
  `{"site":"google.com","hosts":["mail.google.com"],"template":"https://mail.google.com/mail/?extsrc=mailto&url={mailto}"}`,
  Outlook (`outlook.office.com`, `outlook.live.com`), Proton Mail (`mail.proton.me`),
  Fastmail (`app.fastmail.com`), HEY (`app.hey.com`, Omarchy's `omarchy-webapp-handler-hey`).
  🔍 every template; verify each by hand in M8 and drop any that does not open a compose view.
- `inspect` returns `handlers_supported:["mailto"]` for those sites. The preview and Settings
  show "Open email links (mailto:) in this app", **off** by default. `set --mail-links on`
  writes `MimeType=x-scheme-handler/mailto;` and `Exec=arctic-webapp run <id> %u`; off removes
  both.
- Turning it on does not make it your default: Settings' new Email role (owned by the
  default-apps section; `ROLES` in `arctic_settings.py:1790-1804` gains `mimes=['x-scheme-handler/mailto']`)
  lists the web app as a candidate, and choosing it writes `mimeapps.list`.
- `run <id> mailto:…`: the manager parses the URI (`mailto:` only, ≤ 2,048 bytes), percent-
  encodes it into `{mailto}`, checks the result is in scope, and passes it as `--url`. Any
  other URI is ignored and logged.
- Calendar role: category "Calendar" (D-12). No `webcal:` handling. Zoom's `zoommtg:` handler
  (Omarchy) is not done: Zoom calls do not work in WebKit.

### 9. Keyboard behaviour

#### 9.1 In a web-app window

| Keys | Action |
|---|---|
| Ctrl+F; Enter / Shift+Enter; Esc | Find bar (`WebKitFindController`, "n of m" from `counted-matches`) |
| Ctrl+= / Ctrl+− / Ctrl+0, Ctrl+scroll | Zoom, saved in `state.json` |
| F5 / Ctrl+R; Ctrl+Shift+R | Reload; reload bypassing the cache |
| Alt+← / Alt+→, mouse buttons 8/9, swipe | Back / forward |
| Ctrl+P | Print (`WebKitPrintOperation` run_dialog) |
| Ctrl+L | Copy link (Omarchy's Alt+Shift+L is not used: Alt+Shift is the `grp:alt_shift_toggle` layout switch, D7) |
| F11 | Full screen (header hides; also on page request) |
| Ctrl+W / Ctrl+Q | Close window / quit app |
| F12, Ctrl+Shift+I | Inspector, only with devtools on |
| Esc | Closes a banner (= Block / dismiss) |

- The host binds no Super keys, so Mango's binds (Super+B browser, Super+Shift+S area
  screenshot, D7) work while a web app has focus.
- Host shortcuts sit in a window `GtkShortcutController` in the bubble phase, so a page that
  handles a key itself keeps it. 🔍 WebKitGTK 6.0 hands keys the page did not handle back to
  GTK; the smoke test asserts Ctrl+F opens the find bar on a plain page and does not on a page
  that calls `preventDefault()`.
- Context menu: "Open link in new window" becomes "Open link in browser"; "Copy link" is added.

#### 9.2 Get apps → Web apps page (see 10.1)
- Opens with the URL field focused. Typing inspects after ~600 ms; Enter inspects at once.
- Enter runs the page's one primary action for its state: inspect → **Add app** → **Open**.
- Tab / Shift+Tab move through the preview: name, icon row (←/→ choose, Enter/Space picks
  "Choose a file…"), category, engine, switches, the primary button.
- Esc: cancels a running inspect (`Cancel`); otherwise goes back to the chooser
  (`event.accepted = true`, so `Popover.qml:99` does not close the launcher).

#### 9.3 Remove apps → Web apps tab and the launcher
- ↑/↓ move; Delete or Enter on a row opens the confirm sheet; in the sheet Space toggles "Also
  delete sign-in data", Enter confirms (error-style **Remove**), Esc cancels.
- "Saved sign-in data" rows: Delete → **Forget** confirm.
- Launcher: Delete on a web-app row (gap `launcher-uninstall-key`) opens the same sheet through
  `app-owner.py` (10.3).

#### 9.4 User hotkeys for a web app
No Arctic default keys (Omarchy's preinstalled web-app keys were skipped). `Web-Apps.md`
shows a user bind, e.g. `bind=SUPER+ALT,m,spawn,arctic-webapp run
org.arcticlinux.WebApp.YouTubeMusic_4c1a9e` in `~/.config/mango/user.conf` or through
Settings → Shortcuts (`cmd_bind_add`), where D7's shadow check applies. Pressing it again
raises the window (8.3).

### 10. Integration

#### 10.1 Get apps → Web apps (request #1; the Get apps section owns `shell/GetApps.qml`)
- D2's chooser card **Web apps** (glyph `globe`) opens `WebAppPage.qml` as page `'web'`. The
  card is hidden when `WebAppService.available` is false (`arctic-webapp` missing; arctic-shell
  only Recommends it).
- New `shell/WebAppService.qml` (singleton, registered in `shell/qmldir`): one
  `Process{command:['arctic-webapp','serve'], stdinEnabled:true, stdout: SplitParser}` started
  on demand (Get apps web page or Remove apps opened) and stopped when the launcher closes
  (stdin closed). It sends `Hello` first, tells events from responses by the `event` key,
  matches responses by `id`, and exposes `available`, `runtimes`, `apps`, `kept`, `busy`,
  `inspect(url)`, `cancel()`, `install(params)`, `remove(ids, keepData)`, `forget(ids)`,
  `launch(id)`, `refresh()`, and a `changed` signal. `onExited` → "Web apps stopped. Open Get
  apps again to restart it." (same wording pattern as `InstallConsole.qml:99-105`).
- New `shell/WebAppPage.qml`, states:
  1. **Empty**: URL field ("Paste a website address, like music.youtube.com"), a short note:
     "Web apps get their own window, icon and sign-in. Video calls and protected video
     (Netflix, Spotify) need Brave, Chrome or Vivaldi."
  2. **Inspecting**: a status line from `progress` events; Esc cancels.
  3. **Preview**: icon choices (up to 4 candidates + letter icon + "Choose a file…" + "Use an
     icon from the web…"; images from the `inspect-<token>/N.png` paths through
     `AppTile.imageSource`, which the Get apps section adds), editable name, ASCII host with
     `lock` or `alert` glyph, category select, engine select from `runtimes` (unavailable ones
     disabled with "Install Brave" opening the Flathub page), switch "Open other sites in your
     browser" (links=browser, on), switch "Open email links in this app" (only when
     `handlers_supported` has `mailto`), warnings (`alert` glyph, `warning` colour), one
     primary button **Add app** (amber). Duplicate: "Already added: YouTube Music" with
     **Open** and "Add a second copy (another account)" (`new_copy`).
  4. **Done**: "YouTube Music is in your apps" with primary **Open** and ghost **Add another**.
  5. **Offline** error: "You’re offline. You can still add the app with a letter icon." with
     **Add with a letter icon** (Install with `icon:"monogram"`).
- On the live USB: note "Web apps you add here are gone after a restart."
- Contract reconciliation: `research/map-get-apps.json` §2.5 sketched `arctic-webapp create …`
  and `remove ID [--delete-data]`; the engine's names are `install` and `remove ID
  [--keep-data]` (CLI) / `Remove{ids, keep_data}` (serve). The shell uses `serve`.

#### 10.2 Remove apps → Web apps (request #4; the Remove apps section owns its page)
- New `shell/WebAppList.qml` (tab content): `WebAppService.apps` rows (icon through
  `Quickshell.iconPath(icon_name, true)`, name, host, runtime label, "Open" dot when
  `running`, `problem` badge: "Launcher entry missing" / "Record missing" / "Runtime missing").
- Confirm sheet copy: "Remove YouTube Music? Its window closes." with "Also delete sign-in data
  (you’ll be signed out)" unticked by default (D-13) → `Remove{ids, keep_data: !ticked}`.
- Section "Saved sign-in data": `kept` rows with size, **Forget** → `Forget{ids}`.
- Orphans (`problem` set) are removable the same way; `remove` cleans whatever exists.
- `arctic-webapps` itself is protected by the `arctic-*` rule in the Remove apps protected set.

#### 10.3 Launcher (`shell/assets/Icons.js`, `shell/Launcher.qml`)
- Web apps must skip `tileFor` (C9). Put the check inside `Icons.tileFor`, where the key is
  already lowercased: first line `if (key.startsWith('org.arcticlinux.webapp.')) return '';`.
  (If the check lives in `Launcher.qml:61` instead, it must use the exact-case
  `e.id.startsWith('org.arcticlinux.WebApp.')`.) Covered by a new node test (13.3).
- Launcher Delete (gap `launcher-uninstall-key`, owned by the Remove apps section):
  `shell/scripts/app-owner.py` resolves a desktop id with prefix `org.arcticlinux.WebApp.` or
  key `X-Arctic-WebApp-Id` to `{"owner":"webapp","id":"…"}` **before** the user-`.desktop`
  rule (the file lives in `~/.local/share/applications` and would otherwise be treated as a
  hand-made launcher); the shell then calls `WebAppService.remove`.
- Search: `Keywords=web;app;<host>;` lets "web" and the host find web apps.

#### 10.4 Settings (`settings/`)
- `arctic_settings.py`: `TOOLS` gains `'arcticWebapp': 'arctic-webapp'`; new commands (D-7)
  that run `arctic-webapp … --json` with an argv, parse the one line and return it unchanged
  (it already has `ok`/`error`): `webapps` (`list --kept --sizes`), `webapp-set ID KEY VALUE`
  (KEY from an allowlist: `name links notifications devtools rendering runtime category
  mail-links add-domain remove-domain forget-certificate icon`), `webapp-reset-permissions ID`,
  `webapp-refresh ID` (`update`), `webapp-clear ID` (`clear-data`), `webapp-remove ID keep|delete`,
  `webapp-forget ID`. Missing binary → `Failure('Web apps aren’t installed (package arctic-webapps).')`.
- New page `settings/pages/WebAppsPage.qml` (id `webapps`, title "Web apps", icon `globe`;
  added to `settings/pages/qmldir` and `settings/SearchIndex.js` PAGES and ENTRIES), shown when
  `Backend.caps.arcticWebapp`: a list, and per app: Name; Icon (Choose a file / Letter icon /
  Get it from the site again); Open other sites in your browser; Extra sites (add/remove);
  Notifications (Allow / Ask / Block); Engine; Open email links here (when supported);
  Developer tools; Rendering (Automatic / Software: "Try this if the window stays blank");
  Reset permissions; Trusted certificates (forget); Sign out (clear data); Remove.
- `arctic-settings webapps` opens it (the host menu's "Web app settings…").
- `settings/dev/headless.sh` gets a fake `arctic-webapp` fixture so the headless smoke test
  loads the page.

#### 10.5 Mango
- Append to `dotfiles/.config/mango/arctic/rules.conf` (after line 43, "Arctic apps"):

  ```
  # Web apps (arctic-webapp): a second start raises the running app. Mango focuses on activation
  # only for a token from a focused surface; this lets the app's own D-Bus activation through.
  windowrule=activation_bypass:1,appid:^org\.arcticlinux\.WebApp\.
  ```
- Raise `Requires: mangowm >= 0.17.3` at spec `:160` and `:417` (and `:338` for consistency)
  (C1). `%check`'s `mango -p` (spec `:884-897`) validates the line when mango is in the build
  root; `settings/tests` already knows the key.

#### 10.6 Gap items touching web apps (D8)

| Gap item | Priority | What this section does | Owner of the rest |
|---|---|---|---|
| `chromium-theme-policy` | P2 | WebKit host follows the theme natively (8.10); Chromium-runtime apps inherit the managed policy; no engine flags (8.14) | theming section: `packaging/theme-hooks.d/50-chromium` + root helper |
| `launch-or-focus` | P2 | `run` is launch-or-focus: GApplication for WebKit, `mmsg focusid` for Chromium (8.3); web-app ids work with `arctic-open --focus` because app_id = desktop id | apps/shortcuts section: `arctic-open --focus` (moves `arctic-settings:48-59`) |
| `default-app-roles` | P2 | opt-in `mailto` handler for table sites; Calendar category (8.15) | default-apps section: Email and Calendar roles in `ROLES`, `AppsPage.qml`, and the `'Super + W'` → `'Super + B'` fix at `arctic_settings.py:1793` |
| `launcher-uninstall-key` | P1 | web-app owner branch contract (10.3) | Remove apps section |
| `tui-launchers` | P2 | none; it may reuse `desktop.go`'s escaping rules only by copying them (it is shell/Python) | Get apps section |

### 11. Packaging deltas

#### 11.1 `packaging/arctic-linux.spec`

1. Header list (`:7-27`), after `arctic-installer`:
   `#   arctic-webapps         cmd/arctic-webapp (Go) + cmd/arctic-webapp-host (Go + cgo: WebKitGTK 6.0, GTK 4), internal/webapp/, internal/webkit/`
2. `:32` comment: "arcticd, arctic-install and arctic-webapp use the Go linker
   (CGO_ENABLED=0); arctic-webapp-host is cgo, linked externally with Fedora's flags. No
   debuginfo subpackages (docs/BUILD-SPEC.md §9): brp-strip strips every binary." Keep `:33`.
3. BuildRequires after `:47`:
   ```
   # arctic-webapp-host (cgo): the C compiler, WebKitGTK 6.0, GTK 4, libsoup 3; readelf in %%check
   BuildRequires:  gcc
   BuildRequires:  binutils
   BuildRequires:  pkgconfig(webkitgtk-6.0)
   BuildRequires:  pkgconfig(gtk4)
   BuildRequires:  pkgconfig(libsoup-3.0)
   ```
   (`tools/build-rpms.sh:232` `dnf builddep` installs them.)
4. New subpackage after arctic-installer's `%description` (~`:330`), no `BuildArch`
   (x86_64, Go binaries; BUILD-SPEC:60):
   ```
   # ---------------------------------------------------------------------------------------------
   %package -n arctic-webapps
   Summary:        Arctic Linux web apps: any website as an app with its own window and icon
   # libwebkitgtk-6.0.so.4 and libgtk-4.so.1 come from the automatic soname Requires. WebKitGTK has
   # no symbol versions and the host is linked with -z now, so the floor is the version it was
   # built against (docs/BUILD-SPEC.md §11).
   Requires:       webkitgtk6.0%{?_isa} >= %{webkit_built}
   # SVG icons and letter icons → PNG
   Requires:       librsvg2-tools
   # ~/.local/share/icons/hicolor is found through hicolor's index.theme
   Requires:       hicolor-icon-theme
   # A web app's scope uses registrable domains from the Public Suffix List
   Requires:       publicsuffix-list
   Recommends:     arctic-desktop-config = %{version}-%{release}
   Recommends:     arctic-fonts = %{version}-%{release}

   %description -n arctic-webapps
   Any website as an app: its own window, icon, launcher entry and sign-in, separate from your
   browser. arctic-webapp adds, lists, changes and removes web apps (the launcher's Get apps and
   Remove apps use it, and nothing needs a password); each app window is arctic-webapp-host, built
   on WebKitGTK. Sites that need protected media or video calls can open in a Chromium-family
   browser instead.
   ```
   with, near `:31`,
   `%global webkit_built %(pkg-config --modversion webkitgtk-6.0 2>/dev/null || echo 2.50)`
   (the fallback keeps `rpmspec -q` in the `specs` job and `dnf builddep` parsing before the
   -devel package exists) (D-4). No gstreamer Recommends (C14).
5. arctic-shell (`:240-252`): `Recommends: arctic-webapps = %{version}-%{release}` (noarch may
   Recommend an x86_64 package). arctic-desktop (`:405-417`): `Requires: arctic-webapps =
   %{version}-%{release}`, so existing installs get it through arctic-update. Raise mangowm at
   `:160`, `:338`, `:417` to `>= 0.17.3` (10.5).
6. `%build` (`:501-503`):
   ```
     for cmd in arcticd arctic-install arctic-webapp; do
       go build -ldflags "-B gobuildid" -o "_build/bin/$cmd" "./cmd/$cmd"
     done
     # The web-app window (docs/BUILD-SPEC.md §11): cgo against WebKitGTK 6.0 and GTK 4. Go reads
     # CGO_CFLAGS/CGO_LDFLAGS, not the CFLAGS/LDFLAGS rpm exports; -tags webkit selects its files.
     CGO_ENABLED=1 CGO_CFLAGS="%{build_cflags}" CGO_LDFLAGS="%{build_ldflags}" \
       go build -tags webkit -ldflags "-B gobuildid -linkmode=external" \
         -o _build/bin/arctic-webapp-host ./cmd/arctic-webapp-host
   ```
   It inherits `GOFLAGS="-buildmode=pie -trimpath"`. Verified in fedora:44: PIE, BIND_NOW,
   build-id, NEEDED `libwebkitgtk-6.0.so.4`, `libgtk-4.so.1`. Plain `go build`, not `%gobuild`.
7. `%install` after `:744`, under a new `# ---- arctic-webapps` line:
   `install -pm 0755 _build/bin/arctic-webapp %{buildroot}%{_bindir}/` and
   `install -Dpm 0755 _build/bin/arctic-webapp-host %{buildroot}%{_libexecdir}/arctic/arctic-webapp-host`.
8. `%check` libexec loop (`:825-832`), first line inside the loop:
   `case "$(head -c4 "$s")" in "$(printf '\177ELF')") continue ;; esac`
9. `%check` after the loop:
   ```
   # arctic-webapps: the host is the real cgo build and the manager is cgo-free; both start
   # without a display; the launcher entries the manager writes are valid.
   readelf -d %{buildroot}%{_libexecdir}/arctic/arctic-webapp-host | grep -q 'NEEDED.*libwebkitgtk-6\.0\.so\.4'
   ! readelf -d %{buildroot}%{_bindir}/arctic-webapp | grep -q NEEDED
   %{buildroot}%{_libexecdir}/arctic/arctic-webapp-host --version
   %{buildroot}%{_bindir}/arctic-webapp version
   rm -rf _build/webapp-sample _build/webapp-home _build/webapp-run
   mkdir -p _build/webapp-run && chmod 0700 _build/webapp-run
   HOME="$PWD/_build/webapp-home" XDG_RUNTIME_DIR="$PWD/_build/webapp-run" \
     %{buildroot}%{_bindir}/arctic-webapp render-sample _build/webapp-sample
   desktop-file-validate _build/webapp-sample/*.desktop
   ```
   `render-sample` renders two embedded fixtures with no network (a plain app and a mail-link
   app, so `MimeType` + `%u` is validated), monograms through rsvg-convert (BuildRequires
   `:48`), and refuses to run if it would touch the real `$HOME`.
10. `%files` after arctic-installer's (`:1153`):
    ```
    %files -n arctic-webapps
    %license LICENSE
    %{_bindir}/arctic-webapp
    %dir %{_libexecdir}/arctic
    %{_libexecdir}/arctic/arctic-webapp-host
    ```
11. `%changelog`: in the 0.3.0 entry, "arctic-webapps: new subpackage (web apps: arctic-webapp
    manager, arctic-webapp-host on WebKitGTK 6.0)".

Sizes: manager ~6 MB, host ~2–3 MB stripped (prototype host 1.7 MB). Runtime: 23 more
packages, ≈155 MiB installed, ≈47 MiB download (gtk4, libsoup3, bubblewrap, xdg-dbus-proxy,
gstreamer1 are already installed). Build: ≈300 MiB more download per build-rpms.sh run (ci.yml
`rpms`, repo.yml within its 90-minute timeout, iso.yml).

#### 11.2 ISO (`iso/kiwi/config.kiwi`)
After `:72` (the arctic-settings tools):
```xml
<!-- Web apps (Get apps → Web apps; arctic-desktop requires it too; named so it is never
     left out). WebKitGTK 6.0 adds about 155 MiB installed. -->
<package name="arctic-webapps"/>
```
Measure `out/iso` in M6 (estimate +45–50 MB against the 2 GiB limit). If the ISO with Zen
would exceed 2 GiB, stop and report before merging: `--zen auto` would silently drop
preinstalled Zen. Installed systems keep the package (not in `LiveOnlyPackages`).

### 12. CI (`.github/workflows/ci.yml`)

- Job `go` (`:16-39`) is unchanged and keeps `CGO_ENABLED: "0"`. It vets and tests every pure-Go
  web-app package; the PSL tests use the fixture; tagged packages are skipped.
- New job after `:39`:

```yaml
  go-webkit:
    name: Go (web app host: cgo, WebKitGTK 6.0)
    runs-on: ubuntu-latest
    container: registry.fedoraproject.org/fedora:44
    timeout-minutes: 30
    env: { GOTOOLCHAIN: local, GOPROXY: "off", GOFLAGS: -mod=mod, CGO_ENABLED: "1" }
    steps:
      - name: Install tools
        run: |
          dnf -y install git golang gcc binutils webkitgtk6.0-devel gtk4-devel libsoup3-devel \
            publicsuffix-list librsvg2-tools desktop-file-utils sway grim wtype mako dbus-daemon \
            dbus-tools mesa-dri-drivers fontconfig google-noto-sans-fonts procps-ng jq python3
      - uses: actions/checkout@v4
      - name: go vet (tagged), web-app tests, host build
        run: |
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
          go vet -tags webkit ./...
          go test -tags webkit ./internal/webapp/... ./internal/webkit/... ./cmd/arctic-webapp/... ./cmd/arctic-webapp-host/...
          go build -tags webkit -o /tmp/arctic-webapp-host ./cmd/arctic-webapp-host
          readelf -d /tmp/arctic-webapp-host | grep -q 'NEEDED.*libwebkitgtk-6\.0\.so\.4'
          CGO_ENABLED=0 go build -o /tmp/arctic-webapp ./cmd/arctic-webapp
          ! readelf -d /tmp/arctic-webapp | grep -q NEEDED
      - name: Headless smoke test (sandbox off only here; bwrap can't create namespaces in this container)
        run: cmd/arctic-webapp-host/dev/smoke.sh --out /tmp/webapp-shots
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: webapp-screenshots, path: /tmp/webapp-shots/*.png, retention-days: 7 }
```

- `shellcheck` (`:52-54`): add `cmd/arctic-webapp-host/dev/*.sh` to the file list.
- `qml` and `shell-tests` pick up the new QML and `*.cjs` files by themselves. `settings/tests`
  runs the new Python test by discovery.
- `rpms`, repo.yml and iso.yml need no edits; they compile the host through build-rpms.sh.
- D10: the work lands through pull requests; `main` only after every job, `go-webkit`
  included, is green (a push to main publishes to every stable system).

### 13. Tests

#### 13.1 Pure Go (job `go`)
Standard `testing`, table-driven, goldens in `testdata/` as in `cmd/arctic-install/main_test.go`.
- `id_test`: generated ids pass an independent `g_application_id_is_valid` implementation and
  the Arctic grammar (Hebrew, emoji, digits, empty names); hash deterministic; 8 digits on
  collision; `--new-copy`.
- `registry_test`, `lock_test`: atomic writes, 0600/0700 modes, migration, `render` re-render,
  concurrent writers (flock), `busy`.
- `desktop_test`: goldens for webkit, chromium, mail-link, non-ASCII names, names with `;`,
  `\`, newlines. Exec never has a URL and has `%` only as `%u` with `handlers:["mailto"]`;
  never `WebBrowser`, never `NoDisplay`, `MimeType` only for mailto.
- `rules_test`: `dotfiles/.config/mango/arctic/rules.conf` has the `activation_bypass` line and
  its regex (Go `regexp`) matches `NewID` output.
- `buildtag_test`: every `.go`, `.c`, `.h` in `internal/webkit` and `cmd/arctic-webapp-host`
  starts with `//go:build cgo && webkit` (C7).
- `version_test`: `webapp.Version == backend.EngineVersion`.
- `psl_test` + `FuzzPSL`: rules, wildcards (`*.ck`), exceptions (`!www.ck`), `co.uk`,
  `github.io`, IP literals, `localhost`, missing-file fallback.
- `htmlhead_test` + `FuzzHead`: unquoted/uppercase attributes; `<script>` containing
  `</head>` and `<`; comments hiding a `<link>`; `<base>`; several theme-color tags with
  `media`; windows-1252 titles, entities, BOM, CRLF, truncated input.
- `manifest_test` + `FuzzManifest`: W3C start_url/scope/id rules, relative `src`,
  `sizes:"any"`, purpose lists, wrong JSON types.
- `loginwall_test`, `name_test`, `candidates_test`: Accounts redirect → origin probes; typed
  deep-URL precedence; WebP dropped; `og:image` ignored.
- `fetch_test` (httptest): 6 redirects, a loop, https → http, 3 MiB HTML, slow body, wrong
  content type, private-address guard (public page → 127.0.0.1 icon refused; private page
  allowed), UA header.
- `ico_test` + `FuzzICO`: PNG in ICO; 32/24/8/4/1 bpp DIBs; all-zero alpha → AND mask;
  truncated/overlapping entries and count 65 rejected without panics.
- `resample_test`, `tile_test` (golden decoded pixels, not PNG bytes), `monogram_test` (SVG
  goldens; palette ⊂ tokens.json; no amber family; every pair ≥ 4.5:1).
- `svg_test`: uses rsvg-convert when present, else `t.Skip`.
- `policy` tests: navigation matrix (nav type × gesture × main frame × new window × popup ×
  scope × links); SSO redirect chains and cross-domain form posts stay in the app; `mailto:`
  with and without a gesture; IP-host apps. `permissions_test`, `downloads_test` (`../../x`,
  `.bashrc`, 300-byte names), `crash_test` (fake clock), `tls_test` (private-host
  classification).
- `theme_test`: reads `dotfiles/.config/arctic/themes/{winter,polar-night}/theme.json`,
  compares HostCSS with goldens.
- `runtime_test`: detection against a fake filesystem root; argv and env goldens (NVIDIA,
  software rendering, sandbox variable stripped); Chromium `wm_class` vectors (filled in M7).
- `focus_test`: fake `mmsg` on `PATH` (like `shell/tests/test_helpers.py:38-41`): client found
  → `focusid` argv; not found → launch; `mmsg` missing → launch; both `appid`/`app_id` keys.
- `handlers_test`: mailto parsing, percent-encoding into each template, scope check, anything
  but `mailto:` ignored, literal `%u` ignored.
- `catalog_test`: runtime table matches `modules/browser/*/module.toml`.
- `api_test`: pins snake_case wire names and serve transcripts (C2).
- `cmd/arctic-webapp/main_test.go`: usage exits 2, errors exit 1, every `--json` output is
  exactly one line with `ok` and (on failure) a string `error` and `code`, nothing on stderr
  (C3, C4); temp HOME/XDG tree and an httptest fixture site; refuses root (skipped unless
  root).
- Source scan: fails on `"sh", "-c"`, `bash -c`, `InsecureSkipVerify`, and
  `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS` anywhere except `*_test.go` and `dev/smoke.sh`.

Integration (pure Go), fixture sites in `discover/testdata/sites/<name>/`: `manifest`,
`apple-touch`, `ico-only`, `svg-only`, `webp-only` (→ monogram), `no-icon`, `login-redirect`,
`redirect-chain`, `downgrade`, `oversized`, `slow`, `non-html`, `404`, `meta-refresh`,
`mail` (a table site on httptest via an override hook). Each runs Inspect → Install → List →
Set (icon change bumps `.r1`) → Update → Remove `--keep-data` → kept listing → reinstall (same
id, same profile) → Forget, asserting exactly which files appear and disappear.

Fuzzing: `FuzzHead`, `FuzzManifest`, `FuzzICO`, `FuzzPSL`, `FuzzDesktopName`; seeds in
`testdata/fuzz/`; plain `go test` runs the seeds. M8 runs each for 10 minutes locally.

#### 13.2 Tagged (job `go-webkit`)
`internal/webkit/webkit_test.go`: `psl.Site` agrees with `soup_tld_get_base_domain`; WebKit
version ≥ the spec floor; `--version` works without a display; the host's undefined `webkit_*`
symbols equal `symbols.allow` (D-4).

#### 13.3 Shell and Settings
- New `shell/tests/test-icons.cjs`: loads `assets/Icons.js` with `design-data.js` injected
  (strip the `.import` line as `test-launcher.cjs:4-9` strips `.pragma`); `tileFor` returns
  `''` for `org.arcticlinux.WebApp.Signal_1a2b3c` named "Signal" and still returns `signal` for
  `org.signal.Signal`.
- New `shell/tests/test-webapp-service.cjs` (or a Python fake-`serve` test): the event/response
  demultiplexing logic lives in a small `shell/WebAppProtocol.js` so it is testable in node.
- New `settings/tests/test_webapps.py`: fake `arctic-webapp` on `PATH`; pass-through of `ok`
  and `error`; the KEY allowlist; missing binary message.
- qmllint covers `WebAppService.qml`, `WebAppPage.qml`, `WebAppList.qml`, `WebAppsPage.qml`.
- `settings/dev/headless.sh --smoke --fixtures` loads `WebAppsPage.qml` with the fake binary.

#### 13.4 Headless smoke test
`cmd/arctic-webapp-host/dev/smoke.sh` runs `ARCTIC_WEBKIT_SMOKE=1 go test -tags webkit -run
Smoke ./cmd/arctic-webapp-host` (skips unless the variable is set, like `ARCTIC_E2E_DEVICE`).
Setup: sway with a HEADLESS output inside `dbus-run-session`, mako running, `dbus-monitor` on
`org.freedesktop.Notifications`; a temp HOME from `dotfiles/install.sh --target`;
`LIBGL_ALWAYS_SOFTWARE=1` and `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1` (container only);
a fake default browser (a `.desktop` whose Exec appends `%u` to a file, set as the
`x-scheme-handler/https` default in the temp `mimeapps.list`); httptest fixture pages.
Assertions:
1. The window's app_id equals the id (`swaymsg -t get_tree`).
2. The UA equals `webapp.FetchUserAgent` (C10).
3. The title follows the page; `matchMedia('(prefers-color-scheme: dark)')` logged in both
   themes.
4. An in-scope link stays in the app.
5. An out-of-scope link click lands in the fake browser's file.
6. A cross-domain form post stays in the app (C8).
7. A `window.open` popup completes a `postMessage` handshake with its opener.
8. The Notify call carries `app_name` = Name and hint `desktop-entry` = id (`dbus-monitor`,
   D-10).
9. A download lands with a unique name.
10. A second start leaves one window and the pid file unchanged (D-5).
11. SIGHUP applies a zoom change.
12. `kill -SEGV` of the WebKitWebProcess reloads the page.
13. `arctic-webapp remove` stops the host.
14. Rewriting `~/.config/arctic/theme` changes the header colour.
15. Ctrl+F opens the find bar on a plain page and not on a page that calls `preventDefault()`
    (`wtype`).
16. grim screenshots are uploaded.

#### 13.5 Manual matrix (M8: Fedora 44 under Mango, plus one NVIDIA laptop)
- Sign-in: Gmail, Calendar, Outlook (Google and Microsoft SSO) in the WebKit runtime.
- Everyday: Notion, Todoist, GitHub, YouTube, YouTube Music, Slack, Teams chat, Discord text,
  WhatsApp Web, Proton Mail, Figma, Excalidraw, Photopea, vscode.dev.
- Self-hosted: Home Assistant over http and with a self-signed certificate.
- Fallback: Spotify and Netflix in Brave, Meet in Chromium (warning, suggested runtime,
  `StartupWMClass` per brand, launch-or-focus).
- Mail links: each `handlers.json` template from `xdg-open mailto:a@b.c?subject=x`.
- Also: `activation_bypass` focus; popup floating; ISO size before/after; memory per app;
  launcher shows a new app and its icon without a shell restart.

### 14. Docs to update (contract first: BUILD-SPEC.md:5, Contributing.md:19-23)
- `docs/BUILD-SPEC.md`: new **§11 Web apps** (ids, paths, `app.json`, `.desktop` keys incl.
  the mailto variant, CLI + `--json` shapes, serve API and error codes, runtimes, WebKitGTK
  floor rule, security rules); §1 layout (`:15-17` add `cmd/arctic-webapp/`,
  `cmd/arctic-webapp-host/`, `internal/webapp/`, `internal/webkit/`; `:50` ci.yml line adds
  "cgo WebKit host build + headless smoke"); §2 new `arctic-webapps` row and amend `:72`: "Go
  is standard library only; the web-app host also uses cgo against Fedora's WebKitGTK 6.0,
  GTK 4 and libsoup 3, built with `-tags webkit`"; metapackage list `:80-90` adds
  arctic-webapps; §9 `:506` "all 15 packages" → 16 and re-measure "about 9 MB"; `:529` "No
  debuginfo." stays true.
- `docs/PLAN.md`: §3 tree (`:74-118`); new decision row after D12: "D13 Web apps: a pure-Go
  manager + a WebKitGTK 6.0 cgo host, with a Chromium-family fallback runtime" (use the next
  free number if another 0.3.0 section takes D13).
- `docs/wiki/Contributing.md:33`: "Go uses the standard library only (the web-app host also
  uses cgo with Fedora's WebKitGTK 6.0 and GTK 4, built with `-tags webkit`), so the RPM builds
  offline." Add to the checks (`:60-72`): `CGO_ENABLED=1 go vet -tags webkit ./...` (after
  `sudo dnf install gcc webkitgtk6.0-devel gtk4-devel libsoup3-devel`) and
  `node shell/tests/test-icons.cjs`; add rows to "Where things live".
- `docs/wiki/Architecture.md:29-30`, `README.md:50`, `docs/wiki/Building-from-Source.md:206`
  (new "Web apps" row: `go run ./cmd/arctic-webapp inspect example.org`,
  `cmd/arctic-webapp-host/dev/smoke.sh`) and the CI table `:219-224`.
- New `docs/wiki/Web-Apps.md` (linked from `_Sidebar.md` under "Use it"): what a web app is;
  adding and removing; what works and what doesn't (calls, DRM, device APIs) and the engine
  choice; sign-in data and "Saved sign-in data"; email links; hotkeys (9.4); troubleshooting
  (`arctic-webapp set ID --rendering software`, NVIDIA, blank windows, log path); privacy (no
  telemetry, no third-party icon services).
- `docs/wiki/Apps-and-Software.md` §"Get apps" (`:314`) and a "Remove apps" subsection;
  `Release-Notes.md` 0.3.0 entry; `shell/README.md` (WebAppService/WebAppPage/WebAppList);
  `Settings.md` (Web apps page).

### 15. Milestones

| # | Milestone | Days | Work package |
|---|---|---|---|
| M0 | Contract: BUILD-SPEC §11, §1/§2/§9 edits, PLAN D13, wiki stub | 1–2 | WA-0 |
| M1 | Core: ids, paths, registry + flock, desktop writer + goldens, safe remove, pid/running, CLI `list/remove/forget/run(exec)/repair/version` with one-line `--json`; rules_test, buildtag_test, version_test | 3–4 | WA-1 |
| M2 | Discovery: normalise, fetcher + limits + private-address guard, head tokenizer + fuzz, charset, manifest, PSL, login-wall probes, names, candidates, compat table, categories | 5–6 | WA-2 |
| M3 | Icons: sniffing, ICO/DIB, rsvg via stdin, resampler, tile/maskable, token monograms, hicolor writer, revisions, `render-sample` | 3–4 | WA-3 |
| M4 | Manage + API: Inspect sessions/previews, Install/Update/Set/Remove/Forget/ClearData, `serve`, JSON goldens (`Hello.runtimes` lists only `webkit` until M7) | 3–4 | WA-4 |
| M5 | Host MVP: shim, GtkApplication + single instance + pid rule, window and header, session and cookies, navigation policy, external links, popups/OAuth, theme CSS + live reload, state.json, SIGTERM/SIGHUP; rules.conf line + mangowm ≥ 0.17.3 | 6–8 | WA-5 |
| M6 | Packaging and CI: BuildRequires, subpackage, `%build`, `%install`, `%check` ELF skip + assertions, `%files`, Requires/Recommends, config.kiwi, `go-webkit` job + smoke script; measure ISO and update size | 3–4 | WA-6 |
| M7 | Host features: permission banners + store, GNotification, downloads, find/zoom/print/context menu, full screen, audio, crash/offline/TLS pages + certificate pinning, favicon upgrade; Chromium runtime (`runtime.go` table + `catalog_test`, Flatpak profiles, `wm_class` measured per browser, launch-or-focus `focus.go`, runtime-missing fallback); mail links (`handlers.go` + `handlers.json`) | 9–11 | WA-7 |
| M4s | Shell: WebAppService, WebAppPage, WebAppList, tileFor skip, app-owner web branch | 3–4 | WA-8 (after M4) |
| M4t | Settings: commands, WebAppsPage, tests, headless fixture | 2–3 | WA-9 (after M4) |
| M8 | Hardening: manual matrix, NVIDIA and sandbox-denial checks, every 🔍 below, copy review, fuzzing time | 4–5 | WA-10 |

Totals: engine ≈ 37–48 developer-days, plus 5–7 days of shell and Settings UI. First usable
WebKit-only build (add, run, remove from Get apps and Remove apps): M0–M5 + M6 + M4s,
≈ 27–34 days. The spec `Version: 0.3.0` bump itself belongs to the release work (D1).

### 16. Open issues

- 🔍 Quickshell 0.2.1 `DesktopEntry.execute()` with `%u` in Exec (dropped or passed
  literally); `run` ignores a literal `%u` either way (M4, unit test + one manual launch).
- 🔍 Qt/Quickshell showing a newly written hicolor icon without a shell restart (icon
  revisions reduce the risk; M8).
- 🔍 Mango floating transient popup windows (M5; else the `title:^Pop-up: ` rule).
- 🔍 `mmsg get all-clients` app-id key name (M7).
- 🔍 Chromium `--app` app_id prefix per brand and per Flatpak (M7, pinned in `runtime_test`).
- 🔍 SIGTERM to a Flatpak browser's host-side pid closes it (M7; else `state` "Close it first").
- 🔍 Google and Microsoft sign-in in a default-UA WebKitGTK 2.54 view (M8 manual matrix). If
  refused, the preview recommends a Chromium runtime for those sites through `compat.json`.
- 🔍 Page `prefers-color-scheme` following GTK's scheme in 2.54 (smoke test logs it).
- 🔍 GTK 4.22 re-reading `~/.config/gtk-4.0/gtk.css` after a theme switch (M5; fallback in 8.10).
- 🔍 GLib's GNotification backend choice on Mango with xdg-desktop-portal-gtk (smoke assertion 8).
- 🔍 WebKitGTK 6.0 returning unhandled keys to GTK (smoke assertion 15).
- 🔍 `handlers.json` compose templates (M8) and the compat hosts not named in research.
- 🔍 Whether dnf5 adds newly added weak deps on upgrade (not relied on: arctic-desktop
  Requires arctic-webapps).
- 🔍 Per-app memory (estimated 150–300 MB) and the ISO delta (+45–50 MB estimated); the 2 GiB
  / Zen decision rule in 11.2.
- 🔍 MPRIS media keys from a WebKit web app and the GStreamer H.264/AV1 plugin package names on
  F44 (M8).
- Flatpak browsers and managed theme policies belong to the `chromium-theme-policy` hook's
  owner (8.14).
- `site_colour` (D-3) and category-tint monograms (D-2) are deliberate departures for D9; a
  design review may prefer site colours for monograms, which would need a D9 exception.
- Numbering: PLAN D13 and BUILD-SPEC §11 may collide with other 0.3.0 sections; the doc
  editor assigns final numbers.
