#!/usr/bin/env bash
# Run Arctic Settings in a headless sway and take screenshots (smoke test and screenshots).
#
#   settings/dev/headless.sh [options] [<step>…]
#
# Starts sway with a 1280×800 headless output (HEADLESS-1; the window and the screenshots are
# there) inside a D-Bus session (with PipeWire when installed), a throwaway HOME with the
# dotfiles installed (dotfiles/install.sh --target) and the app from this checkout. Steps: `page <id>`, `reveal <page> <searchKey>`,
# `search <text>`, `key <wtype args…>` (up to the next step), `sleep <s>`, `sh <command>`,
# `theme <winter|polar-night>`, `shot <name>`.
#
#   --smoke            open every page, screenshot it (<page>.png), and fail on QML errors or
#                      warnings in the log (the CI check); then add displays up to three and
#                      open Displays again (displays-3.png)
#   --theme NAME       winter or polar-night (default polar-night)
#   --out DIR          where screenshots go (default settings/dev/screenshots)
#   --size WxH         output size (default 1280x800)
#   --outputs N        1 to 3 displays for the Displays page: 2 adds HEADLESS-2 (2560×1440 at
#                      150 %, right of the first), 3 also HEADLESS-3 (1920×1080 turned 90°,
#                      right of that); screenshots stay of HEADLESS-1
#   --fixtures         test data for screenshots: desktop entries for the default apps, the
#                      installer's default-apps file, an arctic-update stand-in with updates
#                      ready, two apps that sent notifications and an arctic-webapp stand-in
#                      with three web apps, one whose browser is gone (none of it is used
#                      outside this script)
#
# Needs sway, grim, quickshell and python3 (wtype for `key`). Inside containers sway refuses a
# binary with file capabilities, so a plain copy is used.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO/settings/dev/screenshots"
SIZE=1280x800
THEME=polar-night
SMOKE=0
FIXTURES=0
OUTPUTS=1
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --smoke) SMOKE=1; shift ;;
    --theme) THEME="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --fixtures) FIXTURES=1; shift ;;
    --outputs) OUTPUTS="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[[ "$OUTPUTS" =~ ^[1-3]$ ]] || { echo "--outputs takes 1, 2 or 3" >&2; exit 2; }
mkdir -p "$OUT"

work="$(mktemp -d /tmp/arctic-settings-headless.XXXXXX)"
export XDG_RUNTIME_DIR="$work/run"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export HOME="$work/home"
mkdir -p "$HOME"
"$REPO/dotfiles/install.sh" --target "$HOME" --theme "$THEME" --no-shell >/dev/null
fc-cache -f >/dev/null 2>&1 || true
ln -sfn "themes/$THEME" "$HOME/.config/arctic/current"
echo "$THEME" > "$HOME/.config/arctic/theme"
export PATH="$HOME/.local/bin:$PATH"
if (( FIXTURES )); then
  apps="$HOME/.local/share/applications"; mkdir -p "$apps"
  fixture() {   # fixture <id> <name> <program> <categories> <mime types>
    printf '[Desktop Entry]\nType=Application\nName=%s\nExec=%s %%U\nCategories=%s\nMimeType=%s\nComment=Test fixture\n' \
      "$2" "$3" "$4" "$5" > "$apps/$1.desktop"
  }
  fixture app.zen_browser.zen "Zen Browser" zen "Network;WebBrowser;" "text/html;x-scheme-handler/http;x-scheme-handler/https;"
  fixture org.mozilla.firefox "Firefox" firefox "Network;WebBrowser;" "text/html;x-scheme-handler/http;x-scheme-handler/https;"
  fixture dev.zed.Zed "Zed" zeditor "Development;TextEditor;" "text/plain;"
  fixture thunar "Thunar" thunar "System;FileManager;" "inode/directory;"
  fixture vlc "VLC media player" vlc "AudioVideo;Player;" "video/mp4;video/x-matroska;audio/mpeg;"
  fixture org.gnome.Loupe "Image Viewer" loupe "Graphics;Viewer;" "image/png;image/jpeg;"
  printf '[Desktop Entry]\nType=Application\nName=kitty\nExec=kitty\nCategories=System;TerminalEmulator;\n' > "$apps/kitty.desktop"
  printf '[Desktop Entry]\nType=Application\nName=Foot\nExec=foot\nCategories=System;TerminalEmulator;\n' > "$apps/foot.desktop"
  mkdir -p "$work/etc"
  cp "$REPO/packaging/desktop/default-apps" "$work/etc/default-apps"
  export ARCTIC_ETC="$work/etc"
  cat > "$HOME/.local/bin/arctic-update" <<'STUB'
