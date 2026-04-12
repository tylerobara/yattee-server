"""InnerTube comments extraction.

Fetches video comments using YouTube's InnerTube /next endpoint and converts
them to Invidious-compatible format for the existing client API.
"""

import logging
from typing import Any, Dict, List, Optional

from innertube._client import innertube_post

logger = logging.getLogger("innertube")


def _extract_text(runs_or_text: Any) -> str:
    """Extract plain text from InnerTube's text structures.

    InnerTube uses either {"simpleText": "..."} or {"runs": [{"text": "..."}]}
    """
    if not runs_or_text:
        return ""
    if isinstance(runs_or_text, str):
        return runs_or_text
    if "simpleText" in runs_or_text:
        return runs_or_text["simpleText"]
    if "runs" in runs_or_text:
        return "".join(run.get("text", "") for run in runs_or_text["runs"])
    return ""


def _extract_text_html(runs_or_text: Any) -> str:
    """Extract HTML-formatted text from InnerTube's text structures.

    Converts bold, italic, and link runs to HTML.
    """
    if not runs_or_text:
        return ""
    if isinstance(runs_or_text, str):
        return runs_or_text
    if "simpleText" in runs_or_text:
        return runs_or_text["simpleText"]
    if "runs" not in runs_or_text:
        return ""

    parts = []
    for run in runs_or_text["runs"]:
        text = run.get("text", "")
        if not text:
            continue

        # Handle links
        nav = run.get("navigationEndpoint")
        if nav:
            url = ""
            if "urlEndpoint" in nav:
                url = nav["urlEndpoint"].get("url", "")
            elif "commandMetadata" in nav:
                url = nav["commandMetadata"].get("webCommandMetadata", {}).get("url", "")
            if url:
                text = f'<a href="{url}">{text}</a>'

        # Handle formatting
        if run.get("bold"):
            text = f"<b>{text}</b>"
        if run.get("italics"):
            text = f"<i>{text}</i>"

        parts.append(text)

    return "".join(parts)


def _extract_thumbnails(thumbnail_data: Any) -> List[Dict[str, Any]]:
    """Extract thumbnail list from InnerTube thumbnail structure."""
    if not thumbnail_data:
        return []
    thumbnails = thumbnail_data.get("thumbnails", [])
    return [
        {
            "url": t.get("url", ""),
            "width": t.get("width", 48),
            "height": t.get("height", 48),
        }
        for t in thumbnails
    ]


