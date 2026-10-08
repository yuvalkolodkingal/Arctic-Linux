#!/usr/bin/env bash
# Install Arctic Linux to a VM disk from the live ISO and boot the result (QEMU, TCG).
#
#   tools/test-install.sh                       UEFI: install, then boot the installed disk
#   tools/test-install.sh --firmware bios       SeaBIOS instead of OVMF
#   tools/test-install.sh --guest-check FILE   Python live/installed assertions in disposable VM
#   tools/test-install.sh --guest-check-interactive  screenshot desktop checks and type the
#                                               test password only after an unlock request marker
#   tools/test-install.sh --reliability-version 1.2 --reliability-app-profile lightweight
#   tools/test-install.sh --stage boot --reliability-version 1.0 --upgrade-to 1.2
#   tools/test-install.sh --stage install       only the install (fresh disk)
#   tools/test-install.sh --stage boot          only boot the disk a previous run installed
#   tools/test-install.sh --boot-network online allow outbound user-mode NAT only for the
#                                               installed boot (default: offline). The live
#                                               installer remains isolated; use this for
#                                               installed Nix fetch/update acceptance.
#   --collect-via console                     authenticate on tty3 and restore the actual
#                                             desktop VT before probing; never launches the
#                                             default GUI terminal (performance first-use).
#   --fresh-boot-from DIR                      boot a fresh QCOW2 overlay of DIR's clean
#                                             installed disk and copied UEFI variables.
#   --performance-context FILE                copy declared paired-run provenance to data CD.
#   tools/test-install.sh --profile FILE        install profile (default profiles/ci/offline.toml:
#                                               the default install with apps from the live
#                                               image; lightweight defaults are kept offline,
#                                               unavailable extras are deferred)
#   tools/test-install.sh --iso PATH            default out/iso/Arctic-Linux-1.2-x86_64.iso
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
#   tools/test-install.sh --via service|sudo    how run.sh starts the engine. service (default):
#                                               as a transient systemd service (systemd-run), the
#                                               context the installer daemon arcticd runs in
#                                               (SELinux unconfined_service_t, service
#                                               environment); sudo: straight from the terminal
#   tools/test-install.sh --boot-append '… systemd.debug_shell=tty9'   when collecting through
#                                               a session fails (a failed login), collect.sh runs
#                                               from the root debug shell on tty9 instead
#   tools/test-install.sh --out DIR             default out/test/install/<firmware>
#   tools/test-install.sh --test-hardware NAME  the engine sees this hardware fixture's PCI devices
#                                               (internal/hw/fixtures.go, e.g. nvidia-laptop): its
#                                               drivers are ticked, installed and built by akmods
#                                               for the new system's kernel (no card needed)
#   tools/test-install.sh --online-via-proxy    give the guest the internet through this host's
#                                               HTTPS proxy ($HTTPS_PROXY on 127.0.0.1, reached as
#                                               10.0.2.2 from QEMU's user network) and its CA
#                                               (ARCTIC_CA_BUNDLE or /root/.ccr/ca-bundle.crt, also
#                                               added to the new system for its dnf); the engine
#                                               treats the network as online (--test-online)
#   e.g. the NVIDIA + LUKS case: --profile profiles/ci/nvidia.toml --test-hardware nvidia-laptop
#        --online-via-proxy
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
# The VM has restricted user-mode networking by default. QEMU blocks guest access to the
# host and outside networks, irrespective of the host's connectivity. Only the explicit
# --online-via-proxy test enables routing for both phases; --boot-network online enables
# it only after installation. Neither adds host forwards or changes the host's networking.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
ISO="$ROOT/out/iso/Arctic-Linux-1.2-x86_64.iso"
FIRMWARE=uefi
STAGE=all
PROFILE="$ROOT/profiles/ci/offline.toml"
INSTALL_TIMEOUT=7200
MEMORY=6144
SMP=4
KVM=0
BOOT_APPEND=auto
INSTALLER=""
VIA=service
OUT=""
GUEST_CHECK=""
GUEST_CHECK_INTERACTIVE=0
RELIABILITY_VERSION=""
RELIABILITY_APP_PROFILE=legacy
UPGRADE_TO=""
PROFILE_EXPLICIT=0
TEST_HARDWARE=""
ONLINE_PROXY=0
BOOT_NETWORK=offline
COLLECT_VIA=terminal
FRESH_BOOT_FROM=""
PERFORMANCE_CONTEXT=""
# Test secrets only (typed into the VM and passed to the installer).
LUKS_PASSPHRASE="glacier lantern frost harbor"
USER_PASSWORD="arctic-ci-pass"

