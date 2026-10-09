#!/usr/bin/env bash
# Boot the Arctic Linux ISO in QEMU (no KVM needed: TCG) and take screenshots.
#
#   tools/test-iso.sh                         UEFI (OVMF), "Try Arctic Linux", 15 min
#   tools/test-iso.sh --firmware bios         SeaBIOS instead of OVMF
#   tools/test-iso.sh --mode install          pick "Install Arctic Linux" in the boot menu
#   tools/test-iso.sh --mode safe|check|disk  the other boot menu entries
#   tools/test-iso.sh --timeout 600           seconds to run after power-on (default 900)
#   tools/test-iso.sh --interval 60           seconds between screenshots once booting
#   tools/test-iso.sh --iso PATH              default out/iso/Arctic-Linux-1.2-x86_64.iso
#   tools/test-iso.sh --memory 4096 --smp 4   guest size (default 4 GiB, 4 vCPUs)
#   tools/test-iso.sh --kvm                   use /dev/kvm when the host has it
#   tools/test-iso.sh --vga std               QEMU display (virtio, default; std = bochs)
#   tools/test-iso.sh --append 'ARGS'         add kernel arguments by editing the entry in GRUB
#   tools/test-iso.sh --debug                 --append 'console=tty0 console=ttyS0,115200
#                                             systemd.journald.forward_to_console=1': the whole
#                                             journal (system and session) lands in serial.log
#   tools/test-iso.sh --collect               at the end, open a terminal (Super+Enter) in the
#                                             live session and copy the session log, failed
#                                             units and warnings to serial.log
#   tools/test-iso.sh --secureboot            UEFI with Secure Boot on (OVMF secboot, MS keys)
#   tools/test-iso.sh --require-startup       require the selected live desktop mode, Mango,
#                                             SELinux enforcing and completed session collection
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
ISO="$ROOT/out/iso/Arctic-Linux-1.2-x86_64.iso"
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
COLLECT=0
REQUIRE_STARTUP=0
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
    --collect) COLLECT=1; shift ;;
    --require-startup) REQUIRE_STARTUP=1; COLLECT=1; shift ;;
    --debug) APPEND="$APPEND console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1"; shift ;;
    --secureboot) SECUREBOOT=1; FIRMWARE=uefi; shift ;;
    --out) OUTBASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$FIRMWARE" in uefi|bios) ;; *) arctic_die "--firmware takes uefi or bios" ;; esac
case "$MODE" in try|install|safe|check|disk) ;; *) arctic_die "--mode takes try, install, safe, check or disk" ;; esac
if (( REQUIRE_STARTUP )); then
  case "$MODE" in try|install|safe) ;; *) arctic_die "--require-startup supports try, install or safe" ;; esac
fi
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

# ---- the QMP driver (runs in the container; tools/lib/vmtest.py has the QMP helpers) -------
read -r -d '' DRIVER <<'PY' || true
import os, sys, time
sys.path.insert(0, "/arctic-lib")
import vmtest
from vmtest import log, looks_like_boot_menu
from iso_startup import collection_command, collection_complete

out, mode, timeout, interval = os.environ["OUT"], os.environ["MODE"], int(os.environ["TIMEOUT"]), int(os.environ["INTERVAL"])
append = os.environ.get("APPEND", "").strip()
collect = os.environ.get("COLLECT") == "1"
require_startup = os.environ.get("REQUIRE_STARTUP") == "1"
t0 = vmtest.T0
vm = vmtest.VM(sys.argv[1:], f"{out}/qmp.sock", "iso", qemu_log=f"{out}/qemu.log")
shot, keys, type_text = vm.shot, vm.keys, vm.type_text

MENU_KEYS = {"try": [], "install": ["down"], "safe": ["down", "down"],
             "check": ["down", "down", "down"], "disk": ["down", "down", "down", "down"]}

# 1. Wait for the boot menu (up to 5 min under TCG), then choose the entry.
menu_seen = False
while time.time() - t0 < min(300, timeout) and vm.alive():
    p = shot("00-probe")
    if p and looks_like_boot_menu(p):
        os.replace(p, f"{out}/01-boot-menu.png")
        log("boot menu on screen: 01-boot-menu.png")
        menu_seen = True
        break
    time.sleep(1)
if os.path.exists(f"{out}/00-probe.png"):
    os.remove(f"{out}/00-probe.png")
if not menu_seen:
    if require_startup:
        log("FAIL: requested boot mode cannot be verified without a detected menu")
        shot("01-no-menu-detected")
        vm.quit()
        sys.exit(1)
    log("boot menu not detected; continuing (the default entry boots by itself)")
    shot("01-no-menu-detected")
else:
    keys("home", *MENU_KEYS[mode])
    time.sleep(0.5)
    shot("02-boot-menu-selected")
    if append:
        # Edit the entry. GRUB shows "setparams '<title>'", an empty line, then the entry's
        # linux line: go to its end, add the arguments, boot with Ctrl+X.
        keys("e")
        time.sleep(1)
        keys("down", "down", "ctrl-e")
        type_text(" " + append, gap=0.2)
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
while time.time() - t0 < timeout and vm.alive():
    elapsed = int(time.time() - start)
    i += 1
    shot(f"{10 + i:02d}-boot-{elapsed:04d}s")
    time.sleep(10 if elapsed < 120 else interval)

if collect and vm.alive():
    # Install mode owns exclusive keyboard focus; preserve its actual window
    # and collect from an authenticated live console instead of driving the UI.
    from iso_startup import collect_session
    try:
        collect_session(vm, mode, require_startup, shot, log, serial_path=f"{out}/serial.log")
    except (RuntimeError, ValueError) as error:
        # Keep the exact collector failure in the screened test.log artifact,
        # rather than only in the running producer's unavailable stderr.
        log(f"FAIL: session collection: {error}")
        shot("99-final")
        vm.quit()
        sys.exit(1)
    if vmtest.serial_has(f"{out}/serial.log", "ARCTIC-COLLECT-END"):
        log("collected the session log into serial.log (between ARCTIC-COLLECT-BEGIN/END)")
    else:
        log("session collection did not complete; inspect the terminal screenshot and serial log")

if vm.alive():
    shot("99-final")
    st = vm.cmd("query-status")
    log(f"final screenshot 99-final.png, vm status: {st.get('return', st)}")
else:
    log(f"qemu exited early with code {vm.proc.returncode}")
vm.quit()
if collect and not collection_complete(f"{out}/serial.log", mode if require_startup else None):
    log("FAIL: selected desktop startup/session collection did not qualify")
    sys.exit(1)
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
      -netdev user,id=net0,restrict=on -device virtio-net-pci,netdev=net0
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
  -e FIRMWARE="$FIRMWARE" -e SECUREBOOT="$SECUREBOOT" -e VGA="$VGA" -e APPEND="$APPEND" -e COLLECT="$COLLECT" -e REQUIRE_STARTUP="$REQUIRE_STARTUP" -e MEMORY="$MEMORY" -e SMP="$SMP" -e DRIVER="$DRIVER" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$ISO:/iso:ro" -v "$OUT:/out" -v "$HERE/lib:/arctic-lib:ro" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "screenshots:"
find "$OUT" -maxdepth 1 -name '*.png' | sort | sed 's,^,  ,'
