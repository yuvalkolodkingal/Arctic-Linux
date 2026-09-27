#!/bin/bash
# Headless end-to-end run of the installer UI against the python mock engine:
# sway (headless, pixman) + quickshell + dev/mock-bridge.py. Walks every wizard
# view through the "installer" IPC target (and real key presses via wtype) and
# saves a screenshot of each one.
#
#   dev/test-headless.sh [out-dir]          default out-dir: dev/screenshots
#   THEME=light dev/test-headless.sh /tmp/shots-light
#
# Needs: sway, grim, quickshell, python3 (wtype optional: keyboard checks).
# Exit status is non-zero when a step doesn't show up or a check fails.
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out=${1:-$here/dev/screenshots}
theme=${THEME:-dark}
mkdir -p "$out"

export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-$(mktemp -d)}
chmod 700 "$XDG_RUNTIME_DIR"
work=$(mktemp -d)
pids=()
cleanup() {
    for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
    rm -rf "$work"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; echo "--- quickshell log" >&2; grep -v MESA "$work/qs.log" | tail -30 >&2 || true; exit 1; }
log() { echo "== $*"; }

# ---- compositor
printf 'output HEADLESS-1 resolution 1280x800\ndefault_border none\n' > "$work/sway.conf"
before=$(ls "$XDG_RUNTIME_DIR" 2>/dev/null | grep -E '^wayland-[0-9]+$' || true)
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
    sway -c "$work/sway.conf" > "$work/sway.log" 2>&1 &
pids+=($!)
for _ in $(seq 50); do
    sock=$(ls "$XDG_RUNTIME_DIR" 2>/dev/null | grep -E '^wayland-[0-9]+$' | grep -vxF "$before" | head -1 || true)
    [ -n "$sock" ] && break
    sleep 0.1
done
[ -n "${sock:-}" ] || { cat "$work/sway.log"; echo "FAIL: sway did not start" >&2; exit 1; }
export WAYLAND_DISPLAY=$sock QT_QPA_PLATFORM=wayland
log "sway on $WAYLAND_DISPLAY"

# ---- installer UI + mock engine
export ARCTIC_INSTALLER_BRIDGE="python3 $here/dev/mock-bridge.py"
export ARCTIC_INSTALLER_THEME=$theme
export ARCTIC_MOCK_SPEED=${ARCTIC_MOCK_SPEED:-1.5}
export ARCTIC_MOCK_LOG="$work/mock.log"
# The live keyboard helper (live/live-keyboard): here a stub that records its arguments.
printf '#!/bin/sh\necho "$*" >> %s/live-keyboard.log\n' "$work" > "$work/live-keyboard"
chmod +x "$work/live-keyboard"
export ARCTIC_LIVE_KEYBOARD="$work/live-keyboard"
start_ui() { # start_ui [VAR=value …]: (re)start quickshell with extra mock settings
    if [ -n "${qs:-}" ]; then kill "$qs" 2>/dev/null || true; wait "$qs" 2>/dev/null || true; fi
    env "$@" quickshell -p "$here" > "$work/qs.log" 2>&1 &
    qs=$!
    pids+=($qs)
}
start_ui

ipc() { quickshell ipc --pid "$qs" call installer "$@" 2>/dev/null; }
state() { ipc state || echo '{}'; }
field() { state | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1',''))"; }
wait_for() { # wait_for <python-expr over d> <what>
    for _ in $(seq 150); do
        if state | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if ($1) else 1)" 2>/dev/null; then return 0; fi
        sleep 0.2
    done
    fail "timed out waiting for $2 (state: $(state))"
}
# ready: the page has been up for its arm delay (the primary action works) and nothing is saving.
wait_page() { wait_for "d.get('page')=='$1' and d.get('ready')" "page $1"; }
shot() { sleep "${2:-0.7}"; grim "$out/$1.png"; log "screenshot $1.png"; }
next() { r=$(ipc next); [ "$r" = "ok" ] || fail "next on $(field page): $r"; }
fill() { r=$(ipc fill "$1"); [ "$r" = "ok" ] || fail "fill $1: $r"; }
# wtype makes a new virtual keyboard each run; give Qt a moment to bind it (-s).
key() { command -v wtype >/dev/null && wtype -s 400 "$@"; }

