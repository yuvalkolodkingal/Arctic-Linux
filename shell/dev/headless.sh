#!/usr/bin/env bash
# Run the shell in a headless sway and take screenshots (development and CI checks).
#
#   shell/dev/headless.sh [options] <name> [<step>…]
#
# Starts sway with a 1280×800 headless output inside a D-Bus session (with PipeWire when
# installed; the shell is the notification server, so `sh notify-send …` steps show toasts), a throwaway HOME with the dotfiles installed (dotfiles/install.sh --target),
# and the shell from this checkout. Each step is either `ipc <target> <function> [args]`,
# `sleep <seconds>`, `key <text>` (wtype), `point <x> <y>` / `click` (wlrctl virtual pointer),
# `sh <command>`, `theme <winter|polar-night>` or `shot <name>`;
# with no steps it takes one screenshot called <name>. Screenshots land in
# shell/dev/screenshots/<name>.png.
#
# Note: wtype and wlrctl each add a virtual keyboard / pointer for one command and remove it
# again, so the shell sees the seat's keyboard come and go: keys arrive (the first one can be
# lost) but keyboard-focus rings don't stay visible in screenshots, and pointer hover/clicks
# are unreliable. Use `ipc` steps where possible.
#
# Options: --live (ARCTIC_FORCE_LIVE=1), --theme winter|polar-night, --size WxH, --keep-home,
#          --fixtures (add desktop entries for Zed, Zen Browser and yazi, as in the design
#          mockups, so launcher screenshots have something to find, point the network menu
#          at shell/tests/fixtures/network.json and add the tray icon of
#          shell/tests/fixtures/sni-menu.py; test data only),
#          --mako (start mako before the shell, to test the hand-over of the notification name)
#          --app-fixtures (Get apps with stand-ins for flatpak, rpm, dnf5, pkexec and arctic-webapp
#          from shell/dev/fixtures: canned packages, Flathub apps, installed apps and a web app)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO/shell/dev/screenshots"
SIZE=1280x800
THEME=polar-night
LIVE=0
KEEP=0
FIXTURES=0
MAKO=0
APP_FIXTURES=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --live) LIVE=1; shift ;;
    --theme) THEME="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --keep-home) KEEP=1; shift ;;
    --fixtures) FIXTURES=1; shift ;;
    --mako) MAKO=1; shift ;;
    --app-fixtures) APP_FIXTURES=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
NAME="${1:?usage: headless.sh [options] <name> [steps…]}"; shift
mkdir -p "$OUT"

export XDG_RUNTIME_DIR=/tmp/arctic-xdg
rm -rf "$XDG_RUNTIME_DIR" && mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export HOME=/tmp/arctic-home
if (( ! KEEP )) || [[ ! -d "$HOME/.config/arctic" ]]; then
  rm -rf "$HOME" && mkdir -p "$HOME"
  "$REPO/dotfiles/install.sh" --target "$HOME" --theme "$THEME" >/dev/null
  fc-cache -f >/dev/null 2>&1 || true
fi
ln -sfn "themes/$THEME" "$HOME/.config/arctic/current"; echo "$THEME" > "$HOME/.config/arctic/theme"
if (( FIXTURES )); then
  apps="$HOME/.local/share/applications"; mkdir -p "$apps"
  fixture() {   # fixture <id> <name> <generic name> <terminal>
    printf '[Desktop Entry]\nType=Application\nName=%s\nGenericName=%s\nComment=Test fixture for screenshots\nExec=true\nTerminal=%s\n' "$2" "$3" "$4" > "$apps/$1.desktop"
  }
  fixture dev.zed.Zed Zed "Code editor" false
  fixture app.zen_browser.zen "Zen Browser" "Web browser" false
  fixture yazi yazi "Terminal file manager" true
  # The network menu answers from test data (network.py's fixture mode) instead of NetworkManager.
  export ARCTIC_NETWORK_FIXTURE="$REPO/shell/tests/fixtures/network.json"
  # …and a tray icon with a menu of every kind of entry (python3-dbus).
  export ARCTIC_SNI_FIXTURE="$REPO/shell/tests/fixtures/sni-menu.py"
