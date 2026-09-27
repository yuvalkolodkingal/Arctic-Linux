#!/usr/bin/env bash
# Check the Arctic package repository end to end with dnf5, in Fedora 44 containers:
#
#   1. arctic-release (from --rpms) replaces fedora-release (dnf --allowerasing, offline) and
#      dnf5 knows the Arctic repositories (repolist --all); an override from
#      `dnf5 config-manager setopt` turns the testing channel on and off.
#   2. With no network at all (--network none), as on the live USB and in the installer,
#      `dnf5 makecache` still succeeds: the unreachable Arctic repository is skipped
#      (skip_if_unavailable=True), and would fail the command without that setting.
#   3. Unsigned (the default): the repository tools/publish-repo.sh --no-sign made (--site),
#      served over HTTP from this machine, answers `dnf5 repoquery --repo arctic` /
#      `--repo arctic-testing` with the packages it holds, and a package downloads from it.
#      gpgcheck and repo_gpgcheck are turned off for this unsigned test repository only.
#   3. --signed: the signed site, as clients use it (file://, no network), with nothing but
#      the key arctic-release installed and every check on (gpgcheck=1, repo_gpgcheck=1,
#      skip_if_unavailable=0): `dnf5 -y makecache` verifies repodata/repomd.xml.asc (librepo,
#      rpm-sequoia), repoquery lists exactly the channel's packages, and dnf5 installs
#      arctic-backgrounds and reinstalls arctic-release from it, checking their signatures
#      (the rpmdb holds no other key). Any error fails. .github/workflows/repo.yml runs this
#      on the site it is about to deploy.
#
#   tools/test-repo.sh [--rpms DIR] [--site DIR] [--signed] [--channel NAME] [--src DIR]
#     --rpms DIR      the built packages (default out/repo): arctic-release comes from here
#     --site DIR      a site from tools/publish-repo.sh (default out/site); without --signed,
#                     step 3 is skipped when it doesn't exist
#     --signed        step 3 against the signed site (needs arctic-release built with the key)
#     --channel NAME  stable | testing: check only that channel (default: every channel in the
#                     site). --signed then also requires --rpms' arctic-release in it
#     --src DIR       the source tree the packages were built from, for the Fedora release
#                     (dist_version in packaging/arctic-linux.spec; default this checkout)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/lib/container.sh
source "$HERE/lib/container.sh"
ROOT="$(arctic_repo_root)"
RPMS="$ROOT/out/repo"
SITE="$ROOT/out/site"
SIGNED=0
ONLY_CHANNEL=""
SRC="$ROOT"

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }
while (( $# )); do
  case "$1" in
    --rpms) RPMS="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --signed) SIGNED=1; shift ;;
    --channel) ONLY_CHANNEL="$2"; shift 2 ;;
    --src) SRC="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) arctic_die "unknown option: $1" ;;
  esac
done
case "$ONLY_CHANNEL" in ""|stable|testing) ;; *) arctic_die "--channel takes stable or testing" ;; esac
RPMS="$(cd "$RPMS" && pwd)"
ls "$RPMS"/arctic-release-[0-9]*.noarch.rpm >/dev/null 2>&1 || arctic_die "no arctic-release package in $RPMS"
releasever="$(sed -n 's/^%global[[:space:]]\+dist_version[[:space:]]\+//p' "$SRC/packaging/arctic-linux.spec" | head -n1)"
[[ "$releasever" =~ ^[0-9]+$ ]] || arctic_die "can't tell the Fedora release (dist_version in $SRC/packaging/arctic-linux.spec)"
if (( SIGNED )); then
  [[ -d "$SITE/repo" ]] || arctic_die "--signed: no site at $SITE"
fi

arctic_ensure_engine
engine="$(arctic_engine)"
arctic_container_args

# Shared by both containers: put arctic-release in place of fedora-release, offline.
# shellcheck disable=SC2016 # expanded in the container
install_release='
set -euo pipefail
rel="$(ls -t /rpms/arctic-release-[0-9]*.noarch.rpm | head -n1)"
echo "==> installing ${rel##*/} in place of fedora-release (no repositories)"
dnf5 -y -q install --allowerasing --disablerepo="*" "$rel"
rpm -q arctic-release
if rpm -q fedora-release-common >/dev/null 2>&1; then echo "FAIL: fedora-release-common is still installed" >&2; exit 1; fi
. /etc/os-release; echo "os-release: $PRETTY_NAME"
[ "$ID" = arctic ] || { echo "FAIL: os-release ID=$ID" >&2; exit 1; }
'

# ---- 1 + 2: offline ------------------------------------------------------------------------
# shellcheck disable=SC2016 # expanded in the container
offline='
echo "==> dnf5 repolist --all"
dnf5 repolist --all
for id in arctic arctic-source arctic-testing arctic-testing-source; do
  dnf5 repolist --all | grep -q "^$id " || { echo "FAIL: dnf5 does not know [$id]" >&2; exit 1; }
