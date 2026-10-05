#!/usr/bin/env bash
# Actual SDDM greeter and ext-session-lock rendering in a disposable Fedora container.
# This session-bus fixture bypasses polkit ONLY on its private test bus. System-bus
# authorization and enforcing SELinux are separate VM checks. Never run on a live PC.
set -euo pipefail
[[ -f /.dockerenv || -f /run/.containerenv ]] || { echo 'Run in a disposable container.' >&2; exit 1; }
[[ "$EUID" == 0 ]] || { echo 'The disposable container test needs its own root account.' >&2; exit 1; }
command -v rg >/dev/null
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-/tmp/shared-wallpaper-shots}"
mkdir -p "$OUT"
export REPO OUT
if [[ "${2:-}" != inner ]]; then
  exec dbus-run-session -- "$0" "$OUT" inner
fi
WORK="$(mktemp -d /tmp/arctic-wallpaper-integration.XXXXXX)"
export HOME="$WORK/home" XDG_RUNTIME_DIR="$WORK/run"
mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export XDG_CONFIG_HOME="$HOME/.config" XDG_CACHE_HOME="$HOME/.cache" XDG_STATE_HOME="$HOME/.local/state"
export ARCTIC_WALLPAPER_TEST_BUS=session ARCTIC_SHELL_DIR="$REPO/shell"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 QT_QPA_PLATFORM=wayland
"$REPO/dotfiles/install.sh" --target "$HOME" --theme polar-night --no-shell >"$OUT/install.log" 2>&1
export PATH="$HOME/.local/bin:$PATH"
pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  pkill -x swaybg 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT
python3 "$REPO/dotfiles/.local/bin/arctic-login-wallpaper" serve --session /var/lib/arctic-login-wallpaper >"$OUT/broker.log" 2>&1 &
pids+=("$!")
for _ in $(seq 50); do arctic-login-wallpaper status >/dev/null 2>&1 && break; sleep .1; done
arctic-login-wallpaper reset >"$OUT/reset.json"
install -m755 /usr/bin/sway "$WORK/sway"
cat > "$WORK/sway.conf" <<'CONF'
output HEADLESS-1 resolution 1280x800 position 0 0
default_border none
CONF
"$WORK/sway" -c "$WORK/sway.conf" >"$OUT/sway.log" 2>&1 &
pids+=("$!")
for _ in $(seq 100); do [[ -S "$XDG_RUNTIME_DIR/wayland-1" || -S "$XDG_RUNTIME_DIR/wayland-0" ]] && break; sleep .1; done
WAYLAND_DISPLAY="$(basename "$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'wayland-*' | head -1)")"
SWAYSOCK="$(find "$XDG_RUNTIME_DIR" -name 'sway-ipc.*.sock' | head -1)"
export WAYLAND_DISPLAY SWAYSOCK
swaymsg create_output >/dev/null
swaymsg output HEADLESS-2 resolution 900x1600 position 1280 0 >/dev/null
python3 - "$WORK" <<'PY'
from PIL import Image
from pathlib import Path
import sys
root=Path(sys.argv[1]); folder=root/'pictures'; folder.mkdir()
Image.new('RGB', (1600,900), '#1468b6').save(folder/'a.png')
Image.new('RGB', (900,1600), '#bb6020').save(folder/'b.png')
PY
arctic-login-wallpaper set "$WORK/pictures/a.png" >"$OUT/separate.json"
# The greeter uses a copied theme and real SDDM test models.
cp -a "$REPO/branding/sddm/arctic" "$WORK/theme"
mkdir -p /usr/share/backgrounds/arctic
cp "$REPO/design/wallpapers/"*.svg /usr/share/backgrounds/arctic/
mkdir -p /dev/dri /usr/share/wayland-sessions
printf '[Desktop Entry]\nName=Mango\nExec=/bin/true\nType=Application\n' > /usr/share/wayland-sessions/arctic-wallpaper-test.desktop
sddm-greeter-qt6 --test-mode --theme "$WORK/theme" >"$OUT/sddm.log" 2>&1 &
greeter=$!; pids+=("$greeter")
sleep 3
shot() {
  grim -o HEADLESS-1 "$OUT/$1-landscape.png"
  grim -o HEADLESS-2 "$OUT/$1-portrait.png"
}
shot sddm-a
arctic-login-wallpaper set "$WORK/pictures/b.png" >"$OUT/separate-b.json"
sleep 6
shot sddm-b
rm /var/lib/arctic-login-wallpaper/current/wallpaper.png
sleep 6
shot sddm-missing
arctic-login-wallpaper set "$WORK/pictures/a.png" >"$OUT/recovered.json"
sleep 6
shot sddm-recovered
kill "$greeter"; wait "$greeter" || true
arctic-wallpaper "$WORK/pictures/a.png" >"$OUT/desktop.log" 2>&1
arctic-login-wallpaper sync-desktop >"$OUT/sync.json"
quickshell -p "$REPO/shell" >"$OUT/lock.log" 2>&1 &
pids+=("$!")
sleep 3
arctic-shell-ipc lock lock >/dev/null
for _ in $(seq 50); do [[ "$(arctic-shell-ipc lock isLocked)" == true ]] && break; sleep .1; done
[[ "$(arctic-shell-ipc lock isLocked)" == true ]]
sleep 2
shot lock-a
# Exercise the actual rotation tick command and its automatic sync hook while locked.
python3 - "$WORK" "$XDG_CONFIG_HOME/arctic/wallpaper-rotate.json" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[2]).write_text(json.dumps(dict(every='30m',folder=sys.argv[1]+'/pictures',shuffle=False)))
PY
arctic-wallpaper next >>"$OUT/desktop.log" 2>&1
sleep 3
shot lock-rotated-b
# Damage a newly published generation, then verify a later valid revision recovers.
arctic-login-wallpaper set "$WORK/pictures/a.png" >"$OUT/before-damage.json"
printf 'invalid PNG' > /var/lib/arctic-login-wallpaper/current/wallpaper.png
sleep 3
shot lock-damaged
arctic-login-wallpaper set "$WORK/pictures/b.png" >"$OUT/after-damage.json"
sleep 3
shot lock-recovered-b
python3 - "$OUT" <<'PY'
from PIL import Image
from pathlib import Path
import sys
root=Path(sys.argv[1])
for screen,size in [('landscape',(1280,800)),('portrait',(900,1600))]:
 def pixel(name):
  image=Image.open(root/(name+'-'+screen+'.png')).convert('RGB'); assert image.size==size
  return image.getpixel((5,5))
 assert pixel('sddm-a')==(20,104,182), (screen,pixel('sddm-a'))
 assert pixel('sddm-b')==(187,96,32), (screen,pixel('sddm-b'))
 assert pixel('sddm-missing')!=pixel('sddm-b')
 assert pixel('sddm-recovered')==pixel('sddm-a')
 assert pixel('lock-a')!=pixel('lock-rotated-b'), (screen,'rotation did not change lock')
 assert pixel('lock-damaged')!=pixel('lock-recovered-b'), (screen,'binding did not recover')
 assert pixel('lock-recovered-b')==pixel('lock-rotated-b')
print('PASS: actual SDDM and secure session lock; portrait/landscape; rotation, missing images and recovery.')
PY
if rg -n 'TypeError|ReferenceError|SyntaxError|Failed to load|is not a type|Cannot assign|Unable to assign' "$OUT/lock.log" "$OUT/sddm.log"; then
  exit 1
fi
