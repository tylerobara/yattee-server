"""Direct YouTube thumbnail proxy.

Proxies thumbnails directly from i.ytimg.com instead of through Invidious.
"""

import logging
from typing import Tuple

from innertube._client import InnerTubeError, innertube_get

logger = logging.getLogger("innertube")

# YouTube's image CDN
YTIMG_BASE = "https://i.ytimg.com"


async def proxy_thumbnail(video_id: str, filename: str) -> Tuple[bytes, int, dict]:
    """Proxy a video thumbnail directly from YouTube's CDN.

    Args:
        video_id: YouTube video ID
        filename: Thumbnail filename (e.g., maxresdefault.jpg, hqdefault.jpg)

    Returns:
        Tuple of (content bytes, status code, headers dict)

    Raises:
        InnerTubeError: On request errors
    """
    url = f"{YTIMG_BASE}/vi/{video_id}/{filename}"

    try:
        response = await innertube_get(url, use_cookies=False)

        headers = {}
        if "content-type" in response.headers:
            headers["content-type"] = response.headers["content-type"]
        if "cache-control" in response.headers:
            headers["cache-control"] = response.headers["cache-control"]

        return response.content, response.status_code, headers

    except Exception as e:
        logger.warning(f"[InnerTube] Thumbnail proxy error: {video_id}/{filename} - {e}")
        raise InnerTubeError(f"Thumbnail proxy failed: {e}")
