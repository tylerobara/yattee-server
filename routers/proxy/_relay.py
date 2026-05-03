"""Byte-relay proxy endpoint for playback.

Unlike ``/proxy/fast/{video_id}``, this endpoint takes the upstream URL
itself (HMAC-signed by the server at extraction time) and streams it
through to the client without yt-dlp re-extraction or on-disk caching.

Why a separate endpoint:

- ``/proxy/fast/`` re-runs yt-dlp on every request, which (a) re-downloads
  the whole file to ``/downloads/{id}_{itag}.{ext}`` before streaming and
  (b) fails outright when yt-dlp can't extract the video (e.g. ended live
  streams: ``This live event has ended``). For those, Invidious or
  InnerTube may have already returned a perfectly good URL, but the fast
  endpoint throws it away.

- The relay just streams bytes from upstream → client with full Range
  passthrough. Time-to-first-byte is small, seek works, and any URL the
  converter can produce (googlevideo, Invidious /videoplayback, an HLS
  variant manifest) is supported uniformly.

For HLS/DASH manifests, the relay rewrites segment URLs in the body so
segments also flow back through the relay (otherwise individual segments
would still hit googlevideo directly and could 403 for the same
client-IP-mismatch reason that motivated all of this).

``/proxy/fast/`` stays in place — it's still the right shape for
**downloads**, where caching the file on disk is desirable.
"""

import base64
import hashlib
import hmac
import logging
import re
import time
import urllib.parse
from typing import Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

import tokens as token_utils
from routers.proxy._streaming import router
from ytdlp_wrapper import is_safe_url

logger = logging.getLogger(__name__)


DEFAULT_TTL_SECONDS = 6 * 60 * 60

HLS_CONTENT_TYPES = ("application/vnd.apple.mpegurl", "application/x-mpegurl")
DASH_CONTENT_TYPES = ("application/dash+xml",)

# yt-dlp's default UA — what googlevideo expects.
UPSTREAM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Headers we accept from the client and forward to upstream.
_FORWARDED_REQUEST_HEADERS = ("range", "if-range", "if-none-match", "if-modified-since")

# Headers we copy from upstream back to the client.
_PASSTHROUGH_RESPONSE_HEADERS = (
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "etag",
    "last-modified",
    "cache-control",
    "expires",
)


