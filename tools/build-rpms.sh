#!/usr/bin/env bash
# Build the Arctic Linux RPMs in a Fedora 44 container → out/repo (a createrepo_c repository).
#
#   tools/build-rpms.sh                 build mangowm + arctic-linux
#   tools/build-rpms.sh --only arctic   only packaging/arctic-linux.spec
#   tools/build-rpms.sh --only mangowm  only packaging/mangowm.spec
#   tools/build-rpms.sh --src DIR       build from DIR instead of this checkout (e.g. a copy
#                                       with placeholder files); DIR need not be a git repo
#   tools/build-rpms.sh --out DIR       output directory (default: <repo>/out)
#
# Source0 of arctic-linux.spec is `git archive --prefix=arctic-linux-0.1.0/` of the working
# tree: the committed tree plus every uncommitted change, including untracked (not ignored)
# files. (Plain `git stash create` would miss untracked files, so a throwaway index is used.)
# The mango release tarball is downloaded once and cached in out/sources/.
#
# Output: out/repo/*.rpm + repodata, out/srpms/*.src.rpm, out/debug/ (debuginfo),
# out/logs/rpmbuild-*.log.
# Needs docker or podman. Behind a proxy, HTTPS_PROXY and the CA bundle are passed through
# (see tools/lib/container.sh); on a GitHub runner nothing extra is needed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"

ROOT="$(arctic_repo_root)"
SRC="$ROOT"
OUT="$ROOT/out"
ONLY=""
VERSION="0.1.0"
MANGO_VERSION="0.17.3"
MANGO_URL="https://github.com/mangowm/mango/archive/refs/tags/${MANGO_VERSION}.tar.gz"

