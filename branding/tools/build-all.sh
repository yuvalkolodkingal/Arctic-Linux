#!/usr/bin/env bash
# Regenerate every branding asset: fonts, brand SVGs, logos, the SDDM theme's
# binary assets, the GRUB theme and the Plymouth images. Runs in one Fedora 44
# container when the host lacks the tools.
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_tools branding/tools/build-all.sh rsvg-convert grub2-mkfont

"$TOOLS_DIR/render-logos.sh"
"$TOOLS_DIR/build-sddm-theme.sh"
"$TOOLS_DIR/build-grub-theme.sh"
"$TOOLS_DIR/build-plymouth-theme.sh"
log "all branding assets regenerated"
