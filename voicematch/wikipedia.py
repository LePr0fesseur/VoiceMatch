"""Wikipedia integration for fetching actor information."""

import logging
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

WIKIPEDIA_FR_API = "https://fr.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_EN_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
USER_AGENT = "VoiceMatch/1.0 (voice recognition app)"


async def fetch_actor_info(actor_name: str) -> Optional[dict]:
    """Fetch actor information from Wikipedia (French first, English fallback)."""
    encoded_name = quote(actor_name.replace(" ", "_"))

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try French Wikipedia first
        result = await _fetch_from_api(client, WIKIPEDIA_FR_API, encoded_name)
        if result:
            return result

        # Fallback to English Wikipedia
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
            headers={"User-Agent": USER_AGENT},
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
    except Exception as e:
        logger.error("Wikipedia API error for '%s': %s", encoded_name, e)

    return None
