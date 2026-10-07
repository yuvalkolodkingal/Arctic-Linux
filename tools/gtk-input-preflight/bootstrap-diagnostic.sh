#!/bin/sh
# First bytes of the diagnostic data CD, run once from the owned live terminal.
set -eu
mkdir -p /run/t
mountpoint -q /run/t || mount -o ro /dev/disk/by-label/ARCTICDIAG /run/t
exec python3 /run/t/native-launcher.py
