#!/usr/bin/env python3
"""Télécharge localement toutes les photos stockées sur le CDN SeaweedFS.

Usage:
    uv run python download_cdn_photos.py [DESTINATION_DIR]

DESTINATION_DIR est optionnel (défaut : cdn_downloads/). Le script est
idempotent : relancer plus tard ne re-télécharge que les fichiers manquants
ou dont la taille a changé sur le CDN.
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

CDN_UPLOAD_URL = os.getenv("CDN_UPLOAD_URL", "")
CDN_PUBLIC_URL = os.getenv("CDN_PUBLIC_URL", "")
CDN_AUTH = (os.getenv("CDN_USER", ""), os.getenv("CDN_PASSWORD", ""))

PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png")


def list_cdn_entries():
    """Retourne la liste des entrées (dicts avec FullPath/FileSize) du
    répertoire CDN, en paginant via l'API de listing du filer SeaweedFS."""
    entries = []
    last_filename = ""
    while True:
        params = {"lastFileName": last_filename} if last_filename else {}
        resp = requests.get(
            CDN_UPLOAD_URL,
            auth=CDN_AUTH,
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        entries.extend(data.get("Entries") or [])
        if not data.get("ShouldDisplayLoadMore"):
            break
        last_filename = data.get("LastFileName", "")
        if not last_filename:
            break
    return entries


def download_file(filename, dest_path):
    url = CDN_PUBLIC_URL + filename
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)


def main():
    if not CDN_UPLOAD_URL or not CDN_PUBLIC_URL:
        print("⚠️  CDN_UPLOAD_URL / CDN_PUBLIC_URL manquant dans .env")
        sys.exit(1)

    dest_dir = sys.argv[1] if len(sys.argv) > 1 else "cdn_downloads"
    os.makedirs(dest_dir, exist_ok=True)

    print(f"📡 Listing des fichiers sur le CDN...")
    entries = list_cdn_entries()
    photos = [
        e for e in entries
        if e["FullPath"].lower().endswith(PHOTO_EXTENSIONS)
    ]
    skipped = len(entries) - len(photos)
    print(f"📷 {len(photos)} photo(s) trouvée(s)" + (f" ({skipped} fichier(s) non-photo ignoré(s))" if skipped else ""))

    downloaded, already_present, failed = 0, 0, 0
    for i, entry in enumerate(photos, 1):
        filename = entry["FullPath"].rsplit("/", 1)[-1]
        dest_path = os.path.join(dest_dir, filename)
        remote_size = entry.get("FileSize", 0)

        if os.path.isfile(dest_path) and os.path.getsize(dest_path) == remote_size:
            already_present += 1
            continue

        print(f"  [{i}/{len(photos)}] {filename}...", end=" ", flush=True)
        try:
            download_file(filename, dest_path)
            print("OK")
            downloaded += 1
        except Exception as e:
            print(f"ÉCHEC ({e})")
            failed += 1

    print()
    print(f"✅ {downloaded} téléchargée(s), {already_present} déjà présente(s), {failed} échec(s)")
    print(f"📁 Dossier : {os.path.abspath(dest_dir)}")


if __name__ == "__main__":
    main()