while (( $# )); do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    --src)  SRC="$(cd "$2" && pwd)"; shift 2 ;;
    --out)  mkdir -p "$2"; OUT="$(cd "$2" && pwd)"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$ONLY" in ""|arctic|mangowm) ;; *) arctic_die "--only takes arctic or mangowm" ;; esac

mkdir -p "$OUT/sources" "$OUT/repo" "$OUT/srpms" "$OUT/logs"

# ---- 1. Source tarballs -------------------------------------------------------------
tarball="$OUT/sources/arctic-linux-$VERSION.tar.gz"
if [[ "$ONLY" != mangowm ]]; then
  rm -f "$tarball"
  if git -C "$SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    arctic_log "archiving the working tree of $SRC (committed + uncommitted + untracked)"
    tmpidx="$(mktemp)"
    trap 'rm -f "$tmpidx"' EXIT
    gitdir="$(git -C "$SRC" rev-parse --git-dir)"
    [[ "$gitdir" = /* ]] || gitdir="$SRC/$gitdir"
    if [[ -f "$gitdir/index" ]]; then cp "$gitdir/index" "$tmpidx"; else rm -f "$tmpidx"; fi
    GIT_INDEX_FILE="$tmpidx" git -C "$SRC" add -A .
    tree="$(GIT_INDEX_FILE="$tmpidx" git -C "$SRC" write-tree)"
    git -C "$SRC" archive --format=tar.gz --prefix="arctic-linux-$VERSION/" -o "$tarball" "$tree"
  else
    arctic_log "archiving $SRC (not a git checkout: plain tar, out/ and .git excluded)"
    tar -C "$(dirname "$SRC")" --exclude-vcs --exclude="$(basename "$SRC")/out" \
      --transform "s,^$(basename "$SRC"),arctic-linux-$VERSION," \
      -czf "$tarball" "$(basename "$SRC")"
  fi
  arctic_log "Source0: $tarball ($(du -h "$tarball" | cut -f1))"
fi

mango_tar="$OUT/sources/mango-$MANGO_VERSION.tar.gz"
if [[ "$ONLY" != arctic && ! -s "$mango_tar" ]]; then
  arctic_log "downloading mango $MANGO_VERSION"
  if ! curl -fsSL --retry 3 --retry-delay 3 -o "$mango_tar.part" "$MANGO_URL"; then
    # Some proxies allow git but not GitHub's archive endpoint: the same tarball is
    # `git archive` of the tag with the mango-<version>/ prefix.
    arctic_log "archive download failed; cloning the $MANGO_VERSION tag with git instead"
    tmpclone="$(mktemp -d)"
    git clone -q --depth 1 --branch "$MANGO_VERSION" https://github.com/mangowm/mango "$tmpclone/mango"
    git -C "$tmpclone/mango" archive --format=tar.gz --prefix="mango-$MANGO_VERSION/" \
      -o "$mango_tar.part" "$MANGO_VERSION"
    rm -rf "$tmpclone"
  fi
  mv "$mango_tar.part" "$mango_tar"
fi

# ---- 2. Build in the container --------------------------------------------------------
specs=()
[[ "$ONLY" != arctic ]] && specs+=(mangowm)
[[ "$ONLY" != mangowm ]] && specs+=(arctic-linux)

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args

# The spec files always come from $SRC/packaging (they are also inside Source0).
inner=$(cat <<'INNER'
dnf -y install rpm-build rpmdevtools createrepo_c 'dnf5-command(builddep)' >/dev/null 2>&1
mkdir -p /root/rpmbuild/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
cp -a /out/sources/. /root/rpmbuild/SOURCES/
# arctic-linux.spec's %check validates the Mango configs when mango is installed: use the
# mangowm built earlier (out/repo) or in this run.
install_mango() {
  local rpm
  rpm="$(ls "$1"/mangowm-[0-9]*.x86_64.rpm 2>/dev/null | head -n1 || true)"
  if [[ -n "$rpm" ]]; then dnf -y install "$rpm" >/dev/null 2>&1 || echo "note: could not install $rpm for %check"; fi
}
[[ " $SPECS " == *" mangowm "* ]] || install_mango /out/repo
for spec in $SPECS; do
  echo "==> $spec: installing build dependencies"
  dnf -y builddep "/src/packaging/$spec.spec" >/dev/null 2>&1 || dnf -y builddep "/src/packaging/$spec.spec"
  echo "==> $spec: rpmbuild -ba"
  if ! rpmbuild -ba "/src/packaging/$spec.spec" > "/out/logs/rpmbuild-$spec.log" 2>&1; then
    tail -n 60 "/out/logs/rpmbuild-$spec.log"
    echo "rpmbuild failed for $spec (full log: out/logs/rpmbuild-$spec.log)" >&2
    exit 1
  fi
  grep -E '^(Wrote|warning):' "/out/logs/rpmbuild-$spec.log" | sed 's,^,  ,' || true
  [[ "$spec" == mangowm ]] && install_mango /root/rpmbuild/RPMS/x86_64
done
mkdir -p /out/debug
rm -f /out/repo/*-debuginfo-*.rpm /out/repo/*-debugsource-*.rpm
find /root/rpmbuild/RPMS -name '*.rpm' \( -name '*-debuginfo-*' -o -name '*-debugsource-*' \) -exec cp -f {} /out/debug/ \;
find /root/rpmbuild/RPMS -name '*.rpm' ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -exec cp -f {} /out/repo/ \;
cp -f /root/rpmbuild/SRPMS/*.src.rpm /out/srpms/
createrepo_c --update /out/repo >/dev/null
chown -R "$HOST_UID:$HOST_GID" /out/repo /out/srpms /out/logs /out/sources /out/debug
echo "==> packages in out/repo:"
ls -1 /out/repo/*.rpm | sed 's,.*/,  ,'
INNER
)

arctic_log "building ${specs[*]} in $ARCTIC_FEDORA_IMAGE ($engine)"
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" \
  -e SPECS="${specs[*]}" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$SRC:/src:ro" -v "$OUT:/out" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "done: $OUT/repo"
