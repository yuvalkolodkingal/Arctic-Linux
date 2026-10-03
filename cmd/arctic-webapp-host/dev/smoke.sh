#!/usr/bin/env bash
# Headless smoke test of the web-app window (CI job go-webkit; Fedora 44 with sway, grim,
# python3, webkitgtk6.0-devel). It builds arctic-webapp and arctic-webapp-host, serves a small
# fixture site, adds it as a web app in a throwaway HOME and runs it in a headless sway:
#
#   cmd/arctic-webapp-host/dev/smoke.sh [--out DIR]
#
# Checks: the window's Wayland app_id is the app id, the title follows the page, the page sees
# webapp.FetchUserAgent (so discovery fetches as the app will), the page's favicon replaces the
# letter icon through the manager, theme switches update the header and website live, notifications set
# to Block stop in the open window, a failed download isn't reported as finished, a second start
# keeps one window and the pid file, SIGTERM saves the window state, and remove stops the app. Screenshots land in DIR (default
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
cp "$REPO/cmd/arctic-webapp-host/dev/fixture-server.py" "$WORK/site/server.py"
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

# The Arctic themes, Winter first (the window follows ~/.config/arctic/current live).
mkdir -p "$XDG_CONFIG_HOME/arctic/themes"
cp "$REPO/cmd/arctic-webapp-host/dev/notification-fixture.py" "$WORK/notification-fixture.py"
cp -r "$REPO/dotfiles/.config/arctic/themes/winter" "$REPO/dotfiles/.config/arctic/themes/polar-night" "$XDG_CONFIG_HOME/arctic/themes/"
ln -sfn themes/winter "$XDG_CONFIG_HOME/arctic/current"
echo winter > "$XDG_CONFIG_HOME/arctic/theme"

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
SWAY_PID=$!
NOTIFY_PID=""
trap 'kill "$SWAY_PID" 2>/dev/null || true; if [ -n "$NOTIFY_PID" ]; then kill "$NOTIFY_PID" 2>/dev/null || true; fi' EXIT
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

python3 "$WORK/notification-fixture.py" "$WORK/notifications.jsonl" >"$WORK/notifications.log" 2>&1 &
NOTIFY_PID=$!
wait_for 'gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.GetCapabilities >/dev/null 2>&1' || fail "notification fixture unavailable"

# The host directly, as `arctic-webapp run` would exec it: run removes the sandbox kill switch
# this container needs (its argv and environment are unit-tested in internal/webapp/manage).
arctic-webapp-host --app-id "$ID" >"$WORK/host.log" 2>&1 &
wait_for '[ -n "$(windows)" ]' || fail "no window with app_id $ID"
wait_for 'windows | grep -q "Smoke Home"' || fail "title did not follow the page: $(windows)"
sleep 2
grim "$OUT/webapp-window.png" && echo "screenshot: $OUT/webapp-window.png"
# Both the window and the website must follow the desktop, without reloading the page.
wait_for 'grep -q "^/theme-result?dark=false" "$WORK/requests.log"' || fail "website did not start in the light desktop theme"
PAGE_LOADS="$(grep -c "^/$(printf '\t')" "$WORK/requests.log")"
HEADER_LIGHT="$(grim -g "640,4 1x1" -t ppm - | od -An -tx1 | tail -1)"
ln -sfn themes/polar-night "$XDG_CONFIG_HOME/arctic/current"
echo polar-night > "$XDG_CONFIG_HOME/arctic/theme"
wait_for 'grep -q "^/theme-result?dark=true" "$WORK/requests.log"' || fail "website did not switch to dark live"
sleep 1.5
HEADER_DARK="$(grim -g "640,4 1x1" -t ppm - | od -An -tx1 | tail -1)"
[ "$HEADER_LIGHT" != "$HEADER_DARK" ] || fail "the header did not follow the theme switch ($HEADER_LIGHT)"
grim "$OUT/webapp-window-dark.png" && echo "screenshot: $OUT/webapp-window-dark.png"
LIGHT_REPORTS="$(grep -c '^/theme-result?dark=false' "$WORK/requests.log" || true)"
ln -sfn themes/winter "$XDG_CONFIG_HOME/arctic/current"
echo winter > "$XDG_CONFIG_HOME/arctic/theme"
wait_for '[ "$(grep -c "^/theme-result?dark=false" "$WORK/requests.log" || true)" -gt "$LIGHT_REPORTS" ]' || fail "website did not switch back to light live"
[ "$(grep -c "^/$(printf '\t')" "$WORK/requests.log")" = "$PAGE_LOADS" ] || fail "theme switch reloaded the website"
grep '^/theme-result?' "$WORK/requests.log" > "$OUT/theme.txt"

