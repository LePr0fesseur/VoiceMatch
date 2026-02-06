# VoiceMatch

**Shazam pour les voix de doubleurs.**

VoiceMatch permet de reconnaitre la voix d'un doubleur a partir d'un extrait audio (micro ou fichier), exactement comme Shazam le fait pour la musique.

## Fonctionnalites

- **Identification vocale** : Enregistrez via micro ou uploadez un extrait audio pour identifier le doubleur
- **Interface publique** : Interface Shazam-like avec bouton micro + upload de fichier
- **Back-office admin** : Espace securise pour gerer la base de voix (ajout/suppression de doubleurs et echantillons)
- **Fiche Wikipedia** : Affichage automatique des infos Wikipedia du doubleur identifie
- **Pipeline audio avance** : VAD, reduction de bruit, pre-emphasis, MFCC, score fusion

## Architecture

```
voicematch/
  app.py        # API FastAPI + routes publiques et admin
  audio.py      # Pipeline audio (ECAPA-TDNN / resemblyzer, VAD, MFCC)
  matcher.py    # Moteur de correspondance (score fusion, per-segment matching)
  indexer.py    # Indexation robuste (multi-segment + augmentation)
  database.py   # Couche SQLite (voix, acteurs, settings admin)
  wikipedia.py  # Integration Wikipedia (FR/EN)
  auth.py       # Authentification admin (PBKDF2 + sessions HMAC)
  config.py     # Configuration

templates/
  index.html    # Interface publique
  admin.html    # Interface admin

static/
  app.js        # JS interface publique
  admin.js      # JS interface admin
  style.css     # Styles publics
  admin.css     # Styles admin
```

## Installation

### Prerequis

- Python 3.10+
- ffmpeg (`sudo apt install ffmpeg` ou `brew install ffmpeg`)

### Etapes

```bash
# Cloner le projet
git clone <repo-url>
cd VoiceMatch

# Creer un environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Installer les dependances
pip install -r requirements.txt
```

## Utilisation

### Lancer le serveur

```bash
python run.py
```

Ouvrir http://localhost:8000 dans votre navigateur.

### Interface publique (/)

- **Micro** : Appuyez sur le bouton central pour enregistrer votre voix ou un extrait
- **Fichier** : Uploadez un fichier audio (WAV, MP3, WebM...)

### Administration (/admin)

1. Accedez a http://localhost:8000/admin
2. Mot de passe par defaut : `admin` (a changer des la premiere connexion)
3. Uploadez des fichiers MP3 pour alimenter la base de voix
4. Gerez les doubleurs et leurs echantillons

### Acces mobile (HTTPS)

L'acces micro sur mobile necessite HTTPS. Pour du developpement local :

```bash
pip install pyopenssl
```

Puis lancez le serveur avec un certificat auto-signe.

## Troubleshooting

### ffmpeg non trouve

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows : telecharger depuis https://ffmpeg.org/download.html
```

### Pas de correspondance trouvee

- Assurez-vous d'avoir indexe suffisamment de voix via l'admin
- L'extrait audio doit durer au moins 1 seconde
- La qualite audio affecte la precision
- Pour les extraits de films, le systeme isole automatiquement les segments de parole

## Technologies

- **FastAPI** : Framework web Python
- **ECAPA-TDNN** (SpeechBrain) : Empreintes vocales (EER 0.80% sur VoxCeleb1)
- **Resemblyzer** : Fallback GE2E si SpeechBrain indisponible
- **WebRTC VAD** : Detection d'activite vocale
- **librosa** : Extraction MFCC (score fusion)
- **SQLite** : Base de donnees locale
- **Web Audio API** : Enregistrement micro dans le navigateur