wait_for "d.get('connected')" "engine connection"

# 1 Welcome
wait_page welcome
shot 01-welcome
fill '{"query": "de"}'
shot 01b-welcome-search
fill '{"query": "", "language": "en_US.UTF-8"}'

# Real keys: Enter = Next (the list has focus, a language is pre-selected).
if command -v wtype >/dev/null; then
    key -k Return
    wait_page keyboard
    # Alt+Left = Back
    key -M alt -k Left -m alt
    wait_page welcome
    # F1 = help
    key -k F1
    shot 00-help-dialog
    key -k Escape
    sleep 0.3
    key -k Return
else
    next
fi

# 2 Keyboard
wait_page keyboard
# Picking a layout applies it to the live session (live-keyboard with the engine's choice).
fill '{"layout": "de"}'
for _ in $(seq 50); do grep -qE '^(--xkb )?de( |$)' "$work/live-keyboard.log" 2>/dev/null && break; sleep 0.1; done
grep -qE '^(--xkb )?de( |$)' "$work/live-keyboard.log" || fail "the German layout wasn't applied live ($(cat "$work/live-keyboard.log" 2>/dev/null))"
fill '{"layout": "us"}'
wait_for "d.get('keyboard') == 'us'" "the US layout saved again"
fill '{"try": "The quick arctic fox"}'
shot 02-keyboard
next

# 3 Network: offline at first, Next disabled until connected.
wait_page network
[ "$(field valid)" = "False" ] || fail "network step should block Next while offline"
shot 03a-network-offline
fill '{"ssid": "Tundra-5G"}'
shot 03b-network-password
fill '{"ssid": "Tundra-5G", "password": "wrong-password"}'
wait_for "d.get('busy') == False" "the connection attempt"
sleep 2
shot 03c-network-wrong-password
fill '{"ssid": "Tundra-5G", "password": "polarnight"}'
wait_for "d.get('valid')" "Wi-Fi connection"
shot 03-network
next

# 4 Time zone
wait_page timezone
shot 04-timezone
fill '{"open": "city"}'
shot 04b-timezone-dropdown
fill '{"open": ""}'
next

# 5 Disk (Tab from the pre-selected card shows the keyboard focus ring)
wait_page disk
shot 05-disk
if command -v wtype >/dev/null; then
    # Keep the virtual keyboard alive while capturing: when it goes away the
    # window loses keyboard focus and the ring (correctly) disappears.
    wtype -s 400 -k Tab -s 2500 &
    sleep 1.4
    shot 05b-disk-focus-ring 0
    wait $! || true
fi
next

# 6 Encryption
wait_page encryption
fill '{"passphrase": "correct horse battery staple", "confirm": "correct horse battery staple", "focus": "confirm"}'
wait_for "d.get('valid')" "a valid passphrase"
shot 06-encryption
fill '{"enabled": false}'
shot 06b-encryption-off
fill '{"enabled": true}'
next

# 7 Account (first with a typo in the confirmation, as in the mockup)
wait_page account
fill '{"full_name": "Noa Levi", "password": "snowy-owl-42", "confirm": "snowy-owl", "focus": "confirm"}'
sleep 0.6
[ "$(field valid)" = "False" ] || fail "account step should block Next while passwords differ"
shot 07-account
fill '{"confirm": "snowy-owl-42"}'
wait_for "d.get('valid')" "a valid account"
shot 07b-account-valid
next

