#!/usr/bin/env bash
# Build the Arctic Linux RPMs in a Fedora 44 container → out/repo (a createrepo_c repository).
#
#   tools/build-rpms.sh                 build mangowm + arctic-linux
#   tools/build-rpms.sh --only arctic   only packaging/arctic-linux.spec
#   tools/build-rpms.sh --only mangowm  only packaging/mangowm.spec
#   tools/build-rpms.sh --src DIR       build from DIR instead of this checkout (e.g. a copy
#                                       with placeholder files, or another commit checked
#                                       out there); DIR need not be a git repo
#   tools/build-rpms.sh --out DIR       output directory (default: <repo>/out)
#   tools/build-rpms.sh --release-suffix auto|none|SUFFIX
#                                       what follows "1" in the Release of both specs
#                                       (Release: 1%{?arctic_snapshot}%{?dist}). auto (the
#                                       default): .<UTC yyyymmddHHMM>.git<commit>, so every
#                                       build is newer than the builds before it, e.g.
#                                       arctic-shell-0.2.0-1.202609280310.gitabc1234.fc44;
#                                       none: plain 1.fc44. Env: ARCTIC_RELEASE_SUFFIX.
#   tools/build-rpms.sh --gpg-public-key FILE
#                                       the Arctic repository's public signing key, shipped by
#                                       arctic-release as /etc/pki/rpm-gpg/RPM-GPG-KEY-arctic.
#                                       Env: ARCTIC_GPG_PUBLIC_KEY (the armored key itself).
#                                       Default: packaging/release/RPM-GPG-KEY-arctic if the
#                                       source tree has it. Without any key the build still
#                                       works, but arctic-release ships the Arctic
#                                       repositories disabled (with a loud warning).
#   tools/build-rpms.sh --require-gpg-key
#                                       fail instead (env ARCTIC_REQUIRE_GPG_KEY=1); used by
#                                       the repository workflow
#
# Source0 of arctic-linux.spec is `git archive --prefix=arctic-linux-<Version>/` of the working
# tree: the committed tree plus every uncommitted change, including untracked (not ignored)
# files (plain `git stash create` would miss untracked files, so a throwaway index is used),
# plus the public key given above. The mango release tarball is downloaded once and cached in
# out/sources/. Versions come from the specs.
#
# Output: out/repo/*.rpm + repodata, out/srpms/*.src.rpm, out/debug/ (debuginfo),
# out/logs/rpmbuild-*.log, and out/BUILD-INFO (key=value lines: version, release_suffix,
# git_commit, gpg_key fingerprint, arctic_repos enabled|disabled, one rpm=/srpm= line per
# package NEVRA built by this run). Packages that earlier runs built from the same specs are
# removed from out/repo and out/srpms first, so they hold one build of each package.
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
SUFFIX_MODE="${ARCTIC_RELEASE_SUFFIX:-auto}"
KEY_FILE=""
REQUIRE_KEY="${ARCTIC_REQUIRE_GPG_KEY:-0}"
KEY_PATH_IN_TREE="packaging/release/RPM-GPG-KEY-arctic"

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

while (( $# )); do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    --src)  SRC="$(cd "$2" && pwd)"; shift 2 ;;
    --out)  mkdir -p "$2"; OUT="$(cd "$2" && pwd)"; shift 2 ;;
    --release-suffix) SUFFIX_MODE="$2"; shift 2 ;;
    --gpg-public-key) KEY_FILE="$2"; shift 2 ;;
    --require-gpg-key) REQUIRE_KEY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$ONLY" in ""|arctic|mangowm) ;; *) arctic_die "--only takes arctic or mangowm" ;; esac

spec_value() { # spec_value SPEC TAG: the first "TAG: value" of a spec (no macros in it)
  sed -n "s/^$2:[[:space:]]*//p" "$SRC/packaging/$1" | head -n1
}
VERSION="$(spec_value arctic-linux.spec Version)"
MANGO_VERSION="$(spec_value mangowm.spec Version)"
[[ "$VERSION" =~ ^[0-9][0-9A-Za-z.+~^_]*$ ]] || arctic_die "can't read Version from packaging/arctic-linux.spec"
[[ "$MANGO_VERSION" =~ ^[0-9][0-9A-Za-z.+~^_]*$ ]] || arctic_die "can't read Version from packaging/mangowm.spec"
MANGO_URL="https://github.com/mangowm/mango/archive/refs/tags/${MANGO_VERSION}.tar.gz"