def _parse_comment_renderer(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an InnerTube commentRenderer to Invidious comment format."""
    comment_id = renderer.get("commentId", "")

    # Author info
    author = _extract_text(renderer.get("authorText"))
    author_endpoint = renderer.get("authorEndpoint", {})
    author_id = author_endpoint.get("browseEndpoint", {}).get("browseId", "")
    author_url = f"/channel/{author_id}" if author_id else ""
    author_thumbnails = _extract_thumbnails(renderer.get("authorThumbnail"))
    is_verified = renderer.get("authorIsChannelOwner", False)

    # Comment content
    content = _extract_text(renderer.get("contentText"))
    content_html = _extract_text_html(renderer.get("contentText"))

    # Published time
    published_text = _extract_text(renderer.get("publishedTimeText"))

    # Likes
    like_count = 0
    vote_count_text = _extract_text(renderer.get("voteCount"))
    if vote_count_text:
        like_count = _parse_count(vote_count_text)

    # Heart (creator liked)
    is_hearted = False
    action_buttons = renderer.get("actionButtons", {}).get("commentActionButtonsRenderer", {})
    if action_buttons.get("creatorHeart"):
        is_hearted = True

    # Pinned
    is_pinned = bool(renderer.get("pinnedCommentBadge"))

    return {
        "commentId": comment_id,
        "author": author,
        "authorId": author_id,
        "authorUrl": author_url,
        "authorThumbnails": author_thumbnails,
        "authorIsChannelOwner": is_verified,
        "content": content,
        "contentHtml": content_html,
        "published": 0,  # InnerTube doesn't give unix timestamp
        "publishedText": published_text,
        "likeCount": like_count,
        "isHearted": is_hearted,
        "isPinned": is_pinned,
        "replies": None,
    }


def _parse_count(text: str) -> int:
    """Parse a count string like '1.2K', '3M', '456' to an integer."""
    text = text.strip().upper().replace(",", "")
    if not text:
        return 0

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if text.endswith(suffix):
            try:
                return int(float(text[:-1]) * mult)
            except ValueError:
                return 0
    try:
        return int(text)
    except ValueError:
        return 0


def _find_comment_section(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find the comment section continuation in a /next response.

    The comments are not inline in the initial /next response — they're behind
    a continuation token in the engagementPanels or the main contents.
    """
    # Try engagementPanels first (most common path for comments)
    for panel in data.get("engagementPanels", []):
        ep_renderer = panel.get("engagementPanelSectionListRenderer", {})
        panel_id = ep_renderer.get("panelIdentifier", "")
        if "comment" in panel_id:
            # The continuation is in the content
            content = ep_renderer.get("content", {})
            section = content.get("sectionListRenderer", {})
            for item_content in section.get("contents", []):
                item_section = item_content.get("itemSectionRenderer", {})
                for cont in item_section.get("contents", []):
                    if "continuationItemRenderer" in cont:
                        token = cont["continuationItemRenderer"].get("continuationEndpoint", {}).get(
                            "continuationCommand", {}
                        ).get("token")
                        if token:
                            return {"continuation": token}
            return None

    # Try frameworkUpdates path (newer YouTube responses)
    mutations = data.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", [])
    for mutation in mutations:
        payload = mutation.get("payload", {})
        if "engagementPanelSectionListEntityPayload" in payload:
            # This is complex — fall back to continuation approach
            pass

    return None


def _parse_entity_comment(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a commentEntityPayload from frameworkUpdates mutations."""
    props = entity.get("properties", {})
    author = entity.get("author", {})
    toolbar = entity.get("toolbar", {})

    comment_id = props.get("commentId", "")
    content = props.get("content", {}).get("content", "")
    published_text = props.get("publishedTime", "")

    author_name = author.get("displayName", "")
    channel_id = author.get("channelId", "")
    is_creator = author.get("isCreator", False)
    avatar_url = author.get("avatarThumbnailUrl", "")

    # Like count from toolbar
    like_count_text = toolbar.get("likeCountNotliked", "") or toolbar.get("likeCountLiked", "")
    like_count = _parse_count(like_count_text) if like_count_text else 0

    # Reply count
    reply_count_text = toolbar.get("replyCount", "")
    reply_count = _parse_count(reply_count_text) if reply_count_text else 0

    # Heart
    is_hearted = bool(toolbar.get("heartState") == "HEART_STATE_HEARTED")

    # Build author thumbnails
    author_thumbnails = []
    if avatar_url:
        author_thumbnails = [{"url": avatar_url, "width": 48, "height": 48}]

    result = {
        "commentId": comment_id,
        "author": author_name,
        "authorId": channel_id,
        "authorUrl": f"/channel/{channel_id}" if channel_id else "",
        "authorThumbnails": author_thumbnails,
        "authorIsChannelOwner": is_creator,
        "content": content,
        "contentHtml": content,
        "published": 0,
        "publishedText": published_text,
        "likeCount": like_count,
        "isHearted": is_hearted,
        "isPinned": False,
        "replies": None,
    }

    if reply_count > 0:
        result["replies"] = {"replyCount": reply_count, "continuation": None}

    return result


def _build_entity_map(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a map of commentId -> commentEntityPayload from frameworkUpdates."""
    entity_map = {}
    mutations = data.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", [])
    for mutation in mutations:
        payload = mutation.get("payload", {})
        if "commentEntityPayload" in payload:
            entity = payload["commentEntityPayload"]
            comment_id = entity.get("properties", {}).get("commentId", "")
            if comment_id:
                entity_map[comment_id] = entity
    return entity_map


def _parse_comments_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse an InnerTube continuation response containing comments.

    YouTube uses two formats:
    - Legacy: commentRenderer inside commentThreadRenderer (older responses)
    - New: commentViewModel with data in frameworkUpdates.entityBatchUpdate.mutations
    """
    comments = []
    continuation = None

    # Build entity map for the new format
    entity_map = _build_entity_map(data)

    # Extract comment IDs and continuation from onResponseReceivedEndpoints
    for endpoint in data.get("onResponseReceivedEndpoints", []):
        actions = endpoint.get("reloadContinuationItemsCommand", {}) or endpoint.get(
            "appendContinuationItemsAction", {}
        )
        items = actions.get("continuationItems", [])

        for item in items:
            if "commentThreadRenderer" in item:
                thread = item["commentThreadRenderer"]

                # New format: commentViewModel
                view_model = thread.get("commentViewModel", {}).get("commentViewModel", {})
                if view_model:
                    comment_id = view_model.get("commentId", "")
                    if comment_id and comment_id in entity_map:
                        comment = _parse_entity_comment(entity_map[comment_id])
                        comments.append(comment)
                    continue

                # Legacy format: commentRenderer
                comment_renderer = thread.get("comment", {}).get("commentRenderer", {})
                if comment_renderer:
                    comment = _parse_comment_renderer(comment_renderer)

                    replies_renderer = thread.get("replies", {}).get("commentRepliesRenderer", {})
                    if replies_renderer:
                        for rc in replies_renderer.get("contents", []):
                            if "continuationItemRenderer" in rc:
                                reply_token = (
                                    rc["continuationItemRenderer"]
                                    .get("continuationEndpoint", {})
                                    .get("continuationCommand", {})
                                    .get("token")
                                )
                                if reply_token:
                                    comment["replies"] = {"replyCount": 0, "continuation": reply_token}
                    comments.append(comment)

            elif "commentRenderer" in item:
                comments.append(_parse_comment_renderer(item["commentRenderer"]))

            elif "continuationItemRenderer" in item:
                token = (
                    item["continuationItemRenderer"]
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )
                if token:
                    continuation = token

    return {"commentCount": None, "comments": comments, "continuation": continuation}


async def get_comments(video_id: str, continuation: Optional[str] = None) -> Dict[str, Any]:
    """Get comments for a video using InnerTube API.

    Args:
        video_id: YouTube video ID
        continuation: Continuation token for pagination (from previous response)

    Returns:
        Dict with keys: comments (list), continuation (str or None)

    Raises:
        InnerTubeError: On API errors
    """
    if continuation:
        # Fetch next page using continuation token
        body = {"continuation": continuation}
        data = await innertube_post("next", body)
        return _parse_comments_response(data)

    # First page: get the video's comment section continuation token
    body = {"videoId": video_id}
    data = await innertube_post("next", body)

    # Find the comment section continuation token
    comment_section = _find_comment_section(data)
    if not comment_section or not comment_section.get("continuation"):
        logger.debug(f"[InnerTube] No comment section found for {video_id}")
        return {"commentCount": None, "comments": [], "continuation": None}

    # Fetch actual comments using the continuation token
    body = {"continuation": comment_section["continuation"]}
    data = await innertube_post("next", body)
    return _parse_comments_response(data)
