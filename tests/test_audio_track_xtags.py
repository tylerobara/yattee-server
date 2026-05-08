"""Tests for xtags-driven audio track displayName enrichment.

iOS Yattee detects "original audio" by substring-matching "original" in
audioTrack.displayName (or by parsing xtags from the stream URL). The relay
proxy hides xtags, so the server bakes the marker into displayName.
"""

from converters._helpers import _enrich_audio_display_name, _xtags_from_url


class TestXtagsFromUrl:
    def test_extracts_acont_and_lang(self):
        url = "https://rr.googlevideo.com/videoplayback?xtags=acont%3Doriginal%3Alang%3Den-US&itag=251"
        assert _xtags_from_url(url) == {"acont": "original", "lang": "en-US"}

    def test_dubbed_auto(self):
        url = "https://rr.googlevideo.com/videoplayback?xtags=acont%3Ddubbed-auto%3Alang%3Dde-DE"
        assert _xtags_from_url(url) == {"acont": "dubbed-auto", "lang": "de-DE"}

    def test_no_xtags(self):
        assert _xtags_from_url("https://rr.googlevideo.com/videoplayback?itag=251") == {}

    def test_empty_or_none(self):
        assert _xtags_from_url("") == {}
        assert _xtags_from_url(None) == {}

    def test_drc_flag(self):
        url = "https://rr.googlevideo.com/videoplayback?xtags=acont%3Doriginal%3Adrc%3D1%3Alang%3Den"
        assert _xtags_from_url(url) == {"acont": "original", "drc": "1", "lang": "en"}


class TestEnrichAudioDisplayName:
    def test_appends_original_when_missing(self):
        xtags = {"acont": "original", "lang": "en-US"}
        assert _enrich_audio_display_name("English (United States)", xtags) == "English (United States) original"

    def test_does_not_duplicate_original(self):
        xtags = {"acont": "original", "lang": "en"}
        assert _enrich_audio_display_name("English original", xtags) == "English original"

    def test_case_insensitive_dedupe(self):
        xtags = {"acont": "original", "lang": "en"}
        assert _enrich_audio_display_name("English Original Audio", xtags) == "English Original Audio"

    def test_falls_back_to_lang_when_displayname_missing(self):
        xtags = {"acont": "original", "lang": "en-US"}
        assert _enrich_audio_display_name(None, xtags) == "en-US original"

    def test_dubbed_auto_marker(self):
        xtags = {"acont": "dubbed-auto", "lang": "de-DE"}
        result = _enrich_audio_display_name("German", xtags)
        assert "auto-dubbed" in result.lower()

    def test_dubbed_auto_dedupe(self):
        xtags = {"acont": "dubbed-auto", "lang": "de-DE"}
        assert _enrich_audio_display_name("German (Auto-dubbed)", xtags) == "German (Auto-dubbed)"

    def test_no_xtags_passthrough(self):
        assert _enrich_audio_display_name("English", {}) == "English"
        assert _enrich_audio_display_name(None, {}) is None

    def test_unknown_acont_passthrough(self):
        xtags = {"acont": "descriptive", "lang": "en"}
        assert _enrich_audio_display_name("English descriptive", xtags) == "English descriptive"
