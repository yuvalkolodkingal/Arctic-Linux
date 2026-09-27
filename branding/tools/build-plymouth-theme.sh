#!/usr/bin/env bash
# Regenerate the Plymouth theme images in branding/plymouth/arctic/ (the
# .plymouth and .script files are hand-written).
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_tools branding/tools/build-plymouth-theme.sh rsvg-convert

OUT="$BRANDING_DIR/plymouth/arctic"
python3 "$TOOLS_DIR/fonts.py" "$DESIGN_DIR/fonts" "$BRANDING_DIR/fonts" >/dev/null
python3 "$TOOLS_DIR/brand.py" "$BRANDING_DIR/src" "$BRANDING_DIR/fonts" >/dev/null
rm -f "$OUT"/*.png
python3 "$TOOLS_DIR/plymouth_assets.py" "$BRANDING_DIR/src" "$BRANDING_DIR/fonts" "$OUT"
log "plymouth theme: $(du -sh "$OUT" | cut -f1) in branding/plymouth/arctic"
