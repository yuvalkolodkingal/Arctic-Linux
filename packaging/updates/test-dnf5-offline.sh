#!/usr/bin/env bash
# test-dnf5-offline.sh — arctic-update against the real dnf5, in a throwaway Fedora container.
#
# CI runs it in registry.fedoraproject.org/fedora:44 (.github/workflows/ci.yml, "dnf5 offline
# updates"). It pins what arctic-update relies on in dnf5 and the actions plugin, so a Fedora
# update that changes them fails here rather than on Arctic machines:
#   - the state file (status, cmd_line, verb, releasevers) and /system-update, as
#     `dnf5 upgrade --offline` / `dnf5 offline _execute` / a regular transaction leave them;
#   - the sentences of `dnf5 offline status` (arctic-update reads only "modified since");
#   - arctic-update.actions (the post-transaction hook) and arctic-snapper.actions (a no-op
#     without snapper's root configuration) don't break transactions;
#   - someone else's offline transaction is left alone; a failed install at the boot is
#     recorded, tried once more, then automatic installs stop.
# The boots are `DNF_SYSTEM_UPGRADE_NO_REBOOT=1 dnf5 offline _execute` (what
# dnf5-offline-transaction.service runs) plus a new boot id in the status file.
#
# It changes the system it runs on (repositories, packages, /system-update, /usr/bin): it
# refuses to run outside a container. Needs: dnf5 dnf5-plugins libdnf5-plugin-actions
# rpm-build createrepo_c python3 util-linux.
set -euo pipefail

if (( EUID != 0 )); then echo "run as root (in a throwaway container)" >&2; exit 2; fi
if [[ ! -e /.dockerenv && ! -e /run/.containerenv && ${ARCTIC_DNF5_TEST_ANYWAY:-} != 1 ]]; then
  echo "this changes the system's repositories and packages: run it in a throwaway container" >&2
  exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HELPER=/usr/libexec/arctic/arctic-update-helper
DATADIR=/usr/lib/sysimage/libdnf5/offline
STATE=$DATADIR/offline-transaction-state.toml
STATUS=/var/lib/arctic/update-status.json
PKGDIR=/var/lib/dnf/offline/packages
SRV=/srv/arctic-test
OURS="dnf5 upgrade --offline -y --refresh"
FOREIGN="dnf5 -q -y install --offline --refresh arctic-d"
# dnf5's sentences (dnf5/commands/offline/offline.cpp); the helper's STALE_TEXT is the one
# arctic-update depends on.
TEXT_NONE="No offline transaction is stored."
TEXT_STORED="An offline transaction was initiated by the following command:"
TEXT_STALE="has been modified since the offline transaction was prepared"
TEXT_INCOMPLETE="An offline transaction was started, but it did not finish."

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '   ok: %s\n' "$*"; }
state_get() { python3 -c 'import sys, tomllib
try: t = tomllib.load(open(sys.argv[1], "rb"))["offline-transaction-state"]
except FileNotFoundError: t = {}
print(t.get(sys.argv[2], ""))' "$STATE" "$1"; }
status_get() { python3 "$HELPER" get "$STATUS" "$1"; }
linked() { [[ -L /system-update && "$(readlink /system-update)" == "$DATADIR" ]]; }
expect() {  # DESCRIPTION ACTUAL WANTED
  [[ $2 == "$3" ]] || fail "$1: got '$2', expected '$3'"
  ok "$1: $3"
}
expect_in() {  # DESCRIPTION TEXT NEEDLE
  [[ $2 == *"$3"* ]] || fail "$1: '$3' not in: $2"
  ok "$1"
}
offline_status() { LC_ALL=C dnf5 offline status 2>&1; }
# A restart: the next check sees another boot than the one the update was scheduled in.
reboot_() { python3 "$HELPER" write-status "$STATUS" "armed_boot=boot-before-$RANDOM"; }
boot_execute() { DNF_SYSTEM_UPGRADE_NO_REBOOT=1 dnf5 offline _execute; }

step "Setting up: arctic-update, the actions hooks, a local repository"
install -Dm0755 "$REPO/dotfiles/.local/bin/arctic-update" /usr/bin/arctic-update
install -Dm0755 "$HERE/arctic-update-helper" "$HELPER"
install -Dm0644 "$HERE/update.conf" /etc/arctic/update.conf
install -Dm0644 "$HERE/update.actions" /etc/dnf/libdnf5-plugins/actions.d/arctic-update.actions
install -Dm0644 "$HERE/snapper.actions" /etc/dnf/libdnf5-plugins/actions.d/arctic-snapper.actions
grep -qE '^enabled *= *(1|true)' /etc/dnf/libdnf5-plugins/actions.conf || fail "the actions plugin isn't enabled"
# No systemd in the container: log what arctic-update asks of systemctl, answer what it reads.
mkdir -p /usr/local/bin
cat > /usr/local/bin/systemctl <<'EOF'
#!/bin/sh
echo "$*" >> /run/fake-systemctl.log
case "$*" in
  *"Wants --value system-update.target"*) echo dnf5-offline-transaction.service ;;
  *"SubState --value"*) echo dead ;;
