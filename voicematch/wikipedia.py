"""Wikipedia integration for fetching actor information."""

import asyncio
import logging
import time
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

WIKIPEDIA_FR_API = "https://fr.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_EN_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
USER_AGENT = (
    "VoiceMatch/1.0 (https://github.com/LePr0fesseur/VoiceMatch; "
    "voice dubber recognition app) httpx/0.28"
)

# Rate limiting: track last request time
_last_request_time: float = 0.0
_MIN_REQUEST_INTERVAL: float = 0.5  # seconds between API calls


async def _rate_limit():
    """Enforce minimum interval between Wikipedia API requests."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        await asyncio.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


async def fetch_actor_info(actor_name: str) -> Optional[dict]:
    """Fetch actor information from Wikipedia (French first, English fallback)."""
    if not actor_name or not actor_name.strip():
        return None

    encoded_name = quote(actor_name.strip().replace(" ", "_"))

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try French Wikipedia first
        await _rate_limit()
        result = await _fetch_from_api(client, WIKIPEDIA_FR_API, encoded_name)
        if result:
            return result

        # Fallback to English Wikipedia
        await _rate_limit()
        result = await _fetch_from_api(client, WIKIPEDIA_EN_API, encoded_name)
        if result:
            return result

    return None


async def _fetch_from_api(
    client: httpx.AsyncClient, base_url: str, encoded_name: str
) -> Optional[dict]:
    """Fetch a summary from a specific Wikipedia API endpoint."""
    try:
        response = await client.get(
            f"{base_url}/{encoded_name}",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
        if response.status_code == 200:
            data = response.json()
            # Skip disambiguation pages
            if data.get("type") == "disambiguation":
                return None
            return {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "extract": data.get("extract", ""),
                "thumbnail": data.get("thumbnail", {}).get("source", ""),
                "url": (
                    data.get("content_urls", {})
                    .get("desktop", {})
                    .get("page", "")
                ),
            }
        elif response.status_code == 404:
            logger.debug("Wikipedia: page not found for '%s' on %s", encoded_name, base_url)
        elif response.status_code == 403:
            logger.warning("Wikipedia 403 Forbidden for '%s' on %s", encoded_name, base_url)
        else:
            logger.warning("Wikipedia HTTP %d for '%s'", response.status_code, encoded_name)
    except httpx.TimeoutException:
        logger.warning("Wikipedia timeout for '%s' on %s", encoded_name, base_url)
    except Exception as e:
        logger.error("Wikipedia API error for '%s': %s", encoded_name, e)

    return None
