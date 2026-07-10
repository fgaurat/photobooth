# Photobooth Bollywood

Photobooth de mariage / événement avec détection de visage, filtres, accessoires SVG et upload CDN. Prend en charge un Canon EOS 5D Mark II (via `gphoto2`) ou une simple webcam (via OpenCV).

## Fonctionnalités

- **Live view MJPEG** en plein écran
- **Décompte animé** superposé au live view + son de bip
- **Freeze de la dernière frame** pendant le traitement ("Gardez la pose !")
- **Filtres CSS** (N&B, sépia, vintage, etc.) appliqués au live view *et* baked dans la photo finale
- **Props SVG** (lunettes, chapeau, moustache, couronne, nœud pap') positionnés en temps réel via MediaPipe Face Mesh (468 points)
- **Mode planche x4** : 4 poses guidées avec décompte configurable, assemblées sur un cadre décoratif Bollywood
- **QR code** pointant vers l'URL publique CDN de la photo
- **Upload CDN asynchrone** (SeaweedFS) + indicateur d'état discret
- **Galerie** avec lightbox et QR code par photo
- **Miroir configurable** (live view et/ou affichage résultat, indépendamment)

## Prérequis

- macOS ou Linux
- Python ≥ 3.8, [`uv`](https://docs.astral.sh/uv/) pour la gestion des dépendances
- Pour le mode Canon : `gphoto2` (CLI) installé sur le système (`brew install gphoto2`)
- Pour le mode webcam : OpenCV, à installer via l'extra `webcam` (voir Installation) — les wheels ne sont pas disponibles pour toutes les plateformes/versions d'OS (ex. macOS ancien sur Intel), d'où l'installation séparée

## Installation

```bash
git clone <repo>
cd photobooth
uv sync                    # mode Canon uniquement
uv sync --extra webcam     # ajoute OpenCV si tu comptes utiliser le mode webcam
cp .env.example .env  # à créer si absent, cf. section Configuration
```

## Lancement

```bash
# Mode Canon (accès USB PTP → sudo requis sur macOS)
sudo uv run python app.py

# Mode webcam (pas de sudo)
uv run python app.py
```

L'app écoute sur **http://localhost:8080**. Galerie sur **/gallery**.

### Empêcher la mise en veille (déploiement événementiel)

`./start.sh` lance l'app avec [`caffeinate`](https://ss64.com/mac/caffeinate.html), pour que le Mac ne se mette jamais en veille (écran fermé ou non) tant que le photobooth tourne :

```bash
./start.sh
```

Le mode (Canon/webcam, et donc le besoin de `sudo`) est lu automatiquement depuis `CAMERA_MODE` dans `.env`.

Pour pouvoir fermer le capot (mode "clamshell" macOS) sans que le Mac ne s'éteigne, il faut en plus :
- le Mac branché sur secteur (pas sur batterie)
- un écran externe connecté et actif

Depuis macOS Monterey, aucun clavier/souris externe n'est requis pour ça — juste l'alimentation et l'écran externe.

## Configuration (`.env`)

```dotenv
# Mode caméra : "canon" (gphoto2) ou "webcam" (OpenCV)
CAMERA_MODE=canon
WEBCAM_INDEX=0                    # index si mode webcam

# Autofocus Canon : "each" | "startup" | "off"
AUTOFOCUS_MODE=each

# Garder les photos sur la carte SD après download
KEEP_ON_CAMERA=false

# Décompte par pose en mode planche (secondes)
COUNTDOWN_STRIP=3

# Effet miroir
MIRROR_LIVEVIEW=false             # pendant la prise
MIRROR_DISPLAY=false              # sur l'écran résultat

# Serveur
PORT=8080

# CDN SeaweedFS
CDN_UPLOAD_URL=https://admin-cdn.example.com/photobooth/
CDN_PUBLIC_URL=https://cdn.example.com/photobooth/
CDN_USER=admin
CDN_PASSWORD=xxxxx
```

## Architecture

### Backend (`app.py`)

Flask, avec un dispatch caméra Canon / webcam :

| Route | Rôle |
|---|---|
| `/` | UI principale (SPA) |
| `/preview` | Flux MJPEG live view |
| `/capture` | Photo unique |
| `/strip-start`, `/strip-shot`, `/strip-end` | Séquence planche x4 (prépare une fois, tire N fois, reprend le live) |
| `/assemble-strip` | Compose les 4 photos sur le cadre Bollywood |
| `/upload-filtered` | Reçoit la photo composée côté canvas (filtre + props) |
| `/qr/<file>` | QR code vers l'URL CDN publique |
| `/cdn-status/<file>` | État de l'upload asynchrone |
| `/gallery`, `/api/gallery`, `/photos/<file>`, `/photos/preview/<file>` | Galerie |

Le process live view Canon (`gphoto2 --capture-movie --stdout`) est géré via `_liveview_proc` + `threading.Lock` pour éviter les conflits PTP entre stream et capture.

### Frontend (`templates/index.html`)

SPA à 4 états : **live → countdown → processing → result**.

- **Filtres** : 8 filtres CSS appliqués via `style.filter` au live, puis via `ctx.filter` sur canvas pour la photo finale
- **Props** : SVG overlays positionnés sur les landmarks Face Mesh. ~15 fps sur le live, one-shot HD sur la photo capturée
- **Audio** : Web Audio API (bips de décompte 880 Hz, shutter 1320+1760 Hz)
- **Composition** : après capture, le frontend compose photo + filtre + props sur un canvas caché → JPEG blob → `POST /upload-filtered`

### CDN (SeaweedFS)

Upload en tâche de fond (thread daemon), l'UI n'est jamais bloquée. Un point d'état (`pending`/`done`/`error`) s'affiche discrètement sur l'écran résultat.

## Mode planche x4 (Bollywood)

Cadre décoré (fond violet profond, bordures dorées, losanges or/magenta) généré dans `static/strip_template.png` (1600×1340). Les 4 emplacements sont définis par `STRIP_SLOTS` dans `app.py` :

```python
STRIP_SLOTS = [
    (60, 60, 728, 598),    # haut gauche
    (812, 60, 728, 598),   # haut droit
    (60, 682, 728, 598),   # bas gauche
    (812, 682, 728, 598),  # bas droit
]
```

Chaque photo est cropée au centre pour remplir exactement son slot (`crop_to_fill`).

## Quirks Canon 5D Mark II (macOS)

- **PTPCamera** : le daemon macOS s'accroche à l'USB à chaque connexion → `killall -9 PTPCamera` avant chaque commande `gphoto2`
- **PTP busy (0x2019)** : il faut ~0.3s à 1s entre stop live view et capture
- **Mirror slap** : quitter le live view = 1 clac mécanique, capture = 1 autre. C'est mécanique, pas un bug.
- **Live view + capture** : mutuellement exclusifs. Le live est stoppé le temps de la capture, puis redémarré.
- **Carte SD pleine** → l'appareil passe en état "busy" persistant qui ne se règle qu'au reboot physique. Mettre `KEEP_ON_CAMERA=false` pour libérer au fil de l'eau.

## Fichiers clés

```
app.py                          # Backend Flask + gestion caméra
templates/index.html            # UI principale (live, filtres, props, planche)
templates/gallery.html          # Galerie avec lightbox + QR
static/props/*.svg              # Accessoires (lunettes, chapeau, etc.)
static/strip_template.png       # Cadre Bollywood de la planche x4
photos/                         # Stockage local (auto-créé)
.env                            # Configuration (non versionné)
```

## Dépendances

Gérées via `uv` (voir `pyproject.toml`) :

- `flask` — serveur web
- `pillow` — composition planche, thumbnails
- `qrcode` — génération QR
- `requests` — upload CDN
- `opencv-python-headless` — webcam (extra optionnel `webcam`, `uv sync --extra webcam`)
- `python-dotenv` — config

Externe : `gphoto2` (CLI système), MediaPipe (chargé depuis CDN côté client).
