"""InnerTube search suggestions.

Uses YouTube's suggest API to get search autocomplete suggestions.
"""

import json
import logging
import re
import urllib.parse
from typing import List

from innertube._client import InnerTubeError, innertube_get

logger = logging.getLogger("innertube")

# YouTube suggestion endpoint (returns JSONP by default, JSON with client=youtube&ds=yt)
SUGGEST_URL = "https://suggestqueries-clients6.youtube.com/complete/search"


async def get_search_suggestions(query: str) -> List[str]:
    """Get search suggestions from YouTube.

    Args:
        query: The search query to get suggestions for

    Returns:
        List of suggestion strings

    Raises:
        InnerTubeError: On request errors
    """
    if not query or not query.strip():
        return []

    encoded_query = urllib.parse.quote(query)
    url = f"{SUGGEST_URL}?client=youtube&ds=yt&q={encoded_query}"

    try:
        response = await innertube_get(url, use_cookies=False)
        response.raise_for_status()

        text = response.text

        # The response is JSONP: window.google.ac.h([...])
        # Extract the JSON array inside
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning(f"[InnerTube] Could not parse suggestions response for query: {query}")
            return []

        data = json.loads(match.group(0))

        # Format: [query, [[suggestion1, 0, [512,433]], [suggestion2, 0, [512,433]], ...], ...]
        if len(data) >= 2 and isinstance(data[1], list):
            return [item[0] for item in data[1] if isinstance(item, list) and item]

        return []

    except Exception as e:
        logger.warning(f"[InnerTube] Search suggestions error: {e}")
        raise InnerTubeError(f"Failed to get search suggestions: {e}")