mkdir -p "$OUT/sources" "$OUT/repo" "$OUT/srpms" "$OUT/logs"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# ---- 0. Release suffix ----------------------------------------------------------------
is_git=0
git -C "$SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1 && is_git=1
BUILD_TIME="$(date -u +%Y%m%d%H%M)"
GIT_COMMIT=""; GIT_SHORT=""; GIT_DIRTY=""
if (( is_git )); then
  GIT_COMMIT="$(git -C "$SRC" rev-parse HEAD)"
  GIT_SHORT="$(git -C "$SRC" rev-parse --short=7 HEAD)"
  if [[ -n "$(git -C "$SRC" status --porcelain --untracked-files=normal 2>/dev/null)" ]]; then GIT_DIRTY=yes; else GIT_DIRTY=no; fi
fi
case "$SUFFIX_MODE" in
  auto) SUFFIX=".$BUILD_TIME"; [[ -n "$GIT_SHORT" ]] && SUFFIX+=".git$GIT_SHORT" ;;
  none) SUFFIX="" ;;
  *)    SUFFIX="$SUFFIX_MODE"; [[ "$SUFFIX" == .* ]] || SUFFIX=".$SUFFIX" ;;
esac
# A Release may not contain "-"; keep to what rpm compares predictably.
[[ -z "$SUFFIX" || "$SUFFIX" =~ ^(\.[A-Za-z0-9_+~^]+)+$ ]] ||
  arctic_die "bad --release-suffix '$SUFFIX': use dot-separated letters, digits, _ + ~ ^"
arctic_log "Release: 1${SUFFIX}.fc44 (arctic-linux $VERSION, mangowm $MANGO_VERSION)"

# ---- 1. The repository's public key (arctic-release) ----------------------------------
key_file=""      # the key file that goes into Source0 (a copy in $tmpdir), if one is supplied
key_note=""
if [[ -n "$KEY_FILE" ]]; then
  [[ -r "$KEY_FILE" ]] || arctic_die "--gpg-public-key: can't read $KEY_FILE"
  cp "$KEY_FILE" "$tmpdir/RPM-GPG-KEY-arctic"; key_note="$KEY_FILE"
elif [[ -n "${ARCTIC_GPG_PUBLIC_KEY:-}" ]]; then
  printf '%s\n' "$ARCTIC_GPG_PUBLIC_KEY" > "$tmpdir/RPM-GPG-KEY-arctic"; key_note="ARCTIC_GPG_PUBLIC_KEY"
fi
if [[ -n "$key_note" ]]; then
  key_file="$tmpdir/RPM-GPG-KEY-arctic"
  # Never let a secret key into a package, whatever was passed by mistake.
  if grep -q 'PRIVATE KEY' "$key_file"; then
    arctic_die "$key_note holds a PRIVATE key: pass the armored PUBLIC key"
  fi
  if ! grep -q -- '-----BEGIN PGP PUBLIC KEY BLOCK-----' "$key_file" ||
     ! grep -q -- '-----END PGP PUBLIC KEY BLOCK-----' "$key_file"; then
    arctic_die "$key_note is not an armored OpenPGP public key (-----BEGIN PGP PUBLIC KEY BLOCK-----)"
  fi
  if [[ -f "$SRC/$KEY_PATH_IN_TREE" ]] && ! cmp -s "$key_file" "$SRC/$KEY_PATH_IN_TREE"; then
    arctic_log "warning: the key from $key_note differs from the committed $KEY_PATH_IN_TREE; arctic-release gets the one from $key_note"
  fi
  arctic_log "arctic-release: repository key from $key_note"
elif [[ -f "$SRC/$KEY_PATH_IN_TREE" ]]; then
  grep -q 'PRIVATE KEY' "$SRC/$KEY_PATH_IN_TREE" && arctic_die "$KEY_PATH_IN_TREE holds a PRIVATE key"
  arctic_log "arctic-release: repository key from $KEY_PATH_IN_TREE"
elif [[ "$ONLY" != mangowm ]]; then
  if [[ "$REQUIRE_KEY" == 1 ]]; then
    arctic_die "no repository public key: set ARCTIC_GPG_PUBLIC_KEY, pass --gpg-public-key FILE or commit $KEY_PATH_IN_TREE"
  fi
  printf '\033[1;33m%s\033[0m\n' \
    "==> WARNING: no Arctic repository public key (--gpg-public-key, ARCTIC_GPG_PUBLIC_KEY or $KEY_PATH_IN_TREE)." \
    "==> WARNING: arctic-release is built with the Arctic repositories DISABLED (enabled=0): systems" \
    "==> WARNING: installed from these packages get no Arctic updates. Fine for local testing only." >&2