while (( $# )); do
  case "$1" in
    --upgrade-to) UPGRADE_TO="$2"; shift 2 ;;
    --reliability-version) RELIABILITY_VERSION="$2"; shift 2 ;;
    --reliability-app-profile) RELIABILITY_APP_PROFILE="$2"; shift 2 ;;
    --guest-check) GUEST_CHECK="$2"; shift 2 ;;
    --guest-check-interactive) GUEST_CHECK_INTERACTIVE=1; shift ;;
    --iso) ISO="$2"; shift 2 ;;
    --firmware) FIRMWARE="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    --profile) PROFILE="$2"; PROFILE_EXPLICIT=1; shift 2 ;;
    --install-timeout) INSTALL_TIMEOUT="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --smp) SMP="$2"; shift 2 ;;
    --kvm) KVM=1; shift ;;
    --boot-append) BOOT_APPEND="$2"; shift 2 ;;
    --installer) INSTALLER="$2"; shift 2 ;;
    --via) VIA="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --test-hardware) TEST_HARDWARE="$2"; shift 2 ;;
    --online-via-proxy) ONLINE_PROXY=1; shift ;;
    --boot-network) BOOT_NETWORK="$2"; shift 2 ;;
    --collect-via) COLLECT_VIA="$2"; shift 2 ;;
    --fresh-boot-from) FRESH_BOOT_FROM="$2"; shift 2 ;;
    --performance-context) PERFORMANCE_CONTEXT="$2"; shift 2 ;;
    -h|--help) sed -n '2,58p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$FIRMWARE" in uefi|bios) ;; *) arctic_die "--firmware takes uefi or bios" ;; esac
case "$STAGE" in all|install|boot) ;; *) arctic_die "--stage takes all, install or boot" ;; esac
case "$COLLECT_VIA" in terminal|console) ;; *) arctic_die "--collect-via takes terminal or console" ;; esac
if [[ -n "$FRESH_BOOT_FROM$PERFORMANCE_CONTEXT" ]]; then
  [[ "$STAGE" == boot && "$COLLECT_VIA" == console && -n "$GUEST_CHECK" && -n "$FRESH_BOOT_FROM" && -r "$PERFORMANCE_CONTEXT" ]] ||
    arctic_die "fresh performance boots need --stage boot, console, guest check, clean source and context"
  [[ -r "$FRESH_BOOT_FROM/target.qcow2" && -r "$FRESH_BOOT_FROM/OVMF_VARS.fd" ]] || arctic_die "no pristine installed disk/UEFI variables"
  FRESH_BOOT_FROM="$(cd "$FRESH_BOOT_FROM" && pwd)"
