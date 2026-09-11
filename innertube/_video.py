"""InnerTube player + next endpoints - video metadata and stream shapes.

Fetches video details from YouTube's InnerTube /player and /next endpoints
in parallel, then merges the result into an Invidious-shaped dict. Stream
URLs from the WEB client are ciphered, so the caller is expected to join
deciphered URLs from yt-dlp by itag via `merge_stream_urls`.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from cachetools import TTLCache

from converters._helpers import _xtags_from_url
from innertube._client import InnerTubeError, innertube_post
from innertube._converters import _parse_storyboard_spec, innertube_player_to_invidious_video

logger = logging.getLogger("innertube")

_video_cache: Optional[TTLCache] = None


def _get_cache() -> TTLCache:
    global _video_cache
    if _video_cache is None:
        from settings import get_settings

        _video_cache = TTLCache(maxsize=100, ttl=get_settings().cache_video_ttl)
    return _video_cache


def reset_cache() -> None:
    global _video_cache
    _video_cache = None


async def get_video_player_next(video_id: str, use_cache: bool = True) -> Dict[str, Any]:
    """Fetch /player and /next in parallel and return an Invidious-shaped dict.

    Raises InnerTubeError when the video is unplayable (LOGIN_REQUIRED, ERROR,
    UNPLAYABLE) so the caller can fall back to yt-dlp / Invidious.

    The returned dict has the same field names as `invidious_to_video_response`
    consumes, but its formatStreams/adaptiveFormats URLs are empty — stream URLs
    must be merged in separately via `merge_stream_urls`.
    """
    cache = _get_cache()
    cache_key = f"player_next:{video_id}"
    if use_cache and cache_key in cache:
        return cache[cache_key]

    player_body = {
        "videoId": video_id,
        "playbackContext": {"contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS"}},
    }
    next_body = {"videoId": video_id}

    player_task = innertube_post("player", player_body)
    next_task = innertube_post("next", next_body)

    results = await asyncio.gather(player_task, next_task, return_exceptions=True)
    player_data, next_data = results

    if isinstance(player_data, Exception):
        raise player_data

    # /next is optional enrichment — don't fail if it breaks
    if isinstance(next_data, Exception):
        logger.warning(f"[InnerTube] /next failed for {video_id}: {next_data}")
        next_data = {}

    # NOTE: we don't raise on UNPLAYABLE/LOGIN_REQUIRED — YouTube frequently
    # returns those for WEB-client /player calls from data-centre IPs even
    # though videoDetails, /next metadata and captions are still populated.
    # The router merges yt-dlp's deciphered URLs by itag, and if the merge
    # yields no streams it falls back to the yt-dlp-only path.
    playability = player_data.get("playabilityStatus", {}) or {}
    status = playability.get("status")
    if status and status != "OK":
        logger.info(f"[InnerTube] /player playabilityStatus={status} for {video_id}")

    if not player_data.get("videoDetails") and not next_data:
        raise InnerTubeError(
            f"No video data: playabilityStatus={status}",
            is_retryable=False,
        )

    result = innertube_player_to_invidious_video(player_data, next_data)

    # The WEB client often omits playerStoryboardSpecRenderer. When the primary
    # /player response has no storyboards, do a supplemental /player call with
    # the TVHTML5 client context which reliably returns the spec, and parse it
    # into the Invidious-shaped list. yt-dlp and Invidious remain as further
    # fallbacks in the router if this also yields nothing.
    if not result.get("storyboards"):
        try:
            spec = await _fetch_storyboard_spec_tvhtml5(video_id)
            if spec:
                result["storyboards"] = _parse_storyboard_spec(spec, video_id)
        except InnerTubeError as e:
            logger.info(f"[InnerTube] TVHTML5 storyboard fetch failed for {video_id}: {e}")

    cache[cache_key] = result
    return result


async def _fetch_storyboard_spec_tvhtml5(video_id: str) -> str:
    """Fetch the raw storyboard spec string via the TVHTML5 client.

    The WEB client omits playerStoryboardSpecRenderer for many videos; TVHTML5
    consistently returns it. We call /player with an overridden context and
    extract the spec string. Caller is responsible for parsing it.
    """
    body = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "TVHTML5",
                "clientVersion": "7.20240304.10.00",
                "hl": "en",
                "gl": "US",
            }
        },
    }
    data = await innertube_post("player", body, use_cookies=False)
    renderer = data.get("storyboards", {}).get("playerStoryboardSpecRenderer", {}) or {}
    return renderer.get("spec") or ""


def _ytdlp_format_key(fmt: Dict[str, Any]) -> Optional[Tuple[str, Tuple[Tuple[str, str], ...]]]:
    """Return the (itag, xtags) join key for a yt-dlp format, or None if unusable.

    yt-dlp names YouTube formats by itag, suffixed when one itag has several
    variants: `140-3` (audio track index on multi-language videos), `251-drc`
    (dynamic range compressed), `hls-480` (HLS ladder). The suffix alone does
    not say which InnerTube variant it is, but the deciphered googlevideo URL
    carries the plain `xtags=acont=...:lang=...` marker, which is exactly what
    InnerTube's protobuf `xtags` decodes to. Formats without an `xtags` param
    (video-only, single-audio-track videos) key on the bare itag.
    """
    url = fmt.get("url")
    if not url:
        return None
    fid = str(fmt.get("format_id") or "")
    itag = fid.split("-", 1)[0]
    if not itag.isdigit():
        return None
    return itag, tuple(sorted(_xtags_from_url(url).items()))


def merge_stream_urls(
    it_video: Dict[str, Any], ytdlp_formats: Optional[List[Dict[str, Any]]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Join InnerTube format shapes with yt-dlp's deciphered URLs by itag.

    InnerTube provides rich metadata (itag, mimeType, bitrate, audioTrack, ...)
    but its WEB client URLs are ciphered. yt-dlp returns deciphered URLs keyed
    by format_id, which is the itag for YouTube, plus the per-track `xtags`
    on the URL for videos with several audio tracks (see `_ytdlp_format_key`).
    We look up by (itag, xtags) and drop formats we cannot serve. InnerTube
    variants yt-dlp does not expose (DRC, `vb=1`) therefore fall away instead
    of duplicating the same URL under several entries.

    Returns (formatStreams, adaptiveFormats) as lists of Invidious-shaped dicts
    with the internal `_xtags` helper key removed.
    """
    ytdlp_by_key: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, Any]] = {}
    for fmt in ytdlp_formats or []:
        key = _ytdlp_format_key(fmt)
        if key is not None:
            ytdlp_by_key.setdefault(key, fmt)

    def _join(fmt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        itag = str(fmt.get("itag") or "")
        xtags = fmt.get("_xtags") or {}
        yt = ytdlp_by_key.get((itag, tuple(sorted(xtags.items()))))
        if not yt:
            return None
        merged = {k: v for k, v in fmt.items() if k != "_xtags"}
        merged["url"] = yt["url"]
        return merged

    merged_format_streams: List[Dict[str, Any]] = []
    merged_adaptive: List[Dict[str, Any]] = []
    dropped = 0

    for fmt in it_video.get("formatStreams", []):
        merged = _join(fmt)
        if merged is None:
            dropped += 1
            continue
        merged_format_streams.append(merged)

    for fmt in it_video.get("adaptiveFormats", []):
        merged = _join(fmt)
        if merged is None:
            dropped += 1
            continue
        merged_adaptive.append(merged)

    if dropped:
        logger.debug(f"[InnerTube] merge_stream_urls: dropped {dropped} itag(s) missing from yt-dlp")

    return merged_format_streams, merged_adaptive
