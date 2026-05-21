"""Regression tests for current InnerTube channel-video rich grid shape."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from feed_fetcher import _process_innertube_video
from innertube._converters import rich_item_to_invidious


def test_rich_item_lockup_view_model_channel_video_converts_to_video():
    """Channel video tabs now wrap videos in lockupViewModel, not videoRenderer."""
    item = {
        "content": {
            "lockupViewModel": {
                "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                "contentId": "eLP3ag0YpyA",
                "metadata": {
                    "lockupMetadataViewModel": {
                        "title": {"content": "Google’s Most-Hated Announcement Ever"},
                        "metadata": {
                            "contentMetadataViewModel": {
                                "metadataRows": [
                                    {
                                        "metadataParts": [
                                            {"text": {"content": "974K views"}},
                                            {"text": {"content": "1 day ago"}},
                                        ]
                                    }
                                ]
                            }
                        },
                    }
                },
                "contentImage": {
                    "thumbnailViewModel": {
                        "overlays": [
                            {
                                "thumbnailBottomOverlayViewModel": {
                                    "badges": [
                                        {
                                            "thumbnailBadgeViewModel": {
                                                "text": "18:01",
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            }
        }
    }

    converted = rich_item_to_invidious(item)

    assert converted is not None
    assert converted["type"] == "video"
    assert converted["videoId"] == "eLP3ag0YpyA"
    assert converted["title"] == "Google’s Most-Hated Announcement Ever"
    assert converted["publishedText"] == "1 day ago"
    assert converted["viewCount"] == 974000
    assert converted["lengthSeconds"] == 1081


def test_feed_processing_uses_lockup_published_text_for_sort_timestamp():
    """Fetched lockup videos still receive a timestamp before database sorting."""
    converted = {
        "videoId": "eLP3ag0YpyA",
        "title": "Google’s Most-Hated Announcement Ever",
        "author": "Linus Tech Tips",
        "authorId": "UCXuqSBlHAE6Xw-yeJA0Tunw",
        "lengthSeconds": 1081,
        "viewCount": 974000,
        "publishedText": "1 day ago",
        "videoThumbnails": [],
    }

    processed = _process_innertube_video(converted, "UCXuqSBlHAE6Xw-yeJA0Tunw")

    assert processed["published_text"] == "1 day ago"
    assert processed["published"] is not None
