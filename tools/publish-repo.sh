#!/usr/bin/env bash
# Publish built RPMs into the Arctic package repository site (GitHub Pages), one channel.
#
#   tools/publish-repo.sh --site DIR --channel stable|testing [options]
#
#   --site DIR         the site tree, updated in place: the published site as it is now
#                      (tools/lib/arcticrepo.py fetch puts it there) or an empty directory
#   --channel NAME     stable | testing
#   --rpms DIR         binary RPMs to add (default out/repo; debuginfo is never published)
#   --srpms DIR        source RPMs to add (default out/srpms); "none" publishes no sources
#   --keep N           builds to keep per package name in each directory (default 3)
#   --no-sign          no signing and no key needed: for testing the layout, the metadata and
#                      the pruning locally. Packages stay unsigned, repomd.xml.asc is removed,
#                      so dnf needs gpgcheck=0 repo_gpgcheck=0 for such a repository
#   --resign-old       re-sign already published packages that don't verify with the current
#                      key (after a key change) instead of failing
#   --src DIR          the source tree the RPMs were built from (default: this checkout): its
#                      packaging/release/{arctic,arctic-testing}.repo, RPM-GPG-KEY-arctic and
#                      the Fedora release (dist_version in packaging/arctic-linux.spec)
#   --base-url URL     the site's URL (default https://yuvalkolodkingal.github.io/O-Tism)
#   --build-info FILE  BUILD-INFO of the build (default: next to --rpms)
#   --budget-mb N      fail when the whole site is larger than N MB (default 900; Pages
#                      sites may be up to 1 GB)
#   --summary FILE     also write a Markdown summary there (the workflow's step summary)
#
# Signing (the default) reads the key from the environment, as .github/workflows/repo.yml
# sets it from the repository secrets:
#   ARCTIC_GPG_PRIVATE_KEY  the armored secret key
#   ARCTIC_GPG_PASSPHRASE   its passphrase (may be empty)
#   ARCTIC_GPG_PUBLIC_KEY   the armored public key: must have the secret key's fingerprint,
#                           as must packaging/release/RPM-GPG-KEY-arctic when it is committed
# Every new RPM and SRPM is signed (rpmsign --addsign) and checked (rpmkeys -K against a
# keyring holding only that public key); so is every package already in the channel. A new
# arctic-release must carry the same key and enable the repository: one without them would
# switch updates off for everyone who installs it.
#
# Layout (both channels side by side; publishing one never touches the other's files):
#   repo/<channel>/fedora-<releasever>/x86_64/   x86_64 + noarch RPMs, repodata/ + repomd.xml.asc
#   repo/<channel>/fedora-<releasever>/source/   SRPMs, repodata/ + repomd.xml.asc
#   repo/<channel>/fedora-<releasever>/PUBLISH-INFO.json
#   RPM-GPG-KEY-arctic, arctic.repo, arctic-testing.repo, index.html, manifest.json
#
# Runs itself in a Fedora 44 container (tools/lib/container.sh) unless rpmsign, createrepo_c,
# gpg, cpio and python3-rpm are all here already.
set -euo pipefail
umask 022

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"
ROOT="$(arctic_repo_root)"

SITE=""; CHANNEL=""; RPMS="$ROOT/out/repo"; SRPMS="$ROOT/out/srpms"; KEEP=3; SIGN=1; RESIGN_OLD=0
SRC="$ROOT"; BASE_URL="https://yuvalkolodkingal.github.io/O-Tism"; BUILD_INFO=""; BUDGET_MB=900
SUMMARY=""; RELEASEVER=""
UPSTREAM_URL="https://yuvalkolodkingal.github.io/O-Tism"

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }
while (( $# )); do
  case "$1" in
    --site) SITE="$2"; shift 2 ;;
    --channel) CHANNEL="$2"; shift 2 ;;
    --rpms) RPMS="$2"; shift 2 ;;
    --srpms) SRPMS="$2"; shift 2 ;;
    --keep) KEEP="$2"; shift 2 ;;
    --no-sign) SIGN=0; shift ;;
    --resign-old) RESIGN_OLD=1; shift ;;
    --src) SRC="$2"; shift 2 ;;
    --base-url) BASE_URL="${2%/}"; shift 2 ;;
    --build-info) BUILD_INFO="$2"; shift 2 ;;
    --budget-mb) BUDGET_MB="$2"; shift 2 ;;
    --summary) SUMMARY="$2"; shift 2 ;;
    --releasever) RELEASEVER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$CHANNEL" in stable|testing) ;; *) arctic_die "--channel takes stable or testing" ;; esac