#!/bin/sh
# Test stand-in for arctic-update (settings/dev/headless.sh --fixtures).
[ "$1" = status ] && echo '{"state":"ready","packages":["kernel-6.18.9","mesa-26.1.2","firefox-143.0","quickshell-0.2.1"],"download_mb":212.5,"staged_at":"2026-09-27T10:12:00Z","channel":"stable","auto":"on"}'
[ "$1" = firmware ] && echo '{"available":true,"devices":[{"name":"System Firmware","vendor":"LENOVO","version":"0.1.40","update":"0.1.42","summary":"","reboot":true}],"error":""}'
exit 0
STUB
  chmod +x "$HOME/.local/bin/arctic-update"
  # Apps that have sent notifications (the shell writes this), for Settings → Notifications.
  mkdir -p "$HOME/.local/state/arctic/notifications"
  printf '{"version":1,"apps":[{"key":"org.signal.Signal","app_name":"Signal","desktop_entry":"org.signal.Signal","last_seen":1790620000},{"key":"Firefox","app_name":"Firefox","last_seen":1790610000}]}\n' \
    > "$HOME/.local/state/arctic/notifications/apps.json"
  # Web apps (stream 1): a stand-in arctic-webapp with three apps (one whose browser is gone)
  # and kept sign-in data.
  cat > "$HOME/.local/bin/arctic-webapp" <<'STUB'
#!/bin/sh
# Test stand-in for arctic-webapp (settings/dev/headless.sh --fixtures).
case "$1" in
  list) echo '{"ok":true,"apps":[{"id":"org.arcticlinux.WebApp.YouTubeMusic_4c1a9e","name":"YouTube Music","url":"https://music.youtube.com/?source=pwa","host":"music.youtube.com","icon_name":"org.arcticlinux.WebApp.YouTubeMusic_4c1a9e","icon_path":"","category":"AudioVideo","runtime":"webkit","runtime_available":true,"running":true,"links":"browser","notifications":"allow","devtools":false,"rendering":"auto","extra_domains":["accounts.google.com"],"handlers":[],"handlers_supported":[],"tls_exceptions":[],"data_bytes":48213504,"problem":"","created":"2026-09-28T12:00:00Z","updated":"2026-09-28T12:00:00Z"},{"id":"org.arcticlinux.WebApp.HomeAssistant_0badf0","name":"Home Assistant","url":"https://ha.lan:8123/","host":"ha.lan:8123","icon_name":"org.arcticlinux.WebApp.HomeAssistant_0badf0","icon_path":"","category":"Utility","runtime":"webkit","runtime_available":true,"running":false,"links":"app","notifications":"ask","devtools":true,"rendering":"software","extra_domains":[],"handlers":[],"handlers_supported":[],"tls_exceptions":[{"host":"ha.lan:8123","sha256":"9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"}],"data_bytes":1203400,"problem":"","created":"2026-09-28T12:00:00Z","updated":"2026-09-28T12:00:00Z"},{"id":"org.arcticlinux.WebApp.Discord_5e0d11","name":"Discord","url":"https://discord.com/app","host":"discord.com","icon_name":"org.arcticlinux.WebApp.Discord_5e0d11","icon_path":"","category":"Network","runtime":"chromium:chromium","runtime_available":false,"running":false,"links":"browser","notifications":"allow","devtools":false,"rendering":"auto","extra_domains":[],"handlers":[],"handlers_supported":[],"tls_exceptions":[],"data_bytes":5302000,"problem":"runtime-missing","created":"2026-09-28T12:00:00Z","updated":"2026-09-28T12:00:00Z"}],"kept":[{"id":"org.arcticlinux.WebApp.Slack_09ab3c","name":"Slack","url":"https://app.slack.com/","data_bytes":2211840}]}' ;;
  runtimes) echo '{"ok":true,"runtimes":[{"id":"webkit","name":"Arctic","available":true,"drm":false,"webrtc":false},{"id":"chromium:brave","name":"Brave","available":true,"drm":true,"webrtc":true},{"id":"chromium:chromium","name":"Chromium","available":false,"drm":false,"webrtc":true}]}' ;;
  *) echo '{"ok":true,"applied":"saved"}' ;;
