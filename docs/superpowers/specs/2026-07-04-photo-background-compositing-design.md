# Fond décoratif + message pour la photo unique

## Contexte

Le photobooth Bollywood a deux flux de sortie :
- **Photo unique** : capturée, filtre + props "bakés" côté navigateur (canvas), uploadée brute via `POST /upload-filtered`.
- **Planche x4** : chaque pose est assemblée côté serveur (PIL) sur `static/strip_template.png` via `STRIP_SLOTS` (déjà un système de cadre décoratif, propre à ce mode).

Le mode photo unique n'a aujourd'hui aucun habillage : la photo uploadée est le fichier final envoyé au CDN. L'objectif est d'ajouter un fond décoratif (ex. décor indien) et un message texte configurables, façon photobooth pro (cf. exemple fourni : cadre pailleté doré/noir avec bandeau de titre en bas en police script).

## Périmètre

- S'applique **uniquement au mode photo unique**. Le mode planche x4 garde `strip_template.png`/`STRIP_SLOTS` inchangés.
- Composition **côté serveur** (PIL), pas côté navigateur — cohérent avec `assemble_strip()`/`crop_to_fill()` déjà existants, et évite de charger le NUC i3 (déjà identifié comme limite en performance) avec un canvas supplémentaire côté client.

## Configuration (`.env`)

Trois nouvelles variables, même convention que l'existant (`MIRROR_LIVEVIEW`, `COUNTDOWN_STRIP`, etc.) :

```dotenv
# Fond décoratif appliqué derrière la photo unique (fichier dans static/backgrounds/)
PHOTO_BACKGROUND=black.png

# Message affiché sous la photo (vide = pas de message)
PHOTO_MESSAGE=Anniversaire de Laura

# Police du message (fichier .ttf/.otf dans static/fonts/, vide = pas de message dessiné)
PHOTO_MESSAGE_FONT=
```

Ces valeurs sont lues dans `app.py` au même endroit que les autres flags (`AUTOFOCUS_MODE`, `MIRROR_LIVEVIEW`, ...), pas besoin de les passer au template Jinja (contrairement à `ENABLE_FACE_PROPS`) puisque tout le traitement est côté serveur.

## Nouveaux dossiers

- `static/backgrounds/` — fonds décoratifs disponibles. Contient au minimum `black.png` (fond de test, généré par cette implémentation).
- `static/fonts/` — polices disponibles. Vide au départ ; l'utilisateur fournira le(s) fichier(s) `.ttf`/`.otf` séparément.

## Point technique découvert en cours de conception

`POST /upload-filtered` (via la fonction JS `composeFinalPhoto()`) est en réalité appelée **à la fois** par le mode photo unique (`startSingleCapture`) et par chacune des 4 poses du mode planche (`startStripCapture`, avant assemblage sur `strip_template.png`). De plus, si aucun filtre ni prop n'est actif, `composeFinalPhoto()` court-circuite entièrement l'appel réseau et renvoie la photo brute telle quelle (`needsProcessing = false`) — ce qui serait aussi le cas typique en mode photo unique avec le filtre "Normal" par défaut.

Conséquences sur l'implémentation :
- Il faut un moyen explicite de dire au serveur "applique le fond/message" uniquement pour le mode photo unique, jamais pour les poses individuelles de la planche.
- Le court-circuit de `composeFinalPhoto()` doit être désactivé en mode photo unique, pour que la composition fond+message s'exécute même sans filtre/prop actif.

Solution retenue :
- `composeFinalPhoto(originalFilename, filterCss, prop, applyBackground)` reçoit un 4ᵉ paramètre booléen.
- `needsProcessing = filterCss !== 'none' || prop.src || applyBackground` — force l'appel à `/upload-filtered` dès que `applyBackground` est vrai.
- `startSingleCapture` appelle `composeFinalPhoto(..., true)`, `startStripCapture` appelle `composeFinalPhoto(..., false)` (comportement actuel inchangé pour la planche).
- Le formulaire envoyé à `/upload-filtered` inclut un champ `apply_background` (`'1'`/`'0'`) ; côté Flask, la composition fond+message ne s'exécute que si ce champ est vrai.

