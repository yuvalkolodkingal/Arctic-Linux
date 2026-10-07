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
PCMANFM_DIAGNOSTIC=""
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
    --pcmanfm-diagnostic) PCMANFM_DIAGNOSTIC="$2"; shift 2 ;;
    --debug) APPEND="$APPEND console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1"; shift ;;
    --secureboot) SECUREBOOT=1; FIRMWARE=uefi; shift ;;
    --out) OUTBASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$FIRMWARE" in uefi|bios) ;; *) arctic_die "--firmware takes uefi or bios" ;; esac
case "$MODE" in try|install|safe|check|disk) ;; *) arctic_die "--mode takes try, install, safe, check or disk" ;; esac
if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  [[ "$FIRMWARE" == uefi && "$MODE" == try && "$KVM" == 1 && "$SECUREBOOT" == 0 && "$COLLECT" == 0 \
     && "$MEMORY" == 4096 && "$SMP" == 2 && "$VGA" == virtio && "$TIMEOUT" == 900 && -c /dev/kvm \
     && "${ARCTIC_VM_TOOLS_PREPARED:-0}" == 1 ]] || arctic_die "invalid explicit diagnostic VM mode/tools"
  [[ "$APPEND" == " console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1" ]] \
    || arctic_die "diagnostic requires exact native serial arguments"
  PCMANFM_DIAGNOSTIC="$(cd "$PCMANFM_DIAGNOSTIC" && pwd)"
  [[ -f "$PCMANFM_DIAGNOSTIC/pcmanfm-controller.py" && -f "$PCMANFM_DIAGNOSTIC/runtime-pins.json" \
     && -f "$PCMANFM_DIAGNOSTIC/bootstrap-diagnostic.sh" ]] || arctic_die "diagnostic source packet absent"
fi
[[ -f "$ISO" ]] || arctic_die "no ISO at $ISO (run tools/build-iso.sh)"
ISO="$(cd "$(dirname "$ISO")" && pwd)/$(basename "$ISO")"

sb=""; if [[ $SECUREBOOT == 1 ]]; then sb="-sb"; fi
OUT="$OUTBASE/$FIRMWARE$sb-$MODE"
if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  [[ ! -e "$OUT" ]] || arctic_die "diagnostic output must be unused"
  mkdir -p "$OUT"
else
  rm -rf "$OUT"; mkdir -p "$OUT"
fi
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

out, mode, timeout, interval = os.environ["OUT"], os.environ["MODE"], int(os.environ["TIMEOUT"]), int(os.environ["INTERVAL"])
append = os.environ.get("APPEND", "").strip()
collect = os.environ.get("COLLECT") == "1"
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

if os.environ.get("PCMANFM_DIAGNOSTIC") == "1":
    import importlib.util
    spec = importlib.util.spec_from_file_location('pcmanfm_controller', '/pcmanfm-diagnostic/pcmanfm-controller.py')
    bulk_owns_cleanup = False
    try:
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        bspec = importlib.util.spec_from_file_location('diagnostic_bulk_channel', '/pcmanfm-diagnostic/bulk-channel.py')
        bulk_module = importlib.util.module_from_spec(bspec); bspec.loader.exec_module(bulk_module)
        bulk_owns_cleanup = True # Only a successful import transfers cleanup ownership.
        bulk_module.run_owned(vm, out,
            lambda bulk: controller.run_v3(vm, out, menu_seen, os.environ['PCMANFM_CHECKER_SHA'], bulk),
            max(0, min(900, vmtest.T0+timeout-time.time())))
    finally:
        if not bulk_owns_cleanup: vm.quit()
    sys.exit(0)

# 2. Splash and boot: every 10 s for the first 2 minutes, then every --interval seconds.
start = time.time()
i = 0
while time.time() - t0 < timeout and vm.alive():
    elapsed = int(time.time() - start)
    i += 1
    shot(f"{10 + i:02d}-boot-{elapsed:04d}s")
    time.sleep(10 if elapsed < 120 else interval)