esac
STUB
  chmod +x "$HOME/.local/bin/arctic-webapp"
fi
export ARCTIC_SHELL_DIR="$REPO/shell"
export XDG_DATA_DIRS=/usr/local/share:/usr/share
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export QT_QPA_PLATFORM=wayland
unset WAYLAND_DISPLAY SWAYSOCK

SWAY="$(command -v sway)"
if command -v getcap >/dev/null && [[ -n "$(getcap "$SWAY" 2>/dev/null)" ]]; then cp "$SWAY" "$work/sway"; SWAY="$work/sway"; fi
printf 'output HEADLESS-1 resolution %s position 0 0\ndefault_border none\nfor_window [title="^Arctic Settings$"] floating enable, resize set 1080 740, move position center\n' "$SIZE" > "$work/sway.conf"
# More displays (sway's create_output, below): a 4K-ish one at 150 % and a portrait one.
printf 'output HEADLESS-2 mode --custom 2560x1440@60Hz scale 1.5 position %s 0\n' "${SIZE%x*}" >> "$work/sway.conf"
printf 'output HEADLESS-3 mode --custom 1920x1080@60Hz transform 90 position %s 0\n' "$(( ${SIZE%x*} + 1706 ))" >> "$work/sway.conf"

cat > "$work/inner.sh" <<'INNER'
#!/usr/bin/env bash
set -uo pipefail
"$SWAY" -c "$WORK/sway.conf" >"$WORK/sway.log" 2>&1 &
for _ in $(seq 100); do ls "$XDG_RUNTIME_DIR"/wayland-[0-9] >/dev/null 2>&1 && break; sleep 0.05; done
export WAYLAND_DISPLAY="$(basename "$(ls "$XDG_RUNTIME_DIR"/wayland-[0-9] | head -1)")"
for _ in $(seq 2 "$OUTPUTS"); do
  swaymsg -s "$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock | head -1)" create_output >/dev/null
done
if command -v pipewire >/dev/null; then
  pipewire >/dev/null 2>&1 &
  sleep 0.3
  wireplumber >/dev/null 2>&1 &
  sleep 0.5
  pw-cli create-node adapter '{ factory.name=support.null-audio-sink node.name=arctic-test-sink node.description="Speakers" media.class=Audio/Sink object.linger=true audio.position=[FL FR] }' >/dev/null 2>&1
fi
command -v swaybg >/dev/null && { arctic-wallpaper >/dev/null 2>&1 || true; }
quickshell -p "$REPO/settings" >"$WORK/qs.log" 2>&1 &
qs=$!
ipc() { quickshell ipc --pid "$qs" call settings "$@" 2>/dev/null; }
settle() {   # the helper has answered and the page has drawn
  for _ in $(seq 100); do [[ "$(ipc ready)" == true ]] && break; sleep 0.1; done
  sleep "${1:-0.8}"
}
shot() { grim -o HEADLESS-1 "$OUT/$1.png" && echo "screenshot: $OUT/$1.png"; }
for _ in $(seq 100); do [[ -n "$(ipc page)" ]] && break; sleep 0.1; done
[[ -n "$(ipc page)" ]] || { echo "FAIL: Settings did not start"; cat "$WORK/qs.log"; exit 1; }
settle 1.5
if (( SMOKE )); then
  for p in $(ipc pages); do
    r="$(ipc open "$p")"
    [[ "$r" == ok ]] || { echo "FAIL: open $p: $r"; exit 1; }
    settle 1.2
    [[ "$(ipc page)" == "$p" ]] || { echo "FAIL: $p did not open"; exit 1; }
    shot "$p"
  done
  ipc search "gaps" >/dev/null; sleep 0.6; shot search
  ipc reveal windows windows.layout >/dev/null; settle 0.8; shot reveal
  # The Displays page with three displays: plug in the others (sway's create_output) and
  # check that the helper sees a tidy layout for the arrangement editor.
  for _ in $(seq "$((OUTPUTS + 1))" 3); do
    swaymsg -s "$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock | head -1)" create_output >/dev/null
  done
  sleep 0.5
  ipc open displays >/dev/null; settle 1.2
  shot displays-3
  python3 "$REPO/settings/scripts/arctic_settings.py" displays | python3 -c '
