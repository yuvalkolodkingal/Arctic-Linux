#!/usr/bin/env bash
# Install Arctic Linux to a VM disk from the live ISO and boot the result (QEMU, TCG).
#
#   tools/test-install.sh                       UEFI: install, then boot the installed disk
#   tools/test-install.sh --firmware bios       SeaBIOS instead of OVMF
#   tools/test-install.sh --stage install       only the install (fresh disk)
#   tools/test-install.sh --stage boot          only boot the disk a previous run installed
#   tools/test-install.sh --profile FILE        install profile (default profiles/ci/offline.toml:
#                                               the default install with apps from the live
#                                               image; Zen, Zed and the codecs are deferred)
#   tools/test-install.sh --iso PATH            default out/iso/Arctic-Linux-0.1-x86_64.iso
#   tools/test-install.sh --install-timeout S   seconds for the install (default 7200)
#   tools/test-install.sh --memory MiB --smp N  guest size (default 6144 MiB, 4 vCPUs)
#   tools/test-install.sh --kvm                 use /dev/kvm when the host has it
#   tools/test-install.sh --installer BIN       run this arctic-install binary (e.g. a fresh
#                                               `CGO_ENABLED=0 go build ./cmd/arctic-install`)
#                                               instead of the ISO's, to test engine fixes
#                                               without rebuilding the ISO
#   tools/test-install.sh --boot-append 'ARGS'  kernel arguments for the installed system's first
#                                               boot, edited into its GRUB entry. Default without
#                                               KVM: plymouth.use-simpledrm. Fedora's Plymouth
#                                               ignores simpledrm when the disk is encrypted and
#                                               waits 8 s (DeviceTimeout) for the GPU driver,
#                                               which TCG never loads in time, so the stock boot
#                                               falls back to the text prompt. '' for none.
#   tools/test-install.sh --out DIR             default out/test/install/<firmware>
#
# Stage "install": a fresh 40 GB sparse target disk (target.qcow2) and, for UEFI, a fresh
# writable OVMF variable store (OVMF_VARS.fd) in the output directory, plus a small data CD
# (iso9660, label ARCTICTEST) with the profile, run.sh and collect.sh. The ISO boots "Try Arctic
# Linux" (the entry is edited to log the journal to the serial port, which tells the harness
# when the live session is up); in the live desktop the harness opens a terminal (Super+Enter)
# and types one command that mounts the data CD and runs run.sh with sudo. run.sh runs
# `arctic-install unattended` with test secrets, tees everything to the serial port, prints
# ARCTIC-INSTALL-EXIT=<code> with the engine log, and powers off.
# Stage "boot": the target disk (and the same OVMF_VARS.fd, so the EFI boot entry the installer
# wrote is used) without the ISO. The harness types the disk passphrase at the Plymouth prompt,
# the password at the SDDM login, waits for the desktop, opens a terminal and runs collect.sh
# from the data CD (failed units, warnings, pending.json, getenforce, the user's shell …) to
# serial-boot.log. Screenshots (PNG) of every step land in the output directory.
#
# The VM has user-mode networking: in this sandbox there is no internet behind it, so the
# install runs offline and the app downloads are deferred to first boot.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
ISO="$ROOT/out/iso/Arctic-Linux-0.1-x86_64.iso"
FIRMWARE=uefi
STAGE=all
PROFILE="$ROOT/profiles/ci/offline.toml"
INSTALL_TIMEOUT=7200
MEMORY=6144
SMP=4
KVM=0
BOOT_APPEND=auto
INSTALLER=""
OUT=""
# Test secrets only (typed into the VM and passed to the installer).
LUKS_PASSPHRASE="glacier lantern frost harbor"
USER_PASSWORD="arctic-ci-pass"

while (( $# )); do
  case "$1" in
    --iso) ISO="$2"; shift 2 ;;
    --firmware) FIRMWARE="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --install-timeout) INSTALL_TIMEOUT="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --smp) SMP="$2"; shift 2 ;;
    --kvm) KVM=1; shift ;;
    --boot-append) BOOT_APPEND="$2"; shift 2 ;;
    --installer) INSTALLER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,46p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$FIRMWARE" in uefi|bios) ;; *) arctic_die "--firmware takes uefi or bios" ;; esac