UA_GOT="$(grep "^/$(printf '\t')" "$WORK/requests.log" | tail -1 | cut -f2)"
[ "$UA_GOT" = "$UA_WANT" ] || fail "user agent: the page saw \"$UA_GOT\"; webapp.FetchUserAgent is \"$UA_WANT\""
PID1="$(cat "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" 2>/dev/null || true)"
[ -n "$PID1" ] || fail "no pid file"

# The page's favicon replaces the letter icon (host → arctic-webapp icon → revision .r1).
wait_for 'grep -q "\"source\": \"host-favicon\"" "$XDG_DATA_HOME/arctic/webapps/$ID/app.json"' || fail "favicon upgrade: $(grep -A3 '"icon"' "$XDG_DATA_HOME/arctic/webapps/$ID/app.json")"
[ -f "$XDG_DATA_HOME/icons/hicolor/128x128/apps/$ID.r1.png" ] || fail "favicon upgrade: no .r1 icon"
grep -q "^Icon=$ID.r1$" "$XDG_DATA_HOME/applications/$ID.desktop" || fail "favicon upgrade: launcher entry not updated"

# Notifications set to Block reach the open window, though WebKit granted them at start: the
# page's next notification is closed at once (the page hears its close event).
arctic-webapp set "$ID" --notifications block --json | grep -q '"applied":"live"' || fail "notifications block: not applied live"
sleep 0.5
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/notify" >/dev/null 2>&1 || fail "opening /notify"
wait_for 'grep -q "^/notification-closed" "$WORK/requests.log"' || fail "a blocked notification was shown"

# A download that fails is never announced as finished; one that completes is.
APPLOG="$XDG_STATE_HOME/arctic/webapps/$ID.log"
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/broken.bin" >/dev/null 2>&1 || fail "opening /broken.bin"
wait_for 'grep -q "download to .*broken" "$APPLOG"' || fail "the broken download didn't start"
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/good.bin" >/dev/null 2>&1 || fail "opening /good.bin"
wait_for 'grep -q "downloaded .*good" "$APPLOG"' || fail "a finished download wasn't reported"
if grep -q "downloaded .*broken" "$APPLOG"; then fail "a failed download was reported as finished: $(grep download "$APPLOG")"; fi

# A second start raises the running app: still one window, same pid file.
timeout 20 arctic-webapp-host --app-id "$ID" >/dev/null 2>&1 || fail "second start did not exit"
sleep 1
[ "$(windows | grep -c .)" = 1 ] || fail "second start: $(windows | grep -c .) windows"
[ "$(cat "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" 2>/dev/null)" = "$PID1" ] || fail "second start changed the pid file"

# GTK/WebKit consumes the Wayland image clipboard from a real input gesture.
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/paste" >/dev/null 2>&1
sleep 1
wtype -s 1200 -M ctrl -k v -m ctrl -s 300 &
PASTE_INPUT=$!
sleep 0.3
wl-copy --type image/png < "$XDG_DATA_HOME/icons/hicolor/128x128/apps/$ID.r1.png"
wl-paste --list-types > "$OUT/clipboard-types.txt"
wait "$PASTE_INPUT"
grim "$OUT/clipboard.png"
wait_for 'grep -Eq "^/paste-result\?files=1&type=image%2Fpng|^/paste-inserted\?images=1" "$WORK/requests.log"' || fail "image clipboard did not reach page"
grep "^/paste-" "$WORK/requests.log" > "$OUT/clipboard-result.txt"
wl-copy --clear

