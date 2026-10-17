#!/usr/bin/env python3
"""Regenerate the brand image set from the Guru Ears logo.

    pip install "pillow>=10"
    python scripts/make_favicons.py

One-off tooling. The generated binaries are committed, so running the portal
never needs Pillow. Rerun only when static/brand/guru-ears-logo.png changes.

The source logo is the "listening ears" icon on a large white canvas. This
trims the canvas, drops the white to transparent, and squares it up:
  mark.png          transparent, tightly cropped, padded to a square
  favicon.ico       16/32/48 from mark.png
  favicon-*.png     32 / 180 / 192 / 512 from mark.png
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.join(HERE, os.pardir, "static", "brand")
SOURCE = os.path.join(BRAND, "guru-ears-logo.png")

PNG_SIZES = {"favicon-32.png": 32, "favicon-180.png": 180,
             "favicon-192.png": 192, "favicon-512.png": 512}
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]


def _rel(path):
    return os.path.relpath(path, os.path.join(HERE, os.pardir))


def build_mark():
    """Trim the white canvas, knock out the background, pad to a square."""
    logo = Image.open(SOURCE).convert("RGBA")
    w, h = logo.size
    rgb = logo.convert("RGB").load()

    # Bounding box from clearly-inked pixels only (black + orange), ignoring the
    # faint mid-tone speckle scattered across the scan.
    ink = Image.new("L", (w, h), 0)
    ipx = ink.load()
    for y in range(h):
        for x in range(w):
            r, g, b = rgb[x, y]
            if min(r, g, b) < 110:
                ipx[x, y] = 255
    bbox = ink.getbbox()

    apx = logo.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _a = apx[x, y]
            if min(r, g, b) > 238:               # near-white -> transparent
                apx[x, y] = (0, 0, 0, 0)

    trimmed = logo.crop(bbox)
    side = round(max(trimmed.size) * 1.12)       # square canvas + ~6% margin
    mark = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    mark.paste(trimmed, ((side - trimmed.width) // 2,
                         (side - trimmed.height) // 2), trimmed)
    dst = os.path.join(BRAND, "mark.png")
    mark.save(dst)
    print("wrote", _rel(dst), mark.size)
    return mark


def make_favicons(mark):
    for name, px in PNG_SIZES.items():
        dst = os.path.join(BRAND, name)
        mark.resize((px, px), Image.LANCZOS).save(dst)
        print("wrote", _rel(dst))
    ico = os.path.join(BRAND, "favicon.ico")
    mark.save(ico, sizes=ICO_SIZES)
    print("wrote", _rel(ico))


def main():
    make_favicons(build_mark())


if __name__ == "__main__":
    main()