if collect and vm.alive():
    # A terminal in the session (Super+Enter → arctic-open terminal), then logs to the serial port.
    shot("97-before-collect")
    keys("meta_l-ret")
    time.sleep(60)
    keys("ret")          # skips the fetch animation (any key does) and gives a fresh prompt
    time.sleep(5)
    shot("98-terminal")
    type_text("sudo sh -c '(echo ARCTIC-COLLECT-BEGIN; "
              'cat ~liveuser/.local/share/sddm/*.log; '
              'echo ARCTIC-CMDLINE-BEGIN; '
              'cat /proc/cmdline; '
              'echo ARCTIC-CMDLINE-END; '
              'echo ARCTIC-SECUREBOOT-BEGIN; '
              'mokutil --sb-state; '
              'echo ARCTIC-SECUREBOOT-END; '
              'echo ARCTIC-FAILED-UNITS-BEGIN; '
              'systemctl --failed --no-pager; '
              'echo ARCTIC-FAILED-UNITS-EXIT=$?; '
              'echo ARCTIC-FAILED-UNITS-END; '
              'echo ARCTIC-WARNINGS-BEGIN; '
              'journalctl -b -p warning --no-pager; '
              'echo ARCTIC-WARNINGS-END; '
              'echo ARCTIC-SELINUX-BEGIN; '
              'getenforce; '
              'echo ARCTIC-SELINUX-END; '
              'echo ARCTIC-AVC-BEGIN; '
              'j=$(mktemp); '
              'journalctl -b --no-pager -o cat >"$j" 2>&1; '
              'echo ARCTIC-AVC-JOURNAL-EXIT=$?; '
              'grep -Ei "avc:.*denied" "$j"; '
              'echo ARCTIC-AVC-FILTER-EXIT=$?; '
              'rm -f "$j"; '
              'echo ARCTIC-AVC-END; '
              'flatpak list; '
              "echo ARCTIC-COLLECT-END) >/dev/ttyS0 2>&1'", gap=0.2)
    keys("ret")
    time.sleep(30)
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
if collect and not (vmtest.serial_has(f"{out}/serial.log", "ARCTIC-COLLECT-BEGIN")
                    and vmtest.serial_has(f"{out}/serial.log", "ARCTIC-COLLECT-END")):
    sys.exit(1)
PY

