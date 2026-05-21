"""Regression tests for current InnerTube channel-video rich grid shape."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from feed_fetcher import _process_innertube_video
from innertube._browse import _extract_items_from_tab
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


def test_trending_grid_renderer_shelf_videos_are_extracted():
    """Gaming trending now nests gridVideoRenderer items inside shelf.content.gridRenderer."""
    grid_video = {
        "videoId": "sTWztaLjD20",
        "title": {"simpleText": "Trending gaming video"},
        "publishedTimeText": {"simpleText": "2 days ago"},
        "shortBylineText": {
            "runs": [
                {
                    "text": "Gaming Creator",
                    "navigationEndpoint": {"browseEndpoint": {"browseId": "UCgaming"}},
                }
            ]
        },
        "viewCountText": {"simpleText": "1.2M views"},
        "thumbnailOverlays": [
            {
                "thumbnailOverlayTimeStatusRenderer": {
                    "text": {"simpleText": "12:34"},
                }
            }
        ],
    }
    data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "selected": True,
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "itemSectionRenderer": {
                                                "contents": [
                                                    {
                                                        "shelfRenderer": {
                                                            "content": {
                                                                "gridRenderer": {
                                                                    "items": [{"gridVideoRenderer": grid_video}]
                                                                }
                                                            }
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
                ]
            }
        }
    }

    items, continuation = _extract_items_from_tab(data)

    assert continuation is None
    assert len(items) == 1
    assert items[0]["videoId"] == "sTWztaLjD20"
    assert items[0]["title"] == "Trending gaming video"
    assert items[0]["author"] == "Gaming Creator"
    assert items[0]["authorId"] == "UCgaming"
    assert items[0]["publishedText"] == "2 days ago"
    assert items[0]["viewCount"] == 1200000
    assert items[0]["lengthSeconds"] == 754
