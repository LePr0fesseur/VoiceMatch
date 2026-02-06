# VoiceMatch

**Shazam pour les voix d'acteurs et doubleurs.**

VoiceMatch permet de reconnaitre la voix d'un acteur ou d'un doubleur a partir d'un extrait audio, exactement comme Shazam le fait pour la musique.

## Fonctionnalites

- **Identification vocale** : Enregistrez ou uploadez un extrait audio pour identifier le doubleur
- **Analyse YouTube** : Collez une URL YouTube pour identifier la voix dans la video
- **Base de donnees auto-alimentee** : L'application recherche automatiquement des videos de doubleurs sur YouTube et construit sa base de voix
- **Interface web** : Interface intuitive avec enregistrement micro en temps reel

## Architecture

```
voicematch/
  app.py        # API FastAPI + serveur web
  youtube.py    # Recherche YouTube + extraction audio (yt-dlp)
  audio.py      # Traitement audio + extraction d'empreintes vocales (resemblyzer)
  matcher.py    # Moteur de correspondance vocale
  indexer.py    # Construction de la base de voix depuis YouTube
  database.py   # Couche base de donnees SQLite
  config.py     # Configuration
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

### Etape 1 : Alimenter la base de voix

Allez dans l'onglet **"Indexer des voix"** :

1. **Indexer une video** : Collez l'URL d'une video YouTube de doubleur
2. **Recherche automatique** : Entrez un nom d'acteur (ex: "Jim Carrey") et l'app recherchera et indexera automatiquement des videos de doubleurs

### Etape 2 : Identifier une voix

Allez dans l'onglet **"Identifier une voix"** :

1. **Micro** : Enregistrez directement depuis votre micro
2. **Fichier** : Uploadez un fichier audio (WAV, MP3, etc.)
3. **YouTube** : Collez une URL YouTube

## Troubleshooting

### yt-dlp ne fonctionne pas
```bash
pip install --upgrade yt-dlp
```

### ffmpeg non trouve
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Telecharger depuis https://ffmpeg.org/download.html
```

### Le modele de voix ne se telecharge pas
Le modele resemblyzer se telecharge automatiquement au premier lancement (~50 Mo). Verifiez votre connexion internet.

### Pas de correspondance trouvee
- Assurez-vous d'avoir indexe suffisamment de voix (onglet "Indexer")
- L'extrait audio doit durer au moins 1 seconde
- La qualite audio affecte la precision

## Technologies

- **FastAPI** : Framework web Python rapide
- **yt-dlp** : Telechargement audio YouTube
- **Resemblyzer** : Empreintes vocales par deep learning (GE2E)
- **librosa** : Traitement audio
- **SQLite** : Base de donnees locale
- **Web Audio API** : Enregistrement micro dans le navigateur
