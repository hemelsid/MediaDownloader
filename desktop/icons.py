"""App icon drawn in code, so it is sharp at every size (window, taskbar, installer, browser extension)."""
from __future__ import annotations

from PIL import Image, ImageDraw

ORANGE = (255, 106, 19, 255)
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def _draw(n: int) -> Image.Image:
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = n / 108
    d.rounded_rectangle((4 * s, 4 * s, 104 * s, 104 * s), radius=24 * s, fill=ORANGE)
    # arrow (slightly bolder than the phone icon so it stays readable when tiny)
    d.polygon([(47 * s, 22 * s), (61 * s, 22 * s), (61 * s, 50 * s), (73 * s, 50 * s), (54 * s, 71 * s),
               (35 * s, 50 * s), (47 * s, 50 * s)], fill="white")
    # tray
    d.polygon([(27 * s, 66 * s), (36 * s, 66 * s), (36 * s, 76 * s), (72 * s, 76 * s), (72 * s, 66 * s),
               (81 * s, 66 * s), (81 * s, 86 * s), (27 * s, 86 * s)], fill="white")
    return img


def make_icon(size: int = 256) -> Image.Image:
    """Draws big and scales down with a high-quality filter — no blurry upscaling."""
    big = _draw(max(512, size * 8))
    return big.resize((size, size), Image.LANCZOS)


def save_ico(path: str):
    imgs = [make_icon(s) for s in ICO_SIZES]
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=imgs[:-1])


if __name__ == "__main__":
    import os
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    save_ico(os.path.join(out, "icon.ico"))
    make_icon(256).save(os.path.join(out, "icon.png"))
