#!/usr/bin/env bash
# test-dnf5-remove.sh — Remove apps against the real dnf5, in a throwaway Fedora container.
#
# CI runs it in registry.fedoraproject.org/fedora:44 (.github/workflows/ci.yml, "dnf5 remove
# previews"). It pins what shell/scripts/apps.py relies on, so a Fedora update that changes it
# fails here rather than on Arctic machines:
#   - `dnf5 remove --store=DIR -y` runs as a normal user and writes DIR/transaction.json, with
#     the reasons User (asked), Dependency (needs it) and Clean (no longer needed);
#   - `--no-autoremove` keeps the unused dependencies;
#   - `--assumeno` prints the transaction and "Operation aborted by the user." (exit 1);
#   - `repoquery --installed --providers-of=requires --recursive` gives the hard closure;
#   - the `repoquery --installed --qf` fields and `rpm -qf --qf '[%{FILENAMES}\t%{=NAME}\n]'`;
#   - `apps.py preview-remove dnf` turns all that into its preview, blocks a removal that takes
#     a protected package along, and root's `dnf5 remove -y` then removes exactly that list.
# Test packages stand in for the desktop: t-app (a launcher entry) needs t-lib; t-meta needs
# t-tool, as arctic-desktop needs blueman.
#
#   test-dnf5-remove.sh [--update-fixtures]   also copy the captured outputs to
#                                             shell/tests/fixtures/apps/ (run locally)
#
# It changes the system it runs on (repositories, packages, users): it refuses to run outside a
# container. Needs: dnf5 rpm-build createrepo_c python3 util-linux (runuser).
set -euo pipefail

if (( EUID != 0 )); then echo "run as root (in a throwaway container)" >&2; exit 2; fi
if [[ ! -e /.dockerenv && ! -e /run/.containerenv && ${ARCTIC_DNF5_TEST_ANYWAY:-} != 1 ]]; then
  echo "this changes the system's repositories and packages: run it in a throwaway container" >&2
  exit 2
