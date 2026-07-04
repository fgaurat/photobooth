"""Pure image-compositing helpers for the single-photo background feature."""

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps


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


def compose_photo_on_background(
    photo,
    background,
    message="",
    font_path=None,
    color="white",
    side_margin_ratio=0.05,
    top_margin_ratio=0.05,
    bottom_margin_ratio=0.05,
):
    """Return a new RGB image: `photo` resized (aspect ratio preserved,
    never cropped) and centered on a copy of `background`, with `message`
    optionally drawn centered below it using the font at `font_path`, in
    `color` (any value PIL's ImageDraw.text `fill` accepts, e.g. a name
    like "white" or a hex string)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    canvas = background.convert("RGB").copy()

    required_canvas_w = photo.width / (1 - 2 * side_margin_ratio)
    if canvas.width < required_canvas_w:
        scale_up = required_canvas_w / canvas.width
        canvas = canvas.resize(
            (round(canvas.width * scale_up), round(canvas.height * scale_up)),
            Image.LANCZOS,
        )

    bg_w, bg_h = canvas.size

    side_margin = round(bg_w * side_margin_ratio)
    top_margin = round(bg_h * top_margin_ratio)
    bottom_margin = round(bg_h * bottom_margin_ratio)

    window_w = bg_w - 2 * side_margin
    scale = window_w / photo.width
    window_h = round(photo.height * scale)

    resized_photo = photo.resize((window_w, window_h), Image.LANCZOS)
    canvas.paste(resized_photo, (side_margin, top_margin))

    if message and font_path and os.path.isfile(font_path):
        text_zone_top = top_margin + window_h
        text_zone_height = bg_h - bottom_margin - text_zone_top

        if text_zone_height > 0:
            try:
                font = fit_font_size(
                    lambda size: ImageFont.truetype(font_path, size),
                    message,
                    window_w,
                    text_zone_height,
                )
            except OSError:
                font = None

            if font is not None:
                draw = ImageDraw.Draw(canvas)
                left, top, right, bottom = draw.textbbox((0, 0), message, font=font)
                text_w = right - left
                text_h = bottom - top
                text_x = side_margin + (window_w - text_w) / 2 - left
                text_y = text_zone_top + (text_zone_height - text_h) / 2 - top
                draw.text((text_x, text_y), message, font=font, fill=color)

    return canvas
