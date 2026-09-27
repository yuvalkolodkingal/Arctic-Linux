#!/usr/bin/env bash
# Boot the Arctic Linux ISO in QEMU (no KVM needed: TCG) and take screenshots.
#
#   tools/test-iso.sh                         UEFI (OVMF), "Try Arctic Linux", 15 min
#   tools/test-iso.sh --firmware bios         SeaBIOS instead of OVMF
#   tools/test-iso.sh --mode install          pick "Install Arctic Linux" in the boot menu
#   tools/test-iso.sh --mode safe|check|disk  the other boot menu entries
#   tools/test-iso.sh --timeout 600           seconds to run after power-on (default 900)
#   tools/test-iso.sh --interval 60           seconds between screenshots once booting
#   tools/test-iso.sh --iso PATH              default out/iso/Arctic-Linux-0.1-x86_64.iso
#   tools/test-iso.sh --memory 4096 --smp 4   guest size (default 4 GiB, 4 vCPUs)
#   tools/test-iso.sh --kvm                   use /dev/kvm when the host has it
#   tools/test-iso.sh --vga std               QEMU display (virtio, default; std = bochs)
#   tools/test-iso.sh --append 'ARGS'         add kernel arguments by editing the entry in GRUB
#   tools/test-iso.sh --debug                 --append 'console=tty0 console=ttyS0,115200
#                                             systemd.journald.forward_to_console=1': the whole
#                                             journal (system and session) lands in serial.log
#   tools/test-iso.sh --secureboot            UEFI with Secure Boot on (OVMF secboot, MS keys)
#
# QEMU runs headless in a Fedora 44 container (qemu-system-x86-core, edk2-ovmf) with a QMP
# socket. Screenshots (PNG) go to out/test/<firmware>-<mode>/: the boot menu when it
# appears (detected on screen: the amber selection of the arctic GRUB theme, or GRUB's text
# menu), the boot splash, then one every --interval seconds, and a last one. The keys for
# the chosen entry are sent with QMP send-key once the menu is on screen. The guest also
# gets an empty 64 GB target disk (sparse qcow2) for the installer. The serial console
# is logged to serial.log.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
ISO="$ROOT/out/iso/Arctic-Linux-0.1-x86_64.iso"
FIRMWARE=uefi
MODE=try
TIMEOUT=900
INTERVAL=60
MEMORY=4096
SMP=4
KVM=0
SECUREBOOT=0
VGA=virtio
APPEND=""
OUTBASE="$ROOT/out/test"

while (( $# )); do
  case "$1" in
    --iso) ISO="$2"; shift 2 ;;
    --firmware) FIRMWARE="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --smp) SMP="$2"; shift 2 ;;
    --kvm) KVM=1; shift ;;
    --vga) VGA="$2"; shift 2 ;;
    --append) APPEND="$APPEND $2"; shift 2 ;;
    --debug) APPEND="$APPEND console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1"; shift ;;
    --secureboot) SECUREBOOT=1; FIRMWARE=uefi; shift ;;
    --out) OUTBASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$FIRMWARE" in uefi|bios) ;; *) arctic_die "--firmware takes uefi or bios" ;; esac
case "$MODE" in try|install|safe|check|disk) ;; *) arctic_die "--mode takes try, install, safe, check or disk" ;; esac
[[ -f "$ISO" ]] || arctic_die "no ISO at $ISO (run tools/build-iso.sh)"
ISO="$(cd "$(dirname "$ISO")" && pwd)/$(basename "$ISO")"

sb=""; if [[ $SECUREBOOT == 1 ]]; then sb="-sb"; fi
OUT="$OUTBASE/$FIRMWARE$sb-$MODE"
rm -rf "$OUT"; mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
kvm_args=()
if (( KVM )) && [[ -e /dev/kvm ]]; then kvm_args=(--device /dev/kvm); fi

# ---- the QMP driver (runs in the container) ----------------------------------------------
read -r -d '' DRIVER <<'PY' || true
import json, os, socket, subprocess, sys, time
from PIL import Image

