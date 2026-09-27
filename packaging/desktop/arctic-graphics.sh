# shellcheck shell=sh
# /etc/profile.d/arctic-graphics.sh (arctic-desktop-config)
# Mango (wlroots + scenefx) on machines without a GPU driver: virtual machines and
# "Safe graphics mode" (nomodeset → simpledrm) only have Mesa's software renderer, which
# wlroots refuses unless allowed. Harmless with a real GPU (it only allows the fallback).
export WLR_RENDERER_ALLOW_SOFTWARE=1
if [ -z "${WLR_NO_HARDWARE_CURSORS:-}" ] && command -v systemd-detect-virt >/dev/null 2>&1; then
  case "$(systemd-detect-virt --vm 2>/dev/null)" in
    none|"") ;;
    *) export WLR_NO_HARDWARE_CURSORS=1 ;;
  esac
fi
