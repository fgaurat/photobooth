"""Pure image-compositing helpers for the single-photo background feature."""

from PIL import Image, ImageDraw


def fit_font_size(font_loader, text, max_width, max_height, min_size=10, max_size=500):
    """Return the largest font produced by font_loader(size) whose rendered
    `text` fits within max_width x max_height. font_loader is a callable
    size:int -> PIL.ImageFont.FreeTypeFont."""
    scratch = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(scratch)

    font = font_loader(min_size)
    for size in range(max_size, min_size - 1, -1):
        font = font_loader(size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        width = right - left
        height = bottom - top
        if width <= max_width and height <= max_height:
            return font

    return font