# Native file chooser: keyboard file selection reaches WebKit's file input.
printf 'fixture' > "$WORK/upload.txt"
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/upload" >/dev/null 2>&1
sleep 1
wtype -s 200 -k Return -s 200
sleep 1
grim "$OUT/upload-dialog.png"
wtype -s 200 -M ctrl -k l -m ctrl -s 200 "$WORK/upload.txt" -s 200 -k Return -s 200
sleep 1
grim "$OUT/upload-after.png"
wait_for 'grep -q "^/upload-result?count=1&name=upload.txt" "$WORK/requests.log"' || fail "native upload selection failed"

# Asynchronous save: cancellation must not finish a download, then save a new file.
arctic-webapp set "$ID" --ask-download on --json >/dev/null
sleep 0.3
BEFORE=$(grep -c 'downloaded .*good' "$APPLOG")
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/good.bin" >/dev/null 2>&1
sleep 1
wtype -s 200 -k Escape -s 200
sleep 0.5
[ "$(grep -c 'downloaded .*good' "$APPLOG")" = "$BEFORE" ] || fail "cancelled chooser saved download"
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/good.bin" >/dev/null 2>&1
sleep 1
grim "$OUT/save-dialog.png"
wtype -s 200 -M ctrl -k l -m ctrl -s 100 -M ctrl -k a -m ctrl -s 100 "$WORK/saved.bin" -s 200 -k Return -s 200
sleep 1
grim "$OUT/save-after.png"
wait_for '[ -f "$WORK/saved.bin" ]' || fail "native save selection failed"
[ "$(cat "$WORK/saved.bin" 2>/dev/null)" = 0123456789 ] || fail "saved download content differs"
arctic-webapp set "$ID" --ask-download off --json >/dev/null

# Native lifecycle: a compositor close hides the window, preserving the primary process.
arctic-webapp set "$ID" --keep-running on --start-at-login on --json >/dev/null
sleep 0.3
swaymsg "[app_id=\"$ID\"] kill" >/dev/null
wait_for '[ -z "$(windows)" ]' || fail "close did not hide window"
kill -0 "$PID1" || fail "hidden app exited"
[ "$(cat "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid")" = "$PID1" ] || fail "hidden process changed"
timeout 20 arctic-webapp-host --app-id "$ID" >/dev/null 2>&1 || fail "hidden activation failed"
wait_for '[ -n "$(windows)" ]' || fail "activation did not restore window"

# Website notification actions restore the hidden app and reach its conversation handler.
arctic-webapp set "$ID" --notifications allow --json >/dev/null
sleep 0.3
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/conversation" >/dev/null 2>&1
swaymsg "[app_id=\"$ID\"] kill" >/dev/null
wait_for 'grep -q "Conversation 42" "$WORK/notifications.jsonl"' || fail "hidden notification not delivered"
grep -q "$ID" "$WORK/notifications.jsonl" || fail "notification missing app identity"
gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.arcticlinux.TestNotifications.ClickLatest >/dev/null
wait_for 'grep -q "^/notification-target" "$WORK/requests.log"' || fail "notification action lost conversation"
wait_for '[ -n "$(windows)" ]' || fail "notification did not restore window"

# Media uses the actual WebKit view and D-Bus service, not a mocked player.
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/media" >/dev/null 2>&1
PLAYER="Arctic_${ID##*.}"
wait_for 'playerctl -p "$PLAYER" metadata title 2>/dev/null | grep -q "Native media fixture"' || fail "MPRIS metadata unavailable"
playerctl -p "$PLAYER" play || fail "MPRIS play action failed"
wait_for '[ "$(playerctl -p "$PLAYER" status 2>/dev/null)" = Playing ]' || fail "MPRIS did not play"
playerctl -p "$PLAYER" pause || fail "MPRIS pause action failed"
wait_for '[ "$(playerctl -p "$PLAYER" status 2>/dev/null)" = Paused ]' || fail "MPRIS did not pause"
playerctl -p "$PLAYER" position 2 || fail "MPRIS seek action failed"
wait_for 'playerctl -p "$PLAYER" position 2>/dev/null | grep -q "^2"' || fail "MPRIS seek position differs"
playerctl -p "$PLAYER" volume 0.5 || fail "MPRIS volume failed"
wait_for 'playerctl -p "$PLAYER" volume 2>/dev/null | grep -q "^0.5"' || fail "MPRIS volume differs"
timeout 20 arctic-webapp-host --app-id "$ID" --url "http://127.0.0.1:$PORT/capabilities" >/dev/null 2>&1
wait_for 'grep -q "^/capabilities-result" "$WORK/requests.log"' || fail "capability probe failed"
grep '^/capabilities-result' "$WORK/requests.log" > "$OUT/capabilities.txt"
wait_for '! playerctl -l 2>/dev/null | grep -q "$PLAYER"' || fail "stale MPRIS after navigation"

