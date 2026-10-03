#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR=/tmp/arctic-nautilus-runtime
mkdir -p "$XDG_RUNTIME_DIR" /home/capture/.config/gtk-4.0 /home/capture/.local/share/fonts /home/capture/.config /home/capture/Documents /home/capture/Downloads /home/capture/Pictures /home/capture/Music /home/capture/Videos /home/capture/Desktop /home/capture/Public /home/capture/Templates
chmod 700 "$XDG_RUNTIME_DIR"
cp /source/design/fonts/*.woff2 /home/capture/.local/share/fonts/
cp /source/dotfiles/.config/gtk-4.0/gtk.css /home/capture/.config/gtk-4.0/gtk.css
cp /source/dotfiles/.config/gtk-4.0/settings.ini /home/capture/.config/gtk-4.0/settings.ini
cp /source/dotfiles/.config/arctic/themes/polar-night/gtk.css /home/capture/.config/gtk-4.0/arctic-colors.css
cat > /home/capture/.config/gtk-4.0/arctic-modern.css <<'CSS'
:root{--accent-bg-color:#f6bd55;--accent-fg-color:#151a21;--accent-color:#f6bd55;--window-bg-color:#1a212a;--window-fg-color:#e9eef3;--view-bg-color:#1a212a;--view-fg-color:#e9eef3;--headerbar-bg-color:#0f141a;--headerbar-fg-color:#e9eef3;--sidebar-bg-color:#0f141a;--sidebar-fg-color:#e9eef3;--card-bg-color:#232b36;--card-fg-color:#e9eef3;--popover-bg-color:#232b36;--popover-fg-color:#e9eef3;}
CSS
printf '\n@import url("arctic-modern.css");\n' >> /home/capture/.config/gtk-4.0/gtk.css
cat > /home/capture/.config/user-dirs.dirs <<'DIRS'
XDG_DESKTOP_DIR="/home/capture/Desktop"
XDG_DOCUMENTS_DIR="/home/capture/Documents"
XDG_DOWNLOAD_DIR="/home/capture/Downloads"
XDG_MUSIC_DIR="/home/capture/Music"
XDG_PICTURES_DIR="/home/capture/Pictures"
XDG_PUBLICSHARE_DIR="/home/capture/Public"
XDG_TEMPLATES_DIR="/home/capture/Templates"
XDG_VIDEOS_DIR="/home/capture/Videos"
DIRS
fc-cache -f >/dev/null 2>&1
gsettings set org.gnome.desktop.interface color-scheme prefer-dark
gsettings set org.gnome.desktop.interface font-name 'Figtree 11'
gsettings set org.gnome.desktop.interface icon-theme Adwaita
gsettings set org.gnome.desktop.wm.preferences button-layout ':'
cat > /capture/sway.conf <<'CONF'
output HEADLESS-1 resolution 608x746
default_border none
default_floating_border none
seat seat0 hide_cursor 100
CONF
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 sway -c /capture/sway.conf >/capture/sway.log 2>&1 &
sway_pid=$!
trap 'kill "$sway_pid" 2>/dev/null || true' EXIT
for i in $(seq 1 60); do
 if [ -S "$XDG_RUNTIME_DIR/wayland-1" ]; then export WAYLAND_DISPLAY=wayland-1;break;fi
 if [ -S "$XDG_RUNTIME_DIR/wayland-0" ]; then export WAYLAND_DISPLAY=wayland-0;break;fi
 sleep .2
done
export GDK_BACKEND=wayland GSK_RENDERER=cairo
nautilus --new-window /home/capture >/capture/nautilus.log 2>&1 &
nautilus_pid=$!
sleep 5
grim /capture/nautilus-tiled.png
nautilus --version > /capture/version.txt
kill "$nautilus_pid" 2>/dev/null || true
