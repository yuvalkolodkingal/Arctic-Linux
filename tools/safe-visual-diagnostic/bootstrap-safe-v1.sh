#!/bin/sh
# Read-only test data CD, separate from the unchanged product ISO.
exec >/dev/ttyS0 2>&1
set -eu
trap 'echo "ARCTIC-SAFE-BOOTSTRAP-EXIT=$?"' 0
echo ARCTIC-SAFE-BOOTSTRAP-BEGIN
test "$(id -u)" = 0
test -b /dev/disk/by-label/ARCTICSAFE
echo "ARCTIC-SAFE-BOOTSTRAP-DEVICE=$(readlink -f /dev/disk/by-label/ARCTICSAFE)"
test ! -e /run/arctic-safe
mkdir -m 0700 /run/arctic-safe
mount -o ro /dev/disk/by-label/ARCTICSAFE /run/arctic-safe
echo ARCTIC-SAFE-BOOTSTRAP-MOUNTED
exec python3 /run/arctic-safe/guest-safe-collector-v1.py
