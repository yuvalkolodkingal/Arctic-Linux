#!/usr/bin/env bash
# Build the Arctic Linux RPMs in a Fedora 44 container → out/repo (a createrepo_c repository).
#
#   tools/build-rpms.sh                 build scenefx + mangowm + arctic-linux
#   tools/build-rpms.sh --only arctic   only packaging/arctic-linux.spec
#   tools/build-rpms.sh --only mangowm  scenefx, then packaging/mangowm.spec
#   tools/build-rpms.sh --only scenefx  only packaging/scenefx.spec
#   tools/build-rpms.sh --src DIR       build from DIR instead of this checkout (e.g. a copy
#                                       with placeholder files, or another commit checked
#                                       out there); DIR need not be a git repo
#   tools/build-rpms.sh --out DIR       output directory (default: <repo>/out)
#   tools/build-rpms.sh --cache DIR     build-only DNF/Go cache (default: <out>/cache/build)
#   tools/build-rpms.sh --no-cache      use fresh caches for a measured cold build
#   tools/build-rpms.sh --release-suffix auto|none|SUFFIX
#                                       snapshot suffix after each spec's base Release.
#                                       auto (default): .<commit time>.<build time>.git<commit>,
#                                       both UTC (yyyymmddHHMMSS of the commit's committer
#                                       date, yyyymmddHHMM of the build), e.g.
#                                       arctic-shell-0.2.0-1.20260928030512.202609280310.gitabc1234.fc44:
#                                       builds of newer code are newer packages, and so is a
#                                       later build of the same commit; an old commit built
#                                       again stays older than the newer code. Not a git
#                                       checkout: the build time stands in for the commit
#                                       time. none: plain base Release.fc44 (1 or 2).
#                                       Env: ARCTIC_RELEASE_SUFFIX.
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
# plus the public key given above. Mango, pinned SceneFX and arctic-linux.spec's Source1 (the
# Nerd Font symbols release) are downloaded once and cached in out/sources/. Versions come from
# the specs; SceneFX integrity is checked on every use and in its %prep.
#
# Output: out/repo/*.rpm + repodata, out/srpms/*.src.rpm, out/debug/ (debuginfo),
# out/logs/rpmbuild-*.log, and out/BUILD-INFO (key=value lines: version, release_suffix,
# build_time, commit_time, git_commit, git_dirty, gpg_key fingerprint,
# arctic_repos enabled|disabled|not-built, one rpm=/srpm= line per
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
CACHE=""
CACHE_ENABLED=1
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
    --cache) CACHE="$2"; CACHE_ENABLED=1; shift 2 ;;
    --no-cache) CACHE_ENABLED=0; shift ;;
    --release-suffix) SUFFIX_MODE="$2"; shift 2 ;;
    --gpg-public-key) KEY_FILE="$2"; shift 2 ;;
    --require-gpg-key) REQUIRE_KEY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$ONLY" in ""|arctic|mangowm|scenefx) ;; *) arctic_die "--only takes arctic, mangowm or scenefx" ;; esac

spec_value() { # spec_value SPEC TAG: the first "TAG: value" of a spec (no macros in it)
  sed -n "s/^$2:[[:space:]]*//p" "$SRC/packaging/$1" | head -n1
}
VERSION="$(spec_value arctic-linux.spec Version)"
MANGO_VERSION="$(spec_value mangowm.spec Version)"
[[ "$VERSION" =~ ^[0-9][0-9A-Za-z.+~^_]*$ ]] || arctic_die "can't read Version from packaging/arctic-linux.spec"
[[ "$MANGO_VERSION" =~ ^[0-9][0-9A-Za-z.+~^_]*$ ]] || arctic_die "can't read Version from packaging/mangowm.spec"
MANGO_URL="https://github.com/mangowm/mango/archive/refs/tags/${MANGO_VERSION}.tar.gz"
SCENEFX_VERSION=""; SCENEFX_SHA256=""
if [[ "$ONLY" != arctic ]]; then
  SCENEFX_VERSION="$(spec_value scenefx.spec Version)"
  SCENEFX_SHA256="$(sed -n 's/^%global[[:space:]]\+scenefx_sha256[[:space:]]\+//p' "$SRC/packaging/scenefx.spec" | head -n1)"
  [[ "$SCENEFX_VERSION" =~ ^[0-9][0-9.]*$ && "$SCENEFX_SHA256" =~ ^[0-9a-f]{64}$ ]] \
    || arctic_die "can't read scenefx version / SHA-256 from packaging/scenefx.spec"
