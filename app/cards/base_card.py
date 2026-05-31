from __future__ import annotations

import os
import re
from dataclasses import dataclass
from PIL import Image

_HEX_RE = re.compile(r'^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$')


def _validate_color(color: str, fallback: str = "#FFFFFF") -> str:
    """Return color if it looks like a valid hex string, else fallback."""
    if _HEX_RE.match(color.strip()):
        return color.strip()
    return fallback


@dataclass
class CardConfig:
    width_in: float = 6.0
    height_in: float = 4.0
    dpi: int = 300
    bg_color: str = "#FFFFFF"

    @property
    def width_px(self) -> int:
        return round(self.width_in * self.dpi)

    @property
    def height_px(self) -> int:
        return round(self.height_in * self.dpi)

    @property
    def is_landscape(self) -> bool:
        return self.width_in >= self.height_in

    def new_canvas(self) -> Image.Image:
        return Image.new("RGB", (self.width_px, self.height_px),
                         _validate_color(self.bg_color))

    def export(self, image: Image.Image, path: str, fmt: str = "PNG") -> str:
        """
        Save image to path.  fmt is 'PNG' or 'JPEG'.
        Returns the final path written.
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fmt = fmt.upper()
        if fmt == "JPG":
            fmt = "JPEG"
        # JPEG doesn't support alpha; convert if needed
        save_image = image
        if fmt == "JPEG" and image.mode == "RGBA":
            bg = Image.new("RGB", image.size, "#FFFFFF")
            bg.paste(image, mask=image.split()[3])
            save_image = bg
        elif fmt == "JPEG" and image.mode != "RGB":
            save_image = image.convert("RGB")

        # Ensure correct extension
        base, ext = os.path.splitext(path)
        if fmt == "JPEG":
            if ext.lower() not in (".jpg", ".jpeg"):
                path = base + ".jpg"
        elif ext.lower() != ".png":
            path = base + ".png"

        save_image.save(path, format=fmt, dpi=(self.dpi, self.dpi), quality=95)
        return path
