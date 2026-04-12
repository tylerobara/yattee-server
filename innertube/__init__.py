"""InnerTube - Direct YouTube API client.

Provides access to YouTube data without requiring an Invidious instance.
"""

from innertube._client import InnerTubeError, get_client, innertube_get, innertube_post
from innertube._comments import get_comments
from innertube._suggestions import get_search_suggestions
from innertube._thumbnails import proxy_thumbnail

__all__ = [
    "InnerTubeError",
    "get_client",
    "get_comments",
    "get_search_suggestions",
    "innertube_get",
    "innertube_post",
    "proxy_thumbnail",
]
