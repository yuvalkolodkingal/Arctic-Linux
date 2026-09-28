#!/usr/bin/env bash
# Regenerate branding/src (brand SVGs), branding/fonts (TTF) and the logo set in
# branding/logos/ (mirrors install paths, packaged as arctic-logos, which
# Provides system-logos in place of fedora-logos / generic-logos).
set -euo pipefail
# shellcheck disable=SC2034  # read by ensure_tools in lib.sh
SCRIPT_ARGS=("$@")
# shellcheck source=branding/tools/lib.sh source-path=SCRIPTDIR
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_tools branding/tools/render-logos.sh rsvg-convert

SRC="$BRANDING_DIR/src"
OUT="$BRANDING_DIR/logos"

log "fonts: design/fonts/*.woff2 -> branding/fonts/*.ttf"
python3 "$TOOLS_DIR/fonts.py" "$DESIGN_DIR/fonts" "$BRANDING_DIR/fonts" >/dev/null

log "brand SVGs -> branding/src"
python3 "$TOOLS_DIR/brand.py" "$SRC" "$BRANDING_DIR/fonts" >/dev/null

rm -rf "${OUT:?}/usr" "${OUT:?}/etc"

# The SVG sources themselves.
install -d "$OUT/usr/share/arctic/logos"
cp "$SRC"/*.svg "$OUT/usr/share/arctic/logos/"

# hicolor app icon (os-release LOGO=arctic-logo-icon), the Fedora-named copy
# some programs hard-code, and start-here for menus. <= 24 px uses the 16 px
# drawing (no eyes, wider gap) as the brand book asks.
for size in 16 22 24 32 36 48 64 96 128 256 512; do
    src="$SRC/arctic-logo-icon.svg"
    [[ $size -le 24 ]] && src="$SRC/arctic-logo-icon-16.svg"
    d="$OUT/usr/share/icons/hicolor/${size}x${size}"
    render_svg "$src" "$d/apps/arctic-logo-icon.png" "$size" "$size"
    install -d "$d/places"
    cp "$d/apps/arctic-logo-icon.png" "$d/apps/fedora-logo-icon.png"
    cp "$d/apps/arctic-logo-icon.png" "$d/places/start-here.png"
done
sc="$OUT/usr/share/icons/hicolor/scalable"
install -d "$sc/apps" "$sc/places" "$OUT/usr/share/icons/hicolor/symbolic/apps"
cp "$SRC/arctic-logo-icon.svg" "$sc/apps/arctic-logo-icon.svg"
cp "$SRC/arctic-logo-icon.svg" "$sc/apps/fedora-logo-icon.svg"
cp "$SRC/arctic-logo-icon.svg" "$sc/apps/start-here.svg"
cp "$SRC/arctic-logo-icon.svg" "$sc/places/start-here.svg"
# GTK recolours -symbolic icons; the one-colour 16 px mark reads best there.
sed 's/#151a21/#2e3436/g' "$SRC/arctic-mark-16-charcoal.svg" \
    > "$OUT/usr/share/icons/hicolor/symbolic/apps/arctic-logo-icon-symbolic.svg"

# /usr/share/pixmaps: the names fedora-logos ships, at the same sizes.
px="$OUT/usr/share/pixmaps"
install -d "$px"
render_svg "$SRC/arctic-mark-mono-white.svg" "$px/system-logo-white.png" 252 252   # sddm, plymouth special://logo
render_svg "$SRC/arctic-mark-winter.svg" "$px/fedora-logo-sprite.png" 252 252
cp "$SRC/arctic-mark-winter.svg" "$px/fedora-logo-sprite.svg"
render_svg "$SRC/arctic-lockup-winter.svg" "$px/fedora-logo.png" 520
render_svg "$SRC/arctic-lockup-winter.svg" "$px/fedora-logo-small.png" 150
render_svg "$SRC/arctic-lockup-winter.svg" "$px/fedora_logo_med.png" 279
render_svg "$SRC/arctic-lockup-mono-white.svg" "$px/fedora_whitelogo_med.png" 279
cp "$SRC/arctic-lockup-mono-white.svg" "$px/fedora_whitelogo.svg"
render_svg "$SRC/arctic-lockup-polar-night.svg" "$px/fedora-gdm-logo.png" 149
# os-release LOGO=arctic-logo-icon: fastfetch, GNOME's About page, hostnamectl and friends look
# for it here (PNG and SVG) as well as in the icon theme.
render_svg "$SRC/arctic-logo-icon.svg" "$px/arctic-logo-icon.png" 256 256
cp "$SRC/arctic-logo-icon.svg" "$px/arctic-logo-icon.svg"

# Watermark for Plymouth's spinner/bgrt themes (used only if someone switches
# away from the arctic theme) and the 16 px favicon lighttpd & co. expect.
render_svg "$SRC/arctic-lockup-polar-night.svg" "$OUT/usr/share/plymouth/themes/spinner/watermark.png" 180
render_svg "$SRC/arctic-logo-icon-16.svg" "$OUT/etc/favicon.png" 16 16

log "logos written to branding/logos ($(find "$OUT" -type f | wc -l) files)"

# The fox as text art for fastfetch / neofetch (arctic-desktop-config installs it in
# /usr/share/arctic/fastfetch; design/themegen/templates/fastfetch carry the same text).
python3 "$TOOLS_DIR/fastfetch_logo.py" --out "$REPO_DIR/dotfiles/.local/share/arctic/fastfetch/logo.txt" >/dev/null
log "fastfetch logo written to dotfiles/.local/share/arctic/fastfetch/logo.txt"