esac
exit 0
EOF
chmod 0755 /usr/local/bin/systemctl
: > /run/fake-systemctl.log

build() {  # NAME RELEASE [PRE-SCRIPTLET-EXIT]
  local top=/root/rpmbuild
  mkdir -p "$top/SPECS"
  cat > "$top/SPECS/$1.spec" <<EOF
Name: $1
Version: 1
Release: $2
Summary: arctic-update test package
License: MIT
BuildArch: noarch
%description
A package for test-dnf5-offline.sh.
${3:+%pre
exit $3}
%install
mkdir -p %{buildroot}/usr/share/$1
echo $2 > %{buildroot}/usr/share/$1/release
%files
/usr/share/$1
EOF
  rpmbuild -bb --quiet "$top/SPECS/$1.spec" >/dev/null 2>&1 || fail "rpmbuild $1-1-$2"
  cp "$top/RPMS/noarch/$1-1-$2.noarch.rpm" "$SRV/pool/"
}
publish() {  # CHANNEL NAME-RELEASE…: put these packages in a channel's repository
  local channel=$1 p; shift
  for p in "$@"; do cp "$SRV/pool/$p.noarch.rpm" "$SRV/$channel/"; done
  createrepo_c -q --update "$SRV/$channel"
}
unpublish() { rm -f "$SRV/$1/$2.noarch.rpm"; createrepo_c -q --update "$SRV/$1"; }

rm -rf "$SRV"
mkdir -p "$SRV/pool" "$SRV/stable" "$SRV/testing"
for p in arctic-a arctic-b; do build $p 1; build $p 2; build $p 3; done
build arctic-c 1
build arctic-d 1
build arctic-bad 1
build arctic-bad 2 1       # its %pre fails: the install at the boot fails
mkdir -p /etc/yum.repos.d.saved
find /etc/yum.repos.d -maxdepth 1 -name '*.repo' -exec mv -t /etc/yum.repos.d.saved {} +
cat > /etc/yum.repos.d/arctic.repo <<EOF
[arctic]
name=Arctic test (stable)
baseurl=file://$SRV/stable
gpgcheck=0
[arctic-testing]
name=Arctic test (testing)
baseurl=file://$SRV/testing
gpgcheck=0
enabled=0
EOF
publish stable arctic-a-1-1 arctic-b-1-1 arctic-bad-1-1 arctic-c-1-1 arctic-d-1-1
createrepo_c -q "$SRV/testing"
dnf5 -q -y install arctic-a arctic-b arctic-bad >/dev/null
expect "the hook ignores a transaction with nothing stored" "$(grep -c restage /run/fake-systemctl.log || true)" 0

step "Up to date"
arctic-update stage
expect "status" "$(status_get state)" idle
expect "dnf5 offline status" "$(offline_status)" "$TEXT_NONE"
expect "channel" "$(arctic-update channel)" "stable: released builds (from the main branch)"

step "Updates are downloaded and scheduled for the next boot"
publish stable arctic-a-1-2 arctic-b-1-2
arctic-update stage
expect "state" "$(state_get status)" ready
expect "cmd_line" "$(state_get cmd_line)" "$OURS"
expect "verb" "$(state_get verb)" upgrade
expect "releasever" "$(state_get target_releasever)" "$(state_get system_releasever)"
linked || fail "/system-update doesn't point at $DATADIR"
ok "/system-update → $DATADIR"
expect_in "dnf5 offline status" "$(offline_status)" "$TEXT_STORED"
expect "helper class" "$(offline_status | python3 "$HELPER" offline-class ready)" stored
expect "status" "$(status_get state)/$(status_get armed)/$(status_get packages)" ready/true/2
staged_at="$(status_get staged_at)"

step "The next day's check stores the same updates again: announced once"
sleep 1
arctic-update stage
expect "staged_at" "$(status_get staged_at)" "$staged_at"
linked || fail "not scheduled after the second check"

step "A regular dnf transaction invalidates it; the hook asks for a check"
: > /run/fake-systemctl.log
dnf5 -q -y install arctic-c >/dev/null
linked && fail "dnf5 left /system-update after a regular transaction"
ok "dnf5 removed /system-update"
expect_in "dnf5 offline status" "$(offline_status)" "$TEXT_STALE"
expect "helper class" "$(offline_status | python3 "$HELPER" offline-class "$(state_get status)")" stale
expect_in "the hook started" "$(cat /run/fake-systemctl.log)" "start --no-block arctic-update-restage.timer"
arctic-update stage
linked || fail "not scheduled again"
expect "replaced, scheduled again" "$(state_get status)/$(offline_status | python3 "$HELPER" offline-class ready)" ready/stored

