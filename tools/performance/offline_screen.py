#!/usr/bin/env python3
"""Strict visual detectors used only by the offline-update intermediate boot."""
from PIL import Image


def looks_like_plain_luks_prompt(path):
    """Recognize Plymouth's unthemed console passphrase fallback.

    Slow TCG boots can expose Plymouth's exact two-colour text canvas instead
    of the graphical amber-edged entry box. Keep this deliberately narrow: the
    caller is about to type its disposable disk passphrase.
    """
    try:
        image = Image.open(path).convert('RGB')
    except OSError:
        return False
    width, height = image.size
    if width < 640 or height < 400:
        return False
    colors = image.getcolors(maxcolors=8)
    if colors is None or len(colors) != 2:
        return False
    (background_count, background), (foreground_count, foreground) = sorted(
        colors, reverse=True)
    pixels = width * height
    if (background_count < pixels * 0.99
            or not 32 <= min(background) <= max(background) <= 72
            or max(background) - min(background) > 12
            or not 224 <= min(foreground) <= max(foreground) <= 255
            or max(foreground) - min(foreground) > 4
            or not pixels * 0.001 <= foreground_count <= pixels * 0.01):
        return False
    mask = Image.new('1', image.size)
    mask.putdata([pixel != background for pixel in image.getdata()])
    bounds = mask.getbbox()
    if bounds is None:
        return False
    left, top, right, bottom = bounds
    return (left <= width * 0.01
            and width * 0.35 <= right <= width * 0.65
            and height * 0.15 <= top <= height * 0.30
            and height * 0.02 <= bottom - top <= height * 0.10)