case "$STAGE" in all|install|boot) ;; *) arctic_die "--stage takes all, install or boot" ;; esac
[[ -f "$PROFILE" ]] || arctic_die "no profile at $PROFILE"
if [[ "$STAGE" != boot ]]; then
  [[ -f "$ISO" ]] || arctic_die "no ISO at $ISO (run tools/build-iso.sh)"
  ISO="$(cd "$(dirname "$ISO")" && pwd)/$(basename "$ISO")"
fi
[[ -n "$OUT" ]] || OUT="$ROOT/out/test/install/$FIRMWARE"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

if [[ "$STAGE" == boot ]]; then
  [[ -f "$OUT/target.qcow2" ]] || arctic_die "no installed disk at $OUT/target.qcow2 (run --stage install first)"
  rm -f "$OUT"/boot-*.png "$OUT/serial-boot.log" "$OUT/qemu-boot.log"
  # Keep the log of the run that installed the disk; test.log starts afresh.
  if [[ -f "$OUT/test.log" ]] && grep -q 'install stage' "$OUT/test.log"; then mv "$OUT/test.log" "$OUT/test-install-stage.log"; fi
  rm -f "$OUT/test.log"
else
  # A new install starts from a blank disk and a blank variable store.
  find "$OUT" -mindepth 1 -maxdepth 1 ! -name '.' -exec rm -rf {} +
fi

# ---- the data CD: profile, install script, collect script -----------------------------------
DATA="$OUT/data"
rm -rf "$DATA"; mkdir -p "$DATA"
cp "$PROFILE" "$DATA/profile.toml"
if [[ -n "$INSTALLER" ]]; then
  [[ -x "$INSTALLER" ]] || arctic_die "--installer: $INSTALLER is not an executable"
  cp "$INSTALLER" "$DATA/arctic-install"
fi
q() { printf "'%s'" "${1//\'/\'\\\'\'}"; }
cat > "$DATA/run.sh" <<EOF
#!/bin/bash
# tools/test-install.sh: runs as root in the live session (typed into a terminal):
# the unattended install, everything teed to the serial port, then power off.
S=/dev/ttyS0
D="\$(dirname "\$(readlink -f "\$0")")"
say() { printf '%s\n' "\$*" | tee -a "\$S"; }
exec 9>/run/arctic-test.lock
if ! flock -n 9 || [ -e /run/arctic-test.started ]; then echo "run.sh already ran"; exit 0; fi
: > /run/arctic-test.started
say "ARCTIC-TEST-STARTED \$(date -u +%FT%TZ)"
export ARCTIC_LUKS_PASSPHRASE=$(q "$LUKS_PASSPHRASE")
export ARCTIC_USER_PASSWORD=$(q "$USER_PASSWORD")
cp "\$D/profile.toml" /run/arctic-test-profile.toml
AI=arctic-install
if [ -x "\$D/arctic-install" ]; then
  cp "\$D/arctic-install" /run/arctic-install-test && AI=/run/arctic-install-test
  say "using the arctic-install from the test data drive"