# Fullscreen and fractional scaling preserve a usable window and keyboard actions.
wtype -s 200 -k F11 -s 200
swaymsg -t get_tree | python3 -c 'import json,sys
stack=[json.load(sys.stdin)]; found=False
while stack:
    n=stack.pop(); stack+=n.get("nodes",[])+n.get("floating_nodes",[])
    if n.get("app_id")==sys.argv[1]: found=n.get("fullscreen_mode",0)>0
sys.exit(0 if found else 1)' "$ID" || fail "fullscreen shortcut failed"
wtype -s 200 -k F11 -s 200
swaymsg output HEADLESS-1 scale 1.25 >/dev/null
sleep 0.5
grim "$OUT/webapp-scaled.png"
swaymsg output HEADLESS-1 scale 1 >/dev/null

# SIGTERM (logout) closes the window the normal way: it saves its state, and the pid file goes.
kill -TERM "$PID1"
wait_for '[ -z "$(windows)" ]' || fail "SIGTERM did not close the window"
wait_for 'grep -q "last_url.*http://127.0.0.1" "$XDG_DATA_HOME/arctic/webapps/$ID/state.json" 2>/dev/null' || fail "no state.json after SIGTERM"
cp "$XDG_DATA_HOME/arctic/webapps/$ID/state.json" "$OUT/state.json"
cp "$APPLOG" "$OUT/host-state.log"
ls -la "$XDG_DATA_HOME/arctic/webapps/$ID" > "$OUT/state-files.txt"
wait_for '[ ! -e "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" ]' || fail "pid file left after SIGTERM"
arctic-webapp-host --app-id "$ID" >>"$WORK/host.log" 2>&1 &
wait_for '[ -n "$(windows)" ]' || fail "no window after a restart"

# A hidden startup maps no window; a second activation restores it.
arctic-webapp quit "$ID" --json >/dev/null
wait_for '[ ! -e "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" ]' || fail "Quit left a process"
arctic-webapp-host --app-id "$ID" --background >>"$WORK/host.log" 2>&1 &
wait_for '[ -e "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" ]' || fail "hidden startup failed"
sleep 1
[ -z "$(windows)" ] || fail "hidden startup mapped a window"
timeout 20 arctic-webapp-host --app-id "$ID" >/dev/null 2>&1
wait_for '[ -n "$(windows)" ]' || fail "startup instance did not restore"
swaymsg "[app_id=\"$ID\"] kill" >/dev/null
wait_for '[ -z "$(windows)" ]' || fail "second hide failed"
arctic-webapp set "$ID" --keep-running off --json >/dev/null
wait_for '[ ! -e "$XDG_RUNTIME_DIR/arctic-webapp/$ID.pid" ]' || fail "disabling background left hidden process"
arctic-webapp-host --app-id "$ID" >>"$WORK/host.log" 2>&1 &
wait_for '[ -n "$(windows)" ]' || fail "no window before remove"

# remove stops the app.
arctic-webapp remove "$ID" --json | grep -q '"stopped":true' || fail "remove did not stop the app"
wait_for '[ -z "$(windows)" ]' || fail "window still open after remove"
[ ! -e "$XDG_CONFIG_HOME/autostart/$ID.desktop" ] || fail "remove left startup entry"

kill "$SWAY_PID" 2>/dev/null
exit "$FAILED"
INNER
chmod +x "$WORK/inner.sh"
export SWAY WORK OUT ID UA_WANT PORT
if dbus-run-session -- "$WORK/inner.sh"; then
  echo "webapp smoke: PASS"
else
  echo "webapp smoke: FAIL (logs in $WORK)"
  grep -v '^[a-z0-9]* *0x' "$WORK/host.log" | head -60 || true
  exit 1
fi
