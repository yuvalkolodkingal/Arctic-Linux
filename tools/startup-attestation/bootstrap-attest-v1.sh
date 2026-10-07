#!/bin/sh
# Disposable read-only data CD only; never a session/startup hook.
exec >/dev/ttyS0 2>&1
set -eu
trap 'echo "ARCTIC-STARTUP-BOOTSTRAP-EXIT=$?"' 0
echo ARCTIC-STARTUP-BOOTSTRAP-BEGIN
test "$(id -u)" = 0
case "$(systemd-detect-virt)" in qemu|kvm) ;; *) exit 1 ;; esac
test "$(getenforce)" = Enforcing
grep -qw rd.live.image /proc/cmdline
grep -qw nomodeset /proc/cmdline
test "$(blkid -t LABEL=ARCTICATTEST -o device | wc -l)" = 1
test -b /dev/disk/by-label/ARCTICATTEST
echo "ARCTIC-STARTUP-BOOTSTRAP-DEVICE=$(readlink -f /dev/disk/by-label/ARCTICATTEST)"
test ! -e /run/arctic-safe
test ! -L /run/arctic-safe
mkdir -m 0700 /run/arctic-safe
mount -o ro /dev/disk/by-label/ARCTICATTEST /run/arctic-safe
echo ARCTIC-STARTUP-BOOTSTRAP-MOUNTED
exec python3 /run/arctic-safe/attest-startup-v1.py
