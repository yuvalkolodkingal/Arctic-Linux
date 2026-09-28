#!/usr/bin/env bash
# Arctic Linux dotfiles — install into a home directory.
#
#   ./install.sh                 install into $HOME (existing files are backed up first)
#   ./install.sh --target DIR    install into DIR instead (e.g. /etc/skel when packaging)
#   ./install.sh --theme winter  start in Winter instead of Polar night
#   ./install.sh --deps          also install the Fedora packages the desktop uses (sudo dnf)
#   ./install.sh --shell         also copy the shell (../shell) to ~/.config/quickshell/arctic
#                                (the default when installing into $HOME; packages use
#                                /usr/share/arctic/shell instead, so --target never copies it)
#
# Copies: this folder's home tree, plus the design's fonts, wallpapers and logos and the theme
# engine (../design/themegen) from ../design.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN="$(cd "$HERE/../design" && pwd)"
TARGET="$HOME"
THEME="polar-night"
DEPS=0
SHELL_COPY=auto

while (( $# )); do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --theme)  THEME="$2"; shift 2 ;;
    --deps)   DEPS=1; shift ;;
    --shell)  SHELL_COPY=1; shift ;;
    --no-shell) SHELL_COPY=0; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Fedora packages (all in Fedora 44 except mangowm, which comes from the Arctic COPR or Terra).
PACKAGES=(
  quickshell python3 python3-pillow python3-pyte python3-dbus python3-gobject-base
  kitty zsh mako swaybg swayidle swaylock waybar fuzzel
  grim slurp wl-clipboard cliphist brightnessctl playerctl wireplumber pavucontrol
  lxqt-policykit network-manager-applet NetworkManager-tui blueman libnotify xdg-user-dirs
  librsvg2-tools jetbrains-mono-fonts-all google-noto-sans-fonts
)

if (( DEPS )); then
  sudo dnf install -y "${PACKAGES[@]}"
  if ! command -v mango >/dev/null 2>&1; then
    echo "note: Mango itself isn't installed. Arctic Linux ships it as 'mangowm' from its COPR;"
    echo "      on plain Fedora you can use Terra: https://mangowm.github.io/docs/installation"
  fi
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup="$TARGET/.local/state/arctic/dotfiles-backup-$stamp"

copy_tree() {   # copy_tree <src dir> <dest dir> — back up anything it would overwrite
  local src="$1" dest="$2" rel
  while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"
    if [[ -e "$dest/$rel" || -L "$dest/$rel" ]] && [[ ! -d "$dest/$rel" || -L "$dest/$rel" ]]; then
      if ! cmp -s "$f" "$dest/$rel" 2>/dev/null; then
        mkdir -p "$(dirname "$backup/$rel")"
        mv "$dest/$rel" "$backup/$rel"
      else
        rm -f "$dest/$rel"
      fi
    fi
    mkdir -p "$(dirname "$dest/$rel")"
    cp -P "$f" "$dest/$rel"
  done < <(find "$src" \( -type f -o -type l \) -print0)
}

# 1. The home tree (everything here except this script and the README).
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
(cd "$HERE" && tar --exclude=./install.sh --exclude=./README.md -cf - .) | (cd "$tmp" && tar -xf -)
copy_tree "$tmp" "$TARGET"

# 2. Design assets: fonts, wallpapers, logos.
mkdir -p "$TARGET/.local/share/fonts/arctic" "$TARGET/.local/share/arctic/wallpapers" "$TARGET/.local/share/arctic/logos"
cp "$DESIGN"/fonts/*.woff2 "$TARGET/.local/share/fonts/arctic/"
cp "$DESIGN"/wallpapers/*.svg "$TARGET/.local/share/arctic/wallpapers/"
cp "$DESIGN"/logos/*.svg "$TARGET/.local/share/arctic/logos/"

# 2b. The theme engine (arctic-themegen; arctic-theme makes wallpaper colours with it) and the
# design data it reads — the packages put the same in /usr/share/arctic/themegen.
engine="$TARGET/.local/share/arctic/themegen"
rm -rf "$engine" && mkdir -p "$engine/data/exports" "$engine/data/icons" "$engine/data/logos"
(cd "$DESIGN/themegen" && tar --exclude=./tests --exclude='__pycache__' -cf - .) | (cd "$engine" && tar -xf -)
cp "$DESIGN"/exports/arctic-tokens.json "$DESIGN"/exports/gtk-arctic-*.css "$engine/data/exports/"
cp "$DESIGN"/icons/*.svg "$engine/data/icons/"
cp "$DESIGN"/logos/arctic-mark-16-*.svg "$engine/data/logos/"

# 3. The shell, for installs without the arctic-shell package.
if [[ "$SHELL_COPY" == 1 || ( "$SHELL_COPY" == auto && "$TARGET" == "$HOME" ) ]]; then
  if [[ -f "$HERE/../shell/shell.qml" ]]; then
    dest="$TARGET/.config/quickshell/arctic"
    rm -rf "$dest" && mkdir -p "$dest"
    (cd "$HERE/../shell" && tar --exclude=./dev --exclude=./tests --exclude='./__pycache__' --exclude='*/__pycache__' -cf - .) | (cd "$dest" && tar -xf -)
  fi
fi

# 4. Pick the starting theme (arctic-theme keeps it from then on).
ln -sfn "themes/$THEME" "$TARGET/.config/arctic/current"
echo "$THEME" > "$TARGET/.config/arctic/theme"

if [[ "$TARGET" == "$HOME" ]]; then
  command -v fc-cache >/dev/null && fc-cache -f "$HOME/.local/share/fonts" >/dev/null 2>&1 || true
  PATH="$HOME/.local/bin:$PATH" arctic-wallpaper render >/dev/null 2>&1 || true
  if [[ "${SHELL##*/}" != zsh ]] && command -v zsh >/dev/null; then
    echo "tip: make zsh your shell with:  chsh -s $(command -v zsh)"
  fi
fi

[[ -d "$backup" ]] && echo "Backed up replaced files to $backup"
echo "Arctic Linux dotfiles installed in $TARGET (theme: $THEME)."
echo "Log in to the Mango session, or press Super+Shift+R in a running one."