[[ -n "$SITE" ]] || arctic_die "--site DIR is required"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || arctic_die "--keep takes a number ≥ 1"
[[ "$BUDGET_MB" =~ ^[1-9][0-9]*$ ]] || arctic_die "--budget-mb takes a number"
[[ -d "$RPMS" ]] || arctic_die "no RPM directory $RPMS (run tools/build-rpms.sh first)"
[[ "$SRPMS" == none || -d "$SRPMS" ]] || arctic_die "no SRPM directory $SRPMS (or pass --srpms none)"
[[ -f "$SRC/packaging/arctic-linux.spec" ]] || arctic_die "--src $SRC is not an Arctic Linux source tree"
mkdir -p "$SITE"
SITE="$(cd "$SITE" && pwd)"; RPMS="$(cd "$RPMS" && pwd)"; SRC="$(cd "$SRC" && pwd)"
[[ "$SRPMS" == none ]] || SRPMS="$(cd "$SRPMS" && pwd)"
[[ -n "$BUILD_INFO" ]] || BUILD_INFO="$(dirname "$RPMS")/BUILD-INFO"
[[ -f "$BUILD_INFO" ]] && BUILD_INFO="$(cd "$(dirname "$BUILD_INFO")" && pwd)/$(basename "$BUILD_INFO")"

# ---- In a Fedora container, unless the tools are here ---------------------------------------
have_tools() {
  local t
  for t in rpm rpmsign rpmkeys rpm2cpio cpio createrepo_c gpg python3; do
    command -v "$t" >/dev/null 2>&1 || return 1
  done
  python3 -c 'import rpm' 2>/dev/null
}
if [[ "${ARCTIC_PUBLISH_IN_CONTAINER:-}" != 1 ]] && ! have_tools; then
  arctic_ensure_engine
  engine="$(arctic_engine)"
  arctic_container_args
  out="$(mktemp -d)"
  trap 'rm -rf "$out"' EXIT
  mounts=(-v "$ROOT:/w/tools:ro" -v "$SITE:/w/site" -v "$RPMS:/w/rpms:ro" -v "$SRC:/w/src:ro" -v "$out:/w/out")
  args=(--site /w/site --channel "$CHANNEL" --rpms /w/rpms --src /w/src --keep "$KEEP"
        --base-url "$BASE_URL" --budget-mb "$BUDGET_MB" --summary /w/out/summary.md)
  if [[ "$SRPMS" == none ]]; then args+=(--srpms none); else mounts+=(-v "$SRPMS:/w/srpms:ro"); args+=(--srpms /w/srpms); fi
  if [[ -f "$BUILD_INFO" ]]; then mounts+=(-v "$BUILD_INFO:/w/BUILD-INFO:ro"); args+=(--build-info /w/BUILD-INFO); fi
  (( SIGN )) || args+=(--no-sign)
  (( RESIGN_OLD )) && args+=(--resign-old)
  [[ -n "$RELEASEVER" ]] && args+=(--releasever "$RELEASEVER")
  # Secrets are passed by name: docker copies them from this environment (not the command line).
  envs=(-e ARCTIC_PUBLISH_IN_CONTAINER=1 -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)"
        -e ARCTIC_GPG_PRIVATE_KEY -e ARCTIC_GPG_PASSPHRASE -e ARCTIC_GPG_PUBLIC_KEY
        -e ARCTIC_SOURCE_REF -e GITHUB_RUN_ID -e GITHUB_REPOSITORY -e GITHUB_SERVER_URL -e GITHUB_REF_NAME)
  # shellcheck disable=SC2016 # expanded in the container
  inner='dnf -y install rpm-sign createrepo_c gnupg2 cpio python3-rpm >/dev/null 2>&1 ||
           dnf -y install rpm-sign createrepo_c gnupg2 cpio python3-rpm
         rc=0; bash /w/tools/tools/publish-repo.sh "$@" || rc=$?
         chown -R "$HOST_UID:$HOST_GID" /w/site /w/out 2>/dev/null || :
         exit $rc'
  arctic_log "publishing in $ARCTIC_FEDORA_IMAGE ($engine)"
  rc=0
  "$engine" run --rm "${ARCTIC_CONTAINER_ARGS[@]}" "${envs[@]}" "${mounts[@]}" \
    "$ARCTIC_FEDORA_IMAGE" bash -c "$ARCTIC_CONTAINER_PROLOGUE$inner" publish "${args[@]}" || rc=$?
  if [[ -n "$SUMMARY" && -f "$out/summary.md" ]]; then cat "$out/summary.md" >> "$SUMMARY"; fi
  exit "$rc"