done
if [ -f /etc/pki/rpm-gpg/RPM-GPG-KEY-arctic ]; then
  dnf5 repolist --enabled | grep -q "^arctic " || { echo "FAIL: [arctic] is not enabled" >&2; exit 1; }
  echo "arctic-release has the key: [arctic] is enabled"
else
  if dnf5 repolist --enabled | grep -q "^arctic "; then echo "FAIL: [arctic] enabled without a key" >&2; exit 1; fi
  echo "arctic-release was built without the key: the Arctic repositories are disabled"
fi
if dnf5 repolist --enabled | grep -q "^arctic-testing "; then echo "FAIL: [arctic-testing] is on by default" >&2; exit 1; fi

echo "==> overrides: dnf5 config-manager setopt arctic-testing.enabled=1, then =0"
dnf5 config-manager setopt arctic-testing.enabled=1
dnf5 repolist --enabled | grep -q "^arctic-testing " || { echo "FAIL: the override did not enable [arctic-testing]" >&2; exit 1; }
cat /etc/dnf/repos.override.d/99-config_manager.repo
dnf5 config-manager setopt arctic-testing.enabled=0
if dnf5 repolist --enabled | grep -q "^arctic-testing "; then echo "FAIL: [arctic-testing] still enabled" >&2; exit 1; fi

# (Fedora'"'"'s own fedora and updates repositories set skip_if_unavailable=False, so they fail
# offline whatever Arctic does: only the Arctic repositories are loaded here.)
arctic_repos=(--repo arctic --repo arctic-testing --setopt=arctic.enabled=1 --setopt=arctic-testing.enabled=1)
echo "==> offline: dnf5 makecache --repo arctic --repo arctic-testing (skip_if_unavailable)"
dnf5 makecache --refresh "${arctic_repos[@]}" 2>&1 | tail -n 3
echo "==> offline: dnf5 repoquery in the same way (a command that needs the metadata)"
dnf5 repoquery --refresh "${arctic_repos[@]}" arctic-release 2>&1 | tail -n 3
echo "==> offline, skip_if_unavailable=False for comparison (must fail)"
if dnf5 makecache --refresh --repo arctic --setopt=arctic.enabled=1 --setopt=arctic.skip_if_unavailable=0 >/dev/null 2>&1; then
  echo "FAIL: an unreachable [arctic] did not fail with skip_if_unavailable=0: the check above proves nothing" >&2; exit 1
fi
echo "OK: offline, the unreachable Arctic repositories are skipped and dnf keeps working"
'
arctic_log "offline checks (--network none)"
"$engine" run --rm --network none -v "$RPMS:/rpms:ro" "$ARCTIC_FEDORA_IMAGE" \
  bash -c "$install_release$offline"

# ---- 3: a published repository -------------------------------------------------------------
if [[ ! -d "$SITE/repo" ]]; then
  arctic_log "no site at $SITE (tools/publish-repo.sh --no-sign --site $SITE ...): skipping the repoquery check"
  exit 0
fi
SITE="$(cd "$SITE" && pwd)"

# Shared: repoquery lists exactly the channel's files ($opts, $dir, $id, $ch set by the caller).
# shellcheck disable=SC2016 # expanded in the container
compare='
compare() {
  dnf5 repoquery "${opts[@]}" --qf "%{name}-%{evr}.%{arch}\n" | sort > /tmp/got
  cat /tmp/got
  (cd "$dir" && ls -1 -- *.rpm) | sed "s/\.rpm$//" | sort > /tmp/want
  if [ "$(cat /tmp/want)" != "$(cat /tmp/got)" ]; then
    echo "FAIL: repoquery --repo $id does not list the $ch packages; expected:" >&2; cat /tmp/want >&2; exit 1
  fi
}
channels() { # the channels to check: stable:arctic testing:arctic-testing, or ONLY_CHANNEL
  for pair in stable:arctic testing:arctic-testing; do
    if [ -z "$ONLY_CHANNEL" ] || [ "$ONLY_CHANNEL" = "${pair%%:*}" ]; then echo "$pair"; fi
  done
}
'

if (( SIGNED )); then
  # shellcheck disable=SC2016 # expanded in the container
  signed='
