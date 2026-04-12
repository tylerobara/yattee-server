"""InnerTube search - channel search.

Uses YouTube's InnerTube resolve_url + browse endpoints to search within channels.
"""

import logging
import urllib.parse
from typing import Any, Dict

from innertube._client import innertube_post
from innertube._converters import video_renderer_to_invidious

logger = logging.getLogger("innertube")


async def search_channel(
    channel_id: str, query: str, page: int = 1
) -> Dict[str, Any]:
    """Search for videos within a channel.

    Uses YouTube's resolve_url endpoint to get the correct browse params
    for a channel search URL, then fetches results via browse.

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        query: Search query string
        page: Page number (1-based)

    Returns:
        Dict with "videos" list and optional "continuation" token
    """
    encoded_query = urllib.parse.quote(query)

    # Step 1: Resolve the channel search URL to get browse params
    if channel_id.startswith("@"):
        search_url = f"https://www.youtube.com/{channel_id}/search?query={encoded_query}"
    else:
        search_url = f"https://www.youtube.com/channel/{channel_id}/search?query={encoded_query}"

    resolve_data = await innertube_post("navigation/resolve_url", {"url": search_url})

    browse_endpoint = resolve_data.get("endpoint", {}).get("browseEndpoint", {})
    browse_id = browse_endpoint.get("browseId", channel_id)
    params = browse_endpoint.get("params")

    if not params:
        logger.warning(f"[InnerTube] Channel search resolve failed for {channel_id}")
        return {"videos": [], "continuation": None}

    # Step 2: Browse with the resolved params to load the channel page with search tab
    browse_data = await innertube_post("browse", {"browseId": browse_id, "params": params})

    # Step 3: Find the search tab's continuation token and fetch results
    tabs = browse_data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])

    for tab in tabs:
        renderer = tab.get("expandableTabRenderer", {}) or tab.get("tabRenderer", {})
        if not renderer.get("selected"):
            continue

        # Check if results are inline in the tab content
        content = renderer.get("content", {})
        sl = content.get("sectionListRenderer", {})
        if sl:
            videos, continuation = _parse_search_sections(sl.get("contents", []))
            if videos:
                logger.info(f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results")
                return {"videos": videos, "continuation": continuation}

        # If tab content is empty, check for a continuation in the tab's endpoint
        tab_endpoint = renderer.get("endpoint", {}).get("browseEndpoint", {})
        tab_params = tab_endpoint.get("params")
        if tab_params and tab_params != params:
            # Fetch the search tab content with its own params
            tab_data = await innertube_post("browse", {"browseId": browse_id, "params": tab_params, "query": query})

            # Check onResponseReceivedActions (continuation-loaded results)
            for action in tab_data.get("onResponseReceivedActions", []):
                append = action.get("appendContinuationItemsAction", {})
                items = append.get("continuationItems", [])
                if items:
                    videos, continuation = _parse_continuation_items(items)
                    if videos:
                        logger.info(f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results")
                        return {"videos": videos, "continuation": continuation}

            # Also check tab content in the response
            tabs2 = tab_data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            for tab2 in tabs2:
                r2 = tab2.get("expandableTabRenderer", {}) or tab2.get("tabRenderer", {})
                if r2.get("selected"):
                    sl2 = r2.get("content", {}).get("sectionListRenderer", {})
                    if sl2:
                        videos, continuation = _parse_search_sections(sl2.get("contents", []))
                        if videos:
                            logger.info(
                                f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results"
                            )
                            return {"videos": videos, "continuation": continuation}

    logger.debug(f"[InnerTube] Channel search {channel_id} q={query}: no results found in response")
    return {"videos": [], "continuation": None}


def _parse_search_sections(sections: list) -> tuple[list, str | None]:
    """Parse video results from sectionListRenderer contents."""
    videos = []
    continuation = None

    for section in sections:
        isr = section.get("itemSectionRenderer", {})
        for item in isr.get("contents", []):
            if "videoRenderer" in item:
                videos.append(video_renderer_to_invidious(item["videoRenderer"]))

        if "continuationItemRenderer" in section:
            token = (
                section["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                continuation = token

    return videos, continuation


def _parse_continuation_items(items: list) -> tuple[list, str | None]:
    """Parse video results from continuation items."""
    videos = []
    continuation = None

    for item in items:
        if "itemSectionRenderer" in item:
            isr = item["itemSectionRenderer"]
            for content in isr.get("contents", []):
                if "videoRenderer" in content:
                    videos.append(video_renderer_to_invidious(content["videoRenderer"]))
        elif "videoRenderer" in item:
            videos.append(video_renderer_to_invidious(item["videoRenderer"]))
        elif "continuationItemRenderer" in item:
            token = (
                item["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                continuation = token

    return videos, continuation