fi
effective_key="$key_file"
[[ -z "$effective_key" && -f "$SRC/$KEY_PATH_IN_TREE" ]] && effective_key="$SRC/$KEY_PATH_IN_TREE"

# ---- 2. Source tarballs -------------------------------------------------------------
tarball="$OUT/sources/arctic-linux-$VERSION.tar.gz"
if [[ "$ONLY" != mangowm ]]; then
  rm -f "$tarball"
  if (( is_git )); then
    arctic_log "archiving the working tree of $SRC (committed + uncommitted + untracked)"
    tmpidx="$tmpdir/index"
    gitdir="$(git -C "$SRC" rev-parse --git-dir)"
    [[ "$gitdir" = /* ]] || gitdir="$SRC/$gitdir"
    [[ -f "$gitdir/index" ]] && cp "$gitdir/index" "$tmpidx"
    GIT_INDEX_FILE="$tmpidx" git -C "$SRC" add -A .
    if [[ -n "$key_file" ]]; then
      blob="$(git -C "$SRC" hash-object -w "$key_file")"
      GIT_INDEX_FILE="$tmpidx" git -C "$SRC" update-index --add --cacheinfo "100644,$blob,$KEY_PATH_IN_TREE"
    fi
    tree="$(GIT_INDEX_FILE="$tmpidx" git -C "$SRC" write-tree)"
    git -C "$SRC" archive --format=tar.gz --prefix="arctic-linux-$VERSION/" -o "$tarball" "$tree"
  else
    arctic_log "archiving $SRC (not a git checkout: plain tar, out/ and .git excluded)"
    base="$(basename "$SRC")"
    excl=(--exclude-vcs --exclude="$base/out")
    [[ -n "$key_file" ]] && excl+=(--exclude="$base/$KEY_PATH_IN_TREE")
    tar -C "$(dirname "$SRC")" "${excl[@]}" --transform "s,^$base,arctic-linux-$VERSION," \
      -cf "${tarball%.gz}" "$base"
    if [[ -n "$key_file" ]]; then
      tar -C "$tmpdir" --transform "s,^RPM-GPG-KEY-arctic\$,arctic-linux-$VERSION/$KEY_PATH_IN_TREE," \
        -rf "${tarball%.gz}" RPM-GPG-KEY-arctic
    fi
    gzip -nf "${tarball%.gz}"
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
    git clone -q --depth 1 --branch "$MANGO_VERSION" https://github.com/mangowm/mango "$tmpdir/mango"
    git -C "$tmpdir/mango" archive --format=tar.gz --prefix="mango-$MANGO_VERSION/" \
      -o "$mango_tar.part" "$MANGO_VERSION"
  fi
  mv "$mango_tar.part" "$mango_tar"
fi

# ---- 3. Build in the container --------------------------------------------------------
specs=()
[[ "$ONLY" != arctic ]] && specs+=(mangowm)
[[ "$ONLY" != mangowm ]] && specs+=(arctic-linux)

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
key_args=()
[[ -n "$effective_key" ]] && key_args=(-v "$effective_key:/gpgkey:ro")

# The spec files always come from $SRC/packaging (they are also inside Source0).
inner=$(cat <<'INNER'
dnf -y install rpm-build rpmdevtools createrepo_c 'dnf5-command(builddep)' cpio >/dev/null 2>&1
mkdir -p /root/rpmbuild/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
cp -a /out/sources/. /root/rpmbuild/SOURCES/
define=()
[[ -n "$RELEASE_SUFFIX" ]] && define=(--define "arctic_snapshot $RELEASE_SUFFIX")
# arctic-linux.spec's %check validates the Mango configs when mango is installed: use the
# mangowm built earlier (out/repo) or in this run.
install_mango() {
  local rpm
  rpm="$(ls -t "$1"/mangowm-[0-9]*.x86_64.rpm 2>/dev/null | head -n1 || true)"
  if [[ -n "$rpm" ]]; then dnf -y install "$rpm" >/dev/null 2>&1 || echo "note: could not install $rpm for %check"; fi
}
[[ " $SPECS " == *" mangowm "* ]] || install_mango /out/repo
for spec in $SPECS; do
  echo "==> $spec: installing build dependencies"
  dnf -y builddep "/src/packaging/$spec.spec" >/dev/null 2>&1 || dnf -y builddep "/src/packaging/$spec.spec"
  echo "==> $spec: rpmbuild -ba ${define[*]}"
  if ! rpmbuild -ba "${define[@]}" "/src/packaging/$spec.spec" > "/out/logs/rpmbuild-$spec.log" 2>&1; then
    tail -n 60 "/out/logs/rpmbuild-$spec.log"
    echo "rpmbuild failed for $spec (full log: out/logs/rpmbuild-$spec.log)" >&2
    exit 1
  fi
  grep -E '^(Wrote|warning):' "/out/logs/rpmbuild-$spec.log" | sed 's,^,  ,' || true
  [[ "$spec" == mangowm ]] && install_mango /root/rpmbuild/RPMS/x86_64
done
# Earlier builds of the specs built now make way (packages of the other spec stay: --only).
mkdir -p /out/debug
for f in /out/repo/*.rpm /out/debug/*.rpm; do
  [[ -e "$f" ]] || continue
  src="$(rpm -qp --nosignature --qf '%{SOURCERPM}' "$f" 2>/dev/null)" || continue
  [[ " $SPECS " == *" ${src%-*-*} "* ]] && rm -f "$f"
done
for f in /out/srpms/*.src.rpm; do
  [[ -e "$f" ]] || continue
  name="$(rpm -qp --nosignature --qf '%{NAME}' "$f" 2>/dev/null)" || continue
  [[ " $SPECS " == *" $name "* ]] && rm -f "$f"
done
find /root/rpmbuild/RPMS -name '*.rpm' \( -name '*-debuginfo-*' -o -name '*-debugsource-*' \) -exec cp -f {} /out/debug/ \;
find /root/rpmbuild/RPMS -name '*.rpm' ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -exec cp -f {} /out/repo/ \;
cp -f /root/rpmbuild/SRPMS/*.src.rpm /out/srpms/
rm -rf /out/repo/repodata
createrepo_c /out/repo >/dev/null

# out/BUILD-INFO: what this run built, for the ISO and repository workflows.
fpr=""
if [[ -r /gpgkey ]]; then
  fpr="$(gpg --batch --with-colons --import-options show-only --import /gpgkey 2>/dev/null | awk -F: '$1 == "fpr" { print $10; exit }')"
fi
repos=not-built
rel="$(ls /root/rpmbuild/RPMS/noarch/arctic-release-[0-9]*.rpm 2>/dev/null | head -n1 || true)"
if [[ -n "$rel" ]]; then
  repos=disabled
  if rpm -qlp "$rel" | grep -x /etc/pki/rpm-gpg/RPM-GPG-KEY-arctic >/dev/null; then repos=enabled; fi
fi
{
  echo "# Written by tools/build-rpms.sh: the packages this build produced."
  echo "version=$VERSION"
  echo "release_suffix=$RELEASE_SUFFIX"
  echo "build_time=$BUILD_TIME"
  echo "git_commit=$GIT_COMMIT"
  echo "git_dirty=$GIT_DIRTY"
  echo "specs=$SPECS"
  echo "gpg_key=$fpr"
  echo "arctic_repos=$repos"
  find /root/rpmbuild/RPMS -name '*.rpm' ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -print0 |
    xargs -0 -r rpm -qp --nosignature --qf 'rpm=%{NEVRA}\n' | sort
  rpm -qp --nosignature --qf 'srpm=%{NAME}-%{EVR}.src\n' /root/rpmbuild/SRPMS/*.src.rpm | sort
} > /out/BUILD-INFO
chown -R "$HOST_UID:$HOST_GID" /out/repo /out/srpms /out/logs /out/sources /out/debug /out/BUILD-INFO
echo "==> packages in out/repo:"
ls -1 /out/repo/*.rpm | sed 's,.*/,  ,'
if [[ "$repos" == disabled ]]; then
  echo "==> WARNING: arctic-release has no repository key: the Arctic repositories are disabled in it" >&2
fi
INNER
)

arctic_log "building ${specs[*]} in $ARCTIC_FEDORA_IMAGE ($engine)"
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${key_args[@]}" \
  -e SPECS="${specs[*]}" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -e RELEASE_SUFFIX="$SUFFIX" -e VERSION="$VERSION" -e BUILD_TIME="$BUILD_TIME" \
  -e GIT_COMMIT="$GIT_COMMIT" -e GIT_DIRTY="$GIT_DIRTY" \
  -v "$SRC:/src:ro" -v "$OUT:/out" \
  "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "done: $OUT/repo (build info: $OUT/BUILD-INFO)"