# 8 Apps (tick Steam too: 9 apps, and the mock makes Steam fail later)
wait_page apps
# The optional groups start folded: only the design's seven sections have app rows.
wait_for "d.get('step',{}).get('open')==[] and d.get('step',{}).get('rows')==38" "folded optional groups"
wait_for "d.get('note')=='8 apps · 2.1 GB download'" "the default download estimate"
fill '{"select": ["steam"]}'
wait_for "d.get('step',{}).get('open')==['gaming'] and d.get('note','').startswith('9 apps')" "Steam ticked, Games open"
shot 08-apps
fill '{"scroll": 520}'
shot 08b-apps-scrolled
fill '{"scroll": 0}'
# Search looks through every group and opens the ones with matches.
fill '{"query": "pdf"}'
wait_for "d.get('step',{}).get('matches',0)>=3 and d.get('step',{}).get('rows')==d.get('step',{}).get('matches')" "search results"
shot 08c-apps-search
fill '{"query": ""}'
# Keyboard: Space on a folded group opens it; Left folds it again.
if command -v wtype >/dev/null; then
    fill '{"focus": "group:music"}'
    key -k space
    wait_for "'music' in d.get('step',{}).get('open',[])" "Space opens a group"
    shot 08d-apps-group-open
    key -k Left
    wait_for "'music' not in d.get('step',{}).get('open',[])" "Left folds a group"
fi
next

# 9 Summary
wait_page summary
shot 09-summary
# Enter doesn't start the install from Summary (only the button does), Esc asks first.
if command -v wtype >/dev/null; then
    key -k Return
    sleep 0.5
    [ "$(field page)" = "summary" ] || fail "Enter on Summary started the install"
fi
r=$(ipc quit); [ "$r" = "asking" ] || fail "Esc on Summary should ask first: $r"
shot 09b-quit-dialog
if command -v wtype >/dev/null; then key -k Escape; sleep 0.4; fi
next

# 10 Installing
wait_page install
wait_for "d.get('page')=='install' and 'Installing ' in d.get('status','') and int(d.get('apps','0/0').split('/')[0]) >= 2" "the apps phase"
shot 10-install 0.2

# 11 Attention: the optional app (Steam) fails
wait_for "d.get('page')=='attention'" "the attention view"
shot 11-attention
r=$(ipc retry); [ "$r" = "ok" ] || fail "retry: $r"

# 12 Done
wait_page done
shot 12-done 1.0