fi
UPDATE=0
[[ ${1:-} == --update-fixtures ]] && UPDATE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APPS="$REPO/shell/scripts/apps.py"
FIXTURES="$HERE/fixtures/apps"
SRV=/srv/arctic-remove-test
WORK=/tmp/arctic-remove-test
TESTUSER=arcticremove

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '   ok: %s\n' "$*"; }
expect() {  # DESCRIPTION ACTUAL WANTED
  [[ $2 == "$3" ]] || fail "$1: got '$2', expected '$3'"
  ok "$1: $3"
}
expect_in() {  # DESCRIPTION TEXT NEEDLE
  [[ $2 == *"$3"* ]] || fail "$1: '$3' not in: $2"
  ok "$1"
}
as_user() { runuser -u "$TESTUSER" -- env HOME="/home/$TESTUSER" XDG_RUNTIME_DIR="$WORK/run" LC_ALL=C "$@"; }
# The Remove reasons of a stored transaction, as "name:reason" words in nevra order.
reasons() { python3 -c 'import json, sys
rpms = json.load(open(sys.argv[1]))["rpms"]
print(" ".join(r["nevra"].rsplit("-", 2)[0] + ":" + r["reason"] for r in sorted(rpms, key=lambda r: r["nevra"]) if r["action"] == "Remove"))' "$1"; }
field() { python3 -c 'import json, sys
data = json.loads(sys.argv[1])
for key in sys.argv[2].split("."):
    data = data[int(key)] if isinstance(data, list) else data.get(key) if data is not None else None
print("" if data is None else data if not isinstance(data, (list, dict)) else json.dumps(data, sort_keys=True))' "$1" "$2"; }
whys() { python3 -c 'import json, sys
print(" ".join(p["name"] + ":" + p["why"] for p in json.loads(sys.argv[1])["packages"]))' "$1"; }

build() {  # NAME [REQUIRES] [desktop]
  local top="$WORK/rpmbuild"
  mkdir -p "$top/SPECS"
  {
    printf 'Name: %s\nVersion: 1\nRelease: 1\nSummary: Remove apps test package %s\nLicense: MIT\nBuildArch: noarch\n' "$1" "$1"
    [[ -n ${2:-} ]] && printf 'Requires: %s\n' "$2"
    printf '%%description\nA package for test-dnf5-remove.sh.\n%%install\nmkdir -p %%{buildroot}/usr/share/%s\n' "$1"
    printf 'head -c 4096 /dev/zero > %%{buildroot}/usr/share/%s/data\n' "$1"
    if [[ -n ${3:-} ]]; then
      printf 'mkdir -p %%{buildroot}/usr/share/applications\n'
      printf 'printf "[Desktop Entry]\\nType=Application\\nName=Test App\\nExec=%s\\n" > %%{buildroot}/usr/share/applications/%s.desktop\n' "$1" "$1"
    fi
    printf '%%files\n/usr/share/%s\n' "$1"
    [[ -n ${3:-} ]] && printf '/usr/share/applications/%s.desktop\n' "$1"
  } > "$top/SPECS/$1.spec"
  rpmbuild -bb --quiet --define "_topdir $top" "$top/SPECS/$1.spec" >/dev/null 2>&1 || fail "rpmbuild $1"
  cp "$top/RPMS/noarch/$1-1-1.noarch.rpm" "$SRV/"
}

step "Setting up: test packages in a local repository, installed; a normal user"
rm -rf "$SRV" "$WORK"
mkdir -p "$SRV" "$WORK/run" "$WORK/out"
build t-lib
build t-app t-lib desktop
build t-tool
build t-meta t-tool
build t-leaf
createrepo_c -q "$SRV"
printf '[arctic-remove-test]\nname=Remove apps test\nbaseurl=file://%s\ngpgcheck=0\n' "$SRV" > /etc/yum.repos.d/arctic-remove-test.repo
dnf5 -q -y --disablerepo='*' --enablerepo=arctic-remove-test install t-app t-meta t-leaf >/dev/null 2>&1 || fail "installing the test packages"
id "$TESTUSER" >/dev/null 2>&1 || useradd -m "$TESTUSER"
chown "$TESTUSER" "$WORK/run" "$WORK/out"
chmod 0700 "$WORK/run"

step "dnf5 remove --store runs as a normal user"
as_user dnf5 remove --store="$WORK/out/app" -y t-app >/dev/null 2>&1 || fail "dnf5 remove --store as a user"
[[ -f $WORK/out/app/transaction.json ]] || fail "no transaction.json"
expect "t-app: asked, its library no longer needed" "$(reasons "$WORK/out/app/transaction.json")" "t-app:User t-lib:Clean"
as_user dnf5 remove --store="$WORK/out/lib" -y t-lib >/dev/null 2>&1 || fail "dnf5 remove --store t-lib"
expect "t-lib: asked, the app that needs it goes too" "$(reasons "$WORK/out/lib/transaction.json")" "t-app:Dependency t-lib:User"
as_user dnf5 remove --store="$WORK/out/keep" -y --no-autoremove t-app >/dev/null 2>&1 || fail "--no-autoremove"
expect "--no-autoremove keeps t-lib" "$(reasons "$WORK/out/keep/transaction.json")" "t-app:User"
rpm -q t-app t-lib >/dev/null || fail "a stored transaction removed something"
ok "nothing was removed by the previews"

step "dnf5 remove --assumeno (the fallback preview)"
set +e
text="$(as_user dnf5 remove --assumeno t-lib 2>&1)"; code=$?
set -e
expect "--assumeno exit code" "$code" 1
expect_in "--assumeno lists dependents" "$text" "Removing dependent packages:"
expect_in "--assumeno aborts" "$text" "Operation aborted by the user."

step "repoquery: the hard closure and the installed facts"
expect "closure of t-meta" "$(as_user dnf5 -q repoquery --installed --providers-of=requires --recursive --qf '%{name}\n' t-meta | sort | tr '\n' ' ')" "t-tool "
facts="$(as_user dnf5 -q repoquery --installed --qf "$(printf '%%{name}\t%%{reason}\t%%{from_repo}\t%%{installsize}\t%%{evr}')\n" t-app t-lib)"
expect "installed facts (tab-separated, \\n ends a line)" "$(printf '%s' "$facts" | sort | cut -f1,2,3,4,5 | tr '\t\n' '| ')" "t-app|User|arctic-remove-test|4154|1-1 t-lib|Dependency|arctic-remove-test|4096|1-1 "
owners="$(rpm -qf --qf '[%{FILENAMES}\t%{=NAME}\n]' -- /usr/share/applications/t-app.desktop /usr/share/t-lib/data 2>/dev/null | grep -E '^/usr/share/(applications/t-app.desktop|t-lib/data)	' | tr '\t\n' '| ')"
expect "rpm -qf owners" "$owners" "/usr/share/applications/t-app.desktop|t-app /usr/share/t-lib/data|t-lib "

step "apps.py preview-remove dnf"
preview="$(as_user python3 "$APPS" preview-remove dnf t-app)" || fail "preview t-app: $preview"
expect "preview t-app" "$(whys "$preview")" "t-app:asked t-lib:unused"
expect "frees" "$(field "$preview" frees_bytes)" "8250"
expect "not blocked" "$(field "$preview" blocked)" ""
preview="$(as_user python3 "$APPS" preview-remove dnf --no-autoremove t-app)" || fail "preview --no-autoremove: $preview"
expect "preview --no-autoremove" "$(whys "$preview")" "t-app:asked"
preview="$(as_user python3 "$APPS" preview-remove dnf t-lib)" || fail "preview t-lib: $preview"
expect "preview t-lib" "$(whys "$preview")" "t-lib:asked t-app:needs-it"
mkdir -p "$WORK/protected.d"
echo t-meta > "$WORK/protected.d/test.conf"
preview="$(as_user env ARCTIC_PROTECTED_DIR="$WORK/protected.d" python3 "$APPS" preview-remove dnf t-tool)" || fail "preview t-tool: $preview"
expect "a protected dependent blocks the removal" "$(field "$preview" blocked.package)" "t-meta"
expect_in "and says why" "$(field "$preview" blocked.message)" "which Arctic Linux needs"
set +e
preview="$(as_user python3 "$APPS" preview-remove dnf t-nothere)"; code=$?
set -e
expect "a package that isn't installed" "$code:$(field "$preview" code)" "1:not-installed"

step "apps.py installed dnf maps the launcher entry to its package"
listing="$(as_user env XDG_DATA_DIRS=/usr/share python3 "$APPS" installed dnf)" || fail "installed dnf: $listing"
row="$(python3 -c 'import json, sys
rows = [r for r in json.loads(sys.argv[1])["apps"] if r["package"] == "t-app"]
print(rows[0]["name"], rows[0]["desktop_ids"], rows[0]["repo"], rows[0]["evr"]) if rows else print("missing")' "$listing")"
expect "t-app row" "$row" "Test App ['t-app'] arctic-remove-test 1-1"

step "root's dnf5 remove -y removes what the preview listed"
dnf5 -q remove -y t-app >/dev/null 2>&1 || fail "dnf5 remove t-app"
if rpm -q t-app >/dev/null 2>&1 || rpm -q t-lib >/dev/null 2>&1; then fail "t-app or t-lib still installed"; fi
rpm -q t-meta t-tool t-leaf >/dev/null || fail "something else went too"
ok "t-app and t-lib removed, nothing else"

if (( UPDATE )); then
  step "Updating $FIXTURES"
  mkdir -p "$FIXTURES"
  cp "$WORK/out/app/transaction.json" "$FIXTURES/dnf5-remove-app.json"
  cp "$WORK/out/lib/transaction.json" "$FIXTURES/dnf5-remove-lib.json"
  cp "$WORK/out/keep/transaction.json" "$FIXTURES/dnf5-remove-no-autoremove.json"
  printf '%s\n' "$text" > "$FIXTURES/dnf5-remove-assumeno.txt"
  ok "copied"
fi
rm -f /etc/yum.repos.d/arctic-remove-test.repo
printf '\n\033[1;32mAll dnf5 remove checks passed.\033[0m\n'