out, mode, timeout, interval = os.environ["OUT"], os.environ["MODE"], int(os.environ["TIMEOUT"]), int(os.environ["INTERVAL"])
append = os.environ.get("APPEND", "").strip()
qemu = subprocess.Popen(sys.argv[1:], stdout=open(f"{out}/qemu.log", "w"), stderr=subprocess.STDOUT)

def log(msg):
    line = f"[{time.time() - t0:6.0f}s] {msg}"
    print(line, flush=True)
    with open(f"{out}/test.log", "a") as f:
        f.write(line + "\n")

class QMP:
    def __init__(self, path):
        for _ in range(300):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(path)
                break
            except OSError:
                if qemu.poll() is not None:
                    raise SystemExit("qemu exited: see qemu.log")
                time.sleep(0.2)
        self.f = self.s.makefile("rw")
        json.loads(self.f.readline())
        self.cmd("qmp_capabilities")

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.f.write(json.dumps(msg) + "\n")
        self.f.flush()
        while True:
            reply = json.loads(self.f.readline())
            if "return" in reply or "error" in reply:
                return reply

t0 = time.time()
qmp = QMP(f"{out}/qmp.sock")
log(f"qemu started: {' '.join(sys.argv[1:])}")

def shot(name):
    path = f"{out}/{name}.png"
    r = qmp.cmd("screendump", filename=path, format="png")
    if "error" in r:
        log(f"screendump failed: {r['error']}")
        return None
    return path

def keys(*names):
    """Press keys one after the other; "ctrl-x" style names press a chord."""
    for k in names:
        chord = k.split("-") if len(k) > 1 and "-" in k else [k]
        qmp.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in chord])
        time.sleep(0.3)

QCODE = {" ": "spc", "=": "equal", ",": "comma", ".": "dot", "-": "minus", "/": "slash",
         ";": "semicolon", "'": "apostrophe"}
SHIFTED = {"_": "minus", ":": "semicolon", "+": "equal", '"': "apostrophe"}

def type_text(text):
    for ch in text:
        if ch.isalnum() and ch.isascii():
            chord = ["shift", ch.lower()] if ch.isupper() else [ch]
        elif ch in QCODE:
            chord = [QCODE[ch]]
        elif ch in SHIFTED:
            chord = ["shift", SHIFTED[ch]]
        else:
            raise SystemExit(f"cannot type {ch!r}")
        qmp.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in chord])
        time.sleep(0.08)