fi
{
  echo "== live system"; cat /proc/cmdline; findmnt /run/rootfsbase; findmnt -t squashfs
  lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS
  nmcli general; nmcli networking connectivity check
  "\$AI" version
} 2>&1 | tee -a "\$S"
start=\$(date +%s)
"\$AI" unattended --profile /run/arctic-test-profile.toml 2>&1 | tee -a "\$S"
rc=\${PIPESTATUS[0]}
say "ARCTIC-INSTALL-DURATION=\$(( \$(date +%s) - start ))s"
say "ARCTIC-ENGINE-LOG-BEGIN"
cat /var/log/arctic-install/engine.log >> "\$S" 2>&1
say "ARCTIC-ENGINE-LOG-END"
if [ "\$rc" != 0 ]; then
  say "ARCTIC-FAILURE-LOGS-BEGIN"
  ls -la /var/log/arctic-install/ >> "\$S" 2>&1
  for f in /var/log/arctic-install/*; do [ "\$f" = /var/log/arctic-install/engine.log ] || { echo "--- \$f"; cat "\$f"; } >> "\$S" 2>&1; done
  { findmnt -R /mnt; dmsetup info -c; ls -l /sys/block/dm-*/holders/
    echo "processes whose mount namespace still has the target:"
    for f in /proc/[0-9]*/mountinfo; do grep -q '/dev/mapper/luks-\| /mnt' "\$f" 2>/dev/null && { p=\${f%/mountinfo}; echo "\${p#/proc/} \$(cat "\$p/comm") \$(readlink "\$p/ns/mnt")"; }; done | sort -k3 -u
  } >> "\$S" 2>&1
  journalctl -b -p warning --no-pager 2>&1 | tail -150 >> "\$S"
  say "ARCTIC-FAILURE-LOGS-END"
fi
say "ARCTIC-INSTALL-EXIT=\$rc"
sync
sleep 3
systemctl poweroff
EOF
cat > "$DATA/collect.sh" <<'EOF'
#!/bin/bash
# tools/test-install.sh: runs as root in the installed system's first session (typed into a
# terminal as `sudo bash collect.sh $$`, so $1 is the terminal's shell) → serial port.
exec >/dev/ttyS0 2>&1
pid="${1:-}"
u="$(stat -c %U "/proc/$pid" 2>/dev/null || echo ci)"
uid="$(id -u "$u")"
sec() { echo; echo "== $*"; }
echo ARCTIC-COLLECT-BEGIN
sec "terminal shell"; echo "pid $pid: $(cat "/proc/$pid/comm" 2>/dev/null) ($(readlink "/proc/$pid/exe" 2>/dev/null))"
sec "user"; getent passwd "$u"; id "$u"
sec "getenforce"; getenforce
sec "cmdline"; cat /proc/cmdline
sec "os-release"; grep -E '^(NAME|VERSION|PRETTY_NAME)=' /etc/os-release
sec "systemctl --failed"; systemctl --failed --no-pager
sec "systemctl --user --failed ($u)"; runuser -u "$u" -- env XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user --failed --no-pager
sec "cat /var/lib/arctic/pending.json"; cat /var/lib/arctic/pending.json
sec "arctic-firstboot"; systemctl status arctic-firstboot.service --no-pager -l | head -30
sec "sessions"; loginctl list-sessions --no-pager; loginctl show-user "$u" --no-pager 2>/dev/null | grep -E '^(State|Sessions)='
sec "session processes"; ps -u "$u" -o pid=,comm=,args= | cut -c1-160 | head -60
sec "lsblk"; lsblk -o NAME,FSTYPE,LABEL,SIZE,MOUNTPOINTS
sec "fstab/crypttab"; cat /etc/fstab /etc/crypttab
sec "efibootmgr"; efibootmgr -v 2>&1 | head -20
sec "flatpak"; flatpak remotes --system; flatpak list --system
sec "default apps"; cat /etc/arctic/default-apps
sec "plymouth"; plymouth-set-default-theme 2>/dev/null
journalctl -b -o short-monotonic --no-pager | grep -iE 'plymouth|virtio.gpu|simpledrm|fbcon|\[drm\]|cryptsetup' | head -40
sec "sddm"; ls /etc/sddm.conf.d/ /usr/lib/sddm/sddm.conf.d/ 2>&1; journalctl -b -u sddm --no-pager | tail -40
sec "journalctl -b -p warning"; journalctl -b -p warning --no-pager
sec "AVC denials"; journalctl -b --no-pager -g 'avc: +denied' | tail -40
sec "engine log (tail)"; tail -60 /var/log/arctic-install/engine.log
echo
echo ARCTIC-COLLECT-END
EOF
chmod 0755 "$DATA/run.sh" "$DATA/collect.sh"

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
kvm_args=()
if (( KVM )) && [[ -e /dev/kvm ]]; then kvm_args=(--device /dev/kvm); fi
if [[ "$BOOT_APPEND" == auto ]]; then
  BOOT_APPEND=""
  if ! (( KVM )) || [[ ! -e /dev/kvm ]]; then BOOT_APPEND="plymouth.use-simpledrm"; fi
