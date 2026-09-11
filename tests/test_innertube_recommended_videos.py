"""Regression tests for /next sidebar recommendation shapes."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from innertube._converters import _recommended_videos_from_next


def _lockup(video_id: str, title: str, content_type: str = "LOCKUP_CONTENT_TYPE_VIDEO") -> dict:
    return {
        "lockupViewModel": {
            "contentType": content_type,
            "contentId": video_id,
            "metadata": {
                "lockupMetadataViewModel": {
                    "title": {"content": title},
                    "metadata": {
                        "contentMetadataViewModel": {
                            "metadataRows": [
                                {
                                    "metadataParts": [
                                        {
                                            "text": {
                                                "content": "Some Channel",
                                                "commandRuns": [
                                                    {
                                                        "onTap": {
                                                            "innertubeCommand": {
                                                                "browseEndpoint": {"browseId": "UCabc123"}
                                                            }
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    ]
                                },
                                {
                                    "metadataParts": [
                                        {"text": {"content": "1.2M views"}},
                                        {"text": {"content": "3 days ago"}},
                                    ]
                                },
                            ]
                        }
                    },
                }
            },
            "contentImage": {
                "thumbnailViewModel": {
                    "overlays": [
                        {
                            "thumbnailOverlayBadgeViewModel": {
                                "thumbnailBadges": [{"thumbnailBadgeViewModel": {"text": "10:23"}}]
                            }
                        }
                    ]
                }
            },
        }
    }


def _next_response(results: list) -> dict:
    return {
        "contents": {
            "twoColumnWatchNextResults": {
                "secondaryResults": {"secondaryResults": {"results": results}}
            }
        }
    }


def test_top_level_lockup_view_model_is_parsed():
    """Current /next responses place lockupViewModel directly in results[*]."""
    nxt = _next_response(
        [
            _lockup("abc12345678", "First video"),
            _lockup("def12345678", "Second video"),
            {"continuationItemRenderer": {}},
        ]
    )
    out = _recommended_videos_from_next(nxt)
    assert [v["videoId"] for v in out] == ["abc12345678", "def12345678"]
    first = out[0]
    assert first["title"] == "First video"
    assert first["author"] == "Some Channel"
    assert first["authorId"] == "UCabc123"
    assert first["lengthSeconds"] == 623
    assert first["viewCountText"] == "1.2M views"


def test_non_video_lockups_are_skipped():
    nxt = _next_response(
        [
            _lockup("RDabc123", "Some mix", content_type="LOCKUP_CONTENT_TYPE_PLAYLIST"),
            _lockup("abc12345678", "A real video"),
        ]
    )
    out = _recommended_videos_from_next(nxt)
    assert [v["videoId"] for v in out] == ["abc12345678"]


def test_item_section_renderer_wrapped_lockups_still_parse():
    nxt = _next_response([{"itemSectionRenderer": {"contents": [_lockup("abc12345678", "Wrapped video")]}}])
    out = _recommended_videos_from_next(nxt)
    assert [v["videoId"] for v in out] == ["abc12345678"]


def test_legacy_compact_video_renderer_still_parses():
    nxt = _next_response(
        [
            {
                "compactVideoRenderer": {
                    "videoId": "abc12345678",
                    "title": {"simpleText": "Legacy video"},
                    "longBylineText": {
                        "runs": [
                            {
                                "text": "Legacy Channel",
                                "navigationEndpoint": {"browseEndpoint": {"browseId": "UCleg123"}},
                            }
                        ]
                    },
                    "lengthText": {"simpleText": "1:00"},
                }
            }
        ]
    )
    out = _recommended_videos_from_next(nxt)
    assert [v["videoId"] for v in out] == ["abc12345678"]
    assert out[0]["title"] == "Legacy video"
