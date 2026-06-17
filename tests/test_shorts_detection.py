"""Tests for YouTube Shorts detection across InnerTube response shapes."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from innertube._converters import (
    _detect_is_short,
    innertube_player_to_invidious_video,
    rich_item_to_invidious,
)


def test_reel_item_renderer_marks_short():
    item = {
        "content": {
            "reelItemRenderer": {
                "videoId": "TGtzINFzY2Q",
                "headline": {"simpleText": "A short clip"},
                "viewCountText": {"simpleText": "1.2M views"},
            }
        }
    }
    converted = rich_item_to_invidious(item)
    assert converted is not None
    assert converted["isShort"] is True


def test_shorts_lockup_view_model_marks_short():
    item = {
        "content": {
            "shortsLockupViewModel": {
                "entityId": "shorts-shelf-item-TGtzINFzY2Q",
                "onTap": {
                    "innertubeCommand": {
                        "reelWatchEndpoint": {"videoId": "TGtzINFzY2Q"}
                    }
                },
                "overlayMetadata": {
                    "primaryText": {"content": "Short title"},
                    "secondaryText": {"content": "1M views"},
                },
            }
        }
    }
    converted = rich_item_to_invidious(item)
    assert converted is not None
    assert converted["videoId"] == "TGtzINFzY2Q"
    assert converted["isShort"] is True


def test_lockup_view_model_video_is_not_short():
    item = {
        "content": {
            "lockupViewModel": {
                "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                "contentId": "eLP3ag0YpyA",
                "metadata": {
                    "lockupMetadataViewModel": {
                        "title": {"content": "Regular video"},
                    }
                },
            }
        }
    }
    converted = rich_item_to_invidious(item)
    assert converted is not None
    assert converted["isShort"] is False


def test_video_renderer_is_not_short():
    item = {
        "content": {
            "videoRenderer": {
                "videoId": "abcdefghijk",
                "title": {"simpleText": "Regular video"},
                "lengthText": {"simpleText": "12:34"},
            }
        }
    }
    converted = rich_item_to_invidious(item)
    assert converted is not None
    assert converted["isShort"] is False


def test_detect_is_short_reads_is_shorts_eligible():
    player = {"microformat": {"playerMicroformatRenderer": {"isShortsEligible": True}}}
    assert _detect_is_short(player, {}) is True

    player = {"microformat": {"playerMicroformatRenderer": {"isShortsEligible": False}}}
    assert _detect_is_short(player, {}) is False


def test_detect_is_short_returns_none_when_field_absent():
    """Unknown is the honest answer when the signal is missing — no length-based guess."""
    player = {"microformat": {"playerMicroformatRenderer": {}}}
    assert _detect_is_short(player, {}) is None


def test_player_response_propagates_is_short():
    player = {
        "videoDetails": {
            "videoId": "TGtzINFzY2Q",
            "title": "T",
            "author": "A",
            "channelId": "UC123",
            "lengthSeconds": "30",
        },
        "microformat": {"playerMicroformatRenderer": {"isShortsEligible": True}},
    }
    converted = innertube_player_to_invidious_video(player)
    assert converted["isShort"] is True
