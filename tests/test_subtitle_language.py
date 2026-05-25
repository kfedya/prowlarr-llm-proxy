"""Tests for subtitle language detection and renaming."""

import pytest

from app.services.subtitle import SubtitleService


class TestDetectLanguageFromFilename:
    """Tests for SubtitleService.detect_language_from_filename."""

    def test_detect_language_2_letter_en(self):
        assert SubtitleService.detect_language_from_filename("video.en.srt") == "eng"

    def test_detect_language_2_letter_ru(self):
        assert SubtitleService.detect_language_from_filename("video.ru.srt") == "rus"

    def test_detect_language_2_letter_fr(self):
        assert SubtitleService.detect_language_from_filename("video.fr.srt") == "fre"

    def test_detect_language_3_letter_eng(self):
        """3-letter codes pass through."""
        assert SubtitleService.detect_language_from_filename("video.eng.srt") == "eng"

    def test_detect_language_3_letter_rus(self):
        assert SubtitleService.detect_language_from_filename("video.rus.srt") == "rus"

    def test_detect_language_full_name_english(self):
        assert SubtitleService.detect_language_from_filename("video.english.srt") == "eng"

    def test_detect_language_full_name_russian(self):
        assert SubtitleService.detect_language_from_filename("video.russian.srt") == "rus"

    def test_detect_language_unknown(self):
        assert SubtitleService.detect_language_from_filename("video.xyz.srt") is None

    def test_detect_language_no_lang_part(self):
        """Single-dot filename has no language segment."""
        assert SubtitleService.detect_language_from_filename("video.srt") is None

    def test_detect_language_case_insensitive_upper(self):
        assert SubtitleService.detect_language_from_filename("video.EN.srt") == "eng"

    def test_detect_language_case_insensitive_title(self):
        assert SubtitleService.detect_language_from_filename("video.English.srt") == "eng"

    def test_detect_language_case_insensitive_mixed(self):
        assert SubtitleService.detect_language_from_filename("video.RuS.srt") == "rus"


class TestRenameSubtitleWithLanguage:
    """Tests for SubtitleService.rename_subtitle_with_language."""

    def test_rename_with_language_detected(self):
        result = SubtitleService.rename_subtitle_with_language(
            "video.en.srt", "Show.S01E01.mkv"
        )
        assert result == "Show.S01E01.eng.srt"

    def test_rename_with_no_language(self):
        """Unknown language keeps original filename."""
        result = SubtitleService.rename_subtitle_with_language(
            "video.srt", "Show.S01E01.mkv"
        )
        assert result == "video.srt"

    def test_rename_preserves_ass_extension(self):
        """Non-srt subtitle extensions are preserved."""
        result = SubtitleService.rename_subtitle_with_language(
            "video.en.ass", "Show.S01E01.mkv"
        )
        assert result == "Show.S01E01.eng.ass"

    def test_rename_with_3_letter_code(self):
        result = SubtitleService.rename_subtitle_with_language(
            "video.rus.srt", "Show.S01E01.mkv"
        )
        assert result == "Show.S01E01.rus.srt"

    def test_rename_with_full_name(self):
        result = SubtitleService.rename_subtitle_with_language(
            "video.french.srt", "Show.S01E01.mkv"
        )
        assert result == "Show.S01E01.fre.srt"

    def test_rename_unknown_keeps_original(self):
        """Unknown language code returns original filename unchanged."""
        result = SubtitleService.rename_subtitle_with_language(
            "random_subtitle.srt", "Show.S01E01.mkv"
        )
        assert result == "random_subtitle.srt"

    def test_rename_preserves_vtt_extension(self):
        result = SubtitleService.rename_subtitle_with_language(
            "video.de.vtt", "Show.S01E01.mkv"
        )
        assert result == "Show.S01E01.ger.vtt"
