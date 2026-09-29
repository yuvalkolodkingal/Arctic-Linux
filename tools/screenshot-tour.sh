#!/usr/bin/env bash
# Take the wiki's screenshots (docs/wiki/images/*.png) from the real Arctic Linux in QEMU (TCG).
#
#   tools/screenshot-tour.sh                     both phases: the live USB, then the installed disk
#   tools/screenshot-tour.sh --phase live        the ISO only: boot menu, splash, live desktop,
#                                                shell surfaces, terminal, tiling, Winter theme,
#                                                Zen, and the installer in demo mode
#   tools/screenshot-tour.sh --phase installed   the installed disk only: passphrase prompt,
#                                                login screen, desktop, lock screen
#   --only NAME[,NAME…]   retake only these images (names without .png; "installer" = all
#                         installer-*); --skip NAME[,NAME…] leaves some out. The boot and the
#                         steps an image depends on still run.
#   --iso PATH            default out/rc/iso/Arctic-Linux-1.0-x86_64.iso (else out/iso/…)
#   --disk-dir DIR        an install made by tools/test-install.sh (target.qcow2, and OVMF_VARS.fd
#                         for a UEFI install; default out/test/install/uefi). Both are copied to
#                         the work dir and the copies are deleted afterwards; the originals are
#                         never written. Without OVMF_VARS.fd the copy boots with SeaBIOS.
#   --luks PASS --password PASS   the installed system's secrets (default: test-install.sh's)
#   --out DIR             where the images go (default docs/wiki/images)
#   --work DIR            raw screendumps, logs, manifest.json (default out/tour)
#   --launcher-query Q    what is typed in the launcher shot (default "te")
#   --memory MiB --smp N  guest size (default 6144 MiB, 4 vCPUs); --kvm uses /dev/kvm
#   --hold SECONDS        keep the VM up at the end of a phase or after a failure and take
#                         commands from `python3 tools/lib/tour.py ctl <work> <op> …` (development)
#
# How it works (tools/lib/tour.py): QEMU runs headless in a Fedora 44 container, 1280x800
# virtio-gpu display, UEFI, a sound card (for the volume OSD). The tour presses the real
# shortcuts over QMP (Super = meta_l) and takes QMP screendumps once the screen has settled.
# In the live session it opens a terminal once to start a small agent (tools/lib/tour-agent.sh,
# fetched over QEMU's user network from the tour's HTTP server on the host), which it uses to
# seed the Get apps package index (the VM has no internet: the real Fedora 44 and Flathub name
# lists are fetched here first), open Thunar, and start and walk the installer against the
# engine's demo mode (ARCTIC_INSTALLER_MOCK=1: nothing is written to any disk) through its IPC.
# Two things this build needs help with, both done the way a person would get past them: the
# shell's popovers don't get keyboard focus from Mango when opened with their shortcut, so the
# tour clicks into the launcher / Get apps field before typing and closes popovers with a click
# outside; and the shortcut sheet is empty unless ~/.local/share/arctic/keys.txt exists, so the
# tour copies /usr/share/arctic/keys.txt there and restarts the shell once.
# The installed-system shots boot a copy of the disk tools/test-install.sh installed.
# Takes about 75 minutes without KVM (the live desktop redraws slowly under TCG); progress in
# <work>/test.log, what each picture shows (and anything left out) in <work>/manifest.json.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
ISO=""
DISK_DIR="$ROOT/out/test/install/uefi"
IMAGES="$ROOT/docs/wiki/images"
WORK="$ROOT/out/tour"
PHASES="live,installed"
ONLY=""
SKIP=""
MEMORY=6144
SMP=4
KVM=0
HOLD=0
PORT=18765
LAUNCHER_QUERY="te"
# tools/test-install.sh's test secrets (the installed disk was made with them).
LUKS_PASSPHRASE="$(sed -n 's/^LUKS_PASSPHRASE="\(.*\)"$/\1/p' "$HERE/test-install.sh")"
USER_PASSWORD="$(sed -n 's/^USER_PASSWORD="\(.*\)"$/\1/p' "$HERE/test-install.sh")"