def _sign(url: str, exp: int) -> str:
    """HMAC-SHA256 of ``url:exp`` keyed by the server's stream-token secret.

    Same key the existing token system uses (``tokens._get_signing_key``),
    so no new secret to provision.
    """
    payload = f"{url}:{exp}".encode("utf-8")
    digest = hmac.new(token_utils._get_signing_key(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")


def _verify(url: str, exp: int, sig: str) -> bool:
    expected = _sign(url, exp)
    return hmac.compare_digest(expected, sig)


def signed_relay_url(
    base_url: str,
    upstream_url: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    content_type: Optional[str] = None,
) -> str:
    """Mint a ``/proxy/relay?...`` URL the client can hit to play this stream.

    The signature gates "only the converter could have produced this URL".
    Without it the relay would be an open HTTP proxy.
    """
    exp = int(time.time()) + ttl_seconds
    sig = _sign(upstream_url, exp)
    params = {"url": upstream_url, "sig": sig, "exp": str(exp)}
    if content_type:
        params["ct"] = content_type
    return f"{base_url.rstrip('/')}/proxy/relay?{urllib.parse.urlencode(params)}"


# --- HLS manifest rewriting -------------------------------------------------

# Lines that are URLs in HLS manifests: either bare lines (segment) or the
# URI="..." attribute on EXT-X-KEY / EXT-X-MAP / EXT-X-MEDIA tags.
_HLS_URI_ATTR_RE = re.compile(r'(URI=")([^"]+)(")')


def _rewrite_hls(body: str, base_url: str, manifest_url: str, ttl_seconds: int) -> str:
    """Rewrite every segment / sub-playlist URL in an HLS manifest to a
    fresh signed relay URL.

    `manifest_url` is needed to resolve relative segment paths.
    """

    def absolutize(target: str) -> str:
        return urllib.parse.urljoin(manifest_url, target)

    out_lines = []
    for line in body.splitlines():
        stripped = line.strip()

        # Lines that aren't URLs we just keep as-is...
        if not stripped or stripped.startswith("#"):
            # ...except for tag lines that embed a URI="..." attribute.
            if "URI=" in stripped:
                def _sub(match):
                    return f'{match.group(1)}{signed_relay_url(base_url, absolutize(match.group(2)), ttl_seconds=ttl_seconds)}{match.group(3)}'
                line = _HLS_URI_ATTR_RE.sub(_sub, line)
            out_lines.append(line)
            continue

        # Bare URL line (segment or variant playlist)
        out_lines.append(signed_relay_url(base_url, absolutize(stripped), ttl_seconds=ttl_seconds))

    return "\n".join(out_lines) + ("\n" if body.endswith("\n") else "")


# --- DASH manifest rewriting ------------------------------------------------

# DASH manifests use BaseURL elements + SegmentTemplate/SegmentList with
# media="..." / initialization="...". A correct rewrite requires real XML
# parsing and resolution of segment templates. For v1 we leave DASH bodies
# untouched — the iOS client already prefers HLS first, and yt-dlp's DASH
# manifests use absolute googlevideo URLs whose `ip=` may still be bound,
# so this is a known limitation. Logged below so we notice it.

# --- Endpoint ---------------------------------------------------------------


@router.get("/relay")
async def relay(
    request: Request,
    url: str,
    sig: str,
    exp: int,
    ct: Optional[str] = None,
):
    if int(time.time()) > exp:
        raise HTTPException(status_code=403, detail="Relay URL expired")

    if not _verify(url, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid relay signature")

    # SSRF guard. The signature already prevents arbitrary URLs from
    # reaching here, but if the converter ever produced a URL pointing at
    # an internal service we still want to refuse.
    if not is_safe_url(url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")

    upstream_headers = {
        "User-Agent": UPSTREAM_USER_AGENT,
        # Don't let httpx negotiate gzip/br upstream — we relay raw bytes and
        # would have to either pass Content-Encoding through or decompress.
        # For media this is overwhelmingly the right call: video bytes are
        # not re-compressible anyway, and avoiding it sidesteps a class of
        # passthrough bugs.
        "Accept-Encoding": "identity",
    }
    for h in _FORWARDED_REQUEST_HEADERS:
        v = request.headers.get(h)
        if v is not None:
            upstream_headers[h] = v

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0),
        follow_redirects=True,
    )

    try:
        upstream_req = client.build_request("GET", url, headers=upstream_headers)
        upstream = await client.send(upstream_req, stream=True)
    except httpx.RequestError as e:
        await client.aclose()
        logger.warning(f"[Relay] Upstream connect failed for {url[:120]}: {e}")
        raise HTTPException(status_code=502, detail=f"Upstream connect failed: {e}") from e

    response_content_type = (ct or upstream.headers.get("content-type") or "").split(";")[0].strip().lower()
    is_hls = response_content_type in HLS_CONTENT_TYPES or url.split("?", 1)[0].endswith(".m3u8")
    is_dash = response_content_type in DASH_CONTENT_TYPES or url.split("?", 1)[0].endswith(".mpd")

    # --- Manifest path: buffer + rewrite + return one-shot --------------
    if is_hls and upstream.status_code == 200:
        try:
            body = await upstream.aread()
            text = body.decode("utf-8", errors="replace")
            base_url = f"{request.url.scheme}://{request.url.netloc}"
            rewritten = _rewrite_hls(text, base_url=base_url, manifest_url=url, ttl_seconds=DEFAULT_TTL_SECONDS)
            headers = {"content-type": "application/vnd.apple.mpegurl"}
            for h in ("cache-control", "etag", "last-modified"):
                v = upstream.headers.get(h)
                if v:
                    headers[h] = v
            return StreamingResponse(
                iter([rewritten.encode("utf-8")]),
                status_code=upstream.status_code,
                headers=headers,
            )
        finally:
            await upstream.aclose()
            await client.aclose()

    if is_dash:
        # Known limitation — pass through with a warning. See note above.
        logger.info(f"[Relay] DASH manifest passthrough (segments not rewritten): {url[:120]}")

    # --- Binary path: stream-and-relay ----------------------------------
    headers = {}
    for h in _PASSTHROUGH_RESPONSE_HEADERS:
        v = upstream.headers.get(h)
        if v:
            headers[h] = v
    if ct:
        headers["content-type"] = ct
    headers.setdefault("accept-ranges", "bytes")

    async def body_iter():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        headers=headers,
    )
