#!/usr/bin/env bash
# Verify Chromium app-window theme following and real WebRTC data/audio/video on Fedora.
# --no-sandbox is confined to this container test; production BrowserExec keeps the sandbox.
set -euo pipefail
OUT=/tmp/chromium-webapp-shots
if [[ ${1:-} == --out ]]; then OUT=$2; shift 2; fi
[[ $# == 0 ]] || { echo "usage: $0 [--out DIR]" >&2; exit 2; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
WORK="$(mktemp -d /tmp/arctic-chromium.XXXXXX)"
mkdir -p "$OUT" "$WORK/bin"
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod
(cd "$REPO" && CGO_ENABLED=0 go build -o "$WORK/bin/arctic-webapp" ./cmd/arctic-webapp)
export XDG_RUNTIME_DIR="$WORK/run" XDG_CONFIG_HOME="$WORK/config" XDG_DATA_HOME="$WORK/data"
export XDG_CACHE_HOME="$WORK/cache" XDG_STATE_HOME="$WORK/state" XDG_CURRENT_DESKTOP=mango
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME/xdg-desktop-portal" "$XDG_DATA_HOME"
chmod 700 "$XDG_RUNTIME_DIR"
cp "$REPO/packaging/desktop/mango-portals.conf" "$XDG_CONFIG_HOME/xdg-desktop-portal/"
export PATH="$WORK/bin:$PATH" WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export GDK_BACKEND=wayland LIBGL_ALWAYS_SOFTWARE=1
export ARCTIC_WEBAPP_ALLOW_ROOT=1  # CI's throwaway user; production still rejects sudo
unset GTK_THEME
PORT=18766
python3 "$REPO/cmd/arctic-webapp-host/dev/fixture-server.py" "$PORT" "$WORK/requests.log" &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
for _ in $(seq 50); do
    python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:$PORT/')" 2>/dev/null && break
    sleep 0.1
done
ID="$(arctic-webapp install "http://127.0.0.1:$PORT/" --runtime chromium:chromium --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"],d; print(d["app"]["id"])')"
PROFILE="$XDG_DATA_HOME/arctic/webapps/$ID/chromium"
SWAY="$(command -v sway)"
if command -v getcap >/dev/null && [[ -n "$(getcap "$SWAY" 2>/dev/null)" ]]; then
    cp "$SWAY" "$WORK/sway"; SWAY="$WORK/sway"
fi
printf 'output HEADLESS-1 resolution 1280x800\ndefault_border none\n' > "$WORK/sway.conf"
cat > "$WORK/session.sh" <<'INNER'
#!/usr/bin/env bash
set -euo pipefail
wait_for() { for _ in $(seq 150); do eval "$1" && return 0; sleep 0.2; done; return 1; }
fail() { echo "FAIL: $* (logs in $WORK)" >&2; tail -20 "$WORK/chromium.log" >&2 || true; exit 1; }
"$SWAY" -c "$WORK/sway.conf" >"$WORK/sway.log" 2>&1 &
SWAY_PID=$!
BROWSER_PID=""
trap 'if [ -n "$BROWSER_PID" ]; then kill "$BROWSER_PID" 2>/dev/null || true; fi; kill "$SWAY_PID" 2>/dev/null || true' EXIT
wait_for 'ls "$XDG_RUNTIME_DIR"/wayland-[0-9] >/dev/null 2>&1' || fail "no Wayland display"
WAYLAND_DISPLAY="$(basename "$(ls "$XDG_RUNTIME_DIR"/wayland-[0-9] | head -1)")"
SWAYSOCK="$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock | head -1)"
export WAYLAND_DISPLAY SWAYSOCK
dbus-update-activation-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_CONFIG_HOME XDG_DATA_HOME
gsettings set org.gnome.desktop.interface gtk-theme Adwaita
gsettings set org.gnome.desktop.interface color-scheme prefer-light
gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop \
    --method org.freedesktop.portal.Settings.Read org.freedesktop.appearance color-scheme > "$OUT/portal-light.txt"
chromium-browser --no-sandbox --ozone-platform=wayland --app="http://127.0.0.1:$PORT/" \
    --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check >"$WORK/chromium.log" 2>&1 &
BROWSER_PID=$!
wait_for 'grep -q "^/theme-result?dark=false" "$WORK/requests.log"' || fail "Chromium did not start light"
PAGE_LOADS="$(grep -c "^/$(printf '\t')" "$WORK/requests.log")"
grim "$OUT/chromium-light.png"
gsettings set org.gnome.desktop.interface gtk-theme Adwaita-dark
gsettings set org.gnome.desktop.interface color-scheme prefer-dark
wait_for 'grep -q "^/theme-result?dark=true" "$WORK/requests.log"' || fail "Chromium did not switch dark live"
grim "$OUT/chromium-dark.png"
LIGHT_REPORTS="$(grep -c '^/theme-result?dark=false' "$WORK/requests.log")"
gsettings set org.gnome.desktop.interface gtk-theme Adwaita
gsettings set org.gnome.desktop.interface color-scheme prefer-light
wait_for '[ "$(grep -c "^/theme-result?dark=false" "$WORK/requests.log")" -gt "$LIGHT_REPORTS" ]' || fail "Chromium did not switch back light"
[ "$(grep -c "^/$(printf '\t')" "$WORK/requests.log")" = "$PAGE_LOADS" ] || fail "theme switch reloaded the site"
grep '^/theme-result?' "$WORK/requests.log" > "$OUT/theme.txt"
chromium-browser --no-sandbox --ozone-platform=wayland --user-data-dir="$PROFILE" \
    --app="http://127.0.0.1:$PORT/rtc" >>"$WORK/chromium.log" 2>&1
wait_for 'swaymsg -t get_tree | grep -q "WebRTC loopback"' || fail "call fixture did not open"
wtype -s 500 -k Return -s 200
wait_for 'grep -q "^/rtc-result?data=ok" "$WORK/requests.log"' || fail "WebRTC data channel did not deliver"
wait_for 'grep -q "^/rtc-result?audio=ok" "$WORK/requests.log"' || fail "WebRTC audio did not deliver"
wait_for 'grep -q "^/rtc-result?video=ok" "$WORK/requests.log"' || fail "WebRTC video did not decode"
grep '^/rtc-result?' "$WORK/requests.log" > "$OUT/webrtc.txt"
grim "$OUT/chromium-webrtc.png"
echo "Chromium webapp smoke: PASS"
INNER
chmod +x "$WORK/session.sh"
export REPO WORK OUT ID PROFILE SWAY PORT
dbus-run-session -- "$WORK/session.sh"
