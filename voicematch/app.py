"""FastAPI web application for VoiceMatch."""

import asyncio
import io
import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database, matcher, indexer, audio
from .config import BASE_DIR, TEMP_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VoiceMatch",
    description="Shazam pour les voix d'acteurs et doubleurs",
    version="0.1.0",
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    database.init_db()
    stats = database.get_db_stats()
    logger.info(
        "VoiceMatch started. Database: %d actors, %d voice samples",
        stats["actors"],
        stats["voice_samples"],
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main page."""
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

    # Save to temp file
    suffix = Path(file.filename).suffix if file.filename else ".wav"
    tmp = TEMP_DIR / f"upload_{id(contents)}{suffix}"
    try:
        tmp.write_bytes(contents)

        # Try matching
        results = await asyncio.to_thread(
            matcher.match_from_file, tmp
        )
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
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-ar", "16000", "-ac", "1", str(wav_tmp)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try as raw wav
            wav_tmp = tmp

        results = await asyncio.to_thread(
            matcher.match_from_file, wav_tmp
        )
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


@app.post("/api/match/youtube")
async def match_youtube(url: str = Form(...)):
    """Match a voice from a YouTube video URL."""
    if not url:
        raise HTTPException(status_code=400, detail="URL YouTube requise")

    try:
        results = await asyncio.to_thread(
            matcher.match_from_youtube, url
        )
        return {"success": True, "results": results, "source_url": url}
    except Exception as e:
        logger.error("Match YouTube error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index/url")
async def index_url(url: str = Form(...)):
    """Index a single YouTube video into the voice database."""
    if not url:
        raise HTTPException(status_code=400, detail="URL YouTube requise")

    try:
        result = await asyncio.to_thread(indexer.index_single_url, url)
        if result:
            return {"success": True, "indexed": result}
        raise HTTPException(
            status_code=422,
            detail="Impossible d'indexer cette video. Verifiez l'URL.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Index URL error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index/search")
async def index_search(
    query: str = Form(""),
    max_videos: int = Form(10),
):
    """Search YouTube for dubbing videos and index them."""
    try:
        results = await asyncio.to_thread(
            indexer.index_from_search, query, max_videos
        )
        return {
            "success": True,
            "indexed_count": len(results),
            "indexed": results,
        }
    except Exception as e:
        logger.error("Index search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/actors")
async def list_actors():
    """List all actors in the database."""
    actors = database.get_all_actors()
    return {"actors": actors}


@app.get("/api/actors/{actor_id}/samples")
async def actor_samples(actor_id: int):
    """Get all voice samples for an actor."""
    samples = database.get_actor_samples(actor_id)
    return {"samples": samples}


@app.get("/api/stats")
async def stats():
    """Get database statistics."""
    return database.get_db_stats()