fi
iso_args=()
if [[ "$STAGE" != boot ]]; then iso_args=(-v "$ISO:/iso:ro"); fi

# ---- the stage driver (runs in the container; tools/lib/vmtest.py has the QMP helpers) ------
read -r -d '' DRIVER <<'PY' || true
import os, sys, time
sys.path.insert(0, "/arctic-lib")
import vmtest
from vmtest import log

E = os.environ
out, fw, stage = E["OUT"], E["FIRMWARE"], E["STAGE"]
mem, smp, accel = E["MEMORY"], E["SMP"], E["ACCEL"]
install_timeout = int(E["INSTALL_TIMEOUT"])
luks, password = E["LUKS_PASSPHRASE"], E["USER_PASSWORD"]
boot_append = E.get("BOOT_APPEND", "").strip()
LIVE_APPEND = "console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1"

def qemu_argv(name, with_iso):
    a = ["qemu-system-x86_64", "-machine", "q35", "-accel", accel, "-cpu", "max", "-smp", smp, "-m", mem,
         "-display", "none", "-vga", "virtio", "-qmp", f"unix:/tmp/qmp-{name}.sock,server=on,wait=off",
         "-serial", f"file:{out}/serial-{name}.log", "-monitor", "none", "-no-reboot",
         "-drive", f"file={out}/target.qcow2,if=none,id=disk,discard=unmap",
         "-device", f"virtio-blk-pci,drive=disk,bootindex={1 if with_iso else 0}",
         "-drive", f"file={out}/data.iso,media=cdrom,readonly=on,if=none,id=data",
         "-device", "ide-cd,drive=data,bus=ide.1",
         "-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0",
         "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc"]
    if with_iso:
        a += ["-drive", "file=/iso,media=cdrom,readonly=on,if=none,id=cd", "-device", "ide-cd,drive=cd,bus=ide.0,bootindex=0"]
    if fw == "uefi":
        a += ["-drive", "if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
              "-drive", f"if=pflash,format=raw,unit=1,file={out}/OVMF_VARS.fd"]
    return a

def wait_menu(vm, prefix, limit):
    t = time.time()
    while time.time() - t < limit and vm.alive():
        p = vm.shot(f"{prefix}-00-probe")
        if p and vmtest.looks_like_boot_menu(p):
            os.replace(p, f"{out}/{prefix}-01-boot-menu.png")
            log(f"boot menu on screen: {prefix}-01-boot-menu.png")
            return True
        time.sleep(1)
    if os.path.exists(f"{out}/{prefix}-00-probe.png"):
        os.remove(f"{out}/{prefix}-00-probe.png")
    vm.shot(f"{prefix}-01-no-menu-detected")
    log("boot menu not detected")
    return False

def edit_entry(vm, prefix, args, line):
    """GRUB: edit the selected entry, append kernel arguments to its linux line (`line`
    lines below the first), boot."""
    vm.keys("e")
    time.sleep(1)
    vm.keys(*(["down"] * line), "ctrl-e")
    vm.type_text(" " + args, gap=0.1)
    time.sleep(0.5)
    vm.shot(f"{prefix}-02-entry-edited")
    vm.keys("ctrl-x")

def open_terminal(vm, prefix):
    vm.keys("meta_l-ret")
    time.sleep(75)
    vm.shot(f"{prefix}-terminal")
    vm.keys("ret")        # skips the fetch animation (any key does) and gives a fresh prompt
    time.sleep(5)

def serial(name):
    return f"{out}/serial-{name}.log"