## Flux de traitement

Dans la route `POST /upload-filtered`, après réception du fichier envoyé par le navigateur (photo avec filtre + props déjà bakés, comportement actuel inchangé), **et uniquement si `apply_background` est vrai** :

1. **Normaliser l'orientation** : appliquer `PIL.ImageOps.exif_transpose()` sur l'image reçue avant tout traitement, pour gérer correctement la rotation EXIF du Canon 5D Mark II (le capteur est monté à la verticale dans le photobooth ; les fichiers bruts sont en paysage 5616×3744 mais doivent s'afficher en portrait).
2. **Charger le fond** : ouvrir `static/backgrounds/{PHOTO_BACKGROUND}`. Si le fichier est introuvable, logguer un avertissement et uploader la photo telle quelle (comportement actuel) plutôt que de faire échouer la capture.
3. **Calculer la fenêtre photo**, en pourcentage des dimensions du fond (donc indépendant de la résolution du fond fourni) :
   - Marge gauche/droite : 12 % de la largeur du fond chacune → largeur de fenêtre = 76 % de la largeur du fond.
   - Marge haute : 5 % de la hauteur du fond.
   - Hauteur de la fenêtre : calculée pour conserver le ratio réel de la photo (pas de recadrage, la photo entière est visible, juste réduite).
4. **Redimensionner et coller** la photo (ratio conservé, `Image.LANCZOS`) centrée horizontalement dans cette fenêtre, sur une copie du fond.
5. **Dessiner le message** (si `PHOTO_MESSAGE` non vide ET `PHOTO_MESSAGE_FONT` valide et présent dans `static/fonts/`) :
   - Zone : de la base de la fenêtre photo jusqu'à une marge basse de 5 % du fond.
   - Texte centré horizontalement, couleur blanche, taille de police ajustée automatiquement pour tenir dans la largeur disponible (76 % du fond, mêmes marges que la photo) sans dépasser la hauteur de la zone.
   - Une seule ligne (pas de wrap multi-ligne dans cette version — si `PHOTO_MESSAGE` est trop long, la police rétrécit jusqu'à tenir).
   - Si `PHOTO_MESSAGE_FONT` est vide ou que le fichier n'existe pas : ne pas dessiner de message, pas d'erreur.
6. **Sauvegarder** l'image composée en JPEG (qualité cohérente avec le reste du code, ex. 92 comme `assemble_strip`), c'est ce fichier qui est uploadé au CDN et servi par `/photos/<filename>` — remplace l'upload de la photo brute filtrée.

## Robustesse

- Fond manquant → fallback photo brute (log warning), jamais d'échec de capture pour l'utilisateur final.
- Police manquante/vide → pas de message dessiné, le reste (fond + photo) s'applique quand même.
- Aucune de ces étapes ne doit faire échouer `/upload-filtered` de façon visible côté UI — en cas d'erreur inattendue dans la composition, logguer et retomber sur la photo brute (même logique de tolérance que le fond manquant), pour ne jamais bloquer un événement en cours.

## Asset de test

Cette implémentation génère `static/backgrounds/black.png` : un fond noir uni, aux dimensions **3744×5616** (portrait — confirmé par un exemple de capture réelle du photobooth, orientée verticalement malgré des dimensions brutes 5616×3744 côté capteur). `PHOTO_BACKGROUND=black.png` est la valeur par défaut dans `.env`. L'utilisateur remplacera ce fichier par un vrai décor indien plus tard, à n'importe quelle résolution — les proportions en % s'adaptent automatiquement.

## Hors périmètre (explicitement exclu)

- Mode planche x4 : non touché.
- Sélection du fond/message/police depuis l'UI (navigateur) : reste de la config serveur (`.env`) uniquement, pas d'interface d'administration.
- Multi-ligne / mise en forme riche du message : une seule ligne, taille auto-ajustée.
- Choix de la police par défaut si `PHOTO_MESSAGE_FONT` n'est pas fourni : aucun fallback vers une police bundlée — l'utilisateur fournit son propre fichier.
