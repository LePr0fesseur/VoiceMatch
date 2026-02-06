"""FastAPI web application for VoiceMatch."""

import asyncio
import logging
import subprocess
from pathlib import Path

from fastapi import (
    Cookie,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, database, indexer, matcher, wikipedia
from .config import (
    ADMIN_DEFAULT_PASSWORD,
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_MAX_AGE,
    ALLOWED_EXTENSIONS,
    BASE_DIR,
    TEMP_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VoiceMatch",
    description="Shazam pour les voix de doubleurs",
    version="0.2.0",
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# --- Startup ---


@app.on_event("startup")
async def startup():
    """Initialize database and default admin password on startup."""
    database.init_db()

    # Create default admin password if none exists
    if database.get_admin_password_hash() is None:
        default_hash = auth.hash_password(ADMIN_DEFAULT_PASSWORD)
        database.set_admin_password_hash(default_hash)
        logger.info("Default admin password set (change it in the admin panel)")

    stats = database.get_db_stats()
    logger.info(
        "VoiceMatch started. Database: %d actors, %d voice samples",
        stats["actors"],
        stats["voice_samples"],
    )


# --- Helper: admin auth check ---


def _require_admin(session_cookie: str | None):
    """Raise 401 if the session cookie is missing or invalid."""
    if not session_cookie or not auth.verify_session_token(session_cookie):
        raise HTTPException(status_code=401, detail="Non autorise")


# =====================================================================
#  PUBLIC ROUTES - Front office (Shazam-like)
# =====================================================================


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the public Shazam-like interface."""
    stats = database.get_db_stats()
    return templates.TemplateResponse(
        "index.html", {"request": request, "stats": stats}
    )


@app.post("/api/match/upload")
async def match_upload(file: UploadFile = File(...)):
    """Match a voice from an uploaded audio file."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    suffix = Path(file.filename).suffix if file.filename else ".wav"
    tmp = TEMP_DIR / f"upload_{id(contents)}{suffix}"
    try:
        tmp.write_bytes(contents)
        results = await asyncio.to_thread(matcher.match_from_file, tmp)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error("Match upload error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


@app.post("/api/match/record")
async def match_record(file: UploadFile = File(...)):
    """Match a voice from a microphone recording (WebM/WAV from browser)."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Enregistrement vide")

    tmp = TEMP_DIR / f"record_{id(contents)}.webm"
    wav_tmp = TEMP_DIR / f"record_{id(contents)}.wav"
    try:
        tmp.write_bytes(contents)

        # Convert webm to wav using ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-ar", "16000", "-ac", "1", str(wav_tmp)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            wav_tmp = tmp

        results = await asyncio.to_thread(matcher.match_from_file, wav_tmp)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error("Match record error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for f in [tmp, wav_tmp]:
            try:
                f.unlink()
            except OSError:
                pass


@app.get("/api/wikipedia/{actor_name:path}")
async def get_wikipedia_info(actor_name: str):
    """Fetch actor information from Wikipedia."""
    info = await wikipedia.fetch_actor_info(actor_name)
    if info:
        return {"success": True, "info": info}
    return {"success": False, "info": None}


@app.get("/api/stats")
async def stats():
    """Get database statistics (public)."""
    return database.get_db_stats()


# =====================================================================
#  ADMIN ROUTES - Back office (secured)
# =====================================================================


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Serve the admin back-office page."""
    return templates.TemplateResponse("admin.html", {"request": request})


@app.post("/api/admin/login")
async def admin_login(password: str = Form(...)):
    """Authenticate as admin."""
    stored_hash = database.get_admin_password_hash()
    if not stored_hash or not auth.verify_password(password, stored_hash):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")

    token = auth.create_session_token()
    is_default = auth.verify_password(ADMIN_DEFAULT_PASSWORD, stored_hash)

    response = JSONResponse({
        "success": True,
        "default_password": is_default,
    })
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@app.post("/api/admin/logout")
async def admin_logout():
    """Log out the admin session."""
    response = JSONResponse({"success": True})
    response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")
    return response


@app.get("/api/admin/check")
async def admin_check(voicematch_session: str | None = Cookie(None)):
    """Check if the current session is authenticated."""
    if voicematch_session and auth.verify_session_token(voicematch_session):
        stored_hash = database.get_admin_password_hash()
        is_default = (
            stored_hash is not None
            and auth.verify_password(ADMIN_DEFAULT_PASSWORD, stored_hash)
        )
        return {"authenticated": True, "default_password": is_default}
    return {"authenticated": False}


@app.post("/api/admin/change-password")
async def admin_change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    voicematch_session: str | None = Cookie(None),
):
    """Change the admin password."""
    _require_admin(voicematch_session)

    stored_hash = database.get_admin_password_hash()
    if not stored_hash or not auth.verify_password(current_password, stored_hash):
        raise HTTPException(
            status_code=401, detail="Mot de passe actuel incorrect"
        )

    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Le nouveau mot de passe doit contenir au moins 6 caracteres",
        )

    new_hash = auth.hash_password(new_password)
    database.set_admin_password_hash(new_hash)
    return {"success": True}


@app.post("/api/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    dubber_name: str = Form(...),
    voicematch_session: str | None = Cookie(None),
):
    """Upload an MP3 file and index it in the voice database (admin only)."""
    _require_admin(voicematch_session)

    if not dubber_name.strip():
        raise HTTPException(status_code=400, detail="Le nom du doubleur est requis")

    # Validate file extension
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Seuls les fichiers MP3 sont acceptes (recu: {suffix or 'inconnu'})",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    tmp = TEMP_DIR / f"admin_upload_{id(contents)}{suffix}"
    wav_tmp = TEMP_DIR / f"admin_upload_{id(contents)}.wav"
    try:
        tmp.write_bytes(contents)

        # Convert MP3 to WAV (16kHz mono) for processing
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-ar", "16000", "-ac", "1", str(wav_tmp)],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=422,
                detail="Impossible de convertir le fichier audio. Verifiez qu'il s'agit d'un MP3 valide.",
            )

        # Index the audio file
        index_result = await asyncio.to_thread(
            indexer.index_audio_file,
            wav_tmp,
            dubber_name.strip(),
            file.filename or "upload.mp3",
        )

        if index_result is None:
            raise HTTPException(
                status_code=422,
                detail="Impossible d'extraire l'empreinte vocale. Verifiez le fichier audio (min 1 seconde de voix).",
            )

        return {"success": True, "indexed": index_result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Admin upload error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for f in [tmp, wav_tmp]:
            try:
                f.unlink()
            except OSError:
                pass


@app.get("/api/admin/actors")
async def admin_list_actors(voicematch_session: str | None = Cookie(None)):
    """List all actors in the database (admin only)."""
    _require_admin(voicematch_session)
    actors = database.get_all_actors()
    return {"actors": actors}


@app.get("/api/admin/actors/{actor_id}/samples")
async def admin_actor_samples(
    actor_id: int,
    voicematch_session: str | None = Cookie(None),
):
    """Get all voice samples for an actor (admin only)."""
    _require_admin(voicematch_session)
    samples = database.get_actor_samples(actor_id)
    return {"samples": samples}


@app.delete("/api/admin/actors/{actor_id}")
async def admin_delete_actor(
    actor_id: int,
    voicematch_session: str | None = Cookie(None),
):
    """Delete an actor and all their voice samples (admin only)."""
    _require_admin(voicematch_session)
    deleted = database.delete_actor(actor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Acteur non trouve")
    return {"success": True}


@app.delete("/api/admin/samples/{sample_id}")
async def admin_delete_sample(
    sample_id: int,
    voicematch_session: str | None = Cookie(None),
):
    """Delete a single voice sample (admin only)."""
    _require_admin(voicematch_session)
    deleted = database.delete_sample(sample_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Echantillon non trouve")
    return {"success": True}
