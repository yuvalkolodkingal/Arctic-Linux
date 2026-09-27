#!/usr/bin/env bash
# Boot the GRUB theme for real and screenshot it: a BIOS rescue ISO made with
# grub2-mkrescue (theme + the live ISO's menu entries), booted in QEMU (TCG,
# std VGA), captured through the QEMU monitor.
# Output: branding/grub/preview/{boot-menu,boot-menu-second,boot-menu-cmdline}.png
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
EXTRA_DEPS="grub2-pc-modules grub2-tools grub2-tools-extra xorriso mtools qemu-system-x86-core seabios-bin seavgabios-bin" \
    ensure_tools branding/tools/preview-grub.sh grub2-mkrescue qemu-system-x86_64 xorriso

THEME="$BRANDING_DIR/grub/arctic"
OUT="$BRANDING_DIR/grub/preview"
RES="${GRUB_PREVIEW_RES:-1920x1080}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT" "$WORK/iso/boot/grub/themes"
cp -r "$THEME" "$WORK/iso/boot/grub/themes/arctic"

{
    echo 'insmod all_video'
    echo 'insmod gfxterm'
    echo 'insmod png'
    echo "set gfxmode=$RES,auto"
    echo 'set gfxpayload=keep'
    for f in "$THEME"/*.pf2; do echo "loadfont \$prefix/themes/arctic/$(basename "$f")"; done
    echo 'terminal_output gfxterm'
    # shellcheck disable=SC2016  # $prefix is expanded by GRUB
    echo 'set theme=$prefix/themes/arctic/theme.txt'
    echo 'set timeout=30'
    echo 'set default=0'
    for e in "Try Arctic Linux" "Install Arctic Linux" "Safe graphics mode" "Check USB for errors" "Boot from first disk"; do
        echo "menuentry '$e' { echo '$e' }"
    done
} > "$WORK/iso/boot/grub/grub.cfg"

grub2-mkrescue -o "$WORK/menu.iso" "$WORK/iso" >"$WORK/mkrescue.log" 2>&1 \
    || die "grub2-mkrescue failed: $(cat "$WORK/mkrescue.log")"

W="${RES%x*}"; H="${RES#*x}"
qemu-system-x86_64 -m 256 -cdrom "$WORK/menu.iso" -boot d -vga std \
    -global VGA.xres="$W" -global VGA.yres="$H" \
    -display none -monitor "unix:$WORK/mon.sock,server,nowait" -no-reboot &
QEMU=$!
trap 'kill $QEMU 2>/dev/null || true; rm -rf "$WORK"' EXIT

monitor() {
    python3 - "$WORK/mon.sock" "$@" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX)
for _ in range(100):
    try:
        s.connect(sys.argv[1]); break
    except OSError:
        time.sleep(0.1)
time.sleep(0.2); s.recv(65536)
for cmd in sys.argv[2:]:
    s.sendall((cmd + "\n").encode()); time.sleep(0.4)
s.close()
EOF
}
shot() {
    monitor "screendump $WORK/shot.ppm"
    sleep 0.5
    python3 -c 'import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2], optimize=True)' "$WORK/shot.ppm" "$OUT/$1"
    log "wrote grub/preview/$1 ($(python3 -c 'import sys; from PIL import Image; print("%dx%d" % Image.open(sys.argv[1]).size)' "$OUT/$1"))"
}

sleep "${GRUB_BOOT_WAIT:-12}"     # SeaBIOS + GRUB + theme load under TCG
shot boot-menu.png
monitor "sendkey down"
sleep 2
shot boot-menu-second.png
monitor "sendkey c"
sleep 2
shot boot-menu-cmdline.png
