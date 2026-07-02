# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

```bash
# Start the server (sudo required for USB/PTP access to Canon camera)
sudo uv run python app.py
```

The app runs on **http://localhost:8080**. Gallery at **/gallery**.

## Architecture

**Bollywood-themed photobooth** using a Canon EOS 5D Mark II via gphoto2, with real-time face detection and CDN distribution.

### Backend (app.py)

Flask server with these responsibilities:
- **Live view streaming** (`/preview`): Runs `gphoto2 --capture-movie --stdout` as a persistent subprocess, parses JPEG frames from the raw byte stream (FFD8/FFD9 markers), serves as multipart MJPEG
- **Photo capture** (`/capture` POST): Stops live view → kills PTPCamera (macOS USB lock) → triggers `gphoto2 --capture-image-and-download` → uploads to SeaweedFS CDN → restarts live view
- **Filtered upload** (`/upload-filtered` POST): Receives canvas-composited photos (filter + props baked in) from the frontend
- **QR code generation** (`/qr/<filename>`): Generates QR codes pointing to CDN public URLs

The live view process is managed with `_liveview_proc` (subprocess) and `_liveview_lock` (threading.Lock) to prevent PTP conflicts between streaming and capture.

### Frontend (templates/index.html)

Single-page app with 4 screen states: live → countdown → processing → result.

- **Filters**: 8 CSS filters applied to live view via `style.filter`, baked into final photo via Canvas `ctx.filter`
- **Props**: SVG overlays (glasses, hat, mustache, crown, bow tie) positioned on MediaPipe Face Mesh landmarks (468 points). Dual processing: ~15fps on live view, one-shot on captured HD photo
- **Audio**: Web Audio API oscillators for countdown beeps (880Hz) and shutter sound (1320+1760Hz)
- **Composition**: After capture, frontend draws photo + filter + props onto a hidden canvas, exports as JPEG blob, uploads via `/upload-filtered`

### CDN (SeaweedFS)

- Upload: `https://admin-cdn.seo4.fun/photobooth/` (basic auth)
- Public: `https://cdn.seo4.fun/photobooth/`
- Credentials are in app.py (kiosk-mode deployment)

## Canon 5D Mark II Quirks

- **PTPCamera**: macOS auto-launches this daemon on USB connect, locking the device. Must `killall -9 PTPCamera` before every gphoto2 command. `disableHotPlug` is set via defaults.
- **PTP busy (0x2019)**: Camera needs time between operations. Live view stop → 0.3s pause → capture.
- **Mirror sounds**: Exiting live view causes one mirror slap, capture causes another. This is mechanical, not a bug.
- **Live view vs capture**: Cannot stream and capture simultaneously. The app stops the MJPEG subprocess, captures, then restarts it.

## Key Files

- `app.py` — Flask routes, gphoto2 subprocess management, CDN upload
- `templates/index.html` — Main UI: MediaPipe face mesh, filters, props, canvas composition, Web Audio
- `templates/gallery.html` — Photo gallery with lightbox and QR codes
- `static/props/*.svg` — Face prop overlays
- `photos/` — Local photo storage (auto-created)

## Dependencies

Managed with `uv`. Core: flask, pillow, qrcode, requests. External: gphoto2 CLI (system), MediaPipe JS (CDN-loaded).
