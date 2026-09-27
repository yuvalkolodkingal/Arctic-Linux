#!/usr/bin/env bash
# Regenerate the SDDM theme's binary assets: the bundled TTF fonts and the
# wallpaper (design/wallpapers/fox-polar-night.svg rendered to PNG).
# The QML is hand-written and lives in branding/sddm/arctic/.
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_tools branding/tools/build-sddm-theme.sh rsvg-convert

THEME="$BRANDING_DIR/sddm/arctic"
WIDTH="${SDDM_BG_WIDTH:-2560}"
HEIGHT="${SDDM_BG_HEIGHT:-1440}"

log "fonts -> sddm/arctic/fonts"
python3 "$TOOLS_DIR/fonts.py" "$DESIGN_DIR/fonts" "$BRANDING_DIR/fonts" >/dev/null
install -d "$THEME/fonts"
for f in Figtree-Regular Figtree-Medium Figtree-SemiBold Figtree-Bold JetBrainsMono-Regular JetBrainsMono-Bold; do
    install -m 0644 "$BRANDING_DIR/fonts/$f.ttf" "$THEME/fonts/$f.ttf"
done
install -m 0644 "$BRANDING_DIR/fonts/OFL.txt" "$THEME/fonts/OFL.txt"

log "background.png (${WIDTH}x${HEIGHT}) from fox-polar-night.svg"
install -d "$BUILD_DIR"
render_svg "$DESIGN_DIR/wallpapers/fox-polar-night.svg" "$BUILD_DIR/sddm-bg.png" "$WIDTH" "$HEIGHT"
# Flatten to RGB (the greeter shows it opaque) and optimise.
python3 -c 'import sys; from PIL import Image; Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], optimize=True)' \
    "$BUILD_DIR/sddm-bg.png" "$THEME/background.png"

log "sddm theme assets done: $(du -sh "$THEME" | cut -f1)"
