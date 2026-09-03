"""Generate the Manara lighthouse favicon + PWA icons.

Committed as PNGs under lms_app/web/. Re-run this script if the palette
or mark ever changes. Reproducible: no randomness, no fonts, no external
assets.

Usage:
    python tooling/gen_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

PRIMARY = (79, 70, 229, 255)         # AppColors.primary — indigo-600
PRIMARY_DARK = (55, 48, 163, 255)    # AppColors.primaryDark — indigo-800
WHITE = (255, 255, 255, 255)

WEB = Path(__file__).resolve().parent.parent / "lms_app" / "web"
ICONS = WEB / "icons"


def _gradient_bg(size: int, radius_frac: float = 0.22) -> Image.Image:
    """Rounded-square indigo gradient background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(PRIMARY[0] * (1 - t) + PRIMARY_DARK[0] * t)
        g = int(PRIMARY[1] * (1 - t) + PRIMARY_DARK[1] * t)
        b = int(PRIMARY[2] * (1 - t) + PRIMARY_DARK[2] * t)
        for x in range(size):
            grad.putpixel((x, y), (r, g, b, 255))
    # Rounded corner mask.
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    r = int(size * radius_frac)
    md.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def _lighthouse(size: int, maskable: bool = False) -> Image.Image:
    """Draw the lighthouse mark on a rounded indigo background.

    maskable=True → keep the mark inside the PWA maskable safe zone
    (central 80%). We just shrink the mark rect by 10% on each side.
    """
    img = _gradient_bg(size, radius_frac=0.24 if not maskable else 0.0)
    d = ImageDraw.Draw(img)

    # Compute the mark's bounding box.
    if maskable:
        inset = int(size * 0.14)
    else:
        inset = int(size * 0.16)
    x0, y0 = inset, inset
    x1, y1 = size - inset, size - inset
    w = x1 - x0
    h = y1 - y0
    cx = x0 + w / 2

    def fx(fx_):
        return x0 + w * fx_
    def fy(fy_):
        return y0 + h * fy_

    # Base plinth.
    d.rounded_rectangle([fx(0.22), fy(0.82), fx(0.78), fy(0.92)],
                        radius=max(2, size // 96), fill=WHITE)
    # Tower (tapered trapezoid).
    d.polygon(
        [
            (fx(0.28), fy(0.82)),
            (fx(0.36), fy(0.38)),
            (fx(0.64), fy(0.38)),
            (fx(0.72), fy(0.82)),
        ],
        fill=WHITE,
    )
    # Gallery walkway rim.
    d.rounded_rectangle([fx(0.32), fy(0.34), fx(0.68), fy(0.40)],
                        radius=max(1, size // 96), fill=WHITE)
    # Lamp housing.
    d.rounded_rectangle([fx(0.40), fy(0.22), fx(0.60), fy(0.34)],
                        radius=max(2, size // 96), fill=WHITE)
    # Roof cone.
    d.polygon(
        [(fx(0.36), fy(0.22)), (cx, fy(0.10)), (fx(0.64), fy(0.22))],
        fill=WHITE,
    )
    # Lamp glow.
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    r = max(3, int(size * 0.045))
    gd.ellipse(
        [cx - r, fy(0.28) - r, cx + r, fy(0.28) + r],
        fill=(255, 255, 255, 160),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.02))
    img = Image.alpha_composite(img, glow)
    # Bright dot at the lamp center.
    d = ImageDraw.Draw(img)
    r = max(2, int(size * 0.025))
    d.ellipse([cx - r, fy(0.28) - r, cx + r, fy(0.28) + r], fill=WHITE)
    return img


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    # Favicon: 64px.
    _lighthouse(64).save(WEB / "favicon.png")
    # PWA icons.
    _lighthouse(192).save(ICONS / "Icon-192.png")
    _lighthouse(512).save(ICONS / "Icon-512.png")
    _lighthouse(192, maskable=True).save(ICONS / "Icon-maskable-192.png")
    _lighthouse(512, maskable=True).save(ICONS / "Icon-maskable-512.png")
    print("Wrote favicon.png + 4 PWA icons under lms_app/web/")


if __name__ == "__main__":
    main()