def looks_like_boot_menu(path):
    """The arctic GRUB theme: an amber (#f6bd55) selection bar. GRUB's text menu: a light
    highlight bar spanning most of a text row."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w < 320:
        return False
    small = im.resize((w // 4, h // 4))
    px = small.load()
    sw, sh = small.size
    amber = 0
    bar_rows = 0
    for y in range(sh):
        bright = 0
        for x in range(sw):
            r, g, b = px[x, y]
            if abs(r - 246) < 30 and abs(g - 189) < 35 and abs(b - 85) < 40:
                amber += 1
            if r > 150 and g > 150 and b > 150:
                bright += 1
        if bright > sw * 0.6:
            bar_rows += 1
    return amber > 400 or 2 <= bar_rows <= sh // 6

MENU_KEYS = {"try": [], "install": ["down"], "safe": ["down", "down"],
             "check": ["down", "down", "down"], "disk": ["down", "down", "down", "down"]}

# 1. Wait for the boot menu (up to 5 min under TCG), then choose the entry.
menu_seen = False
n = 0
while time.time() - t0 < min(300, timeout) and qemu.poll() is None:
    p = shot("00-probe")
    n += 1
    if p and looks_like_boot_menu(p):
        os.replace(p, f"{out}/01-boot-menu.png")
        log("boot menu on screen: 01-boot-menu.png")
        menu_seen = True
        break
    time.sleep(1)
if os.path.exists(f"{out}/00-probe.png"):
    os.remove(f"{out}/00-probe.png")
if not menu_seen:
    log("boot menu not detected; continuing (the default entry boots by itself)")
    shot("01-no-menu-detected")
else:
    keys("home", *MENU_KEYS[mode])
    time.sleep(0.5)
    shot("02-boot-menu-selected")
    if append:
        # Edit the entry. Fedora's GRUB shows "setparams '<title>'" as line 1; the linux line
        # is line 2: go to its end, add the arguments, boot with Ctrl+X.
        keys("e")
        time.sleep(1)
        keys("down", "ctrl-e")
        type_text(" " + append)
        time.sleep(0.5)
        shot("03-boot-entry-edited")
        keys("ctrl-x")
        log(f"selected the '{mode}' entry with extra kernel arguments: {append}")
    else:
        keys("ret")
        log(f"selected the '{mode}' entry")

# 2. Splash and boot: every 10 s for the first 2 minutes, then every --interval seconds.
start = time.time()
i = 0
while time.time() - t0 < timeout and qemu.poll() is None:
    elapsed = int(time.time() - start)
    i += 1
    shot(f"{10 + i:02d}-boot-{elapsed:04d}s")
    time.sleep(10 if elapsed < 120 else interval)

if qemu.poll() is None:
    shot("99-final")
    st = qmp.cmd("query-status")
    log(f"final screenshot 99-final.png, vm status: {st.get('return', st)}")
    qmp.cmd("quit")
else:
    log(f"qemu exited early with code {qemu.returncode}")
qemu.wait(timeout=30)
PY

inner=$(cat <<'INNER'
pkgs=(qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow
      qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci)
dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
qemu-img create -q -f qcow2 /tmp/target.qcow2 64G
accel="tcg,thread=multi"
[ -e /dev/kvm ] && accel=kvm
machine=q35
[ "$SECUREBOOT" = 1 ] && machine=q35,smm=on
args=(qemu-system-x86_64 -machine "$machine" -accel "$accel" -cpu max -smp "$SMP" -m "$MEMORY"
      -display none -vga "$VGA" -qmp "unix:$OUT/qmp.sock,server=on,wait=off"
      -serial "file:$OUT/serial.log" -monitor none -no-reboot
      -drive file=/iso,media=cdrom,readonly=on,if=none,id=cd -device ide-cd,drive=cd,bootindex=0
      -drive file=/tmp/target.qcow2,if=none,id=disk -device virtio-blk-pci,drive=disk,bootindex=1
      -netdev user,id=net0 -device virtio-net-pci,netdev=net0
      -device qemu-xhci -device usb-tablet -rtc base=utc)
if [ "$FIRMWARE" = uefi ]; then
  code=/usr/share/edk2/ovmf/OVMF_CODE.fd
  vars=/usr/share/edk2/ovmf/OVMF_VARS.fd
  if [ "$SECUREBOOT" = 1 ]; then
    # Fedora's secboot vars have the Microsoft/Red Hat keys enrolled and Secure Boot on.
    code=/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd
    vars=/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd
    args+=(-global driver=cfi.pflash01,property=secure,value=on)
  fi
  cp "$vars" /tmp/vars.fd
  args+=(-drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=/tmp/vars.fd")
fi
python3 -c "$DRIVER" "${args[@]}"
rm -f "$OUT/qmp.sock"
chown -R "$HOST_UID:$HOST_GID" "$OUT"
INNER
)

arctic_log "booting $(basename "$ISO") ($FIRMWARE, mode $MODE, ${TIMEOUT}s) → $OUT"
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${kvm_args[@]}" \
  -e OUT=/out -e MODE="$MODE" -e TIMEOUT="$TIMEOUT" -e INTERVAL="$INTERVAL" \
  -e FIRMWARE="$FIRMWARE" -e SECUREBOOT="$SECUREBOOT" -e VGA="$VGA" -e APPEND="$APPEND" -e MEMORY="$MEMORY" -e SMP="$SMP" -e DRIVER="$DRIVER" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$ISO:/iso:ro" -v "$OUT:/out" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "screenshots:"
find "$OUT" -maxdepth 1 -name '*.png' | sort | sed 's,^,  ,'
