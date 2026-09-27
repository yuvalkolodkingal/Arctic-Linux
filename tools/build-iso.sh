#!/usr/bin/env bash
# Build the Arctic Linux live ISO with kiwi-ng in a privileged Fedora 44 container.
#
#   tools/build-iso.sh                  → out/iso/Arctic-Linux-0.1-x86_64.iso (+ .sha256)
#   tools/build-iso.sh --repo DIR       local RPM repository (default out/repo, from
#                                       tools/build-rpms.sh)
#   tools/build-iso.sh --work DIR       kiwi build root and scratch space (default out/kiwi-work;
#                                       needs ~15 GB; removed afterwards unless --keep-work)
#   tools/build-iso.sh --cache DIR      keep kiwi's dnf package cache in DIR between builds
#   tools/build-iso.sh --out DIR        output directory (default out/iso)
#   tools/build-iso.sh --debug          kiwi --debug
#   tools/build-iso.sh --zen auto|yes|no  preinstall Zen Browser (Flathub) in the live image:
#                                       auto (default) keeps it only while the ISO is ≤ 2 GiB
#
# Uses iso/kiwi/ (config.kiwi, config.sh, grub template), Fedora 44 + updates from the
# mirrors, and the local repository for mangowm and the arctic-* packages.
# Works on a developer machine (docker or podman, behind a proxy too) and on a GitHub
# ubuntu runner (docker, --privileged).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
REPO="$ROOT/out/repo"
WORK="$ROOT/out/kiwi-work"
OUT="$ROOT/out/iso"
CACHE=""
KEEP_WORK=0
DEBUG=""
ZEN=auto
ISO_NAME="Arctic-Linux-0.1-x86_64.iso"

while (( $# )); do
  case "$1" in
    --repo)  REPO="$2"; shift 2 ;;
    --work)  WORK="$2"; shift 2 ;;
    --out)   OUT="$2"; shift 2 ;;
    --cache) CACHE="$2"; shift 2 ;;
    --keep-work) KEEP_WORK=1; shift ;;
    --debug) DEBUG="--debug"; shift ;;
    --zen) ZEN="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done

case "$ZEN" in auto|yes|no) ;; *) arctic_die "--zen takes auto, yes or no" ;; esac
[[ -f "$REPO/repodata/repomd.xml" ]] || arctic_die "no RPM repository at $REPO (run tools/build-rpms.sh first)"
ls "$REPO"/arctic-desktop-*.rpm >/dev/null 2>&1 || arctic_die "$REPO has no arctic-desktop package"
ls "$REPO"/mangowm-*.rpm >/dev/null 2>&1 || arctic_die "$REPO has no mangowm package"

mkdir -p "$WORK" "$OUT" "$ROOT/out/logs"
REPO="$(cd "$REPO" && pwd)"; WORK="$(cd "$WORK" && pwd)"; OUT="$(cd "$OUT" && pwd)"
LOGS="$(cd "$ROOT/out/logs" && pwd)"
cache_args=()
if [[ -n "$CACHE" ]]; then
  mkdir -p "$CACHE"; CACHE="$(cd "$CACHE" && pwd)"
  cache_args=(-v "$CACHE:/var/cache/kiwi")
fi