step "The boot installs it"
boot_execute
expect "installed" "$(rpm -q arctic-a)" arctic-a-1-2.noarch
expect "dnf5 cleaned up" "$(offline_status)" "$TEXT_NONE"
linked && fail "/system-update still there"
reboot_
out="$(arctic-update stage)"
expect_in "reported" "$out" "were installed"
expect "status" "$(status_get state)/$(status_get boot_failures)" idle/0

step "An install that fails at the boot is recorded, tried once more, then paused"
publish stable arctic-bad-1-2
arctic-update stage
linked || fail "not scheduled"
boot_execute && fail "the broken package installed"
expect "state after the failed boot" "$(state_get status)" transaction-incomplete
expect_in "dnf5 offline status" "$(offline_status)" "$TEXT_INCOMPLETE"
linked && fail "/system-update still there after _execute"
reboot_
arctic-update stage
expect "first failure" "$(status_get boot_failures)/$(status_get state)/$(status_get armed)" 1/ready/true
linked || fail "not tried again"
boot_execute && fail "the broken package installed"
reboot_
arctic-update stage
expect "second failure: paused" "$(status_get boot_failures)/$(status_get state)/$(status_get armed)" 2/failed/false
linked && fail "scheduled although paused"
arctic-update status | grep -q "aren't scheduled automatically" || fail "status doesn't say it's paused"
arctic-update now >/dev/null
expect "arctic-update now starts again" "$(status_get boot_failures)/$(status_get armed)" 0/true
linked || fail "not scheduled by arctic-update now"
dnf5 -q offline clean
unpublish stable arctic-bad-1-2
python3 "$HELPER" write-status "$STATUS" armed=false armed_boot= state=idle

step "Someone else's offline transaction is left alone"
publish stable arctic-a-1-3
dnf5 -q -y install --offline --refresh arctic-d >/dev/null
expect "stored" "$(state_get cmd_line)" "$FOREIGN"
arctic-update stage
expect "cmd_line kept" "$(state_get cmd_line)" "$FOREIGN"
expect "status kept" "$(state_get status)" download-complete
[[ -e $PKGDIR/arctic-d-1-1.noarch.rpm ]] || fail "its package was deleted"
linked && fail "someone else's transaction was scheduled"
expect_in "status message" "$(status_get message)" "prepared with '$FOREIGN'"
out="$(arctic-update now 2>&1)" && fail "arctic-update now replaced it"
expect_in "now refuses" "$out" "arctic-update now --replace"
out="$(arctic-update apply --yes 2>&1)" && fail "arctic-update apply went ahead"
expect_in "apply refuses" "$out" "dnf5 offline reboot"
out="$(arctic-update channel testing 2>&1)" && fail "arctic-update channel went ahead"
expect_in "channel refuses" "$out" "--replace"
expect "channel unchanged" "$(arctic-update channel)" "stable: released builds (from the main branch)"
arctic-update now --replace >/dev/null
expect "replaced on request" "$(state_get cmd_line)/$(state_get status)" "$OURS/ready"
[[ -e $PKGDIR/arctic-d-1-1.noarch.rpm ]] && fail "the replaced transaction's package is still there"
ok "its package was removed with it"
boot_execute
expect "installed" "$(rpm -q arctic-a)" arctic-a-1-3.noarch
reboot_
arctic-update stage >/dev/null

step "Someone else's, with nothing to update: still left alone"
dnf5 -q -y install --offline --refresh arctic-d >/dev/null
arctic-update stage
expect "cmd_line kept" "$(state_get cmd_line)/$(state_get status)" "$FOREIGN/download-complete"
linked && fail "someone else's transaction was scheduled"
ok "not scheduled"
dnf5 -q offline clean

step "Automatic updates off: the scheduled update stays downloaded"
publish stable arctic-b-1-3
arctic-update stage
linked || fail "not scheduled"
arctic-update auto off
linked && fail "still scheduled with AUTO=off"
expect "state" "$(state_get status)" download-complete
[[ -e $PKGDIR/arctic-b-1-3.noarch.rpm ]] || fail "the download was deleted"
expect_in "timer disabled" "$(cat /run/fake-systemctl.log)" "disable --now arctic-update-stage.timer"
arctic-update auto on
linked || fail "not scheduled again by auto on"
expect "state" "$(state_get status)" ready

step "Channels"
arctic-update channel testing
expect "channel" "$(arctic-update channel)" "testing: development builds (from the dev branch), newer than stable"
expect "the download from the other channel was dropped" "$(offline_status)" "$TEXT_NONE"
linked && fail "/system-update left after switching channels"
arctic-update channel stable </dev/null
expect "channel" "$(arctic-update channel)" "stable: released builds (from the main branch)"

printf '\n\033[1;32mdnf5 offline updates: all checks passed\033[0m\n'