fi
case "$BOOT_NETWORK" in offline|online) ;; *) arctic_die "--boot-network takes offline or online" ;; esac
case "$RELIABILITY_APP_PROFILE" in legacy|lightweight) ;; *) arctic_die "--reliability-app-profile takes legacy or lightweight" ;; esac
if [[ -n "$UPGRADE_TO" ]]; then
  [[ "$STAGE" == boot && -n "$RELIABILITY_VERSION" && "$UPGRADE_TO" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] ||
    arctic_die "--upgrade-to requires --stage boot and --reliability-version SOURCE"
fi
if [[ -n "$RELIABILITY_VERSION" ]]; then
  [[ "$RELIABILITY_VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] || arctic_die "invalid reliability version"
  [[ -z "$GUEST_CHECK" ]] || arctic_die "--reliability-version and --guest-check are mutually exclusive"
  GUEST_CHECK="$HERE/reliability/guest.py"
  if ! (( PROFILE_EXPLICIT )); then PROFILE="$HERE/reliability/profiles/$RELIABILITY_APP_PROFILE.toml"; fi
fi
[[ -f "$PROFILE" ]] || arctic_die "no profile at $PROFILE"
if [[ "$STAGE" != boot ]]; then
  [[ -f "$ISO" ]] || arctic_die "no ISO at $ISO (run tools/build-iso.sh)"
  ISO="$(cd "$(dirname "$ISO")" && pwd)/$(basename "$ISO")"
fi
[[ -n "$OUT" ]] || OUT="$ROOT/out/test/install/$FIRMWARE"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

if [[ "$STAGE" == boot ]]; then
  if [[ -n "$FRESH_BOOT_FROM" ]]; then
    [[ "$OUT" != "$FRESH_BOOT_FROM" && ! -e "$OUT/target.qcow2" ]] || arctic_die "fresh boot needs a separate unused overlay directory"
  else
    [[ -f "$OUT/target.qcow2" ]] || arctic_die "no installed disk at $OUT/target.qcow2 (run --stage install first)"
  fi
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
if [[ -n "$PERFORMANCE_CONTEXT" ]]; then cp "$PERFORMANCE_CONTEXT" "$DATA/performance-context.json"; fi
if [[ -n "$GUEST_CHECK" ]]; then cp "$GUEST_CHECK" "$DATA/guest-check.py"; fi
if [[ -n "$RELIABILITY_VERSION" ]]; then
  printf '{"version":"%s","upgrade_to":"%s","app_profile":"%s"}\n' \
    "$RELIABILITY_VERSION" "$UPGRADE_TO" "$RELIABILITY_APP_PROFILE" > "$DATA/config.json"
fi
if [[ -n "$INSTALLER" ]]; then
  [[ -x "$INSTALLER" ]] || arctic_die "--installer: $INSTALLER is not an executable"
  cp "$INSTALLER" "$DATA/arctic-install"
fi
q() { printf "'%s'" "${1//\'/\'\\\'\'}"; }
UNATTENDED_ARGS=""
[[ -n "$TEST_HARDWARE" ]] && UNATTENDED_ARGS+=" --test-hardware $(q "$TEST_HARDWARE")"
if (( ONLINE_PROXY )); then
  proxy="${HTTPS_PROXY:-${https_proxy:-}}"
  port="${proxy##*:}"; port="${port%%/*}"
  [[ "$proxy" == *127.0.0.1:* || "$proxy" == *localhost:* ]] && [[ "$port" =~ ^[0-9]+$ ]] ||
    arctic_die "--online-via-proxy needs HTTPS_PROXY=http://127.0.0.1:PORT (got '${proxy:-nothing}')"
  ca="${ARCTIC_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}"
  [[ -r "$ca" ]] || arctic_die "--online-via-proxy: no CA bundle at $ca (set ARCTIC_CA_BUNDLE)"
  cp "$ca" "$DATA/proxy-ca.crt"
  echo "PROXY_PORT=$port" > "$DATA/proxy.env"
  UNATTENDED_ARGS+=" --test-online"
fi
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
AI=/usr/bin/arctic-install
if [ -x "\$D/arctic-install" ]; then
  # Under /usr/local/bin with its default label (bin_t), so that a service runs it in the
  # same SELinux domain as the ISO's own binaries.
  install -m 0755 "\$D/arctic-install" /usr/local/bin/arctic-install-test && AI=/usr/local/bin/arctic-install-test
  restorecon "\$AI" 2>/dev/null
  say "using the arctic-install from the test data drive"
fi
VIA=$(q "$VIA")
PROXY=""
if [ -f "\$D/proxy.env" ]; then
  # --online-via-proxy: the host's proxy through QEMU's user network, and its CA for TLS.
  . "\$D/proxy.env"
  PROXY="http://10.0.2.2:\$PROXY_PORT"
  export https_proxy="\$PROXY" HTTPS_PROXY="\$PROXY" no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
  cp "\$D/proxy-ca.crt" /etc/pki/ca-trust/source/anchors/arctic-test-proxy.crt && update-ca-trust extract
  say "online through \$PROXY: \$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 https://mirrors.fedoraproject.org/ 2>&1)"
  # The new system is copied from the image (/run/rootfsbase), without that CA; dnf in its
  # chroot checks TLS against the new system's trust store. Add the CA as soon as the system
  # is configured (crypttab written), long before the apps phase downloads anything.
  ( for _ in \$(seq 1 7200); do
      if grep -qs luks /mnt/etc/crypttab || grep -qs 'subvol=@' /mnt/etc/fstab; then
        sleep 5
        cp "\$D/proxy-ca.crt" /mnt/etc/pki/ca-trust/source/anchors/arctic-test-proxy.crt &&
          chroot /mnt update-ca-trust extract && say "proxy CA added to the new system"
        break
      fi
      sleep 2
    done ) &
fi
{
  echo "== live system"; cat /proc/cmdline; findmnt /run/rootfsbase; findmnt -t squashfs
  lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS
  nmcli general; nmcli networking connectivity check
  "\$AI" version
} 2>&1 | tee -a "\$S"
if [ "$ONLINE_PROXY" != 1 ]; then
  # Check transport reachability, not TLS trust or an HTTP success code: any HTTP response
  # would mean the supposedly offline guest can reach an outside server.
  response=\$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 5 http://fedoraproject.org/ || true)
  say "ARCTIC-OFFLINE-HTTP-RESPONSE=\$response"
  if [ "\$response" != 000 ]; then
    say 'ARCTIC-OFFLINE-GATE=failed: outside HTTP response received'
    systemctl poweroff; exit 93
  fi
  say 'ARCTIC-OFFLINE-GATE=passed: restricted QEMU network, no outside HTTP response'
fi
if [ -f "\$D/guest-check.py" ]; then
  python3 "\$D/guest-check.py" live >> "\$S" 2>&1
  smoke_rc=\$?
  say "ARCTIC-LIVE-SMOKE-EXIT=\$smoke_rc"
  if [ "\$smoke_rc" != 0 ]; then systemctl poweroff; exit "\$smoke_rc"; fi
fi
start=\$(date +%s)
if [ "\$VIA" = service ]; then
  # What arcticd.service gets: a system service's SELinux domain and environment.
  say "running the install as a systemd service (\$(getenforce))"
  systemd-run --wait --pipe --collect --quiet id -Z 2>&1 | tee -a "\$S"
  penv=()
  [ -n "\$PROXY" ] && penv=(-E https_proxy -E HTTPS_PROXY -E no_proxy -E NO_PROXY)
  systemd-run --wait --pipe --collect --quiet --unit=arctic-test-install \\
    -E ARCTIC_LUKS_PASSPHRASE -E ARCTIC_USER_PASSWORD "\${penv[@]}" \\
    "\$AI" unattended --profile /run/arctic-test-profile.toml$UNATTENDED_ARGS 2>&1 | tee -a "\$S"
  rc=\${PIPESTATUS[0]}
else
  "\$AI" unattended --profile /run/arctic-test-profile.toml$UNATTENDED_ARGS 2>&1 | tee -a "\$S"
  rc=\${PIPESTATUS[0]}
fi
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
if [ -f /run/t/performance-context.json ]; then
  # Standard console authentication leaves default GUI roles unexecuted. Return
  # to the actual SDDM desktop VT before observing them; no boot/security hooks.
  python3 - <<'PY' || exit 1
from pathlib import Path
import subprocess,time
sessions=[]
for path in Path('/proc').glob('[0-9]*'):
    try:
        if path.stat().st_uid==0 or (path/'comm').read_text().strip()!='mango':continue
        env=dict(item.split('=',1) for item in (path/'environ').read_bytes().decode().split('\0') if '=' in item)
        sessions.append(env['XDG_SESSION_ID'])
    except (OSError,KeyError,UnicodeError):continue
if len(set(sessions))!=1:raise RuntimeError('No unique actual desktop session for console restoration')
session=sessions[0]
kind=subprocess.check_output(['loginctl','show-session',session,'-p','Type','--value'],text=True).strip()
vt=subprocess.check_output(['loginctl','show-session',session,'-p','VTNr','--value'],text=True).strip()
if kind!='wayland' or not vt.isdecimal() or int(vt)<=0:raise RuntimeError('Invalid actual desktop VT')
subprocess.run(['chvt',vt],check=True,timeout=10)
for _ in range(50):
    active=subprocess.check_output(['loginctl','show-session',session,'-p','Active','--value'],text=True).strip()
    if active=='yes':break
    time.sleep(.1)
else:raise RuntimeError('Desktop VT did not become active')
print('ARCTIC-PERFORMANCE-CONSOLE-RESTORED session='+session+' vt='+vt,flush=True)
PY
fi
pid="${1:-}"
u="$(stat -c %U "/proc/$pid" 2>/dev/null || echo ci)"
uid="$(id -u "$u")"
sec() { echo; echo "== $*"; }
echo ARCTIC-COLLECT-BEGIN
if [ -f /run/t/proxy.env ]; then
  # Explicit online testing of an already-installed disposable guest. Keep TLS
  # verification enabled; this trust is never added to the shipped ISO.
  . /run/t/proxy.env
  export HTTPS_PROXY="http://10.0.2.2:$PROXY_PORT" https_proxy="http://10.0.2.2:$PROXY_PORT"
  export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
  cp /run/t/proxy-ca.crt /etc/pki/ca-trust/source/anchors/arctic-test-proxy.crt
  update-ca-trust extract
fi
sec "terminal shell"; echo "pid $pid: $(cat "/proc/$pid/comm" 2>/dev/null) ($(readlink "/proc/$pid/exe" 2>/dev/null))"
sec "user"; getent passwd "$u"; id "$u"
sec "home"; findmnt /home; ls -ldnZ / /home /home/* 2>&1; stat "/home/$u" 2>&1; getfacl -p /home "/home/$u" 2>&1 | head -20
ls -lanZ "/home/$u" 2>&1 | head -30
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
if [ -f /run/t/guest-check.py ]; then
  python3 /run/t/guest-check.py installed
  echo "ARCTIC-INSTALLED-SMOKE-EXIT=$?"
fi
echo ARCTIC-COLLECT-END
if [ -f /run/t/guest-check.py ]; then sync; systemctl poweroff; fi
EOF
chmod 0755 "$DATA/run.sh" "$DATA/collect.sh"
# The launcher goes into the data CD's system area (its first 32 KiB, which ISO 9660 leaves
# unused), so the command typed into the VM is only `sudo sh /dev/sr0`: under TCG a busy guest
# can lose keys (QEMU's PS/2 queue holds 16 bytes), and the shorter the command the better.
# bash stops at the exec, before the NUL padding and the file system behind it.
cat > "$OUT/sysarea.sh" <<'EOF'
#!/bin/bash
# tools/test-install.sh: first bytes of the test data CD, run as `sudo sh /dev/sr0 [PID]`.
mkdir -p /run/t
mountpoint -q /run/t || mount -o ro /dev/disk/by-label/ARCTICTEST /run/t || exit 1
if [ -e /run/rootfsbase ]; then exec bash /run/t/run.sh; else exec bash /run/t/collect.sh "$@"; fi
exit 1
EOF

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
    # Explicit boot-only connectivity must never make an offline install online.
    online = E.get("ONLINE_PROXY") == "1" or (not with_iso and E.get("BOOT_NETWORK") == "online")
    a = ["qemu-system-x86_64", "-machine", "q35", "-accel", accel, "-cpu", "max", "-smp", smp, "-m", mem,
         "-display", "none", "-vga", "virtio", "-qmp", f"unix:/tmp/qmp-{name}.sock,server=on,wait=off",
         "-serial", f"file:{out}/serial-{name}.log", "-monitor", "none", "-no-reboot",
         "-drive", f"file={out}/target.qcow2,if=none,id=disk,discard=unmap",
         "-device", f"virtio-blk-pci,drive=disk,bootindex={1 if with_iso else 0}",
         "-drive", f"file={out}/data.iso,media=cdrom,readonly=on,if=none,id=data",
         "-device", "ide-cd,drive=data,bus=ide.0",   # sr0: `sudo sh /dev/sr0` runs its launcher
         "-netdev", "user,id=net0" + ("" if online else ",restrict=on"),
         "-device", "virtio-net-pci,netdev=net0",
         "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc"]
    if with_iso:
        a += ["-drive", "file=/iso,media=cdrom,readonly=on,if=none,id=cd", "-device", "ide-cd,drive=cd,bus=ide.1,bootindex=0"]
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
    # The terminal’s fetch animation reads keys (any key skips it): press Enter, then give the
    # prompt time to come up so the command isn't eaten by the animation.
    vm.keys("ret")
    time.sleep(15)
    vm.keys("ret")
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
            vm.type_text("sudo sh /dev/sr0", gap=0.3)
            vm.keys("ret")
            t = time.time()
            while time.time() - t < (3600 if E.get("GUEST_CHECK") else 240) and vm.alive():
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
            if E.get("COLLECT_VIA") == "console":
                return 93  # performance cannot clone a disk stopped by vm.quit()
        elif E.get("COLLECT_VIA") == "console":
            if vm.proc.returncode != 0:
                return 94
            log("ARCTIC-PRISTINE-INSTALL-POWEROFF=clean")
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
        # A dropped key means a wrong passphrase: Plymouth asks again (after the splash was
        # back on screen), and the passphrase is typed again, up to three times.
        p = None
        for attempt in (1, 2, 3):
            vm.type_text(luks, gap=0.3)
            time.sleep(1)
            vm.shot(f"boot-32-luks-typed-{attempt}")
            vm.keys("ret")
            time.sleep(15)
            vm.shot(f"boot-33-unlocking-{attempt}")
            t = time.time()
            left_prompt = False
            again = False
            while time.time() - t < 1500 and vm.alive():
                q = vm.shot("boot-40-probe")
                kind = vmtest.classify(q) if q else "none"
                if kind == "login":
                    p = q
                    break
                if kind != "prompt":
                    left_prompt = True
                elif left_prompt:
                    again = True
                    break
                time.sleep(10)
            if not again:
                break
            log(f"the passphrase prompt is back (attempt {attempt}): typing it again")
            vm.shot(f"boot-34-prompt-again-{attempt}")
        if p:
            time.sleep(30)
            vm.shot("boot-41-login")
            log("login screen on screen: boot-41-login.png")
        else:
            vm.shot("boot-41-no-login-detected")
            log("no login screen detected; typing the password anyway")
            ok = False
        for attempt in (1, 2, 3):
            vm.type_text(password, gap=0.3)
            time.sleep(1)
            vm.shot(f"boot-42-password-typed-{attempt}")
            vm.keys("ret")
            # SDDM clears the field and says so when the password was wrong; the card stays.
            t = time.time()
            gone = False
            while time.time() - t < 150 and vm.alive():
                time.sleep(10)
                q = vm.shot("boot-43-probe")
                if q and vmtest.classify(q) != "login":
                    gone = True
                    break
            if gone:
                break
            log(f"still on the login screen after the password (attempt {attempt}): typing it again")
            vm.shot(f"boot-43-login-again-{attempt}")
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
        collected = False
        lock_password_sent = False
        for attempt in ((1,) if E.get("COLLECT_VIA") == "console" else (1, 2, 3)):
            if E.get("COLLECT_VIA") == "console":
                vm.keys("ctrl-alt-f3")
                time.sleep(5)
                vm.type_text(E["PROFILE_USER"], gap=.3)
                vm.keys("ret")
                time.sleep(3)
                vm.type_text(password, gap=.3)
                vm.keys("ret")
                time.sleep(5)
            else:
                open_terminal(vm, f"boot-5{attempt + 1}")
            vm.type_text("sudo sh /dev/sr0", gap=0.3)
            vm.keys("ret")
            time.sleep(10)
            vm.shot(f"boot-5{attempt + 1}-sudo")
            vm.type_text(password, gap=0.3)
            vm.keys("ret")
            t = time.time()
            last_probe_shot = t
            probe_shots = 0
            while time.time() - t < (3600 if E.get("GUEST_CHECK") else 240) and vm.alive():
                if vmtest.serial_has(serial("boot"), "ARCTIC-COLLECT-END"):
                    collected = True
                    break
                if E.get("GUEST_CHECK_INTERACTIVE") == "1":
                    if time.time() - last_probe_shot >= 10:
                        probe_shots += 1
                        vm.shot(f"boot-58-check-{attempt}-{probe_shots:03d}")
                        last_probe_shot = time.time()
                    if not lock_password_sent and vmtest.serial_has(serial("boot"), "ARCTIC-DESKTOP-UNLOCK-REQUESTED"):
                        vm.shot("boot-58-locked-before-authentication")
                        vm.type_text(password, gap=0.3)
                        vm.keys("ret")
                        lock_password_sent = True
                time.sleep(5)
            collected = vmtest.serial_has(serial("boot"), "ARCTIC-COLLECT-END")
            vm.shot(f"boot-5{attempt + 1}-collected")
            if collected:
                log(f"collected into serial-boot.log (ARCTIC-COLLECT-BEGIN/END, attempt {attempt})")
                break
            log(f"collect.sh did not finish (attempt {attempt})")
        if not collected and "systemd.debug_shell" in boot_append:
            # No session (e.g. the login failed): collect from the root debug shell on tty9.
            log("collecting from the debug shell on tty9")
            vm.keys("ctrl-alt-f9")
            time.sleep(10)
            vm.type_text("sh /dev/sr0", gap=0.3)
            vm.keys("ret")
            t = time.time()
            while time.time() - t < 300 and vm.alive():
                if vmtest.serial_has(serial("boot"), "ARCTIC-COLLECT-END"):
                    collected = True
                    break
                time.sleep(5)
            vm.shot("boot-59-debug-shell")
            log("collected from the debug shell" if collected else "debug shell collect did not finish")
            ok = False   # the session itself didn't work
        if not collected:
            ok = False
        if E.get("GUEST_CHECK") and vmtest.serial_value(serial("boot"), "ARCTIC-INSTALLED-SMOKE-EXIT=") != "0":
            ok = False
        time.sleep(5)
        vm.shot("boot-99-final")
        if E.get("GUEST_CHECK") and not vm.wait_exit(120):
            ok = False
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
    if rc == 0 and E.get("UPGRADE_TO"):
        # Collect fresh evidence after the signed transaction, without the live ISO.
        # The generic guest checker owns collection and shutdown in both boots.
        os.rename(serial("boot"), f"{out}/serial-upgrade.log")
        os.rename(f"{out}/qemu-boot.log", f"{out}/qemu-upgrade.log")
        for f in os.listdir(out):
            if f.startswith("boot-") and f.endswith(".png"):
                os.rename(f"{out}/{f}", f"{out}/upgrade-{f}")
        rc = stage_boot()
        log(f"post-upgrade boot stage: exit {rc}")
for f in os.listdir(out):
    if f.endswith("-probe.png"):
        os.remove(os.path.join(out, f))
sys.exit(rc)
PY

inner=$(cat <<'INNER'
pkgs=(qemu-system-x86-core qemu-img edk2-ovmf seabios-bin python3-pillow xorriso
      qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci)
if [[ "$VM_TOOLS_PREPARED" == 1 ]]; then
  rpm -q "${pkgs[@]}" >/dev/null
else
  dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
fi
{
  rpm -q "${pkgs[@]}" | sort
  qemu-system-x86_64 --version
  sha256sum /usr/share/edk2/ovmf/*.fd /usr/share/seabios/*.bin
} > "$OUT/vm-toolchain.txt"
xorriso -as mkisofs -quiet -V ARCTICTEST -J -R -G "$OUT/sysarea.sh" -o "$OUT/data.iso" "$OUT/data"
if [ "$STAGE" != boot ]; then
  qemu-img create -q -f qcow2 "$OUT/target.qcow2" 40G
  [ "$FIRMWARE" = uefi ] && cp /usr/share/edk2/ovmf/OVMF_VARS.fd "$OUT/OVMF_VARS.fd"
elif [ -n "$FRESH_BOOT_FROM" ]; then
  [ ! -e "$OUT/target.qcow2" ] || { echo "fresh overlay already exists" >&2; exit 1; }
  qemu-img check -q "$FRESH_BOOT_FROM/target.qcow2"
  qemu-img create -q -f qcow2 -F qcow2 -b "$FRESH_BOOT_FROM/target.qcow2" "$OUT/target.qcow2"
  cp "$FRESH_BOOT_FROM/OVMF_VARS.fd" "$OUT/OVMF_VARS.fd"
fi
PROFILE_USER="$(python3 -c 'import pathlib,tomllib,sys; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["account"]["username"])' "$OUT/data/profile.toml")"
[[ "$PROFILE_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || exit 1
export PROFILE_USER
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
name_args=()
base_args=()
if [[ -n "$FRESH_BOOT_FROM" ]]; then base_args=(-v "$FRESH_BOOT_FROM:$FRESH_BOOT_FROM:ro"); fi
if [[ -n "${ARCTIC_VM_CONTAINER_NAME:-}" ]]; then
  [[ "$ARCTIC_VM_CONTAINER_NAME" =~ ^arctic-paired-[a-z0-9-]{1,80}$ ]] || arctic_die "invalid task VM container name"
  name_args=(--name "$ARCTIC_VM_CONTAINER_NAME")
fi
"$engine" run --rm "${name_args[@]}" "${ARCTIC_CONTAINER_ARGS[@]}" "${kvm_args[@]}" \
  -e VM_TOOLS_PREPARED="${ARCTIC_VM_TOOLS_PREPARED:-0}" \
  -e OUT="$OUT" -e FIRMWARE="$FIRMWARE" -e STAGE="$STAGE" -e MEMORY="$MEMORY" -e SMP="$SMP" \
  -e GUEST_CHECK="$GUEST_CHECK" -e UPGRADE_TO="$UPGRADE_TO" -e INSTALL_TIMEOUT="$INSTALL_TIMEOUT" -e BOOT_APPEND="$BOOT_APPEND" \
  -e GUEST_CHECK_INTERACTIVE="$GUEST_CHECK_INTERACTIVE" \
  -e ONLINE_PROXY="$ONLINE_PROXY" -e BOOT_NETWORK="$BOOT_NETWORK" \
  -e COLLECT_VIA="$COLLECT_VIA" -e FRESH_BOOT_FROM="$FRESH_BOOT_FROM" \
  -e LUKS_PASSPHRASE="$LUKS_PASSPHRASE" -e USER_PASSWORD="$USER_PASSWORD" -e DRIVER="$DRIVER" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$HERE/lib:/arctic-lib:ro" -v "$OUT:$OUT" "${iso_args[@]}" "${base_args[@]}" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner" || rc=$?

arctic_log "result: exit $rc (serial logs, test.log and screenshots in $OUT)"
if [[ -n "$GUEST_CHECK" ]]; then
  # Preserve actionable evidence in workflow logs as well as downloadable artifacts.
  grep -a 'ARCTIC-NIX-ACCEPTANCE\|ARCTIC-.*SMOKE-EXIT' "$OUT"/serial-*.log || true
  if (( rc != 0 )); then tail -n 120 "$OUT"/serial-*.log || true; fi
fi
find "$OUT" -maxdepth 1 -name '*.png' | sort | sed 's,^,  ,'
exit "$rc"
