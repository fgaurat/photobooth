#!/usr/bin/env python3
"""Photobooth — Canon EOS 5D Mark II (gphoto2) ou webcam (OpenCV)."""

import io
import os
import subprocess
import threading
import time
from datetime import datetime

import qrcode
import requests
from dotenv import load_dotenv
from photo_compositing import compose_photo_on_background
from flask import Flask, render_template, jsonify, send_from_directory, send_file, Response, request

load_dotenv()

app = Flask(__name__)
PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

# --- Configuration depuis .env ---
CAMERA_MODE = os.getenv("CAMERA_MODE", "canon")  # "canon" ou "webcam"
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "0"))
PORT = int(os.getenv("PORT", "8080"))

AUTOFOCUS_MODE = os.getenv("AUTOFOCUS_MODE", "off")  # "each", "startup", "off"
COUNTDOWN_STRIP = int(os.getenv("COUNTDOWN_STRIP", "5"))
KEEP_ON_CAMERA = os.getenv("KEEP_ON_CAMERA", "true").lower() == "true"
MIRROR_LIVEVIEW = os.getenv("MIRROR_LIVEVIEW", "true").lower() == "true"
MIRROR_DISPLAY = os.getenv("MIRROR_DISPLAY", "false").lower() == "true"
ENABLE_FACE_PROPS = os.getenv("ENABLE_FACE_PROPS", "false").lower() == "true"
BACKGROUNDS_DIR = os.path.join(os.path.dirname(__file__), "static", "backgrounds")
FONTS_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
PHOTO_BACKGROUND = os.getenv("PHOTO_BACKGROUND", "black.png")
PHOTO_MESSAGE = os.getenv("PHOTO_MESSAGE", "").replace("\\n", "\n")
PHOTO_MESSAGE_FONT = os.getenv("PHOTO_MESSAGE_FONT", "")
PHOTO_MESSAGE_COLOR = os.getenv("PHOTO_MESSAGE_COLOR", "white")
_photo_message_size = os.getenv("PHOTO_MESSAGE_SIZE", "")
PHOTO_MESSAGE_SIZE = int(_photo_message_size) if _photo_message_size else None
PHOTO_MESSAGE_ZONE = float(os.getenv("PHOTO_MESSAGE_ZONE", "0.20"))

CDN_UPLOAD_URL = os.getenv("CDN_UPLOAD_URL", "")
CDN_PUBLIC_URL = os.getenv("CDN_PUBLIC_URL", "")
CDN_AUTH = (os.getenv("CDN_USER", ""), os.getenv("CDN_PASSWORD", ""))

# =============================================
# CANON (gphoto2)
# =============================================

_liveview_proc = None
_liveview_lock = threading.Lock()


def _canon_start_liveview():
    global _liveview_proc
    with _liveview_lock:
        if _liveview_proc and _liveview_proc.poll() is None:
            return
        subprocess.run(["killall", "-9", "PTPCamera"], capture_output=True)
        subprocess.run(["killall", "-9", "gphoto2"], capture_output=True)
        time.sleep(1.0)
        _liveview_proc = subprocess.Popen(
            ["gphoto2", "--capture-movie", "--stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        print("📡 Live view Canon démarré")


def _canon_stop_liveview():
    global _liveview_proc
    with _liveview_lock:
        if _liveview_proc and _liveview_proc.poll() is None:
            _liveview_proc.terminate()
            _liveview_proc.wait(timeout=5)
            _liveview_proc = None


def _canon_preview_generate():
    buf = b""
    while True:
        if _liveview_proc is None or _liveview_proc.poll() is not None:
            break
        chunk = _liveview_proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while True:
            start = buf.find(b"\xff\xd8")
            end = buf.find(b"\xff\xd9", start + 2) if start != -1 else -1
            if start == -1 or end == -1:
                break
            frame = buf[start:end + 2]
            buf = buf[end + 2:]
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )


def _canon_autofocus():
    """Déclenche l'autofocus du Canon."""
    print("🔍 Autofocus...")
    result = subprocess.run(
        ["gphoto2", "--set-config", "autofocusdrive=1"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        print("✅ Autofocus OK")
    else:
        print(f"⚠️  Autofocus échoué: {result.stderr.strip()}")
    time.sleep(0.3)


def _canon_prepare():
    print("⏹  Arrêt du live view Canon...")
    _canon_stop_liveview()
    subprocess.run(["killall", "-9", "PTPCamera"], capture_output=True)
    time.sleep(0.3)
    if AUTOFOCUS_MODE == "each":
        _canon_autofocus()


def _canon_capture():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"photo_{timestamp}.jpg"
    filepath = os.path.join(PHOTOS_DIR, filename)

    cmd = [
        "gphoto2",
        "--capture-image-and-download",
        "--filename", filepath,
        "--force-overwrite",
    ]
    if not KEEP_ON_CAMERA:
        cmd.insert(2, "--no-keep")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    print(f"✅ Canon : {filename}")
    return filename, filepath


def _canon_resume():
    _canon_start_liveview()


# =============================================
# WEBCAM (OpenCV)
# =============================================

_webcam = None
_webcam_lock = threading.Lock()


def _webcam_open():
    import cv2

    global _webcam
    with _webcam_lock:
        if _webcam is not None and _webcam.isOpened():
            return
        print(f"📷 Ouverture webcam {WEBCAM_INDEX}...")
        _webcam = cv2.VideoCapture(WEBCAM_INDEX)
        _webcam.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        _webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)


def _webcam_close():
    global _webcam
    with _webcam_lock:
        if _webcam is not None:
            _webcam.release()
            _webcam = None


def _webcam_preview_generate():
    import cv2

    _webcam_open()
    while True:
        with _webcam_lock:
            if _webcam is None or not _webcam.isOpened():
                break
            ret, frame = _webcam.read()
        if not ret:
            time.sleep(0.05)
            continue
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        )
        time.sleep(0.033)  # ~30 fps


def _webcam_prepare():
    pass  # pas besoin de stopper la webcam


def _webcam_capture():
    import cv2

    _webcam_open()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"photo_{timestamp}.jpg"
    filepath = os.path.join(PHOTOS_DIR, filename)

    with _webcam_lock:
        if _webcam is None or not _webcam.isOpened():
            raise RuntimeError("Webcam non disponible")
        ret, frame = _webcam.read()

    if not ret:
        raise RuntimeError("Impossible de capturer une image depuis la webcam")

    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"✅ Webcam : {filename}")
    return filename, filepath