key=/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic
[ -s "$key" ] || { echo "FAIL: ${rel##*/} has no $key: built without the repository key" >&2; exit 1; }
fpr="$(gpg --batch --with-colons --import-options show-only --import "$key" 2>/dev/null | awk -F: '"'"'$1 == "fpr" { print $10; exit }'"'"')"
echo "arctic-release trusts key ${fpr:-?}"
if rpm -q gpg-pubkey >/dev/null 2>&1; then echo "note: the image'"'"'s rpmdb already holds keys: $(rpm -q gpg-pubkey | tr "\n" " ")"; fi
installed="$(rpm -q --qf "%{name}-%{evr}.%{arch}" arctic-release)"
checked=0
for pair in $(channels); do
  ch="${pair%%:*}"; id="${pair#*:}"
  base="/site/repo/$ch/fedora-$RELEASEVER"
  dir="$base/x86_64"
  if [ ! -d "$dir" ]; then
    if [ -n "$ONLY_CHANNEL" ]; then echo "FAIL: the site has no $ch channel ($dir)" >&2; exit 1; fi
    echo "(no $ch channel in the site)"; continue
  fi
  # As a client has it, with every check on and nothing skipped.
  opts=(--repo "$id" --setopt="$id.enabled=1" --setopt="$id.baseurl=file://$dir/"
        --setopt="$id.gpgcheck=1" --setopt="$id.repo_gpgcheck=1" --setopt="$id.skip_if_unavailable=0")
  echo "==> dnf5 -y makecache --repo $id: repomd.xml.asc checked with the key from arctic-release"
  dnf5 -y makecache --refresh "${opts[@]}"
  if [ -d "$base/source" ]; then
    echo "==> dnf5 -y makecache --repo $id-source"
    dnf5 -y makecache --refresh --repo "$id-source" --setopt="$id-source.enabled=1" \
      --setopt="$id-source.baseurl=file://$base/source/" --setopt="$id-source.gpgcheck=1" \
      --setopt="$id-source.repo_gpgcheck=1" --setopt="$id-source.skip_if_unavailable=0"
  fi
  echo "==> dnf5 repoquery --repo $id (the $ch channel)"
  compare
  echo "==> dnf5 -y install --repo $id arctic-backgrounds: its signature checked by dnf5"
  dnf5 -y install "${opts[@]}" arctic-backgrounds
  rpm -q arctic-backgrounds
  rpm -e --nodeps arctic-backgrounds
  if grep -qx "$installed" /tmp/got; then
    echo "==> dnf5 -y reinstall --repo $id $installed (the arctic-release just built)"
    dnf5 -y reinstall "${opts[@]}" arctic-release
  elif [ -n "$ONLY_CHANNEL" ]; then
    echo "FAIL: $installed (from --rpms) is not in the $ch channel" >&2; exit 1
  else
    echo "($installed is not in the $ch channel: not reinstalled from it)"
  fi
  checked=$((checked + 1))
done
[ "$checked" -gt 0 ] || { echo "FAIL: the site has no channel" >&2; exit 1; }
echo "keys in the rpmdb (dnf5 imported the Arctic one):"; rpm -q gpg-pubkey --qf "  %{version}-%{release} %{summary}\n"
echo "OK: dnf5 verified the signed repository with the key from arctic-release"
'
  arctic_log "signed repository checks against $SITE (file://, --network none)"
  "$engine" run --rm --network none -v "$RPMS:/rpms:ro" -v "$SITE:/site:ro" \
    -e RELEASEVER="$releasever" -e ONLY_CHANNEL="$ONLY_CHANNEL" "$ARCTIC_FEDORA_IMAGE" \
    bash -c "$install_release$compare$signed"
  arctic_log "all repository checks passed"
  exit 0
fi

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$SITE" >/dev/null 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || :' EXIT
for _ in $(seq 1 50); do curl -fsS -o /dev/null "http://127.0.0.1:$port/manifest.json" 2>/dev/null && break; sleep 0.2; done

# shellcheck disable=SC2016 # expanded in the container
online='
url="http://127.0.0.1:$PORT"
checked=0
for pair in $(channels); do
  ch="${pair%%:*}"; id="${pair#*:}"
  dir="/site/repo/$ch/fedora-$RELEASEVER/x86_64"
  [ -d "$dir" ] || { echo "(no $ch channel in the site)"; continue; }
  opts=(--repo "$id" --setopt="$id.enabled=1" --setopt="$id.baseurl=$url/repo/$ch/fedora-$RELEASEVER/x86_64/"
        --setopt="$id.gpgcheck=0" --setopt="$id.repo_gpgcheck=0" --setopt="$id.skip_if_unavailable=0")
  echo "==> dnf5 repoquery --repo $id (the $ch channel, served from the host)"
  opts+=(--refresh)
  compare
  echo "==> dnf5 download --repo $id arctic-release"
  rm -rf /tmp/dl; dnf5 download "${opts[@]}" --destdir /tmp/dl arctic-release >/dev/null
  ls /tmp/dl/arctic-release-*.rpm
  checked=$((checked + 1))
done
[ "$checked" -gt 0 ] || { echo "FAIL: the site has no channel" >&2; exit 1; }
echo "OK: dnf5 reads the published repository"
'
arctic_log "repository checks against $SITE (http://127.0.0.1:$port)"
"$engine" run --rm --network host -v "$RPMS:/rpms:ro" -v "$SITE:/site:ro" \
  -e PORT="$port" -e RELEASEVER="$releasever" -e ONLY_CHANNEL="$ONLY_CHANNEL" "$ARCTIC_FEDORA_IMAGE" \
  bash -c "$install_release$compare$online"
arctic_log "all repository checks passed"
