#!/usr/bin/env bash
# Lance le photobooth en empêchant le Mac de se mettre en veille (écran
# fermé ou non). Nécessite une alimentation secteur + un écran externe
# branché pour pouvoir fermer le capot (mode "clamshell" macOS).
#
# sudo n'est utilisé qu'en mode Canon (accès USB PTP) — pas en mode webcam,
# pour éviter de créer des fichiers appartenant à root dans photos/.
set -euo pipefail

cd "$(dirname "$0")"

camera_mode=$(grep -E '^CAMERA_MODE=' .env 2>/dev/null | tail -1 | cut -d= -f2)

if [ "$camera_mode" = "canon" ]; then
  exec caffeinate -d -i -s sudo uv run python app.py
else
  exec caffeinate -d -i -s uv run python app.py
fi