fi
SCENEFX_URL="https://github.com/wlrfx/scenefx/archive/refs/tags/${SCENEFX_VERSION}/scenefx-${SCENEFX_VERSION}.tar.gz"
# --- stream 6: arctic-linux.spec's Source1, pinned there by version and SHA-256. Specs before
# 0.3 (an older --src) have none, and nothing to fetch.
NERD_VERSION="$(sed -n 's/^%global[[:space:]]\+nerd_version[[:space:]]\+//p' "$SRC/packaging/arctic-linux.spec" | head -n1)"
NERD_SHA256="$(sed -n 's/^%global[[:space:]]\+nerd_sha256[[:space:]]\+//p' "$SRC/packaging/arctic-linux.spec" | head -n1)"
if [[ -n "$NERD_VERSION$NERD_SHA256" ]]; then
  [[ "$NERD_VERSION" =~ ^[0-9][0-9.]*$ && "$NERD_SHA256" =~ ^[0-9a-f]{64}$ ]] \
    || arctic_die "can't read nerd_version / nerd_sha256 from packaging/arctic-linux.spec"
fi
NERD_URL="https://github.com/ryanoasis/nerd-fonts/releases/download/v${NERD_VERSION}/NerdFontsSymbolsOnly.tar.xz"
# --- end stream 6

mkdir -p "$OUT/sources" "$OUT/repo" "$OUT/srpms" "$OUT/logs"
cache_args=()
if [[ "$CACHE_ENABLED" == 1 ]]; then
  CACHE="${CACHE:-$OUT/cache/build}"
  mkdir -p "$CACHE"; CACHE="$(cd "$CACHE" && pwd)"
  [[ "$CACHE" != / && "$CACHE" != "$ROOT" && "$CACHE" != "$SRC" && "$CACHE" != "$OUT" ]] \
    || arctic_die "--cache needs a dedicated build-cache directory"
  cache_args=(-v "$CACHE:/cache")
fi
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# ---- 0. Release suffix ----------------------------------------------------------------
is_git=0
git -C "$SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1 && is_git=1
now="$(date -u +%s)"
BUILD_TIME="$(date -u -d "@$now" +%Y%m%d%H%M)"
# The commit's (committer) time orders builds by code first: an ISO built later from an older
# commit must not outrank the repository's builds of newer commits.
COMMIT_TIME="$(date -u -d "@$now" +%Y%m%d%H%M%S)"
GIT_COMMIT=""; GIT_SHORT=""; GIT_DIRTY=""
if (( is_git )); then
  GIT_COMMIT="$(git -C "$SRC" rev-parse HEAD)"
  GIT_SHORT="$(git -C "$SRC" rev-parse --short=7 HEAD)"
  COMMIT_TIME="$(TZ=UTC git -C "$SRC" log -1 --format=%cd --date=format-local:%Y%m%d%H%M%S HEAD)"
  if [[ -n "$(git -C "$SRC" status --porcelain --untracked-files=normal 2>/dev/null)" ]]; then GIT_DIRTY=yes; else GIT_DIRTY=no; fi
fi
[[ "$COMMIT_TIME" =~ ^[0-9]{14}$ ]] || arctic_die "can't read the commit time of $SRC (got '$COMMIT_TIME')"
case "$SUFFIX_MODE" in
  auto) SUFFIX=".$COMMIT_TIME.$BUILD_TIME"; [[ -n "$GIT_SHORT" ]] && SUFFIX+=".git$GIT_SHORT" ;;
  none) SUFFIX="" ;;
  *)    SUFFIX="$SUFFIX_MODE"; [[ "$SUFFIX" == .* ]] || SUFFIX=".$SUFFIX" ;;
