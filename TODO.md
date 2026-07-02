# Photobooth Bollywood — TODO

## Fait
- [x] Capture photo Canon EOS 5D Mark II via gphoto2
- [x] Live view streaming MJPEG
- [x] Countdown sonore 3-2-1 + flash
- [x] 8 filtres CSS en temps réel (N&B, Sepia, Vintage, Punch, Cool, Warm, Drama)
- [x] 5 accessoires face tracking via MediaPipe (lunettes, chapeau, moustache, couronne, noeud pap)
- [x] Upload CDN SeaweedFS + QR code
- [x] Mode planche x4 (capture en rafale + assemblage Pillow)
- [x] Galerie photo séparée avec lightbox
- [x] Thème Bollywood (or/magenta/pourpre, polices Baloo 2/Mukta, sparkles, bordures)
- [x] Config .env (basculer Canon/webcam, credentials CDN, port)
- [x] Mode webcam OpenCV pour tester sans Canon

## A faire

### Prioritaire
- [ ] Cadre/watermark Bollywood — bordure dorée + nom de l'événement sur chaque photo
- [ ] Ecran d'accueil animé — titre, animation, "Touche l'écran pour commencer"
- [ ] Mode veille — retour auto à l'écran d'accueil après 30s d'inactivité

### Accessoires
- [ ] Props cumulables — pouvoir mettre lunettes + chapeau en même temps
- [x] Props Bollywood — bindi, tikka, turban, collier de fleurs (maala)
- [ ] Textes/bulles — "Superstar!", "Bollywood Queen" en lettres dorées

### Partage
- [ ] Envoi par email — champ email pour s'envoyer la photo
- [ ] Galerie en ligne — page publique avec QR code global (toutes les photos de l'événement)

### Impression
- [ ] Impression directe — support imprimante photo (DNP, Canon Selphy)

### Admin
- [ ] Page admin (/admin) — stats, config timer, choix des filtres/props actifs, nom de l'événement
- [ ] Réglages appareil — ISO, ouverture, balance des blancs depuis l'interface

### Qualité
- [ ] Recadrage auto — centrer sur les visages détectés
- [ ] Mise au point — option AF ou MF fixe configurable via gphoto2