# ---- stage 1: install from the live session ------------------------------------------------
def stage_install():
    vm = vmtest.VM(qemu_argv("install", True), "/tmp/qmp-install.sock", "install")
    try:
        if wait_menu(vm, "install", 300):
            vm.keys("home")
            edit_entry(vm, "install", LIVE_APPEND, 2)   # setparams, (empty), linux
            log("selected 'Try Arctic Linux' with the journal on the serial port")
        start = time.time()
        # The live session is up when live-session logs its mode (journal → serial).
        n = 0
        while time.time() - start < 1500 and vm.alive():
            if vmtest.serial_has(serial("install"), "live session mode:"):
                log(f"live session started after {time.time() - start:.0f}s")
                break
            n += 1
            if n % 6 == 1:
                vm.shot(f"install-10-boot-{int(time.time() - start):04d}s")
            time.sleep(10)
        else:
            log("no 'live session mode' line in the serial log; trying the terminal anyway")
        time.sleep(120)   # the shell (Quickshell) and the welcome card settle
        vm.shot("install-20-live-desktop")
        started = False
        for attempt in (1, 2, 3):
            open_terminal(vm, f"install-2{attempt}")
            vm.type_text("sudo mount -m -L ARCTICTEST /run/t; sudo bash /run/t/run.sh")
            vm.keys("ret")
            t = time.time()
            while time.time() - t < 240 and vm.alive():
                if vmtest.serial_has(serial("install"), "ARCTIC-TEST-STARTED"):
                    started = True
                    break
                time.sleep(5)
            vm.shot(f"install-2{attempt}-command-typed")
            if started:
                log(f"run.sh started (attempt {attempt})")
                break
            log(f"run.sh did not start (attempt {attempt})")
        if not started:
            vm.shot("install-29-not-started")
            return 90
        t = time.time()
        k = 0
        while time.time() - t < install_timeout and vm.alive():
            if k % 10 == 0:
                vm.shot(f"install-30-{int((time.time() - t) / 60):03d}min")
            k += 1
            if vmtest.serial_has(serial("install"), "ARCTIC-INSTALL-EXIT="):
                vm.shot("install-40-finished")
                break
            time.sleep(30)
        rc = vmtest.serial_value(serial("install"), "ARCTIC-INSTALL-EXIT=")
        log(f"install finished after {time.time() - t:.0f}s: exit {rc}")
        if rc is None:
            log("install timed out")
            vm.shot("install-49-timeout")
            return 91
        if not vm.wait_exit(600):
            vm.shot("install-48-no-poweroff")
            log("the live system did not power off")
        return int(rc) if rc.isdigit() else 92
    finally:
        vm.quit()

# ---- stage 2: boot the installed disk ------------------------------------------------------
def wait_for(vm, prefix, want, limit, every=5):
    """Poll screenshots until classify() says `want` (a set); returns the path or None."""
    t = time.time()
    last = None
    while time.time() - t < limit and vm.alive():
        p = vm.shot(f"{prefix}-probe")
        if p:
            kind = vmtest.classify(p)
            if kind != last:
                log(f"screen: {kind} ({time.time() - t:.0f}s)")
                last = kind
            if kind in want:
                return p
        time.sleep(every)
    return None