avail_gb=$(( $(df -Pk "$WORK" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
arctic_log "free space for the kiwi build root ($WORK): ${avail_gb} GB"
(( avail_gb >= 12 )) || arctic_log "warning: less than 12 GB free; the build may run out of space"

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args

inner=$(cat <<'INNER'
dnf -y install kiwi-cli kiwi-systemdeps-iso-media kiwi-systemdeps-filesystems \
  distribution-gpg-keys erofs-utils flatpak >/dev/null 2>&1 || \
  dnf -y install kiwi-cli kiwi-systemdeps-iso-media kiwi-systemdeps-filesystems distribution-gpg-keys erofs-utils flatpak
kiwi-ng --version || :
# kiwi needs loop devices for the EFI image on some hosts.
for i in $(seq 0 7); do [ -e /dev/loop$i ] || mknod -m 0660 /dev/loop$i b 7 $i 2>/dev/null || :; done
rm -rf /work/build /work/root
fail() { echo "kiwi failed: $1; last lines of out/logs/$2:" >&2; tail -n 80 "/logs/$2" >&2 || :; exit 1; }

# 1. prepare: install the packages into /work/root and run config.sh.
kiwi-ng $KIWI_DEBUG --logfile /logs/kiwi-prepare.log --color-output system prepare \
  --description /desc --root /work/root \
  --add-repo dir:///repo,rpm-md,arctic-local,1,false,false || fail prepare kiwi-prepare.log

# 2. Zen Browser from Flathub, installed into the image from outside (no chroot), so "Try"
#    has a browser. Kept only while the ISO stays within GitHub's 2 GiB asset limit.
zen=0
if [ "$ZEN" != no ]; then
  export FLATPAK_SYSTEM_DIR=/work/root/var/lib/flatpak
  if flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo &&
     flatpak install --system -y --noninteractive flathub app.zen_browser.zen; then
    zen=1
    flatpak list --system --columns=application,version,size || :
  else
    echo "note: could not install Zen from Flathub; building without it" >&2
    [ "$ZEN" = yes ] && exit 1
  fi
  unset FLATPAK_SYSTEM_DIR
fi

create() {
  rm -rf /work/build
  kiwi-ng $KIWI_DEBUG --logfile /logs/kiwi-create.log --color-output system create \
    --root /work/root --target-dir /work/build || fail create kiwi-create.log
}

# 3. create: SELinux labels, live initrd, erofs root, ISO.
create
iso=$(ls /work/build/*.iso | head -n1)
if [ "$zen" = 1 ] && [ "$ZEN" = auto ] && [ "$(stat -c %s "$iso")" -gt 2147483648 ]; then
  echo "note: with Zen the ISO is $(( $(stat -c %s "$iso") / 1048576 )) MiB (> 2 GiB): rebuilding without it" >&2
  FLATPAK_SYSTEM_DIR=/work/root/var/lib/flatpak flatpak uninstall --system -y --noninteractive --all || :
  rm -rf /work/root/var/lib/flatpak/repo/objects/* /work/root/var/lib/flatpak/app /work/root/var/lib/flatpak/runtime
  zen=0
  create
  iso=$(ls /work/build/*.iso | head -n1)
fi
echo "zen_preinstalled=$zen" > "/out/${ISO_NAME%.iso}.build-info"
cp -f "$iso" "/out/$ISO_NAME"
( cd /out && sha256sum "$ISO_NAME" > "$ISO_NAME.sha256" )
cp -f /work/build/*.packages "/out/${ISO_NAME%.iso}.packages" 2>/dev/null || :
chown "$HOST_UID:$HOST_GID" /out/* /logs/kiwi-*.log 2>/dev/null || :
if [ "$KEEP_WORK" != 1 ]; then rm -rf /work/build /work/root; fi
INNER
)

arctic_log "building the ISO with kiwi-ng in $ARCTIC_FEDORA_IMAGE ($engine, privileged)"
start=$(date +%s)
"$engine" run --rm --privileged "${ARCTIC_CONTAINER_ARGS[@]}" "${cache_args[@]}" \
  -e ISO_NAME="$ISO_NAME" -e KIWI_DEBUG="$DEBUG" -e ZEN="$ZEN" -e KEEP_WORK="$KEEP_WORK" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$ROOT/iso/kiwi:/desc:ro" -v "$REPO:/repo:ro" -v "$WORK:/work" -v "$OUT:/out" -v "$LOGS:/logs" \
  "$ARCTIC_FEDORA_IMAGE" bash ${ARCTIC_TRACE:+-x} -c "$ARCTIC_CONTAINER_PROLOGUE$inner"
[[ $KEEP_WORK == 1 ]] || rmdir "$WORK" 2>/dev/null || true

iso="$OUT/$ISO_NAME"
[[ -f "$iso" ]] || arctic_die "no ISO produced"
size=$(stat -c %s "$iso")
arctic_log "built $iso: $(( size / 1024 / 1024 )) MiB in $(( ($(date +%s) - start) / 60 )) min"
if (( size > 2147483648 )); then
  arctic_log "note: the ISO is larger than 2 GiB (GitHub release assets are limited to 2 GiB)"
fi
cat "$OUT/${ISO_NAME%.iso}.build-info" 2>/dev/null || true
cat "$iso.sha256"