inner=$(cat <<'INNER'
pkgs=(qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow
      qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci)
if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then
  pkgs+=(xorriso)
  rpm -q "${pkgs[@]}" >/dev/null
else
  dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
fi
disk_size=64G
[ "$PCMANFM_DIAGNOSTIC" != 1 ] || disk_size=40G
qemu-img create -q -f qcow2 /tmp/target.qcow2 "$disk_size"
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
if [ "$PCMANFM_DIAGNOSTIC" = 1 ]; then
  mkdir /tmp/diagnostic-data
  cp /pcmanfm-diagnostic/guest-pcmanfm-diagnostic.py /tmp/diagnostic-data/guest-check.py
  for f in native_smoke.py native-launcher.py atspi-snapshot.py gtk-entry-control.py bounded-launch.py security-collector.py bulk-channel.py gtk-physical.py runtime-pins.json bootstrap-diagnostic.sh original-h264-aac-1s.mp4 codec-fixture-manifest.json; do
    cp "/pcmanfm-diagnostic/$f" /tmp/diagnostic-data/
  done
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'exec python3 /run/t/guest-check.py' > /tmp/diagnostic-data/run.sh
  xorriso -as mkisofs -quiet -V ARCTICDIAG -J -R -G /pcmanfm-diagnostic/bootstrap-diagnostic.sh \
    -o /tmp/diagnostic-data.iso /tmp/diagnostic-data
  # Match the frozen native v4 device choices; only task paths/data payload differ.
  args=(qemu-system-x86_64 -machine q35 -accel kvm -cpu max -smp "$SMP" -m "$MEMORY"
        -display none -vga virtio -qmp "unix:$OUT/qmp.sock,server=on,wait=off"
        -serial "file:$OUT/serial.log" -monitor none -no-reboot
        -chardev "socket,id=arctic_bulk,path=$OUT/bulk.sock,server=on,wait=off"
        -device virtio-serial-pci,id=arctic_bulk_bus
        -device virtserialport,bus=arctic_bulk_bus.0,chardev=arctic_bulk,name=org.arctic.diagnostic.bulk
        -drive file=/tmp/target.qcow2,if=none,id=disk,discard=unmap -device virtio-blk-pci,drive=disk,bootindex=1
        -drive file=/tmp/diagnostic-data.iso,media=cdrom,readonly=on,if=none,id=data -device ide-cd,drive=data,bus=ide.0
        -netdev user,id=net0,restrict=on -device virtio-net-pci,netdev=net0
        -device qemu-xhci -device usb-tablet -rtc base=utc
        -audiodev "wav,id=native_audio,path=$OUT/diagnostic-audio.wav,out.frequency=48000,out.channels=2,out.format=s16"
        -device intel-hda -device hda-output,audiodev=native_audio
        -drive file=/iso,media=cdrom,readonly=on,if=none,id=cd -device ide-cd,drive=cd,bus=ide.1,bootindex=0
        -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=/tmp/vars.fd")
  {
    qemu-system-x86_64 --version
    rpm -q "${pkgs[@]}"
    sha256sum "$(command -v qemu-system-x86_64)" "$code" "$vars" /tmp/diagnostic-data.iso /pcmanfm-diagnostic/*.py
    printf '%q ' "${args[@]}"; printf '\n'
    printf '%s\n' 'Actual new tools/data payload; no earlier tool byte parity or audio acceptance claim.'
  } > "$OUT/pcmanfm-toolchain.txt"
fi
python3 -c "$DRIVER" "${args[@]}"
rm -f "$OUT/qmp.sock"
chown -R "$HOST_UID:$HOST_GID" "$OUT"
INNER
)

arctic_log "booting $(basename "$ISO") ($FIRMWARE, mode $MODE, ${TIMEOUT}s) → $OUT"
# Optional, bounded ownership for timeout cleanup in test-only callers.
name_args=()
if [[ -n "${ARCTIC_VM_CONTAINER_NAME:-}" ]]; then
  [[ "$ARCTIC_VM_CONTAINER_NAME" =~ ^arctic-paired-[a-z0-9-]{1,80}$ ]] || arctic_die "invalid task VM container name"
  name_args=(--name "$ARCTIC_VM_CONTAINER_NAME")
fi
diagnostic_args=()
diagnostic_enabled=0
checker_sha=""
if [[ -n "$PCMANFM_DIAGNOSTIC" ]]; then
  diagnostic_enabled=1
  diagnostic_args=(-v "$PCMANFM_DIAGNOSTIC:/pcmanfm-diagnostic:ro")
  checker_sha="$(sha256sum "$PCMANFM_DIAGNOSTIC/guest-pcmanfm-diagnostic.py")"
  checker_sha="${checker_sha%% *}"
fi
"$engine" run --rm "${diagnostic_args[@]}" "${name_args[@]}" "${ARCTIC_CONTAINER_ARGS[@]}" "${kvm_args[@]}" \
  -e PCMANFM_DIAGNOSTIC="$diagnostic_enabled" -e PCMANFM_CHECKER_SHA="$checker_sha" -e OUT=/out -e MODE="$MODE" -e TIMEOUT="$TIMEOUT" -e INTERVAL="$INTERVAL" \
  -e FIRMWARE="$FIRMWARE" -e SECUREBOOT="$SECUREBOOT" -e VGA="$VGA" -e APPEND="$APPEND" -e COLLECT="$COLLECT" -e MEMORY="$MEMORY" -e SMP="$SMP" -e DRIVER="$DRIVER" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$ISO:/iso:ro" -v "$OUT:/out" -v "$HERE/lib:/arctic-lib:ro" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "screenshots:"
find "$OUT" -maxdepth 1 -name '*.png' | sort | sed 's,^,  ,'
