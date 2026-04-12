"""InnerTube search - channel search.

Uses YouTube's InnerTube /search endpoint for searching within channels.
"""

import logging
from typing import Any, Dict

from innertube._client import innertube_post
from innertube._converters import (
    channel_renderer_to_invidious,
    playlist_renderer_to_invidious,
    video_renderer_to_invidious,
)

logger = logging.getLogger("innertube")


async def search_channel(
    channel_id: str, query: str, page: int = 1
) -> Dict[str, Any]:
    """Search for videos within a channel.

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        query: Search query string
        page: Page number (1-based) — note: InnerTube uses continuation tokens,
              so pagination beyond page 1 may not be supported without continuation

    Returns:
        Dict with "videos" list and optional "continuation" token
    """
    # For channel search, we use the /search endpoint with a channel filter
    # The channel filter is specified via the browseId in the endpoint context
    body = {
        "query": query,
        "params": _encode_channel_search_param(channel_id),
    }

    data = await innertube_post("search", body)

    videos = []
    continuation = None

    # Parse search results
    section_list = (
        data.get("contents", {})
        .get("twoColumnSearchResultsRenderer", {})
        .get("primaryContents", {})
        .get("sectionListRenderer", {})
    )

    for section in section_list.get("contents", []):
        item_section = section.get("itemSectionRenderer", {})
        for item in item_section.get("contents", []):
            if "videoRenderer" in item:
                videos.append(video_renderer_to_invidious(item["videoRenderer"]))
            elif "playlistRenderer" in item:
                videos.append(playlist_renderer_to_invidious(item["playlistRenderer"]))
            elif "channelRenderer" in item:
                videos.append(channel_renderer_to_invidious(item["channelRenderer"]))

        # Check for continuation
        if "continuationItemRenderer" in section:
            token = (
                section["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                continuation = token

    logger.info(f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results")
    return {"videos": videos, "continuation": continuation}


def _encode_channel_search_param(channel_id: str) -> str:
    """Encode channel search filter parameter.

    This creates a protobuf-encoded base64 parameter that filters search
    results to a specific channel. The encoding follows YouTube's protobuf
    search parameter format.
    """
    import base64

    # Protobuf encoding for channel filter:
    # Field 2 (search filter), wire type 2 (length-delimited)
    # Sub-field 1 (channel ID), wire type 2
    channel_bytes = channel_id.encode("utf-8")
    # Protobuf: field 2, wire type 2 -> tag = (2 << 3) | 2 = 18
    # Inner: field 2, wire type 2 -> tag = (2 << 3) | 2 = 18
    # Inner inner: field 1, wire type 2 -> tag = (1 << 3) | 2 = 10

    inner = bytes([10, len(channel_bytes)]) + channel_bytes
    middle = bytes([18, len(inner)]) + inner
    outer = bytes([18, len(middle)]) + middle

    return base64.b64encode(outer).decode("utf-8")