fi

# ---- From here on: in Fedora ----------------------------------------------------------------
AR=(python3 "$HERE/lib/arcticrepo.py")
[[ -n "$RELEASEVER" ]] || RELEASEVER="$(sed -n 's/^%global[[:space:]]\+dist_version[[:space:]]\+//p' "$SRC/packaging/arctic-linux.spec" | head -n1)"
[[ "$RELEASEVER" =~ ^[0-9]+$ ]] || arctic_die "can't tell the Fedora release (dist_version in packaging/arctic-linux.spec)"
CHAN="$SITE/repo/$CHANNEL/fedora-$RELEASEVER"
BIN="$CHAN/x86_64"
SRCDIR="$CHAN/source"
COMMITTED_KEY="$SRC/packaging/release/RPM-GPG-KEY-arctic"

work="$(mktemp -d)"
export GNUPGHOME="$work/gnupg"
mkdir -m 700 "$GNUPGHOME"
cleanup() {
  gpgconf --kill all >/dev/null 2>&1 || :
  [[ -f "$GNUPGHOME/passphrase" ]] && shred -u "$GNUPGHOME/passphrase" 2>/dev/null || :
  rm -rf "$work"
}
trap cleanup EXIT
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }

# Primary fingerprints of the keys in an armored public key file (one per line); refuses
# anything that holds secret key material.
key_fprs() {
  if grep -q 'PRIVATE KEY' "$1" ||
     gpg --batch --with-colons --import-options show-only --import < "$1" 2>/dev/null | grep -q '^sec'; then
    arctic_die "$2 holds SECRET key material: it must never be published"
  fi
  gpg --batch --with-colons --import-options show-only --import < "$1" 2>/dev/null |
    awk -F: '$1 == "pub" { want = 1; next } $1 == "fpr" && want { print $10; want = 0 }'
}

