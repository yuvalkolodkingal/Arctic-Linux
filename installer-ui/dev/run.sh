#!/bin/sh
# Run the installer UI from a repo checkout against the python mock engine
# (no root, no daemon). Needs quickshell and python3.
#   dev/run.sh                      mock engine, Polar night
#   ARCTIC_INSTALLER_THEME=light dev/run.sh
#   ARCTIC_MOCK_ONLINE=1 ARCTIC_MOCK_FAIL=steam dev/run.sh   (see mock-bridge.py)
#   ARCTIC_INSTALLER_BRIDGE="arctic-install bridge --mock" dev/run.sh   (Go engine)
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${ARCTIC_INSTALLER_BRIDGE:=python3 $here/dev/mock-bridge.py}"
export ARCTIC_INSTALLER_BRIDGE
exec quickshell -p "$here" "$@"
