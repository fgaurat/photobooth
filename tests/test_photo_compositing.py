from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from photo_compositing import fit_font_size, compose_photo_on_background

SAMARKAN_FONT_PATH = str(
    Path(__file__).parent.parent / "static" / "fonts" / "samarkan" / "SAMAN___.TTF"
)


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


def test_compose_uses_the_same_margin_ratio_on_sides_as_on_top_by_default():
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(photo, background)

    # Default side margin now matches the 5% top margin (was 12%): at
    # x=100 (past the new 5%*1000=50px margin, still short of the old
    # 12%*1000=120px margin) and a y within the photo's vertical span,
    # this pixel is only red if the side margin actually shrank to 5%.
    assert result.getpixel((100, 500)) == (255, 0, 0)


def test_compose_upscales_a_background_smaller_than_the_photo():
    photo = Image.new("RGB", (2000, 3000), "red")
    background = Image.new("RGB", (500, 800), "black")

    result = compose_photo_on_background(photo, background)

    # required_canvas_w = 2000 / (1 - 2*0.05) = 2222.22 -> 2222;
    # background (500x800, aspect 0.625) scaled up by 2222/500=4.444 ->
    # (2222, 3556). The photo then fits its window at scale=1.0 (native
    # resolution, not downscaled) rather than being squeezed into a
    # canvas smaller than itself.
    assert result.size == (2222, 3556)


def test_compose_resizes_and_centers_photo_on_background():
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(photo, background)

    assert result.size == (1000, 2000)
    assert result.mode == "RGB"
    # Center of the background sits inside the pasted photo window.
    assert result.getpixel((result.width // 2, result.height // 2)) == (255, 0, 0)
    # Top-left corner sits in the margin, outside the photo window.
    assert result.getpixel((2, 2)) == (0, 0, 0)


def test_compose_skips_message_when_font_path_is_none():
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(photo, background, message="Anniversaire de Laura")

    assert result.size == (1000, 2000)


def test_compose_skips_message_when_font_file_is_missing():
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(
        photo,
        background,
        message="Anniversaire de Laura",
        font_path="/nonexistent/font.ttf",
    )

    assert result.size == (1000, 2000)


def test_compose_skips_message_when_font_file_is_invalid(tmp_path):
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    bad_font_path = tmp_path / "not_a_font.ttf"
    bad_font_path.write_bytes(b"this is not a valid font file")

    result = compose_photo_on_background(
        photo,
        background,
        message="Anniversaire de Laura",
        font_path=str(bad_font_path),
    )

    assert result.size == (1000, 2000)


def test_compose_draws_message_in_the_configured_color():
    photo = Image.new("RGB", (400, 600), "black")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(
        photo,
        background,
        message="Test",
        font_path=SAMARKAN_FONT_PATH,
        color="red",
    )

    # Photo and background are both pure black, so any non-black pixel in
    # the text zone must come from the rendered message itself.
    # side_margin_ratio=0.05, top_margin_ratio=0.05 -> side_margin=50,
    # top_margin=100, window_w=900, scale=2.25, window_h=1350,
    # text_zone_top=1450, bottom_margin=100 -> text_zone_bottom=1900.
    text_zone = result.crop((50, 1450, 950, 1900))
    (min_r, max_r), (min_g, max_g), (min_b, max_b) = text_zone.getextrema()

    assert max_r > 150
    assert max_g < 80
    assert max_b < 80


def test_compose_defaults_message_color_to_white():
    photo = Image.new("RGB", (400, 600), "black")
    background = Image.new("RGB", (1000, 2000), "black")

    result = compose_photo_on_background(
        photo,
        background,
        message="Test",
        font_path=SAMARKAN_FONT_PATH,
    )

    text_zone = result.crop((50, 1450, 950, 1900))
    (min_r, max_r), (min_g, max_g), (min_b, max_b) = text_zone.getextrema()

    assert max_r > 150
    assert max_g > 150
    assert max_b > 150


def _rendered_text_bbox_area(image, crop_box):
    text_zone = image.crop(crop_box)
    diff = ImageChops.difference(text_zone, Image.new("RGB", text_zone.size, (0, 0, 0)))
    bbox = diff.getbbox()
    assert bbox is not None, "expected some rendered (non-black) text pixels"
    left, top, right, bottom = bbox
    return (right - left) * (bottom - top)


def test_compose_uses_a_fixed_font_size_when_given_instead_of_auto_fit():
    photo = Image.new("RGB", (400, 600), "black")
    background = Image.new("RGB", (1000, 2000), "black")
    crop_box = (0, 1450, 1000, 2000)

    small = compose_photo_on_background(
        photo, background, message="Test", font_path=SAMARKAN_FONT_PATH, font_size=20
    )
    large = compose_photo_on_background(
        photo, background, message="Test", font_path=SAMARKAN_FONT_PATH, font_size=80
    )

    assert _rendered_text_bbox_area(large, crop_box) > _rendered_text_bbox_area(small, crop_box)


def test_compose_ignores_fixed_font_size_when_font_file_is_invalid(tmp_path):
    photo = Image.new("RGB", (400, 600), "red")
    background = Image.new("RGB", (1000, 2000), "black")

    bad_font_path = tmp_path / "not_a_font.ttf"
    bad_font_path.write_bytes(b"this is not a valid font file")

    result = compose_photo_on_background(
        photo,
        background,
        message="Test",
        font_path=str(bad_font_path),
        font_size=40,
    )

    assert result.size == (1000, 2000)