def stage_boot():
    vm = vmtest.VM(qemu_argv("boot", False), "/tmp/qmp-boot.sock", "boot")
    ok = True
    try:
        if wait_menu(vm, "boot", 240):
            if boot_append:
                # A BLS entry: load_video, set gfxpayload=keep, insmod gzio, linux, initrd.
                edit_entry(vm, "boot", boot_append, 3)
                log(f"booting with extra arguments: {boot_append}")
            else:
                vm.keys("ret")
                log("booting the default entry")
        p = wait_for(vm, "boot-30", {"prompt"}, 900)
        if p:
            time.sleep(3)
            vm.shot("boot-31-luks-prompt")
            log("passphrase prompt on screen: boot-31-luks-prompt.png")
        else:
            vm.shot("boot-31-no-prompt-detected")
            log("no passphrase prompt detected; typing the passphrase anyway")
            ok = False
        vm.type_text(luks, gap=0.25)
        time.sleep(1)
        vm.shot("boot-32-luks-typed")
        vm.keys("ret")
        time.sleep(15)
        vm.shot("boot-33-unlocking")
        p = wait_for(vm, "boot-40", {"login"}, 1500, every=10)
        if p:
            time.sleep(30)
            vm.shot("boot-41-login")
            log("login screen on screen: boot-41-login.png")
        else:
            vm.shot("boot-41-no-login-detected")
            log("no login screen detected; typing the password anyway")
            ok = False
        vm.type_text(password, gap=0.25)
        time.sleep(1)
        vm.shot("boot-42-password-typed")
        vm.keys("ret")
        # The desktop: the login card is gone and the screen settles.
        t = time.time()
        prev = None
        stable = 0
        i = 0
        while time.time() - t < 900 and vm.alive():
            time.sleep(20)
            i += 1
            p = vm.shot(f"boot-50-session-{i:02d}")
            if not p:
                continue
            kind = vmtest.classify(p)
            if prev and kind != "login":
                stable = stable + 1 if vmtest.changed_fraction(prev, p) < 0.02 else 0
            prev = p
            if stable >= 2 and time.time() - t > 90:
                break
        log(f"session settled after {time.time() - t:.0f}s")
        time.sleep(30)
        vm.shot("boot-51-desktop")
        open_terminal(vm, "boot-52")
        vm.type_text("sudo mount -m -L ARCTICTEST /run/t; sudo bash /run/t/collect.sh $$")
        vm.keys("ret")
        time.sleep(10)
        vm.shot("boot-53-sudo")
        vm.type_text(password, gap=0.2)
        vm.keys("ret")
        t = time.time()
        while time.time() - t < 300 and vm.alive():
            if vmtest.serial_has(serial("boot"), "ARCTIC-COLLECT-END"):
                log("collected into serial-boot.log (ARCTIC-COLLECT-BEGIN/END)")
                break
            time.sleep(5)
        else:
            log("collect.sh did not finish")
            ok = False
        vm.shot("boot-54-collected")
        time.sleep(5)
        vm.shot("boot-99-final")
        return 0 if ok else 1
    finally:
        vm.quit()

rc = 0
if stage in ("all", "install"):
    rc = stage_install()
    log(f"install stage: exit {rc}")
if rc == 0 and stage in ("all", "boot"):
    rc = stage_boot()
    log(f"boot stage: exit {rc}")
for f in os.listdir(out):
    if f.endswith("-probe.png"):
        os.remove(os.path.join(out, f))
sys.exit(rc)
PY

inner=$(cat <<'INNER'
pkgs=(qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow xorriso
      qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci)
dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
xorriso -as mkisofs -quiet -V ARCTICTEST -J -R -o "$OUT/data.iso" "$OUT/data"
if [ "$STAGE" != boot ]; then
  qemu-img create -q -f qcow2 "$OUT/target.qcow2" 40G
  [ "$FIRMWARE" = uefi ] && cp /usr/share/edk2/ovmf/OVMF_VARS.fd "$OUT/OVMF_VARS.fd"
fi
ACCEL="tcg,thread=multi"
[ -e /dev/kvm ] && ACCEL=kvm
export ACCEL
rc=0
python3 -c "$DRIVER" || rc=$?
chown -R "$HOST_UID:$HOST_GID" "$OUT"
exit $rc
INNER
)

arctic_log "install test ($FIRMWARE, stage $STAGE, profile $(basename "$PROFILE")) → $OUT"
rc=0
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${kvm_args[@]}" \
  -e OUT="$OUT" -e FIRMWARE="$FIRMWARE" -e STAGE="$STAGE" -e MEMORY="$MEMORY" -e SMP="$SMP" \
  -e INSTALL_TIMEOUT="$INSTALL_TIMEOUT" -e BOOT_APPEND="$BOOT_APPEND" \
  -e LUKS_PASSPHRASE="$LUKS_PASSPHRASE" -e USER_PASSWORD="$USER_PASSWORD" -e DRIVER="$DRIVER" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$HERE/lib:/arctic-lib:ro" -v "$OUT:$OUT" "${iso_args[@]}" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner" || rc=$?

arctic_log "result: exit $rc (serial logs, test.log and screenshots in $OUT)"
find "$OUT" -maxdepth 1 -name '*.png' | sort | sed 's,^,  ,'
exit "$rc"