esac
# A Release may not contain "-"; keep to what rpm compares predictably.
[[ -z "$SUFFIX" || "$SUFFIX" =~ ^(\.[A-Za-z0-9_+~^]+)+$ ]] ||
  arctic_die "bad --release-suffix '$SUFFIX': use dot-separated letters, digits, _ + ~ ^"
arctic_log "Release suffix: ${SUFFIX:-none}.fc44 (arctic-linux $VERSION base 1, mangowm $MANGO_VERSION base 1, scenefx ${SCENEFX_VERSION:-not-built} base 2)"

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
elif [[ "$ONLY" != mangowm && "$ONLY" != scenefx ]]; then
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
if [[ "$ONLY" != mangowm && "$ONLY" != scenefx ]]; then
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
    # git archive prefetches every blob in a partial clone, even export-ignored
    # artwork. Prune those roots from this temporary archive index first. The
    # working tree and its real index stay intact; Source0 has the same payload.
    git -C "$SRC" ls-tree --name-only -z "$tree" > "$tmpdir/archive-roots"
    GIT_INDEX_FILE="$tmpidx" git -C "$SRC" check-attr --cached -z export-ignore --stdin \
      < "$tmpdir/archive-roots" > "$tmpdir/archive-attributes"
    archive_ignored=()
    while IFS= read -r -d '' archive_path && IFS= read -r -d '' archive_attribute \
        && IFS= read -r -d '' archive_value; do
      if [[ "$archive_attribute" == export-ignore && "$archive_value" == set && "$archive_path" != .gitattributes ]]; then
        archive_ignored+=("$archive_path")
      fi
    done < "$tmpdir/archive-attributes"
    if (( ${#archive_ignored[@]} )); then
      GIT_INDEX_FILE="$tmpidx" git --literal-pathspecs -C "$SRC" ls-files -z -- "${archive_ignored[@]}" \
        > "$tmpdir/archive-ignored-files"
      GIT_INDEX_FILE="$tmpidx" git -C "$SRC" update-index --force-remove -z --stdin \
        < "$tmpdir/archive-ignored-files"
      tree="$(GIT_INDEX_FILE="$tmpidx" git -C "$SRC" write-tree)"
    fi
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
if [[ "$ONLY" != arctic && "$ONLY" != scenefx && ! -s "$mango_tar" ]]; then
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

# Validate cached sources as well as fresh downloads. SceneFX's %prep repeats this
# immutable Fedora/upstream archive check before applying the Safe-mode patch.
if [[ "$ONLY" != arctic ]]; then
  scenefx_tar="$OUT/sources/scenefx-$SCENEFX_VERSION.tar.gz"
  if [[ ! -s "$scenefx_tar" ]]; then
    arctic_log "downloading scenefx $SCENEFX_VERSION"
    curl -fsSL --retry 3 --retry-delay 3 -o "$scenefx_tar.part" "$SCENEFX_URL" \
      || arctic_die "couldn't download $SCENEFX_URL"
    echo "$SCENEFX_SHA256  $scenefx_tar.part" | sha256sum -c --quiet - \
      || { rm -f "$scenefx_tar.part"; arctic_die "SceneFX source doesn't match the pinned SHA-256"; }
    mv "$scenefx_tar.part" "$scenefx_tar"
  fi
  echo "$SCENEFX_SHA256  $scenefx_tar" | sha256sum -c --quiet - \
    || arctic_die "cached SceneFX source doesn't match the pinned SHA-256"
  cp "$SRC/packaging/scenefx/test_safe_completion.py" "$OUT/sources/"
fi

# --- stream 6: Source1 (the Nerd Font symbols release); a download that doesn't match the pinned
# SHA-256 is refused here rather than by rpmbuild's %prep.
nerd_tar="$OUT/sources/NerdFontsSymbolsOnly-$NERD_VERSION.tar.xz"
if [[ -n "$NERD_VERSION" && "$ONLY" != mangowm && "$ONLY" != scenefx && ! -s "$nerd_tar" ]]; then
  arctic_log "downloading the Nerd Font symbols $NERD_VERSION"
  curl -fsSL --retry 3 --retry-delay 3 -o "$nerd_tar.part" "$NERD_URL" \
    || arctic_die "couldn't download $NERD_URL"
  echo "$NERD_SHA256  $nerd_tar.part" | sha256sum -c --quiet - \
    || { rm -f "$nerd_tar.part"; arctic_die "$NERD_URL doesn't match the SHA-256 in arctic-linux.spec"; }
  mv "$nerd_tar.part" "$nerd_tar"
fi
# --- end stream 6

# Companion compositor patches live alongside the specs and are applied by %autosetup.
if [[ -d "$SRC/packaging/patches" ]]; then
  cp -a "$SRC/packaging/patches/." "$OUT/sources/"
fi

# ---- 3. Build in the container --------------------------------------------------------
specs=()
[[ "$ONLY" != arctic ]] && specs+=(scenefx)
[[ "$ONLY" != arctic && "$ONLY" != scenefx ]] && specs+=(mangowm)
[[ "$ONLY" != mangowm && "$ONLY" != scenefx ]] && specs+=(arctic-linux)

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args
BUILD_IMAGE_ID="$(arctic_resolve_image "$engine" "$ARCTIC_FEDORA_IMAGE")"
key_args=()
[[ -n "$effective_key" ]] && key_args=(-v "$effective_key:/gpgkey:ro")

# The spec files always come from $SRC/packaging (they are also inside Source0).
inner=$(cat <<'INNER'
printf 'phase\telapsed_seconds\n' > /out/logs/build-timings.tsv
phase_started=$SECONDS
dnf_args=()
if [[ "$BUILD_CACHE_ENABLED" == 1 ]]; then
  mkdir -p /cache/dnf /cache/go-build
  dnf_args=(--setopt=system_cachedir=/cache/dnf --setopt=keepcache=True)
fi
if ! dnf "${dnf_args[@]}" -y install rpm-build rpmdevtools createrepo_c 'dnf5-command(builddep)' cpio binutils > /out/logs/build-tools-install.log 2>&1; then
  tail -n 80 /out/logs/build-tools-install.log
  exit 1
fi
printf 'build_tools_install\t%s\n' "$((SECONDS - phase_started))" >> /out/logs/build-timings.tsv
mkdir -p /root/rpmbuild/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
cp -a /out/sources/. /root/rpmbuild/SOURCES/
define=()
[[ -n "$RELEASE_SUFFIX" ]] && define=(--define "arctic_snapshot $RELEASE_SUFFIX")
# arctic-linux.spec's %check validates the Mango configs when mango is installed: use the
# mangowm built earlier (out/repo) or in this run.
install_mango() {
  local rpm
  rpm="$(ls -t "$1"/mangowm-[0-9]*.x86_64.rpm 2>/dev/null | head -n1 || true)"
  if [[ "${2:-optional}" == required ]]; then
    [[ -n "$rpm" ]] || return 1
    dnf "${dnf_args[@]}" -y install "$rpm" || return 1
    verify_installed_rpm "$rpm" mangowm /usr/bin/mango || return 1
    verify_scenefx || return 1
    # Validate the installed, newly built executable's actual loader resolution.
    rpm -V mangowm || return 1
    readelf -d /usr/bin/mango > /out/logs/mango-dynamic.log || return 1
    grep -Eq '\(NEEDED\).*\[libscenefx-0\.5\.so\]' /out/logs/mango-dynamic.log || return 1
    ldd /usr/bin/mango > /out/logs/mango-linkage.log || return 1
    local resolved
    resolved="$(awk '$1 == "libscenefx-0.5.so" && $2 == "=>" { print $3 }' /out/logs/mango-linkage.log)"
    [[ "$(readlink -e "$resolved")" == /usr/lib64/libscenefx-0.5.so ]]
  elif [[ -n "$rpm" ]]; then
    dnf "${dnf_args[@]}" -y install "$rpm" >/dev/null 2>&1 || echo "note: could not install $rpm for %check"
  fi
}
verify_installed_rpm() {
  local expected installed owner expected_files installed_files
  local identity='%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'
  local files='%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILELINKTOS}\t%{FILEMODES}\n]'
  expected="$(rpm -qp --nosignature --qf "$identity" "$1")" || return 1
  installed="$(rpm -q "$2" --qf "$identity")" || return 1
  [[ "$expected" =~ ^"$2"-[0-9]+:[0-9][A-Za-z0-9.+~^_]*-[A-Za-z0-9._+~^]+[.]x86_64$ \
      && "$installed" == "$expected" ]] || return 1
  if [[ -n "${3:-}" ]]; then
    owner="$(rpm -qf "$3" --qf "$identity")" || return 1
    [[ "$owner" == "$expected" ]] || return 1
  fi
  # Identity alone cannot distinguish different payloads rebuilt at the same EVR.
  # Verify against the local RPM's SHA-256 file/link/mode inventory as well.
  expected_files="$(rpm -qp --nosignature --qf "$files" "$1")" || return 1
  installed_files="$(rpm -q "$2" --qf "$files")" || return 1
  [[ "$expected_files" == $'8\n/'* && "$installed_files" == "$expected_files" ]] || return 1
  rpm -V "$2"
}
verify_scenefx() {
  local owner provider
  local identity='%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'
  owner="$(rpm -qf /usr/lib64/libscenefx-0.5.so --qf "$identity")" || return 1
  provider="$(rpm -q --whatprovides 'scenefx(arctic-software-sync) = 0.5' --qf "$identity")" || return 1
  [[ "$owner" =~ ^scenefx-[0-9]+:0[.]5-[A-Za-z0-9._+~^]+[.]x86_64$ && "$provider" == "$owner" ]] || return 1
  rpm -V scenefx
}
install_scenefx() {
  local rpm devel
  rpm="$(ls -t "$1"/scenefx-[0-9]*.x86_64.rpm 2>/dev/null | head -n1)"
  devel="$(ls -t "$1"/scenefx-devel-[0-9]*.x86_64.rpm 2>/dev/null | head -n1)"
  [[ -n "$rpm" && -n "$devel" ]] || return 1
  dnf "${dnf_args[@]}" -y install "$rpm" "$devel" || return 1
  verify_installed_rpm "$rpm" scenefx /usr/lib64/libscenefx-0.5.so || return 1
  verify_installed_rpm "$devel" scenefx-devel || return 1
  verify_scenefx
}
if [[ " $SPECS " != *" scenefx "* && -n "$(ls /out/repo/scenefx-[0-9]*.x86_64.rpm 2>/dev/null)" ]]; then
  install_scenefx /out/repo
fi
[[ " $SPECS " == *" mangowm "* ]] || install_mango /out/repo
for spec in $SPECS; do
  echo "==> $spec: installing build dependencies"
  phase_started=$SECONDS
  if ! dnf "${dnf_args[@]}" -y builddep "/src/packaging/$spec.spec" > "/out/logs/builddep-$spec.log" 2>&1; then
    tail -n 80 "/out/logs/builddep-$spec.log"
    exit 1
  fi
  printf '%s_builddep\t%s\n' "$spec" "$((SECONDS - phase_started))" >> /out/logs/build-timings.tsv
  if [[ "$BUILD_CACHE_ENABLED" == 1 && "$spec" == arctic-linux ]]; then
    native_key=$(rpm -qa --qf '%{NAME}\t%{NEVRA}\n' | python3 /arctic-build-cache.py \
      --image-id "$BUILD_IMAGE_ID" --manifest /out/logs/go-cache-inputs.json)
    export ARCTIC_GOCACHE="/cache/go-build/$native_key"
    echo "==> Go compiler cache: $native_key (native dependencies and builder verified)"
  fi
  echo "==> $spec: rpmbuild -ba ${define[*]}"
  phase_started=$SECONDS
  if ! rpmbuild -ba "${define[@]}" "/src/packaging/$spec.spec" > "/out/logs/rpmbuild-$spec.log" 2>&1; then
    tail -n 60 "/out/logs/rpmbuild-$spec.log"
    echo "rpmbuild failed for $spec (full log: out/logs/rpmbuild-$spec.log)" >&2
    exit 1
  fi
  printf '%s_rpmbuild\t%s\n' "$spec" "$((SECONDS - phase_started))" >> /out/logs/build-timings.tsv
  grep -E '^(Wrote|warning):' "/out/logs/rpmbuild-$spec.log" | sed 's,^,  ,' || true
  [[ "$spec" != scenefx ]] || install_scenefx /root/rpmbuild/RPMS/x86_64
  [[ "$spec" != mangowm ]] || install_mango /root/rpmbuild/RPMS/x86_64 required
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
# Check the complete package set together: individual builds do not detect two
# packages installing different contents at the same path. An empty RPM database
# avoids Fedora/Arctic release replacement and dependency checks in this file check.
transaction_root="$(mktemp -d)"
rpm --root "$transaction_root" --initdb
rpm --root "$transaction_root" --install --test --nodeps /out/repo/*.rpm
rm -rf "$transaction_root"
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
  echo "commit_time=$COMMIT_TIME"
  echo "git_commit=$GIT_COMMIT"
  echo "git_dirty=$GIT_DIRTY"
  echo "specs=$SPECS"
  echo "gpg_key=$fpr"
  echo "arctic_repos=$repos"
  echo "builder_image_id=$BUILD_IMAGE_ID"
  echo "build_cache_enabled=$BUILD_CACHE_ENABLED"
  echo "go_cache_key=${native_key:-}"
  find /root/rpmbuild/RPMS -name '*.rpm' ! -name '*-debuginfo-*' ! -name '*-debugsource-*' -print0 |
    xargs -0 -r rpm -qp --nosignature --qf 'rpm=%{NEVRA}\n' | sort
  rpm -qp --nosignature --qf 'srpm=%{NAME}-%{EVR}.src\n' /root/rpmbuild/SRPMS/*.src.rpm | sort
} > /out/BUILD-INFO
chown -R "$HOST_UID:$HOST_GID" /out/repo /out/srpms /out/logs /out/sources /out/debug /out/BUILD-INFO
if [[ "$BUILD_CACHE_ENABLED" == 1 ]]; then chown -R "$HOST_UID:$HOST_GID" /cache/dnf /cache/go-build; fi
echo "==> packages in out/repo:"
ls -1 /out/repo/*.rpm | sed 's,.*/,  ,'
if [[ "$repos" == disabled ]]; then
  echo "==> WARNING: arctic-release has no repository key: the Arctic repositories are disabled in it" >&2
fi
INNER
)

arctic_log "building ${specs[*]} in $ARCTIC_FEDORA_IMAGE ($engine)"
"$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${key_args[@]}" "${cache_args[@]}" \
  -e BUILD_CACHE_ENABLED="$CACHE_ENABLED" -e BUILD_IMAGE_ID="$BUILD_IMAGE_ID" \
  -e SPECS="${specs[*]}" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -e RELEASE_SUFFIX="$SUFFIX" -e VERSION="$VERSION" -e BUILD_TIME="$BUILD_TIME" -e COMMIT_TIME="$COMMIT_TIME" \
  -e GIT_COMMIT="$GIT_COMMIT" -e GIT_DIRTY="$GIT_DIRTY" \
  -v "$HERE/build-cache.py:/arctic-build-cache.py:ro" \
  -v "$SRC:/src:ro" -v "$OUT:/out" \
  "$BUILD_IMAGE_ID" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner"

arctic_log "done: $OUT/repo (build info: $OUT/BUILD-INFO)"