def _webcam_resume():
    pass  # la webcam reste ouverte


# =============================================
# DISPATCH selon le mode
# =============================================

def start_preview():
    if CAMERA_MODE == "canon":
        _canon_start_liveview()
    else:
        _webcam_open()


def stop_preview():
    if CAMERA_MODE == "canon":
        _canon_stop_liveview()
    else:
        pass


def prepare_camera():
    if CAMERA_MODE == "canon":
        _canon_prepare()
    else:
        _webcam_prepare()


def do_single_capture():
    if CAMERA_MODE == "canon":
        return _canon_capture()
    else:
        return _webcam_capture()


def resume_preview():
    if CAMERA_MODE == "canon":
        _canon_resume()
    else:
        _webcam_resume()


# =============================================
# ROUTES
# =============================================

@app.route("/")
def index():
    return render_template(
        "index.html",
        countdown_strip=COUNTDOWN_STRIP,
        mirror_liveview=MIRROR_LIVEVIEW,
        mirror_display=MIRROR_DISPLAY,
        enable_face_props=ENABLE_FACE_PROPS,
    )


@app.route("/preview-thumb")
def preview_thumb():
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (100, 100), (80, 80, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.route("/preview")
def preview_stream():
    if CAMERA_MODE == "canon":
        _canon_start_liveview()
        gen = _canon_preview_generate()
    else:
        gen = _webcam_preview_generate()

    return Response(gen, mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/capture", methods=["POST"])
def capture():
    try:
        prepare_camera()
        print("📸 Capture...")
        filename, filepath = do_single_capture()
        upload_to_cdn_async(filepath, filename)
        resume_preview()
        return jsonify({"filename": filename})

    except subprocess.TimeoutExpired:
        resume_preview()
        return jsonify({"error": "Timeout — l'appareil ne répond pas"}), 500
    except Exception as e:
        resume_preview()
        return jsonify({"error": str(e)}), 500


@app.route("/strip-start", methods=["POST"])
def strip_start():
    try:
        if CAMERA_MODE == "canon":
            _canon_stop_liveview()
            subprocess.run(["killall", "-9", "PTPCamera"], capture_output=True)
            time.sleep(1.0)
        return jsonify({"ok": True})
    except Exception as e:
        resume_preview()
        return jsonify({"error": str(e)}), 500


@app.route("/strip-shot", methods=["POST"])
def strip_shot():
    try:
        print("📸 Strip shot...")
        filename, filepath = do_single_capture()
        upload_to_cdn_async(filepath, filename)
        return jsonify({"filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/strip-end", methods=["POST"])
def strip_end():
    resume_preview()
    return jsonify({"ok": True})


STRIP_TEMPLATE = os.path.join(os.path.dirname(__file__), "static", "strip_template.png")

# Positions des 4 photos dans le template (x, y, largeur, hauteur)
STRIP_SLOTS = [
    (60, 60, 728, 598),
    (812, 60, 728, 598),
    (60, 682, 728, 598),
    (812, 682, 728, 598),
]


def crop_to_fill(img, target_w, target_h):
    """Redimensionne et crope au centre pour remplir exactement target_w x target_h."""
    from PIL import Image as PILImage
    src_ratio = img.width / img.height
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_h = target_h
        new_w = int(img.width * target_h / img.height)
    else:
        new_w = target_w
        new_h = int(img.height * target_w / img.width)
    resized = img.resize((new_w, new_h), PILImage.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


@app.route("/assemble-strip", methods=["POST"])
def assemble_strip():
    from PIL import Image as PILImage

    data = request.get_json()
    filenames = data.get("filenames", [])
    if not filenames:
        return jsonify({"error": "Pas de photos"}), 400

    images = []
    for fname in filenames:
        fpath = os.path.join(PHOTOS_DIR, fname)
        if os.path.exists(fpath):
            images.append(PILImage.open(fpath))

    if not images:
        return jsonify({"error": "Aucune photo trouvée"}), 400

    template = PILImage.open(STRIP_TEMPLATE).convert("RGB")

    for i, img in enumerate(images):
        if i >= len(STRIP_SLOTS):
            break
        x, y, w, h = STRIP_SLOTS[i]
        cropped = crop_to_fill(img, w, h)
        template.paste(cropped, (x, y))
        cropped.close()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    strip_filename = f"strip_{timestamp}.jpg"
    strip_path = os.path.join(PHOTOS_DIR, strip_filename)
    template.save(strip_path, "JPEG", quality=92)

    for img in images:
        img.close()
    template.close()

    print(f"✅ Planche : {strip_filename}")
    upload_to_cdn_async(strip_path, strip_filename)
    return jsonify({"filename": strip_filename})


_cdn_status = {}


def upload_to_cdn(filepath, filename):
    if not CDN_UPLOAD_URL:
        return
    _cdn_status[filename] = "pending"
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                CDN_UPLOAD_URL + filename,
                files={"file": (filename, f, "image/jpeg")},
                auth=CDN_AUTH,
                timeout=30,
            )
            resp.raise_for_status()
        _cdn_status[filename] = "done"
        print(f"☁️  CDN OK : {filename}")
    except Exception as e:
        _cdn_status[filename] = "error"
        print(f"⚠️  Upload CDN échoué: {e}")


def upload_to_cdn_async(filepath, filename):
    threading.Thread(target=upload_to_cdn, args=(filepath, filename), daemon=True).start()


@app.route("/cdn-status/<path:filename>")
def cdn_status(filename):
    return jsonify({"status": _cdn_status.get(filename, "unknown")})


@app.route("/qr/<path:filename>")
def qr_code(filename):
    url = CDN_PUBLIC_URL + filename
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


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
                photo,
                background,
                message=PHOTO_MESSAGE,
                font_path=font_path,
                color=PHOTO_MESSAGE_COLOR,
                font_size=PHOTO_MESSAGE_SIZE,
                text_zone_ratio=PHOTO_MESSAGE_ZONE,
            )
            composed.save(filepath, "JPEG", quality=92)
    except Exception as e:
        print(f"⚠️  Composition fond échouée : {e}")


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


@app.route("/photos/<path:filename>")
def serve_photo(filename):
    return send_from_directory(PHOTOS_DIR, filename)


@app.route("/photos/preview/<path:filename>")
def serve_photo_preview(filename):
    from PIL import Image as PILImage

    filepath = os.path.join(PHOTOS_DIR, filename)
    if not os.path.exists(filepath):
        return "Not found", 404

    img = PILImage.open(filepath)
    img.thumbnail((1280, 1280), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    img.close()
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.route("/gallery")
def gallery_page():
    return render_template("gallery.html")


@app.route("/api/gallery")
def gallery_api():
    files = sorted(
        [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith((".jpg", ".jpeg", ".cr2"))],
        reverse=True,
    )
    return jsonify(files)


if __name__ == "__main__":
    print(f"📸 Photobooth démarré en mode [{CAMERA_MODE}] — AF: {AUTOFOCUS_MODE} — photos dans {PHOTOS_DIR}")
    if CAMERA_MODE == "canon" and AUTOFOCUS_MODE == "startup":
        subprocess.run(["killall", "-9", "PTPCamera"], capture_output=True)
        time.sleep(0.3)
        _canon_autofocus()
    app.run(host="0.0.0.0", port=PORT, debug=True)
