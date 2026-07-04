from PIL import Image, ImageDraw, ImageFont

from photo_compositing import fit_font_size


def _measure(text, font):
    scratch = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(scratch)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def test_fit_font_size_fits_within_a_narrow_box():
    font_loader = lambda size: ImageFont.load_default(size=size)

    font = fit_font_size(font_loader, "Anniversaire de Laura", max_width=300, max_height=60)

    width, height = _measure("Anniversaire de Laura", font)
    assert width <= 300
    assert height <= 60
    # Confirms real shrinking happened, distinct from the min-size-floor test below.
    assert font.size > 10


def test_fit_font_size_grows_for_a_generous_box():
    font_loader = lambda size: ImageFont.load_default(size=size)

    small_font = fit_font_size(font_loader, "Hi", max_width=50, max_height=30)
    large_font = fit_font_size(font_loader, "Hi", max_width=2000, max_height=1000)

    assert large_font.size > small_font.size


def test_fit_font_size_falls_back_to_min_size_when_nothing_fits():
    font_loader = lambda size: ImageFont.load_default(size=size)

    font = fit_font_size(
        font_loader, "This text will never fit", max_width=1, max_height=1, min_size=7
    )

    assert font.size == 7
