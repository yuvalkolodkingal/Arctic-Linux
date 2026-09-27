#!/usr/bin/env bash
# Screenshot the SDDM theme: `sddm-greeter-qt6 --test-mode` under a headless
# sway (pixman renderer, Mesa llvmpipe for Qt Quick), captured with grim.
#
# Runs only inside a throwaway Fedora container (it adds test users), so on a
# host it re-executes itself in registry.fedoraproject.org/fedora:44.
# Output: branding/sddm/preview/*.png
#
#   login-single.png        one user, password field focused
#   login-error.png         after a wrong password (test mode answers every login with a failure)
#   login-power-focus.png   keyboard focus on Suspend: focus ring + tooltip
#   login-multi.png         three users, picker
#   login-multi-focus.png   keyboard focus on the user picker (Tab from the password field)
#   login-session-menu.png  session menu open (keyboard)
#   login-1280x800.png      smaller screen
#   login-960x600.png       the mockup's size, to compare with mockup-login-polar-night.png
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [[ -z "${ARCTIC_BRANDING_IN_CONTAINER:-}" ]]; then
    EXTRA_DEPS="sddm sway grim wtype qt6-qtwayland qt6-qtsvg mesa-dri-drivers mesa-libEGL mesa-libGL google-noto-sans-fonts" \
        reexec_in_container branding/tools/preview-sddm.sh
    exit 0
fi

OUT="$BRANDING_DIR/sddm/preview"
mkdir -p "$OUT"
WORK="$(mktemp -d)"
export XDG_RUNTIME_DIR="$WORK/xdg"
mkdir -m 0700 "$XDG_RUNTIME_DIR"
export LANG=C.UTF-8

# sway ships with file capabilities that a container cannot exec; a copy drops them.
install -m 0755 /usr/bin/sway "$WORK/sway"
# SDDM lists Wayland sessions only when /dev/dri exists; give it a Mango session.
mkdir -p /dev/dri /usr/share/wayland-sessions
cat > /usr/share/wayland-sessions/mango.desktop <<'EOF'
[Desktop Entry]
Name=Mango
Comment=Arctic Linux desktop (preview entry)
Exec=/bin/true
Type=Application
EOF

# Theme copy with the keyboard layout the installer would write.
cp -r "$BRANDING_DIR/sddm/arctic" "$WORK/theme"
printf '[General]\nkeyboardLayout=us\n' > "$WORK/theme/theme.conf.user"

SWAY_PID=""
GREETER_PID=""
cleanup() {
    [[ -n "$GREETER_PID" ]] && kill "$GREETER_PID" 2>/dev/null || true
    [[ -n "$SWAY_PID" ]] && kill "$SWAY_PID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

stop() {  # PID
    [[ -n "$1" ]] || return 0
    kill "$1" 2>/dev/null || true
    wait "$1" 2>/dev/null || true
}

start_sway() {  # WIDTHxHEIGHT
    stop "$GREETER_PID"; GREETER_PID=""
    stop "$SWAY_PID"; SWAY_PID=""
    cat > "$WORK/sway.conf" <<EOF
output HEADLESS-1 resolution $1 bg #000000 solid_color
default_border none
focus_follows_mouse no
EOF
    rm -f "$XDG_RUNTIME_DIR"/wayland-*
    WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
        "$WORK/sway" -c "$WORK/sway.conf" >"$WORK/sway.log" 2>&1 &
    SWAY_PID=$!
    WAYLAND_DISPLAY=""
    for _ in $(seq 50); do
        for sock in "$XDG_RUNTIME_DIR"/wayland-*; do
            [[ -S "$sock" ]] && WAYLAND_DISPLAY="$(basename "$sock")"
        done
        [[ -n "$WAYLAND_DISPLAY" ]] && break
        sleep 0.1
    done
    [[ -n "$WAYLAND_DISPLAY" ]] || die "sway did not start: $(cat "$WORK/sway.log")"
    export WAYLAND_DISPLAY
}

set_users() {  # "login:Real Name" ...
    local u
    local name uid
    while IFS=: read -r name _ uid _; do
        if (( uid >= 1000 && uid < 60000 )); then userdel -r "$name" 2>/dev/null || true; fi
    done < <(cat /etc/passwd)
    for u in "$@"; do useradd -m -c "${u#*:}" "${u%%:*}"; done
    mkdir -p /var/lib/sddm
    printf '[Last]\nUser=noa\nSession=mango.desktop\n' > /var/lib/sddm/state.conf
}

start_greeter() {
    stop "$GREETER_PID"
    QT_QPA_PLATFORM=wayland sddm-greeter-qt6 --test-mode --theme "$WORK/theme" >"$WORK/greeter.log" 2>&1 &
    GREETER_PID=$!
    sleep "${GREETER_WAIT:-5}"
    kill -0 "$GREETER_PID" 2>/dev/null || die "greeter exited: $(cat "$WORK/greeter.log")"
}

shot() { grim "$OUT/$1"; log "wrote sddm/preview/$1"; }

# keys ARGS... : type with wtype. The virtual keyboard must outlive the
# screenshot: when it goes away sway sends the window a keyboard leave and Qt
# drops focus. So wtype waits before typing (keymap settles) and after.
keys() {
    wtype -s 700 "$@" -s 5000 >/dev/null 2>&1 &
    local pid=$!
    sleep "${KEYS_WAIT:-2}"
    echo "$pid"
}

start_sway 1920x1080
set_users "noa:Noa Levi"
start_greeter
shot login-single.png

k=$(KEYS_WAIT=2.8 keys not-my-password -k Return)
shot login-error.png
stop "$k"
k=$(KEYS_WAIT=2 keys -k Tab -k Tab -k Tab)   # log in -> session -> suspend (focus ring + tooltip)
shot login-power-focus.png
stop "$k"

set_users "noa:Noa Levi" "amit:Amit Cohen" "guest:Guest"
start_greeter
shot login-multi.png
k=$(KEYS_WAIT=1.5 keys -k Tab)
shot login-multi-focus.png
stop "$k"
k=$(KEYS_WAIT=2 keys -k Tab -k Tab -k Return)   # users -> log in -> session, open
shot login-session-menu.png
stop "$k"

start_sway 1280x800
set_users "noa:Noa Levi"
start_greeter
shot login-1280x800.png

# Same size as the design mockups (components/LoginScreen, 960x600).
start_sway 960x600
set_users "noa:Noa Levi" "amit:Amit Cohen" "guest:Guest"
start_greeter
shot login-960x600.png
