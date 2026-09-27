#!/usr/bin/env bash
# Regenerate the reference screenshots in shell/dev/screenshots/ (runs dev/headless.sh a few times).
# Needs: quickshell, sway, grim, wtype, pipewire + wireplumber + pipewire-utils, mako,
# python3-pillow, python3-pyte, librsvg2-tools. Get apps suggestions use the dnf package list:
# the first run of scripts/package-index.py fills ~/.cache/arctic/packages.txt (it is copied
# into the throwaway HOME from $ARCTIC_PACKAGES when set).
set -uo pipefail
H="$(dirname "$0")/headless.sh"
pk="${ARCTIC_PACKAGES:-}"
copy_packages="true"
[[ -n "$pk" && -f "$pk" ]] && copy_packages="mkdir -p ~/.cache/arctic && cp '$pk' ~/.cache/arctic/packages.txt"

"$H" --fixtures polar-night \
  shot bar-polar-night \
  ipc launcher toggle sleep 1 shot launcher-home \
  ipc launcher search ze sleep 1 shot launcher-query \
  ipc launcher search '=2+2' sleep 1 shot launcher-calc \
  ipc launcher close \
  sh "wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.6" sleep 0.4 shot osd-volume sleep 2 \
  ipc wallpapers toggle sleep 3 shot wallpapers ipc wallpapers toggle \
  sh "$copy_packages" ipc apps install sleep 1.5 shot get-apps \
  sh "wtype -s 300 neovim" sleep 1 shot get-apps-suggestions ipc launcher close \
  ipc power toggle sleep 1 shot power-menu ipc power toggle \
  ipc keys toggle sleep 1 shot keys ipc keys toggle \
  theme winter sleep 2 shot theme-toggled-winter

"$H" --theme winter --fixtures winter \
  shot bar-winter \
  ipc launcher search ze sleep 1 shot launcher-winter \
  ipc launcher search '=12*4+2' sleep 1 shot launcher-calc-winter ipc launcher close \
  sh "wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.35" sleep 0.4 shot osd-winter sleep 2 \
  ipc wallpapers toggle sleep 3 shot wallpapers-winter ipc wallpapers toggle \
  ipc power toggle sleep 1 shot power-winter ipc power toggle \
  ipc lock lock sleep 2 sh "wtype -s 300 abc" sleep 0.3 shot lock-winter

"$H" --live live \
  ipc welcome open sleep 1 shot live-welcome \
  ipc power toggle sleep 1 shot live-power ipc power toggle \
  ipc lock lock sleep 1.5 shot lock-live

"$H" lock \
  ipc lock lock sleep 2 sh "wtype -s 300 hunter2" sleep 0.5 shot lock-typing \
  sh "wtype -k Return" sleep 4 shot lock-error
