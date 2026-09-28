#!/usr/bin/env bash
# Headless smoke test of the web-app window (CI job go-webkit; Fedora 44 with sway, grim,
# python3, webkitgtk6.0-devel). It builds arctic-webapp and arctic-webapp-host, serves a small
# fixture site, adds it as a web app in a throwaway HOME and runs it in a headless sway:
#
#   cmd/arctic-webapp-host/dev/smoke.sh [--out DIR]
#
# Checks: the window's Wayland app_id is the app id, the title follows the page, the page sees
# webapp.FetchUserAgent (so discovery fetches as the app will), the page's favicon replaces the
# letter icon through the manager, a second start keeps one window and the pid file, and remove
# stops the app. Screenshots land in DIR (default
# /tmp/webapp-shots). The navigation rules themselves are unit-tested in internal/webapp/policy.
#
# Containers can't create the user namespaces WebKit's bubblewrap sandbox needs, so this script
# (and only this script) sets WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 and starts the host
# directly; `arctic-webapp run` removes that variable for real launches.
set -euo pipefail

OUT=/tmp/webapp-shots
while (( $# )); do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    *) echo "usage: $0 [--out DIR]" >&2; exit 2 ;;
  esac
done
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
WORK="$(mktemp -d /tmp/webapp-smoke.XXXXXX)"
mkdir -p "$OUT" "$WORK/bin" "$WORK/site" "$WORK/home"
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod

(cd "$REPO" && CGO_ENABLED=0 go build -o "$WORK/bin/arctic-webapp" ./cmd/arctic-webapp)
(cd "$REPO" && CGO_ENABLED=1 go build -tags webkit -o "$WORK/bin/arctic-webapp-host" ./cmd/arctic-webapp-host)
UA_WANT="$(sed -n 's/^const FetchUserAgent = "\(.*\)"$/\1/p' "$REPO/internal/webapp/version.go")"

# ---- fixture site: records every request's path and User-Agent
cat > "$WORK/site/server.py" <<'PY'
import http.server, os, struct, sys, zlib
LOG = sys.argv[2]
def png(size, rgb):
    raw = b"".join(b"\0" + bytes(rgb) * size for _ in range(size))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
ICON = png(96, (40, 110, 200))
PAGES = {
    "/": b"<!doctype html><html><head><title>Smoke Home</title><link rel=manifest href=/app.webmanifest></head>"
         b"<body style='background:#9cf'><h1>Smoke</h1><a id=out href='https://example.com/elsewhere'>out</a>"
         b"<a id=in href='/second'>in</a></body></html>",
    "/second": b"<!doctype html><title>Second Page</title><p>second</p>",
    "/app.webmanifest": b'{"name":"Smoke App","start_url":"/","icons":[]}',
}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(LOG, "a") as f:
            f.write(self.path + "\t" + self.headers.get("User-Agent", "") + "\n")
        body = PAGES.get(self.path.split("?")[0])
        # The favicon appears only after install, so the app starts with a letter icon and the
        # window's favicon upgrade has something to do.
        if self.path == "/favicon.ico" and os.path.exists(LOG + ".icon"):
            body = ICON
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        ctype = "text/html; charset=utf-8"
        if self.path.endswith("manifest"):
            ctype = "application/manifest+json"
        elif self.path == "/favicon.ico":
            ctype = "image/png"
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
PORT=18765
python3 "$WORK/site/server.py" "$PORT" "$WORK/requests.log" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 50); do python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:$PORT/')" 2>/dev/null && break; sleep 0.1; done

# ---- throwaway session
export HOME="$WORK/home" XDG_RUNTIME_DIR="$WORK/run" XDG_CONFIG_HOME="$WORK/home/.config"
export XDG_DATA_HOME="$WORK/home/.local/share" XDG_CACHE_HOME="$WORK/home/.cache" XDG_STATE_HOME="$WORK/home/.local/state"
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME/applications" && chmod 700 "$XDG_RUNTIME_DIR"
export PATH="$WORK/bin:$PATH" ARCTIC_WEBAPP_HOST="$WORK/bin/arctic-webapp-host"
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
export ARCTIC_WEBAPP_ALLOW_ROOT=1
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 GDK_BACKEND=wayland

ID="$(arctic-webapp install "http://127.0.0.1:$PORT/" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"], d; print(d["app"]["id"])')"
echo "installed $ID"
touch "$WORK/requests.log.icon"

SWAY="$(command -v sway)"
if command -v getcap >/dev/null && [[ -n "$(getcap "$SWAY" 2>/dev/null)" ]]; then cp "$SWAY" "$WORK/sway"; SWAY="$WORK/sway"; fi
printf 'output HEADLESS-1 resolution 1280x800\ndefault_border none\n' > "$WORK/sway.conf"

cat > "$WORK/inner.sh" <<'INNER'
#!/usr/bin/env bash
set -uo pipefail
fail() { echo "FAIL: $*"; FAILED=1; }
FAILED=0
"$SWAY" -c "$WORK/sway.conf" >"$WORK/sway.log" 2>&1 &
for _ in $(seq 100); do ls "$XDG_RUNTIME_DIR"/wayland-[0-9] >/dev/null 2>&1 && break; sleep 0.05; done
WAYLAND_DISPLAY="$(basename "$(ls "$XDG_RUNTIME_DIR"/wayland-[0-9] | head -1)")"
SWAYSOCK="$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock | head -1)"
export WAYLAND_DISPLAY SWAYSOCK
tree() { swaymsg -t get_tree 2>/dev/null; }
windows() { tree | python3 -c 'import json,sys
def walk(n):
    if n.get("app_id") == sys.argv[1]: yield n
    for c in n.get("nodes", []) + n.get("floating_nodes", []): yield from walk(c)
print("\n".join(w.get("name") or "" for w in walk(json.load(sys.stdin))))' "$ID"; }
wait_for() { for _ in $(seq 150); do eval "$1" && return 0; sleep 0.2; done; return 1; }

# The host directly, as `arctic-webapp run` would exec it: run removes the sandbox kill switch
# this container needs (its argv and environment are unit-tested in internal/webapp/manage).
arctic-webapp-host --app-id "$ID" >"$WORK/host.log" 2>&1 &
wait_for '[ -n "$(windows)" ]' || fail "no window with app_id $ID"
wait_for 'windows | grep -q "Smoke Home"' || fail "title did not follow the page: $(windows)"
sleep 2
grim "$OUT/webapp-window.png" && echo "screenshot: $OUT/webapp-window.png"
UA_GOT="$(grep "^/$(printf '\t')" "$WORK/requests.log" | tail -1 | cut -f2)"
[ "$UA_GOT" = "$UA_WANT" ] || fail "user agent: the page saw \"$UA_GOT\"; webapp.FetchUserAgent is \"$UA_WANT\""
PID1="$(cat "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" 2>/dev/null || true)"
[ -n "$PID1" ] || fail "no pid file"

# The page's favicon replaces the letter icon (host → arctic-webapp icon → revision .r1).
wait_for 'grep -q "\"source\": \"host-favicon\"" "$XDG_DATA_HOME/arctic/webapps/$ID/app.json"' || fail "favicon upgrade: $(grep -A3 '"icon"' "$XDG_DATA_HOME/arctic/webapps/$ID/app.json")"
[ -f "$XDG_DATA_HOME/icons/hicolor/128x128/apps/$ID.r1.png" ] || fail "favicon upgrade: no .r1 icon"
grep -q "^Icon=$ID.r1$" "$XDG_DATA_HOME/applications/$ID.desktop" || fail "favicon upgrade: launcher entry not updated"

# A second start raises the running app: still one window, same pid file.
timeout 20 arctic-webapp-host --app-id "$ID" >/dev/null 2>&1 || fail "second start did not exit"
sleep 1
[ "$(windows | grep -c .)" = 1 ] || fail "second start: $(windows | grep -c .) windows"
[ "$(cat "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" 2>/dev/null)" = "$PID1" ] || fail "second start changed the pid file"

# remove stops the app.
arctic-webapp remove "$ID" --json | grep -q '"stopped":true' || fail "remove did not stop the app"
wait_for '[ -z "$(windows)" ]' || fail "window still open after remove"

pkill -f "$SWAY" 2>/dev/null
exit "$FAILED"
INNER
chmod +x "$WORK/inner.sh"
export SWAY WORK OUT ID UA_WANT
if dbus-run-session -- "$WORK/inner.sh"; then
  echo "webapp smoke: PASS"
else
  echo "webapp smoke: FAIL (logs in $WORK)"
  grep -v '^[a-z0-9]* *0x' "$WORK/host.log" | head -60 || true
  exit 1
fi
