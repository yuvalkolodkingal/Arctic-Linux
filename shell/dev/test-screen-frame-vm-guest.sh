#!/usr/bin/env bash
# Private rendering fixture only; enforcing SELinux remains an independent ISO gate.
set -euo pipefail
export HOME=/root PATH=/usr/bin:/usr/sbin:/bin:/sbin
cleanup() {
  status=$?
  if [[ "$status" == 0 ]]; then printf 'ARCTIC-FRAME-VM-PASS\n'; else printf 'ARCTIC-FRAME-VM-FAIL status=%s\n' "$status"; fi
  sync
  poweroff -f
}
trap cleanup EXIT
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
modprobe udmabuf || test -c /dev/udmabuf
test -c /dev/udmabuf
cd /arctic
git config --global --add safe.directory /arctic
for compositor in mango sway; do
  python3 shell/dev/test-screen-frame.py --compositor "$compositor" \
    --baseline-ref 2d5ac68847a5feb541177aeaa5a9a00d5ad44815 --out "out/test/frame/$compositor"
done
