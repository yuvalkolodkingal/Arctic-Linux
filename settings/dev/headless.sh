#!/usr/bin/env bash
# Run Arctic Settings in a headless sway and take screenshots (smoke test and screenshots).
#
#   settings/dev/headless.sh [options] [<step>…]
#
# Starts sway with a 1280×800 headless output inside a D-Bus session (with PipeWire when
# installed), a throwaway HOME with the dotfiles installed (dotfiles/install.sh --target) and
# the app from this checkout. Steps: `page <id>`, `reveal <page> <searchKey>`,
# `search <text>`, `key <wtype args…>` (up to the next step), `sleep <s>`, `sh <command>`,
# `theme <winter|polar-night>`, `shot <name>`.
#
#   --smoke            open every page, screenshot it (<page>.png), and fail on QML errors or
#                      warnings in the log (the CI check)
#   --theme NAME       winter or polar-night (default polar-night)
#   --out DIR          where screenshots go (default settings/dev/screenshots)
#   --size WxH         output size (default 1280x800)
#   --fixtures         test data for screenshots: desktop entries for the default apps, the
#                      installer's default-apps file, and an arctic-update stand-in with updates
#                      ready (none of it is used outside this script)
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
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --smoke) SMOKE=1; shift ;;
    --theme) THEME="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --fixtures) FIXTURES=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
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
fi
export ARCTIC_SHELL_DIR="$REPO/shell"
export XDG_DATA_DIRS=/usr/local/share:/usr/share
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export QT_QPA_PLATFORM=wayland
unset WAYLAND_DISPLAY SWAYSOCK

SWAY="$(command -v sway)"
if command -v getcap >/dev/null && [[ -n "$(getcap "$SWAY" 2>/dev/null)" ]]; then cp "$SWAY" "$work/sway"; SWAY="$work/sway"; fi
printf 'output HEADLESS-1 resolution %s\ndefault_border none\nfor_window [title="^Arctic Settings$"] floating enable, resize set 1080 740, move position center\n' "$SIZE" > "$work/sway.conf"

cat > "$work/inner.sh" <<'INNER'
#!/usr/bin/env bash
set -uo pipefail
"$SWAY" -c "$WORK/sway.conf" >"$WORK/sway.log" 2>&1 &
for _ in $(seq 100); do ls "$XDG_RUNTIME_DIR"/wayland-[0-9] >/dev/null 2>&1 && break; sleep 0.05; done
export WAYLAND_DISPLAY="$(basename "$(ls "$XDG_RUNTIME_DIR"/wayland-[0-9] | head -1)")"
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
shot() { grim "$OUT/$1.png" && echo "screenshot: $OUT/$1.png"; }
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
export SWAY WORK="$work" REPO OUT SMOKE
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
