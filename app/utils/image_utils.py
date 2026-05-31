from __future__ import annotations

from PIL import Image


def apply_export_margin(img: Image.Image, bg_color: str, margin_pct: float) -> Image.Image:
    """Return a new image with a proportional margin border added around *img*.

    *margin_pct* is expressed as a percentage of the card dimensions, e.g. ``3``
    means 3 % of the width is added on the left and right, and 3 % of the height
    is added on the top and bottom.  The original card is centered on the expanded
    canvas filled with *bg_color*.  Returns *img* unchanged when *margin_pct* is
    zero or negative.
    """
    if margin_pct <= 0:
        return img

    pad_x = max(1, round(img.width  * margin_pct / 100))
    pad_y = max(1, round(img.height * margin_pct / 100))

    new_w = img.width  + pad_x * 2
    new_h = img.height + pad_y * 2

    canvas = Image.new(img.mode, (new_w, new_h), bg_color)
    canvas.paste(img, (pad_x, pad_y))
    return canvas
