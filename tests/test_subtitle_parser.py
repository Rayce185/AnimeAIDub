"""Tests for subtitle parser."""

from pathlib import Path
from pipeline.subtitle_parser import parse_subtitles, SubtitleEntry, ParseResult


TEST_DIR = Path(__file__).parent / "fixtures"


def test_ass_filters_signs(tmp_path: Path):
    """ASS parser should exclude Sign/Title styles and keep Default dialogue."""
    ass_content = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
Style: Sign,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Sign,,0,0,0,,{\\pos(100,200)}Room 101
Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Hello world!
Dialogue: 0,0:00:09.00,0:00:12.00,Default,,0,0,0,,How are you?
"""
    f = tmp_path / "test.ass"
    f.write_text(ass_content)

    result = parse_subtitles(f)
    assert result.dialogue_count == 2
    assert result.entries[0].text == "Hello world!"
    assert result.entries[1].text == "How are you?"
    assert "Sign" in result.styles_found
    assert "Default" in result.styles_found


def test_ass_strips_override_tags(tmp_path: Path):
    """ASS override tags like {\\an8} should be removed from text."""
    ass_content = """[Script Info]
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\\an8}They're finally gone...
Dialogue: 0,0:00:06.00,0:00:10.00,Default,,0,0,0,,Line one\\NLine two
"""
    f = tmp_path / "test.ass"
    f.write_text(ass_content)

    result = parse_subtitles(f)
    assert result.entries[0].text == "They're finally gone..."
    assert result.entries[1].text == "Line one Line two"


def test_ass_extracts_speaker_name(tmp_path: Path):
    """ASS Name field should populate speaker."""
    ass_content = """[Script Info]
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:05.00,Default,Aki,0,0,0,,Hello there.
Dialogue: 0,0:00:06.00,0:00:10.00,Default,Chio,0,0,0,,Hey!
"""
    f = tmp_path / "test.ass"
    f.write_text(ass_content)

    result = parse_subtitles(f)
    assert result.entries[0].speaker == "Aki"
    assert result.entries[1].speaker == "Chio"


def test_srt_basic_parse(tmp_path: Path):
    """SRT parser should extract timestamps and text."""
    srt_content = """1
00:00:05,000 --> 00:00:08,000
Hello world!

2
00:00:09,000 --> 00:00:12,500
How are you?
"""
    f = tmp_path / "test.srt"
    f.write_text(srt_content)

    result = parse_subtitles(f)
    assert result.format == "srt"
    assert result.dialogue_count == 2
    assert result.entries[0].text == "Hello world!"
    assert result.entries[0].start_ms == 5000
    assert result.entries[0].end_ms == 8000
    assert result.entries[1].text == "How are you?"


def test_srt_strips_html_tags(tmp_path: Path):
    """SRT HTML-style tags should be removed."""
    srt_content = """1
00:00:01,000 --> 00:00:05,000
<i>Thinking to himself...</i>

2
00:00:06,000 --> 00:00:10,000
<b>Important!</b>
"""
    f = tmp_path / "test.srt"
    f.write_text(srt_content)

    result = parse_subtitles(f)
    assert result.entries[0].text == "Thinking to himself..."
    assert result.entries[1].text == "Important!"


def test_deduplication(tmp_path: Path):
    """Sequential entries with same text should be collapsed."""
    srt_content = """1
00:00:01,000 --> 00:00:01,500
Sign text

2
00:00:01,500 --> 00:00:02,000
Sign text

3
00:00:02,000 --> 00:00:02,500
Sign text

4
00:00:05,000 --> 00:00:08,000
Actual dialogue
"""
    f = tmp_path / "test.srt"
    f.write_text(srt_content)

    result = parse_subtitles(f)
    # The 3 "Sign text" entries should collapse into 1
    sign_entries = [e for e in result.entries if e.text == "Sign text"]
    assert len(sign_entries) == 1
    assert sign_entries[0].start_ms == 1000
    assert sign_entries[0].end_ms == 2500


def test_min_duration_filter(tmp_path: Path):
    """Entries shorter than min_duration_ms should be filtered."""
    srt_content = """1
00:00:01,000 --> 00:00:01,040
Flash frame

2
00:00:05,000 --> 00:00:08,000
Normal dialogue
"""
    f = tmp_path / "test.srt"
    f.write_text(srt_content)

    result = parse_subtitles(f, min_duration_ms=100)
    assert result.dialogue_count == 1
    assert result.entries[0].text == "Normal dialogue"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tests = [
            test_ass_filters_signs,
            test_ass_strips_override_tags,
            test_ass_extracts_speaker_name,
            test_srt_basic_parse,
            test_srt_strips_html_tags,
            test_deduplication,
            test_min_duration_filter,
        ]
        for t in tests:
            try:
                t(tmp)
                print(f"  PASS: {t.__name__}")
            except AssertionError as e:
                print(f"  FAIL: {t.__name__} — {e}")
            except Exception as e:
                print(f"  ERROR: {t.__name__} — {e}")