while (( $# )); do
  case "$1" in
    --phase) PHASES="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --skip) SKIP="$2"; shift 2 ;;
    --iso) ISO="$2"; shift 2 ;;
    --disk-dir) DISK_DIR="$2"; shift 2 ;;
    --luks) LUKS_PASSPHRASE="$2"; shift 2 ;;
    --password) USER_PASSWORD="$2"; shift 2 ;;
    --out) IMAGES="$2"; shift 2 ;;
    --work) WORK="$2"; shift 2 ;;
    --launcher-query) LAUNCHER_QUERY="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --smp) SMP="$2"; shift 2 ;;
    --kvm) KVM=1; shift ;;
    --hold) HOLD="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) sed -n '2,41p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
PHASES="${PHASES//both/live,installed}"
if [[ -z "$ISO" ]]; then
  ISO="$ROOT/out/rc/iso/Arctic-Linux-1.0-x86_64.iso"
  [[ -f "$ISO" ]] || ISO="$ROOT/out/iso/Arctic-Linux-1.0-x86_64.iso"
fi
if [[ "$PHASES" == *live* ]]; then
  [[ -f "$ISO" ]] || arctic_die "no ISO at $ISO (run tools/build-iso.sh)"
  ISO="$(cd "$(dirname "$ISO")" && pwd)/$(basename "$ISO")"
