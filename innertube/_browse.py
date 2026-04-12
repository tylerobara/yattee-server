"""InnerTube browse endpoint - trending, popular, channel tabs.

Uses YouTube's InnerTube /browse endpoint to fetch categorized content.
"""

import logging
from typing import Any, Dict, List, Optional

from innertube._client import _build_context, _get_client_version, innertube_post
from innertube._converters import (
    grid_playlist_to_invidious,
    grid_video_to_invidious,
    rich_item_to_invidious,
    video_renderer_to_invidious,
)

logger = logging.getLogger("innertube")

# Channel tab param tokens (base64-encoded protobuf)
# These tell the /browse endpoint which tab to show
CHANNEL_TAB_PARAMS = {
    "videos": "EgZ2aWRlb3PyBgQKAjoA",
    "shorts": "EgZzaG9ydHPyBgUKA5oBAA%3D%3D",
    "streams": "EgdzdHJlYW1z8gYECgJ6AA%3D%3D",
    "playlists": "EglwbGF5bGlzdHPyBgQKAkIA",
}


def _extract_items_from_tab(data: Dict[str, Any]) -> tuple[List[Dict], Optional[str]]:
    """Extract video/playlist items and continuation from a browse response tab."""
    items = []
    continuation = None

    # Navigate the response structure
    # Path: contents -> twoColumnBrowseResultsRenderer -> tabs[] -> tabRenderer -> content
    tabs = (
        data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    )

    for tab in tabs:
        tab_renderer = tab.get("tabRenderer", {})
        tab_content = tab_renderer.get("content", {})

        # richGridRenderer (trending, channel videos)
        rich_grid = tab_content.get("richGridRenderer", {})
        if rich_grid:
            for item in rich_grid.get("contents", []):
                if "richItemRenderer" in item:
                    converted = rich_item_to_invidious(item["richItemRenderer"])
                    if converted:
                        items.append(converted)
                elif "continuationItemRenderer" in item:
                    token = (
                        item["continuationItemRenderer"]
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )
                    if token:
                        continuation = token

        # sectionListRenderer (trending page uses this)
        section_list = tab_content.get("sectionListRenderer", {})
        if section_list:
            for section in section_list.get("contents", []):
                section_renderer = section.get("itemSectionRenderer", {})
                for content in section_renderer.get("contents", []):
                    if "shelfRenderer" in content:
                        shelf_items = (
                            content["shelfRenderer"]
                            .get("content", {})
                            .get("expandedShelfContentsRenderer", {})
                            .get("items", [])
                        )
                        for shelf_item in shelf_items:
                            if "videoRenderer" in shelf_item:
                                items.append(video_renderer_to_invidious(shelf_item["videoRenderer"]))
                    elif "videoRenderer" in content:
                        items.append(video_renderer_to_invidious(content["videoRenderer"]))
                    elif "gridVideoRenderer" in content:
                        items.append(grid_video_to_invidious(content["gridVideoRenderer"]))
                    elif "gridPlaylistRenderer" in content:
                        items.append(grid_playlist_to_invidious(content["gridPlaylistRenderer"]))

                # Check for continuation in section
                if "continuationItemRenderer" in section:
                    token = (
                        section["continuationItemRenderer"]
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )
                    if token:
                        continuation = token

    return items, continuation


def _extract_items_from_continuation(data: Dict[str, Any]) -> tuple[List[Dict], Optional[str]]:
    """Extract items from a continuation response."""
    items = []
    continuation = None

    for action in data.get("onResponseReceivedActions", []):
        append_action = action.get("appendContinuationItemsAction", {})
        for item in append_action.get("continuationItems", []):
            if "richItemRenderer" in item:
                converted = rich_item_to_invidious(item["richItemRenderer"])
                if converted:
                    items.append(converted)
            elif "gridVideoRenderer" in item:
                items.append(grid_video_to_invidious(item["gridVideoRenderer"]))
            elif "gridPlaylistRenderer" in item:
                items.append(grid_playlist_to_invidious(item["gridPlaylistRenderer"]))
            elif "videoRenderer" in item:
                items.append(video_renderer_to_invidious(item["videoRenderer"]))
            elif "continuationItemRenderer" in item:
                token = (
                    item["continuationItemRenderer"]
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )
                if token:
                    continuation = token

    return items, continuation


async def get_trending(region: str = "US") -> List[Dict[str, Any]]:
    """Get trending videos from YouTube.

    Args:
        region: Region code (e.g., "US", "GB", "DE")

    Returns:
        List of video dicts in Invidious format
    """
    version = await _get_client_version()
    body = {
        "browseId": "FEtrending",
        "context": _build_context(region=region, client_version=version),
    }
    data = await innertube_post("browse", body)
    items, _ = _extract_items_from_tab(data)
    logger.info(f"[InnerTube] Trending: got {len(items)} videos for region={region}")
    return items


async def get_popular() -> List[Dict[str, Any]]:
    """Get popular videos from YouTube.

    YouTube merged popular into trending, so this returns trending content.
    """
    return await get_trending()


async def get_channel_videos(
    channel_id: str, continuation: Optional[str] = None
) -> Dict[str, Any]:
    """Get channel videos tab.

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        continuation: Continuation token for pagination

    Returns:
        Dict with "videos" list and optional "continuation" token
    """
    if continuation:
        body = {"continuation": continuation}
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_continuation(data)
    else:
        body = {
            "browseId": channel_id,
            "params": CHANNEL_TAB_PARAMS["videos"],
        }
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_tab(data)

    logger.info(f"[InnerTube] Channel videos {channel_id}: got {len(items)} videos")
    return {"videos": items, "continuation": next_cont}


async def get_channel_shorts(
    channel_id: str, continuation: Optional[str] = None
) -> Dict[str, Any]:
    """Get channel shorts tab."""
    if continuation:
        body = {"continuation": continuation}
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_continuation(data)
    else:
        body = {
            "browseId": channel_id,
            "params": CHANNEL_TAB_PARAMS["shorts"],
        }
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_tab(data)

    return {"videos": items, "continuation": next_cont}


async def get_channel_streams(
    channel_id: str, continuation: Optional[str] = None
) -> Dict[str, Any]:
    """Get channel past live streams tab."""
    if continuation:
        body = {"continuation": continuation}
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_continuation(data)
    else:
        body = {
            "browseId": channel_id,
            "params": CHANNEL_TAB_PARAMS["streams"],
        }
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_tab(data)

    return {"videos": items, "continuation": next_cont}


async def get_channel_playlists(
    channel_id: str, continuation: Optional[str] = None
) -> Dict[str, Any]:
    """Get channel playlists tab."""
    if continuation:
        body = {"continuation": continuation}
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_continuation(data)
    else:
        body = {
            "browseId": channel_id,
            "params": CHANNEL_TAB_PARAMS["playlists"],
        }
        data = await innertube_post("browse", body)
        items, next_cont = _extract_items_from_tab(data)

    return {"playlists": items, "continuation": next_cont}