fi
export PATH="$HOME/.local/bin:$PATH"
export ARCTIC_SHELL_DIR="$REPO/shell"
export XDG_DATA_DIRS=/usr/local/share:/usr/share
if (( APP_FIXTURES )); then
  apps_fixtures="$REPO/shell/dev/fixtures/apps"
  export PATH="$REPO/shell/dev/fixtures/bin:$PATH"
  export XDG_DATA_DIRS="$apps_fixtures/share:$apps_fixtures/flatpak/exports/share:$XDG_DATA_DIRS"
  export ARCTIC_WEBAPP_CMD="$REPO/shell/dev/fixtures/bin/arctic-webapp" ARCTIC_SWCATALOG="$apps_fixtures/swcatalog"
  export ARCTIC_FLATPAK_SYSTEM_DIR="$apps_fixtures/flatpak" ARCTIC_INSTALL_MARK="$apps_fixtures/share"
  export ARCTIC_DEFAULT_APPS="$apps_fixtures/default-apps" ARCTIC_WHEEL=1
  rm -f "$XDG_RUNTIME_DIR/fake-apps.json"
fi
(( LIVE )) && export ARCTIC_FORCE_LIVE=1
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export QT_QPA_PLATFORM=wayland

# sway refuses to start from a binary with file capabilities inside containers; use a plain copy.
SWAY="$(command -v sway)"
if command -v getcap >/dev/null && [[ -n "$(getcap "$SWAY" 2>/dev/null)" ]]; then cp "$SWAY" /tmp/sway-nocap; SWAY=/tmp/sway-nocap; fi

conf=/tmp/arctic-sway.conf
cat > "$conf" <<CONF
output HEADLESS-1 resolution $SIZE
default_border none
gaps inner 8
CONF

inner=/tmp/arctic-headless-inner.sh
cat > "$inner" <<'INNER'
#!/usr/bin/env bash
set -uo pipefail
"$SWAY" -c "$SWAYCONF" >/tmp/arctic-sway.log 2>&1 &
for _ in $(seq 100); do ls "$XDG_RUNTIME_DIR"/wayland-[0-9] >/dev/null 2>&1 && break; sleep 0.05; done
export WAYLAND_DISPLAY="$(basename "$(ls "$XDG_RUNTIME_DIR"/wayland-[0-9] | head -1)")"
export SWAYSOCK="$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock 2>/dev/null | head -1)"
if command -v pipewire >/dev/null; then
  pipewire >/dev/null 2>&1 &
  sleep 0.3
  wireplumber >/dev/null 2>&1 &
  sleep 0.5
  # A virtual output, so the volume item and OSD have a real PipeWire sink to follow.
  pw-cli create-node adapter '{ factory.name=support.null-audio-sink node.name=arctic-test-sink node.description="Speakers" media.class=Audio/Sink object.linger=true audio.position=[FL FR] }' >/dev/null 2>&1
fi
if (( MAKO )) && command -v mako >/dev/null; then mako >/dev/null 2>&1 & sleep 0.5; fi
arctic-wallpaper >/dev/null 2>&1 || true
arctic-shell --foreground >/tmp/arctic-shell.log 2>&1 &
[[ -n "${ARCTIC_SNI_FIXTURE:-}" ]] && python3 -c 'import dbus, gi' 2>/dev/null && { python3 "$ARCTIC_SNI_FIXTURE" >/tmp/arctic-sni.log 2>&1 & }
sleep 4
shot() { grim "$OUT/$1.png" && echo "screenshot: $OUT/$1.png"; }
if (( $# == 0 )); then shot "$NAME"; fi
while (( $# )); do
  case "$1" in
    ipc)   shift; args=(); while (( $# )) && [[ " ipc sleep key shot theme sh point click " != *" $1 "* ]]; do args+=("$1"); shift; done
           arctic-shell-ipc "${args[@]}" || echo "ipc failed: ${args[*]}" ;;
    sleep) sleep "$2"; shift 2 ;;
    key)   wtype "$2" 2>/dev/null || echo "wtype missing"; shift 2 ;;
    theme) arctic-theme "$2" >/dev/null 2>&1; shift 2 ;;
    sh)    timeout 10 sh -c "$2"; shift 2 ;;
    point) wlrctl pointer move -5000 -5000; wlrctl pointer move "$2" "$3"; shift 3 ;;
    click) wlrctl pointer click left; shift ;;
    shot)  shot "$2"; shift 2 ;;
    *)     echo "unknown step $1"; shift ;;
  esac
done
arctic-shell --stop
pkill -f sni-menu.py; pkill -x mako; pkill -x wireplumber; pkill -x pipewire; pkill -x swaybg
kill %1 2>/dev/null; pkill -f "$SWAY" 2>/dev/null
INNER
chmod +x "$inner"
export SWAY SWAYCONF="$conf" OUT NAME MAKO
dbus-run-session -- "$inner" "$@"
echo "--- shell log (warnings and errors) ---"
grep -a -E -i "warn|error|fail|typeerror|referenceerror" /tmp/arctic-shell.log | grep -v -E "MESA|ZINK|dri2|libEGL" | head -40
