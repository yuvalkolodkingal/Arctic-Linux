#!/usr/bin/env bash
# Boot the Plymouth theme for real: a Fedora kernel + a dracut initramfs with
# plymouth, the arctic theme and the 90arctic-plymouth module, booted in QEMU
# (TCG, std VGA 1920x1080, bochs-drm). There is no root disk, so the initrd
# waits and the splash stays up long enough to screenshot.
#
# Output: branding/plymouth/preview/
#   splash-a.png, splash-b.png      two frames 0.7 s apart (they must differ: breathing/dots)
#   splash-reduced-a/b.png          arctic.reduce_motion=1: two frames that must be identical
#   passphrase.png                  `plymouth ask-for-password` with 6 characters typed
# Runs only in a throwaway Fedora container (it installs the theme system-wide).
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [[ -z "${ARCTIC_BRANDING_IN_CONTAINER:-}" ]]; then
    EXTRA_DEPS="plymouth plymouth-plugin-script plymouth-scripts dracut systemd systemd-udev kbd qemu-system-x86-core seabios-bin seavgabios-bin" \
        reexec_in_container branding/tools/preview-plymouth.sh
    exit 0
fi
if ! ls /lib/modules/*/vmlinuz >/dev/null 2>&1; then
    dnf -y -q install --setopt=install_weak_deps=False --setopt=tsflags=noscripts kernel-core kernel-modules-core >/dev/null
fi
KV="$(find /lib/modules -mindepth 1 -maxdepth 1 -printf '%f\n' | sort -V | tail -1)"
[[ -f "/lib/modules/$KV/modules.dep" ]] || depmod -a "$KV"   # skipped when installed with noscripts
OUT="$BRANDING_DIR/plymouth/preview"
WORK="$(mktemp -d)"
QEMU=""
cleanup() { [[ -n "$QEMU" ]] && kill "$QEMU" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT
mkdir -p "$OUT"

# theme + dracut module, installed as the RPMs will
rm -rf /usr/share/plymouth/themes/arctic /usr/lib/dracut/modules.d/90arctic-plymouth
cp -r "$BRANDING_DIR/plymouth/arctic" /usr/share/plymouth/themes/arctic
cp -r "$BRANDING_DIR/plymouth/dracut/90arctic-plymouth" /usr/lib/dracut/modules.d/
plymouth-set-default-theme arctic
# QEMU/TCG brings up bochs-drm slowly; give plymouthd longer than the default 8 s
# to find it before it falls back to the text splash. (Append: the theme
# lookup in plymouth-set-default-theme only reads the first key of [Daemon].)
sed -i '/^DeviceTimeout=/d' /etc/plymouth/plymouthd.conf
echo 'DeviceTimeout=60' >> /etc/plymouth/plymouthd.conf
[[ "$(plymouth-set-default-theme)" == arctic ]] || die "arctic is not the default plymouth theme"

# test-only unit: ask for a passphrase when the kernel command line says so
mkdir -p "$WORK/extra/etc/systemd/system/sysinit.target.wants"
cat > "$WORK/extra/etc/systemd/system/arctic-askpass-test.service" <<'EOF'
[Unit]
Description=Ask for a passphrase (Arctic splash preview)
DefaultDependencies=no
ConditionKernelCommandLine=arctic.test_prompt=1
After=plymouth-start.service
Wants=plymouth-start.service
[Service]
Type=simple
ExecStart=/bin/sh -c 'sleep 3; exec /usr/bin/plymouth ask-for-password --prompt="Please enter passphrase for disk luks-test"'
EOF
ln -s ../arctic-askpass-test.service "$WORK/extra/etc/systemd/system/sysinit.target.wants/arctic-askpass-test.service"

log "dracut initramfs for $KV"
dracut -q --force --no-hostonly --no-compress --kver "$KV" \
    -m "base systemd systemd-initrd dracut-systemd udev-rules kernel-modules drm plymouth arctic-plymouth" \
    --add-drivers "bochs virtio-gpu" --include "$WORK/extra" / "$WORK/initrd.img"
lsinitrd "$WORK/initrd.img" > "$WORK/initrd.list"
grep -q 'themes/arctic/arctic.script' "$WORK/initrd.list" || die "theme missing from the initramfs"
grep -q 'plymouth-start.service.d/arctic-reduce-motion.conf' "$WORK/initrd.list" || die "reduce-motion hook missing"
grep -q 'usr/libexec/arctic/plymouth-reduce-motion' "$WORK/initrd.list" || die "reduce-motion script missing"

boot() {  # extra kernel args
    [[ -n "$QEMU" ]] && { kill "$QEMU" 2>/dev/null; wait "$QEMU" 2>/dev/null || true; }
    rm -f "$WORK/mon.sock" "$WORK/serial.log"
    qemu-system-x86_64 -m 1024 -kernel "/lib/modules/$KV/vmlinuz" -initrd "$WORK/initrd.img" \
        -append "quiet splash rhgb root=LABEL=arctic-nonexistent rd.timeout=0 console=ttyS0 plymouth.ignore-serial-consoles loglevel=3 rd.driver.pre=bochs $*" \
        -vga std -global VGA.xres=1920 -global VGA.yres=1080 -display none \
        -serial "file:$WORK/serial.log" -monitor "unix:$WORK/mon.sock,server,nowait" -no-reboot &
    QEMU=$!
}
monitor() {
    python3 - "$WORK/mon.sock" "$@" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX)
for _ in range(200):
    try:
        s.connect(sys.argv[1]); break
    except OSError:
        time.sleep(0.1)
time.sleep(0.2); s.recv(65536)
for cmd in sys.argv[2:]:
    s.sendall((cmd + "\n").encode()); time.sleep(0.25)
time.sleep(0.3)
s.close()
EOF
}
grab() {  # OUT.png
    monitor "screendump $WORK/shot.ppm"
    python3 -c 'import sys; from PIL import Image; Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], optimize=True)' "$WORK/shot.ppm" "$1"
}
# wait until the splash (amber eyes) is on screen
wait_splash() {
    for _ in $(seq 90); do
        sleep 2
        grab "$WORK/probe.png" 2>/dev/null || continue
        if python3 - "$WORK/probe.png" <<'EOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGB").resize((480, 270))
amber = sum(1 for p in im.getdata() if p[0] > 200 and 150 < p[1] < 210 and p[2] < 120)
sys.exit(0 if amber > 3 else 1)
EOF
        then return 0; fi
    done
    die "splash never appeared; serial log: $(tail -20 "$WORK/serial.log")"
}
differs() {  # A B -> prints the number of differing pixels
    python3 - "$1" "$2" <<'EOF'
import sys
from PIL import Image, ImageChops
a, b = (Image.open(p).convert("RGB") for p in sys.argv[1:3])
print(sum(1 for p in ImageChops.difference(a, b).getdata() if p != (0, 0, 0)))
EOF
}

log "boot 1: splash"
boot
wait_splash
sleep 3
grab "$OUT/splash-a.png"; sleep 0.7; grab "$OUT/splash-b.png"
log "splash frames differ in $(differs "$OUT/splash-a.png" "$OUT/splash-b.png") px (animation)"

log "boot 2: arctic.reduce_motion=1"
boot arctic.reduce_motion=1
wait_splash
sleep 3
grab "$OUT/splash-reduced-a.png"; sleep 0.7; grab "$OUT/splash-reduced-b.png"
log "reduced frames differ in $(differs "$OUT/splash-reduced-a.png" "$OUT/splash-reduced-b.png") px (want 0)"

log "boot 3: passphrase prompt"
boot arctic.test_prompt=1
wait_splash
sleep 8
monitor "sendkey a" "sendkey r" "sendkey c" "sendkey t" "sendkey i" "sendkey c"
sleep 1.5
grab "$OUT/passphrase.png"
log "wrote plymouth/preview/{splash-a,splash-b,splash-reduced-a,splash-reduced-b,passphrase}.png"
