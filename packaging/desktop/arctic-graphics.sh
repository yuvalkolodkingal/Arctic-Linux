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
# NVIDIA's driver drawing the screen (a desktop whose monitors are on an NVIDIA card, the
# installer's "NVIDIA driver"): VA-API through libva-nvidia-driver (direct backend, the
# only one that works with current drivers) and GLX from NVIDIA. On a hybrid laptop the
# integrated GPU drew the boot screen, so wlroots renders Mango on it (it picks the boot_vga
# card) and these stay unset; apps run on the NVIDIA card only when asked to, e.g.
# __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia (or
# __NV_PRIME_RENDER_OFFLOAD=1 for Vulkan).
if [ -d /sys/module/nvidia_drm ]; then
  for arctic_card in /sys/class/drm/card[0-9] /sys/class/drm/card[0-9][0-9]; do
    [ -r "$arctic_card/device/boot_vga" ] || continue
    [ "$(cat "$arctic_card/device/boot_vga" 2>/dev/null)" = 1 ] || continue
    [ "$(cat "$arctic_card/device/vendor" 2>/dev/null)" = 0x10de ] || continue
    export LIBVA_DRIVER_NAME="${LIBVA_DRIVER_NAME:-nvidia}"
    export NVD_BACKEND="${NVD_BACKEND:-direct}"
    export __GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-nvidia}"
    break
  done
  unset arctic_card
fi