import json, sys
d = json.load(sys.stdin)
names = sorted(o["name"] for o in d["arranged"])
assert names == ["HEADLESS-1", "HEADLESS-2", "HEADLESS-3"] and not d["problems"] and d["main"] == "HEADLESS-1", d
' || { echo "FAIL: the Displays page doesn't get three tidy displays"; exit 1; }
  echo "PASS: three displays reach the arrangement editor"
  ipc open windows >/dev/null; settle 0.8
  # A change goes all the way: QML → helper → settings.conf (sourced by config.conf) → state.
  ipc set gappih 14 >/dev/null; settle 0.3
  grep -qx 'gappih=14' "$HOME/.config/mango/settings.conf" || { echo "FAIL: gappih=14 not in settings.conf"; exit 1; }
  grep -qx 'source-optional=~/.config/mango/settings.conf' "$HOME/.config/mango/config.conf" || { echo "FAIL: config.conf doesn't source settings.conf"; exit 1; }
  [[ "$(ipc value gappih)" == 14 ]] || { echo "FAIL: the app didn't pick up gappih=14 ($(ipc value gappih))"; exit 1; }
  ipc set gappih 500 >/dev/null; settle 0.3
  grep -qx 'gappih=14' "$HOME/.config/mango/settings.conf" || { echo "FAIL: an out-of-range value was written"; exit 1; }
  shot error-toast
  echo "PASS: a change reached settings.conf and a bad one was refused"
fi
while (( $# )); do
  case "$1" in
    page)   ipc open "$2" >/dev/null; settle; shift 2 ;;
    reveal) ipc reveal "$2" "$3" >/dev/null; settle; shift 3 ;;
    search) ipc search "$2" >/dev/null; sleep 0.6; shift 2 ;;
    key)    shift; args=(); while (( $# )) && [[ " page reveal search key sleep sh theme shot " != *" $1 "* ]]; do args+=("$1"); shift; done
            # The seat has no keyboard until wtype makes one: give the window the focus first.
            swaymsg -s "$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock | head -1)" '[title="^Arctic Settings$"] focus' >/dev/null 2>&1
            wtype "${args[@]}" 2>/dev/null || echo "wtype missing" ;;
    sleep)  sleep "$2"; shift 2 ;;
    sh)     timeout 20 sh -c "$2"; shift 2 ;;
    theme)  arctic-theme "$2" >/dev/null 2>&1; sleep 1; shift 2 ;;
    shot)   shot "$2"; shift 2 ;;
    *)      echo "unknown step $1"; shift ;;
  esac
done
ipc quit >/dev/null
sleep 0.5
kill "$qs" 2>/dev/null
pkill -x wireplumber; pkill -x pipewire; pkill -x swaybg
pkill -f "$SWAY" 2>/dev/null
exit 0
INNER
chmod +x "$work/inner.sh"
export SWAY WORK="$work" REPO OUT SMOKE OUTPUTS
status=0
dbus-run-session -- "$work/inner.sh" "$@" || status=$?

# QML problems: errors always fail; in --smoke, warnings from Settings' own files fail too.
problems="$(grep -a -E -i "typeerror|referenceerror|is not a type|cannot assign|unable to assign|is not defined|error:|failed to load|binding loop" "$work/qs.log" \
  | grep -v -E "MESA|ZINK|dri2|libEGL|Could not attach|QSocketNotifier" || true)"
echo "--- quickshell log (warnings and errors) ---"
grep -a -E -i "warn|error|fail" "$work/qs.log" | grep -v -E "MESA|ZINK|dri2|libEGL" | head -40
if [[ -n "$problems" ]]; then
  echo "FAIL: QML problems in the log:" >&2
  echo "$problems" >&2
  status=1
fi
if (( SMOKE )) && (( status == 0 )); then echo "PASS: every page loaded without QML errors"; fi
rm -rf "$work"
exit "$status"
