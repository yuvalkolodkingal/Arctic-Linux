#!/bin/sh
# Read-only test data CD, separate from the unchanged product ISO.
set -eu
test ! -e /run/arctic-safe
mkdir -m 0700 /run/arctic-safe
mount -o ro /dev/sr1 /run/arctic-safe
exec python3 /run/arctic-safe/guest-safe-collector-v1.py >/dev/ttyS0 2>&1