fi
mkdir -p "$IMAGES" "$WORK"
IMAGES="$(cd "$IMAGES" && pwd)"
WORK="$(cd "$WORK" && pwd)"
rm -rf "$WORK/raw" "$WORK/ctl" "$WORK"/*.log "$WORK"/*.sock

# The installed disk: copy it (never boot the original), unless that phase is off.
DISK_COPY=""
VARS_COPY=""
NO_DISK_REASON=""
if [[ "$PHASES" == *installed* ]]; then
  if [[ ! -f "$DISK_DIR/target.qcow2" ]]; then
    NO_DISK_REASON="no installed disk in $DISK_DIR (run tools/test-install.sh first)"
    arctic_log "$NO_DISK_REASON: the installed-system shots are skipped"
  elif pgrep -f "qemu-system.*$DISK_DIR/target.qcow2" >/dev/null 2>&1; then
    NO_DISK_REASON="the disk in $DISK_DIR is still in use by a running test"
    arctic_log "$NO_DISK_REASON: the installed-system shots are skipped"
  else
    mkdir -p "$WORK/installed"
    arctic_log "copying the installed disk from $DISK_DIR"
    cp --sparse=always "$DISK_DIR/target.qcow2" "$WORK/installed/target.qcow2"
    DISK_COPY="$WORK/installed/target.qcow2"
    # With an OVMF variable store the disk was installed in UEFI mode (its boot entry lives
    # there); without one, in BIOS mode (SeaBIOS).
    if [[ -f "$DISK_DIR/OVMF_VARS.fd" ]]; then
      cp "$DISK_DIR/OVMF_VARS.fd" "$WORK/installed/OVMF_VARS.fd"
      VARS_COPY="$WORK/installed/OVMF_VARS.fd"
    fi
  fi
fi

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
kvm_args=()
if (( KVM )) && [[ -e /dev/kvm ]]; then kvm_args=(--device /dev/kvm); fi
iso_args=()
if [[ "$PHASES" == *live* ]]; then iso_args=(-v "$ISO:/iso:ro"); fi

inner=$(cat <<'INNER'
pkgs=(qemu-system-x86-core qemu-img edk2-ovmf python3-pillow
      qemu-device-display-virtio-vga qemu-device-display-virtio-gpu qemu-device-display-virtio-gpu-pci)
dnf -y install "${pkgs[@]}" >/dev/null 2>&1 || dnf -y install "${pkgs[@]}"
# The Get apps console's package index, which the VM can't fetch itself (no internet there):
# the same lists package-index.py would cache, refreshed once a day.
if [[ "$PHASES" == *live* ]]; then
  if [ -z "$(find "$OUT/packages.txt" -mmin -1440 2>/dev/null)" ]; then
    dnf -q repoquery --available --qf '%{name}\n' 2>/dev/null | grep -v ' ' | sort -u > "$OUT/packages.txt.new" \
      && [ -s "$OUT/packages.txt.new" ] && mv "$OUT/packages.txt.new" "$OUT/packages.txt" \
      || { echo "note: could not list the Fedora packages" >&2; rm -f "$OUT/packages.txt.new"; }
  fi
  # With summaries and repositories, for the Fedora packages page (package-index.py's TSV).
  if [ -z "$(find "$OUT/packages.tsv" -mmin -1440 2>/dev/null)" ]; then
    dnf -q repoquery --available --qf "$(printf '%%{name}\t%%{repoid}\t%%{summary}')\n" 2>/dev/null \
      | sort -t "$(printf '\t')" -k1,1 -u > "$OUT/packages.tsv.new" \
      && [ -s "$OUT/packages.tsv.new" ] && mv "$OUT/packages.tsv.new" "$OUT/packages.tsv" \
      || { echo "note: could not list the Fedora packages with summaries" >&2; rm -f "$OUT/packages.tsv.new"; }
  fi
  if [ -z "$(find "$OUT/flathub.txt" -mmin -1440 2>/dev/null)" ]; then
    curl -fsSL --max-time 120 https://flathub.org/api/v2/appstream \
      | python3 -c 'import json,sys; print("\n".join(sorted(json.load(sys.stdin))))' > "$OUT/flathub.txt.new" \
      && [ -s "$OUT/flathub.txt.new" ] && mv "$OUT/flathub.txt.new" "$OUT/flathub.txt" \
      || { echo "note: could not list the Flathub apps" >&2; rm -f "$OUT/flathub.txt.new"; }
  fi
fi
AUDIO=0
if qemu-system-x86_64 -device help 2>/dev/null | grep -q '"ich9-intel-hda"' \
   && qemu-system-x86_64 -device help 2>/dev/null | grep -q '"hda-output"'; then AUDIO=1; fi
export AUDIO
ACCEL="tcg,thread=multi"
[ -e /dev/kvm ] && ACCEL=kvm
export ACCEL
rc=0
python3 /arctic-lib/tour.py || rc=$?
chown -R "$HOST_UID:$HOST_GID" "$OUT" "$IMAGES"
exit $rc
INNER
)

arctic_log "screenshot tour (phases $PHASES) → $IMAGES (work: $WORK)"
rc=0
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${kvm_args[@]}" \
  -e OUT="$WORK" -e IMAGES="$IMAGES" -e PHASES="$PHASES" -e ONLY="$ONLY" -e SKIP="$SKIP" \
  -e ISO=/iso -e DISK_COPY="$DISK_COPY" -e VARS_COPY="$VARS_COPY" -e NO_DISK_REASON="$NO_DISK_REASON" \
  -e LUKS_PASSPHRASE="$LUKS_PASSPHRASE" -e USER_PASSWORD="$USER_PASSWORD" \
  -e MEMORY="$MEMORY" -e SMP="$SMP" -e HOLD="$HOLD" -e PORT="$PORT" -e LAUNCHER_QUERY="$LAUNCHER_QUERY" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$HERE/lib:/arctic-lib:ro" -v "$WORK:$WORK" -v "$IMAGES:$IMAGES" "${iso_args[@]}" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner" || rc=$?

# The disk copy is big and only needed for this run.
rm -rf "$WORK/installed"
arctic_log "result: exit $rc (log: $WORK/test.log, raw screendumps: $WORK/raw, list: $WORK/manifest.json)"
find "$IMAGES" -maxdepth 1 -name '*.png' -newer "$WORK/test.log" 2>/dev/null | sort | sed 's,^,  ,' || true
exit "$rc"