# ---- scenario 2: wired (network step skipped) + a core failure, Winter theme
log "scenario 2: wired, core failure"
start_ui ARCTIC_MOCK_WIRED=1 ARCTIC_MOCK_FATAL=2 ARCTIC_INSTALLER_THEME=light
wait_for "d.get('connected')" "engine connection (2)"
wait_page welcome
next
wait_page keyboard
next
wait_page timezone        # network skipped: wired and online
ipc back >/dev/null
wait_page keyboard        # and skipped going back too
next
wait_page timezone
shot 04w-timezone-winter
next
wait_page disk
fill '{"disk": "/dev/sda"}'
shot 05w-disk-no-alongside-winter
next
wait_page encryption
fill '{"passphrase": "short", "confirm": "short"}'
sleep 0.5
[ "$(field valid)" = "False" ] || fail "a too-short passphrase must block Next"
fill '{"suggest": true}'
wait_for "d.get('valid')" "a suggested passphrase"
shot 06w-encryption-suggested-winter
next
wait_page account
fill '{"full_name": "Ada Frost", "password": "glacier-lake-7", "confirm": "glacier-lake-7", "username": "Root"}'
sleep 0.5
[ "$(field valid)" = "False" ] || fail "an upper-case username must block Next"
fill '{"username": "root"}'
wait_for "d.get('valid')" "account form"
next
wait_for "d.get('fields',{}).get('username')" "the engine's username error"
shot 07w-account-engine-error-winter
fill '{"username": "ada"}'
wait_for "d.get('valid')" "account form (2)"
# The password as the disk passphrase too: it must pass as a passphrase (Fair or better).
fill '{"same_as_disk": true, "password": "iloveyou", "confirm": "iloveyou"}'
sleep 0.6
[ "$(field valid)" = "False" ] || fail "a Weak password can't be the disk passphrase too"
fill '{"same_as_disk": false, "password": "glacier-lake-7", "confirm": "glacier-lake-7"}'
wait_for "d.get('valid')" "account form (3)"
next
wait_page apps
# Office is "pick one" but optional: clicking the ticked suite unticks it.
fill '{"toggle": ["collabora"]}'
next
wait_page summary
shot 09w-summary-winter
next
wait_for "d.get('page')=='failed'" "the core failure view"
shot 11b-failed-winter
ipc savelog >/dev/null
shot 11c-failed-log-saved-winter
fill '{"show_details": true}'
shot 11d-failed-details-winter
# Change your answers: back to the Summary, pick the other disk, install again.
r=$(ipc change); [ "$r" = "ok" ] || fail "change after failure: $r"
wait_page summary
ipc goto disk >/dev/null
wait_page disk
fill '{"disk": "/dev/nvme0n1", "mode": "erase"}'
next
wait_page summary         # Change → Next goes back to Summary
ipc goto encryption >/dev/null
wait_page encryption      # the passphrase is kept: Next works with empty fields
[ "$(field valid)" = "True" ] || fail "a kept passphrase should allow Next"
shot 06x-encryption-kept-winter
next
wait_page summary
ipc goto account >/dev/null
wait_page account         # so is the password
[ "$(field valid)" = "True" ] || fail "a kept password should allow Next"
next
wait_page summary
next
wait_for "d.get('page')=='failed'" "the core failure view (2)"
r=$(ipc retry); [ "$r" = "ok" ] || fail "retry after failure: $r"
wait_for "d.get('page')=='attention'" "the optional app failure (2)"
r=$(ipc skip); [ "$r" = "ok" ] || fail "skip: $r"
wait_page done
shot 12w-done-winter 1.0

# ---- scenario 3: the engine can't be reached
log "scenario 3: engine not reachable"
start_ui ARCTIC_INSTALLER_BRIDGE='sh -c "echo arctic-install: cannot connect to /run/arcticd.sock >&2; exit 3"'
wait_for "d.get('failure')" "the engine failure message"
shot 00b-engine-down
# As `arctic-install bridge` does it: a failed event on stdout. It is about the engine (the
# "couldn't start" screen with its message), not a failed install.
cat > "$work/no-engine-bridge" << 'EOF'
#!/bin/sh
echo '{"event":"failed","title":"The installer could not start","message":"The installer engine is not running.","details":"dial unix /run/arcticd.sock: no such file","fatal":true}'
echo "arctic-install bridge: dial unix /run/arcticd.sock: no such file" >&2
exit 1
EOF
chmod +x "$work/no-engine-bridge"
start_ui ARCTIC_INSTALLER_BRIDGE="$work/no-engine-bridge"
wait_for "'engine is not running' in d.get('failure','') and d.get('page') == ''" "the bridge's own message"
shot 00c-engine-down-bridge-message

# ---- Esc on the first step quits straight away (nothing to lose)
start_ui
wait_for "d.get('connected')" "engine connection (4)"
wait_page welcome
if command -v wtype >/dev/null; then
    key -k Escape
else
    ipc quit >/dev/null || true
fi
for _ in $(seq 50); do kill -0 "$qs" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$qs" 2>/dev/null; then fail "Esc on Welcome didn't quit the installer"; fi
grep -q '"office": \[\]' "$work/mock.log" || fail "unticking the office suite didn't reach the engine"

log "mock engine requests:"
grep -c ' < ' "$work/mock.log" || true
if grep -q -E 'polarnight|correct horse|snowy-owl|glacier-lake' "$work/mock.log"; then
    fail "a secret reached the mock log"
fi
log "OK: all steps shown; screenshots in $out"
