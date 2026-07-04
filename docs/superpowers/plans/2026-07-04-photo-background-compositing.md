# Photo Background Compositing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Composite the single-photo output onto a configurable decorative background with a configurable text message, server-side, without touching the strip x4 mode.

**Architecture:** A new pure, dependency-free module `photo_compositing.py` implements the image math (resize/paste/auto-fit text) and is unit-tested with pytest. `app.py`'s `/upload-filtered` route calls into it only when the frontend explicitly signals single-photo mode via a new `apply_background` form field, falling back to today's raw-save behavior on any missing asset or error. The frontend (`templates/index.html`) is updated to always request background compositing for single photos (even with the default "Normal" filter) and never for strip poses.

**Tech Stack:** Python 3.8, Flask, Pillow (PIL), pytest (new dev dependency), vanilla JS (existing frontend).

## Global Constraints

- Applies **only** to single-photo mode (`startSingleCapture` / `/upload-filtered` with `apply_background=1`). Strip mode (`/strip-shot`, `/assemble-strip`, `STRIP_SLOTS`) must remain byte-for-byte unaffected.
- All compositing happens **server-side** (PIL) — never add canvas work for this feature in the browser.
- New `.env` config, read the same way as existing flags in `app.py`: `PHOTO_BACKGROUND` (default `black.png`), `PHOTO_MESSAGE` (default empty string), `PHOTO_MESSAGE_FONT` (default empty string).
- Layout is percentage-based on the background's own dimensions: side margins 12% each, top margin 5%, bottom margin 5%.
- The photo is resized preserving its aspect ratio and is never cropped.
- The message is drawn as a single line, white, auto-shrunk to fit the available width/height; if `PHOTO_MESSAGE` is empty or `PHOTO_MESSAGE_FONT` is empty/missing on disk, no text is drawn — no error.
- A missing background file, missing font, or any unexpected error during compositing must fall back to saving the raw uploaded photo (today's behavior) and log a warning — capturing a photo must never fail because of this feature.
- Test placeholder asset: `static/backgrounds/black.png`, solid black, portrait, **3744×5616** px.

---

### Task 1: `fit_font_size` — auto-fit text sizing (TDD)

**Files:**
- Create: `photo_compositing.py`
- Create: `tests/test_photo_compositing.py`
- Modify: `pyproject.toml` (add pytest dev dependency + pytest config)

**Interfaces:**
- Produces: `fit_font_size(font_loader, text, max_width, max_height, min_size=10, max_size=500) -> PIL.ImageFont.FreeTypeFont` — `font_loader` is a callable `size:int -> ImageFont.FreeTypeFont`. Returns the largest font (by point size, searched from `max_size` down to `min_size`) whose rendered `text` bounding box fits within `max_width` x `max_height`. Falls back to `font_loader(min_size)` if nothing fits.

- [ ] **Step 1: Add pytest as a dev dependency**

Run: `uv add --dev pytest`
Expected: `pyproject.toml` gains a `[dependency-groups]` (or `[tool.uv] dev-dependencies`) entry for `pytest`, and `uv.lock` is updated.

- [ ] **Step 2: Configure pytest to find the top-level module**

Add this to `pyproject.toml` (new section, anywhere after `[project]`):

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

This is required because `tests/` has no `__init__.py`, so pytest would otherwise only add `tests/` (not the repo root) to `sys.path`, and `import photo_compositing` would fail.

- [ ] **Step 3: Write the failing test**

Create `tests/test_photo_compositing.py`:

```python
from PIL import Image, ImageDraw, ImageFont

from photo_compositing import fit_font_size


def _measure(text, font):
    scratch = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(scratch)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def test_fit_font_size_fits_within_a_narrow_box():
    font_loader = lambda size: ImageFont.load_default(size=size)

    font = fit_font_size(font_loader, "Anniversaire de Laura", max_width=100, max_height=40)

    width, height = _measure("Anniversaire de Laura", font)
    assert width <= 100
    assert height <= 40


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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_photo_compositing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'photo_compositing'`

- [ ] **Step 5: Write the minimal implementation**

Create `photo_compositing.py`:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_photo_compositing.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock photo_compositing.py tests/test_photo_compositing.py
git commit -m "Add fit_font_size helper with pytest test coverage"
```

---

### Task 2: `compose_photo_on_background` (TDD)

**Files:**
- Modify: `photo_compositing.py`
- Modify: `tests/test_photo_compositing.py`

**Interfaces:**
- Consumes: `fit_font_size(font_loader, text, max_width, max_height, min_size=10, max_size=500)` from Task 1.
- Produces: `compose_photo_on_background(photo, background, message="", font_path=None, side_margin_ratio=0.12, top_margin_ratio=0.05, bottom_margin_ratio=0.05) -> PIL.Image.Image` — `photo` and `background` are already-opened `PIL.Image.Image` objects. Returns a new RGB image the same size as `background`, with `photo` (EXIF-corrected, aspect-preserved, resized) pasted centered inside the margin-defined window, and `message` drawn centered below it if `message` is non-empty and `font_path` points to an existing file. Never raises on a missing/invalid `font_path` — silently skips drawing text.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_photo_compositing.py`:

```python
from photo_compositing import compose_photo_on_background


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_photo_compositing.py -v`
Expected: FAIL with `ImportError: cannot import name 'compose_photo_on_background'`

- [ ] **Step 3: Write the minimal implementation**

Replace the contents of `photo_compositing.py` with:

```python
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
    side_margin_ratio=0.12,
    top_margin_ratio=0.05,
    bottom_margin_ratio=0.05,
):
    """Return a new RGB image: `photo` resized (aspect ratio preserved,
    never cropped) and centered on a copy of `background`, with `message`
    optionally drawn centered below it using the font at `font_path`."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    canvas = background.convert("RGB").copy()
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
            font = fit_font_size(
                lambda size: ImageFont.truetype(font_path, size),
                message,
                window_w,
                text_zone_height,
            )
            draw = ImageDraw.Draw(canvas)
            left, top, right, bottom = draw.textbbox((0, 0), message, font=font)
            text_w = right - left
            text_h = bottom - top
            text_x = side_margin + (window_w - text_w) / 2 - left
            text_y = text_zone_top + (text_zone_height - text_h) / 2 - top
            draw.text((text_x, text_y), message, font=font, fill="white")

    return canvas
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_photo_compositing.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add photo_compositing.py tests/test_photo_compositing.py
git commit -m "Add compose_photo_on_background for the single-photo frame feature"
```

---

### Task 3: Wire compositing into the Flask backend

**Files:**
- Modify: `app.py:33` (config block)
- Modify: `app.py:454-463` (`/upload-filtered` route)
- Create: `static/backgrounds/black.png` (via a one-off command, not a permanent script)
- Create: `static/fonts/.gitkeep`

**Interfaces:**
- Consumes: `compose_photo_on_background(photo, background, message="", font_path=None, ...)` from Task 2.
- Produces: `apply_photo_background(filepath: str) -> None` in `app.py` — opens the file at `filepath` in place, composites it against the configured background/message/font if available, and overwrites `filepath` with the result. Never raises — logs and returns on any failure.

- [ ] **Step 1: Create the folders and the test background asset**

Run:
```bash
mkdir -p static/backgrounds static/fonts
touch static/fonts/.gitkeep
uv run python -c "from PIL import Image; Image.new('RGB', (3744, 5616), 'black').save('static/backgrounds/black.png')"
```
Expected: `static/backgrounds/black.png` exists; `file static/backgrounds/black.png` reports `PNG image data, 3744 x 5616`.

- [ ] **Step 2: Add the new config variables**

In `app.py`, right after line 33 (`ENABLE_FACE_PROPS = ...`), add:

```python
BACKGROUNDS_DIR = os.path.join(os.path.dirname(__file__), "static", "backgrounds")
FONTS_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
PHOTO_BACKGROUND = os.getenv("PHOTO_BACKGROUND", "black.png")
PHOTO_MESSAGE = os.getenv("PHOTO_MESSAGE", "")
PHOTO_MESSAGE_FONT = os.getenv("PHOTO_MESSAGE_FONT", "")
```

Add this import near the top of `app.py`, with the other project-local/third-party imports (after the `from dotenv import load_dotenv` line):

```python
from photo_compositing import compose_photo_on_background
```

- [ ] **Step 3: Add the `apply_photo_background` helper**

In `app.py`, directly above the `/upload-filtered` route (before line 454), add:

```python
def apply_photo_background(filepath):
    background_path = os.path.join(BACKGROUNDS_DIR, PHOTO_BACKGROUND)
    if not os.path.isfile(background_path):
        print(f"⚠️  Fond introuvable : {background_path}")
        return

    from PIL import Image as PILImage

    font_path = os.path.join(FONTS_DIR, PHOTO_MESSAGE_FONT) if PHOTO_MESSAGE_FONT else None

    try:
        with PILImage.open(filepath) as photo, PILImage.open(background_path) as background:
            composed = compose_photo_on_background(
                photo, background, message=PHOTO_MESSAGE, font_path=font_path
            )
            composed.save(filepath, "JPEG", quality=92)
    except Exception as e:
        print(f"⚠️  Composition fond échouée : {e}")
```

(The local `from PIL import Image as PILImage` matches the existing lazy-import style already used elsewhere in `app.py`, e.g. in `assemble_strip`.)

- [ ] **Step 4: Wire it into the route**

Replace the `/upload-filtered` route (`app.py:454-463`):

```python
@app.route("/upload-filtered", methods=["POST"])
def upload_filtered():
    if "file" not in request.files:
        return jsonify({"error": "Pas de fichier"}), 400
    f = request.files["file"]
    filename = request.form.get("filename", f"filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    filepath = os.path.join(PHOTOS_DIR, filename)
    f.save(filepath)

    if request.form.get("apply_background") == "1":
        apply_photo_background(filepath)

    upload_to_cdn_async(filepath, filename)
    return jsonify({"filename": filename})
```

- [ ] **Step 5: Verify the route manually with curl**

Start the server in another terminal: `CAMERA_MODE=webcam uv run python app.py`

Then run, from the repo root:
```bash
curl -s -F "file=@photos/photo_20260704_162953_360619.jpg" -F "filename=bg_test.jpg" -F "apply_background=1" http://localhost:8080/upload-filtered
uv run python -c "from PIL import Image; print(Image.open('photos/bg_test.jpg').size)"
```
Expected: the curl call returns `{"filename":"bg_test.jpg"}`, and the printed size is `(3744, 5616)` (the background's size, proving the photo was composited onto it rather than saved raw).

- [ ] **Step 6: Commit**

```bash
git add app.py static/backgrounds/black.png static/fonts/.gitkeep
git commit -m "Composite single-photo uploads onto a configurable background"
```

---

### Task 4: Frontend — request background compositing only for single-photo mode

**Files:**
- Modify: `templates/index.html:1155-1177` (`startSingleCapture`)
- Modify: `templates/index.html:1179-1245` (`startStripCapture`)
- Modify: `templates/index.html:1261-1335` (`composeFinalPhoto`)

**Interfaces:**
- Consumes: `POST /upload-filtered` now accepts an `apply_background` form field (`'1'`/`'0'`) from Task 3.
- Produces: `composeFinalPhoto(originalFilename, filterCss, prop, applyBackground)` — 4th parameter added; callers must pass `true` for single-photo captures and `false` for strip poses.

- [ ] **Step 1: Update `composeFinalPhoto`'s signature and short-circuit condition**

In `templates/index.html`, find (around line 1261-1263):

```javascript
    async function composeFinalPhoto(originalFilename, filterCss, prop) {
      const needsProcessing = filterCss !== 'none' || prop.src;
      if (!needsProcessing) return originalFilename;
```

Replace with:

```javascript
    async function composeFinalPhoto(originalFilename, filterCss, prop, applyBackground) {
      const needsProcessing = filterCss !== 'none' || prop.src || applyBackground;
      if (!needsProcessing) return originalFilename;
```

- [ ] **Step 2: Send the flag to the server**

In the same function, find (around line 1330-1333):

```javascript
      const form = new FormData();
      form.append('file', blob, finalName);
      form.append('filename', finalName);
      await fetch('/upload-filtered', { method: 'POST', body: form });
```

Replace with:

```javascript
      const form = new FormData();
      form.append('file', blob, finalName);
      form.append('filename', finalName);
      form.append('apply_background', applyBackground ? '1' : '0');
      await fetch('/upload-filtered', { method: 'POST', body: form });
```

- [ ] **Step 3: Pass `true` from single-photo capture**

In `startSingleCapture` (around line 1165), find:

```javascript
        const finalFilename = await composeFinalPhoto(data.filename, filterCss, prop);
```

Replace with:

```javascript
        const finalFilename = await composeFinalPhoto(data.filename, filterCss, prop, true);
```

- [ ] **Step 4: Pass `false` from strip capture**

In `startStripCapture` (around line 1222), find:

```javascript
          const finalFile = await composeFinalPhoto(fname, filterCss, prop);
```

Replace with:

```javascript
          const finalFile = await composeFinalPhoto(fname, filterCss, prop, false);
```

- [ ] **Step 5: Manual verification in the browser**

With the server running (`CAMERA_MODE=webcam uv run python app.py`):
1. Open `http://localhost:8080`, capture a single photo with the default "Normal" filter.
2. Confirm the result screen shows the photo on the black background (not the raw webcam frame edge-to-edge).
3. Switch to "Planche x4", capture a strip.
4. Confirm the assembled strip still uses `strip_template.png` exactly as before (no black background/message anywhere in the strip).

- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "Send apply_background flag from single-photo capture only"
```

---

### Task 5: Config defaults and end-to-end verification

**Files:**
- Modify: `.env`

**Interfaces:**
- None (final integration task).

- [ ] **Step 1: Add the new variables to `.env`**

Append to `.env` (near the other display-related settings, e.g. after `MIRROR_DISPLAY`):

```dotenv
# Fond décoratif appliqué derrière la photo unique (fichier dans static/backgrounds/)
PHOTO_BACKGROUND=black.png

# Message affiché sous la photo (vide = pas de message)
PHOTO_MESSAGE=Anniversaire de Laura

# Police du message (fichier .ttf/.otf dans static/fonts/, vide = pas de message dessiné)
PHOTO_MESSAGE_FONT=
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass (6 from Tasks 1-2, no regressions).

- [ ] **Step 3: End-to-end manual check with a real capture**

With `CAMERA_MODE=webcam uv run python app.py` running:
1. Capture a single photo. Confirm the result photo shows your webcam frame resized and centered on the black background, with no message text (since `PHOTO_MESSAGE_FONT` is still empty — no font file provided yet).
2. Rename/point `PHOTO_BACKGROUND` to a nonexistent file temporarily (e.g. `PHOTO_BACKGROUND=missing.png`), restart the server, capture again, and confirm the capture still succeeds (falls back to the raw photo, check the server console for the `⚠️  Fond introuvable` warning). Revert `PHOTO_BACKGROUND` to `black.png` afterwards.

- [ ] **Step 4: Commit**

```bash
git add .env
git commit -m "Add default PHOTO_BACKGROUND/PHOTO_MESSAGE/PHOTO_MESSAGE_FONT config"
```