# ---- 1. The key ----------------------------------------------------------------------------
FPR=""; PUBKEY=""
if (( SIGN )); then
  [[ -n "${ARCTIC_GPG_PRIVATE_KEY:-}" ]] || arctic_die "ARCTIC_GPG_PRIVATE_KEY is not set (or pass --no-sign for a local test)"
  [[ -n "${ARCTIC_GPG_PUBLIC_KEY:-}" ]] || arctic_die "ARCTIC_GPG_PUBLIC_KEY is not set"
  PASSFILE="$GNUPGHOME/passphrase"
  ( umask 077; printf '%s' "${ARCTIC_GPG_PASSPHRASE:-}" > "$PASSFILE" )
  printf '%s\n' "$ARCTIC_GPG_PRIVATE_KEY" |
    gpg --batch --pinentry-mode loopback --passphrase-file "$PASSFILE" --import >"$work/import.log" 2>&1 ||
    { sed 's/^/  /' "$work/import.log" >&2; arctic_die "could not import ARCTIC_GPG_PRIVATE_KEY"; }
  unset ARCTIC_GPG_PRIVATE_KEY
  mapfile -t secret < <(gpg --batch --with-colons --list-secret-keys |
    awk -F: '$1 == "sec" { want = 1; next } $1 == "fpr" && want { print $10; want = 0 }')
  (( ${#secret[@]} == 1 )) || arctic_die "ARCTIC_GPG_PRIVATE_KEY must hold exactly one secret key (found ${#secret[@]})"
  FPR="${secret[0]}"
  caps="$(gpg --batch --with-colons --list-secret-keys "$FPR" | awk -F: '$1 == "sec" { print $12; exit }')"
  [[ "$caps" == *S* ]] || arctic_die "the key $FPR can't sign (capabilities: $caps)"
  arctic_log "signing key: $FPR"

  printf '%s\n' "$ARCTIC_GPG_PUBLIC_KEY" > "$work/public.asc"
  got="$(key_fprs "$work/public.asc" ARCTIC_GPG_PUBLIC_KEY)"
  [[ "$got" == "$FPR" ]] || arctic_die "ARCTIC_GPG_PUBLIC_KEY is key ${got:-<none>}, but the signing key is $FPR"
  PUBKEY="$work/public.asc"
  if [[ -f "$COMMITTED_KEY" ]]; then
    got="$(key_fprs "$COMMITTED_KEY" packaging/release/RPM-GPG-KEY-arctic)"
    [[ "$got" == "$FPR" ]] ||
      arctic_die "the committed packaging/release/RPM-GPG-KEY-arctic is key ${got:-<none>}, but the signing key is $FPR: fix one of them"
    PUBKEY="$COMMITTED_KEY"
    arctic_log "the committed packaging/release/RPM-GPG-KEY-arctic matches the signing key"
  fi
  SIGN_ARGS=(--define "_openpgp_sign gpg" --define "_openpgp_sign_id $FPR" --define "_gpg_name $FPR"
             --define "_gpg_path $GNUPGHOME" --define "_gpg_digest_algo sha256"
             --define "_gpg_sign_cmd_extra_args --batch --yes --pinentry-mode loopback --passphrase-file $PASSFILE")
  # A keyring with nothing but the public key, to check every signature against.
  VDB="$work/rpmdb"; mkdir -p "$VDB"
  rpmkeys --dbpath "$VDB" --import "$PUBKEY"
  VGPG="$work/verify-gnupg"; mkdir -m 700 "$VGPG"
  gpg --homedir "$VGPG" --batch --quiet --import "$PUBKEY" 2>/dev/null
else
  warn "--no-sign: packages and metadata stay UNSIGNED (local test only)"
  for k in "$COMMITTED_KEY" "${ARCTIC_GPG_PUBLIC_KEY:+env}"; do
    [[ -n "$k" ]] || continue
    if [[ "$k" == env ]]; then printf '%s\n' "$ARCTIC_GPG_PUBLIC_KEY" > "$work/public.asc"; k="$work/public.asc"; fi
    [[ -f "$k" ]] || continue
    FPR="$(key_fprs "$k" "$k" | head -n1)"; PUBKEY="$k"; break
  done
fi

sign_pkgs() { (( $# )) || return 0; rpmsign "${SIGN_ARGS[@]}" --addsign "$@" >/dev/null; }
resign_pkgs() { (( $# )) || return 0; rpmsign "${SIGN_ARGS[@]}" --resign "$@" >/dev/null; }
# Signed by the key (and only verifiable with it: the keyring holds nothing else).
verify_pkg() {
  local out
  out="$(rpmkeys --dbpath "$VDB" -Kv "$1" 2>&1)" || return 1
  grep -q 'signature.*: OK$' <<<"$out" && ! grep -Eq 'NOT OK|NOKEY|NOTTRUSTED|NOTFOUND' <<<"$out"
}
hdr_digest() { rpm -qp --nosignature --nodigest --qf '%{SHA256HEADER}' "$1" 2>/dev/null; }
in_section_enabled() { # in_section_enabled FILE SECTION: "enabled=1" in [SECTION]
  awk -v s="[$2]" '/^\[/ { cur = $0 } cur == s && $0 == "enabled=1" { f = 1 } END { exit !f }' "$1"
}

# ---- 2. What's new ---------------------------------------------------------------------------
mkdir -p "$work/new/x86_64" "$work/new/source"
stage() { # stage FILE KIND
  local f="$1" kind="$2" b dest
  b="$(basename "$f")"
  dest="$CHAN/$kind/$b"
  if [[ -e "$dest" ]]; then
    if [[ "$(hdr_digest "$dest")" == "$(hdr_digest "$f")" ]]; then
      arctic_log "already published: $b"; return 0
    fi
    warn "replacing $b: a different build with the same name"
  fi
  cp -p "$f" "$work/new/$kind/$b"
}
for f in "$RPMS"/*.rpm; do
  [[ -e "$f" ]] || continue
  case "${f##*/}" in *.src.rpm|*-debuginfo-*|*-debugsource-*) continue ;; esac
  arch="$(rpm -qp --nosignature --qf '%{ARCH}' "$f")"
  case "$arch" in x86_64|noarch) ;; *) arctic_die "${f##*/}: arch $arch has no place in the repository (x86_64, noarch)" ;; esac
  stage "$f" x86_64
done
if [[ "$SRPMS" != none ]]; then
  for f in "$SRPMS"/*.src.rpm; do [[ -e "$f" ]] && stage "$f" source; done
fi
mapfile -t new_bin < <(find "$work/new/x86_64" -name '*.rpm' | sort)
mapfile -t new_src < <(find "$work/new/source" -name '*.rpm' | sort)
arctic_log "$CHANNEL: ${#new_bin[@]} new packages, ${#new_src[@]} new source packages"

# ---- 3. Sign and check the new packages ----------------------------------------------------
if (( SIGN )); then
  sign_pkgs "${new_bin[@]}" "${new_src[@]}"
  for f in "${new_bin[@]}" "${new_src[@]}"; do
    verify_pkg "$f" || { rpmkeys --dbpath "$VDB" -Kv "$f" >&2 || :; arctic_die "${f##*/}: not signed by $FPR after rpmsign"; }
  done
fi
for f in "${new_bin[@]}"; do
  [[ "${f##*/}" == arctic-release-[0-9]* ]] || continue
  x="$work/release-check"; rm -rf "$x"; mkdir -p "$x"
  (cd "$x" && rpm2cpio "$f" | cpio -idm --quiet 2>/dev/null)
  k="$x/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic"; r="$x/usr/share/dnf5/repos.d/arctic.repo"
  problem=""
  if [[ ! -f "$k" ]]; then
    problem="it has no /etc/pki/rpm-gpg/RPM-GPG-KEY-arctic (built without ARCTIC_GPG_PUBLIC_KEY?)"
  elif [[ -n "$FPR" && "$(key_fprs "$k" "${f##*/}")" != "$FPR" ]]; then
    problem="its RPM-GPG-KEY-arctic is not the signing key $FPR"
  elif ! in_section_enabled "$r" arctic; then
    problem="its arctic.repo doesn't enable [arctic]"
  fi
  if [[ -n "$problem" ]]; then
    if (( SIGN )); then
      arctic_die "${f##*/}: $problem. Publishing it would switch updates off for every system that installs it."
    fi
    warn "${f##*/}: $problem"
  fi
done

# ---- 4. Into the site, prune, check what stays ---------------------------------------------
mkdir -p "$BIN"
for f in "${new_bin[@]}"; do mv -f "$f" "$BIN/"; done
if (( ${#new_src[@]} )) || [[ -d "$SRCDIR" ]]; then
  mkdir -p "$SRCDIR"
  for f in "${new_src[@]}"; do mv -f "$f" "$SRCDIR/"; done
fi
dirs=("$BIN"); [[ -d "$SRCDIR" ]] && dirs+=("$SRCDIR")
for d in "${dirs[@]}"; do "${AR[@]}" prune --dir "$d" --keep "$KEEP"; done

if (( SIGN )); then
  bad=()
  while IFS= read -r -d '' f; do verify_pkg "$f" || bad+=("$f"); done < <(find "${dirs[@]}" -maxdepth 1 -name '*.rpm' -print0)
  if (( ${#bad[@]} )); then
    if (( RESIGN_OLD )); then
      warn "re-signing ${#bad[@]} published packages with $FPR (--resign-old)"
      resign_pkgs "${bad[@]}"
      for f in "${bad[@]}"; do verify_pkg "$f" || arctic_die "${f##*/}: still not verifiable after re-signing"; done
    else
      printf '  %s\n' "${bad[@]##*/}" >&2
      arctic_die "${#bad[@]} published packages don't verify with $FPR (a key change? rerun with --resign-old)"
    fi
  fi
fi

# ---- 5. Metadata ---------------------------------------------------------------------------
# The metadata a new repomd.xml replaces stays for 2 days (by mtime; the site's files keep theirs
# through the Pages artifact): GitHub Pages lets caches serve a page for up to 10 minutes, and a
# client that gets the old repomd.xml then still finds the files it names.
for d in "${dirs[@]}"; do
  createrepo_c --update --retain-old-md-by-age=2d --quiet "$d"
  rm -f "$d/repodata/repomd.xml.asc"
  if (( SIGN )); then
    gpg --batch --yes --pinentry-mode loopback --passphrase-file "$PASSFILE" --local-user "$FPR" \
        --digest-algo sha256 --armor --detach-sign --output "$d/repodata/repomd.xml.asc" "$d/repodata/repomd.xml"
    gpg --homedir "$VGPG" --batch --quiet --verify "$d/repodata/repomd.xml.asc" "$d/repodata/repomd.xml" 2>/dev/null ||
      arctic_die "$d/repodata/repomd.xml.asc does not verify"
  fi
done

# ---- 6. The site's own files -----------------------------------------------------------------
if [[ -n "$PUBKEY" ]]; then cp "$PUBKEY" "$SITE/RPM-GPG-KEY-arctic"; chmod 0644 "$SITE/RPM-GPG-KEY-arctic"; fi
for f in arctic.repo arctic-testing.repo; do
  {
    echo "# Arctic Linux package repository for Fedora $RELEASEVER, $BASE_URL/"
    echo "# Arctic Linux has it built in (arctic-release). Elsewhere:"
    echo "#   sudo dnf config-manager addrepo --from-repofile=$BASE_URL/$f"
    grep -v '^#' "$SRC/packaging/release/$f" |
      sed -e "s|$UPSTREAM_URL|$BASE_URL|g" \
          -e "s|^gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-arctic\$|gpgkey=$BASE_URL/RPM-GPG-KEY-arctic|" \
          -e '/^\[arctic\]$/,/^\[/ s/^enabled=0$/enabled=1/' \
          -e '/^\[arctic-testing\]$/,/^\[/ s/^enabled=0$/enabled=1/'
  } > "$SITE/$f"
done
"${AR[@]}" channel-info --site "$SITE" --channel "$CHANNEL" --releasever "$RELEASEVER" --build-info "$BUILD_INFO"
"${AR[@]}" index --site "$SITE" --base-url "$BASE_URL" ${FPR:+--fingerprint "$FPR"}
"${AR[@]}" manifest --site "$SITE"

# ---- 7. Size budget, summary -------------------------------------------------------------------
bytes="$(du -sb "$SITE" | cut -f1)"
mb=$(( (bytes + 1048575) / 1048576 ))
arctic_log "site size: $mb MB ($bytes bytes; budget $BUDGET_MB MB)"
summary() {
  echo "### Arctic repository: $CHANNEL"
  echo
  echo "- Site: $BASE_URL/ ($mb MB of the $BUDGET_MB MB budget)"
  echo "- Packages: $BASE_URL/repo/$CHANNEL/fedora-$RELEASEVER/x86_64/"
  echo "- Signed: $( (( SIGN )) && echo "yes, key \`$FPR\`" || echo "**no** (--no-sign)")"
  echo "- New: ${#new_bin[@]} packages, ${#new_src[@]} source packages; keeping $KEEP builds per package"
  echo
  echo '```'
  find "${dirs[@]}" -maxdepth 1 -name '*.rpm' -printf '%f\n' | sort
  echo '```'
}
if [[ -n "$SUMMARY" ]]; then summary >> "$SUMMARY"; fi
if (( mb > BUDGET_MB )); then
  arctic_die "the site is $mb MB, over the $BUDGET_MB MB budget (GitHub Pages sites are limited to 1 GB): lower --keep"
fi
arctic_log "published $CHANNEL into $SITE"
