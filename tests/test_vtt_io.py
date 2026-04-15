"""vtt_io モジュールのユニットテスト。"""
from __future__ import annotations

import textwrap
import tempfile
from pathlib import Path

import pytest

from vtt_synced_voice.vtt_io import (
    VttCue,
    _parse_timestamp,
    format_timestamp,
    read_vtt,
    write_vtt,
)


class TestFormatTimestamp:
    def test_zero(self):
        assert format_timestamp(0.0) == "00:00:00.000"

    def test_one_hour(self):
        assert format_timestamp(3600.0) == "01:00:00.000"

    def test_milliseconds(self):
        assert format_timestamp(1.500) == "00:00:01.500"

    def test_rounding(self):
        # 1フレーム（30fps）= 0.033...秒
        assert format_timestamp(0.0333) == "00:00:00.033"

    def test_negative_clamped_to_zero(self):
        assert format_timestamp(-1.0) == "00:00:00.000"


class TestParseTimestamp:
    def test_basic(self):
        assert _parse_timestamp("00:00:03.550") == pytest.approx(3.55)

    def test_with_hours(self):
        assert _parse_timestamp("01:02:03.456") == pytest.approx(3723.456)

    def test_roundtrip(self):
        for seconds in [0.0, 1.5, 61.001, 3661.999]:
            assert _parse_timestamp(format_timestamp(seconds)) == pytest.approx(seconds, abs=0.001)


class TestReadWriteVtt:
    VTT_CONTENT = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:02.500
        こんにちは

        00:00:03.000 --> 00:00:04.000
        世界
    """)

    def test_read_cue_count(self, tmp_path):
        vtt_file = tmp_path / "test.vtt"
        vtt_file.write_text(self.VTT_CONTENT, encoding="utf-8")
        cues = read_vtt(str(vtt_file))
        assert len(cues) == 2

    def test_read_timestamps(self, tmp_path):
        vtt_file = tmp_path / "test.vtt"
        vtt_file.write_text(self.VTT_CONTENT, encoding="utf-8")
        cues = read_vtt(str(vtt_file))
        assert cues[0].start == pytest.approx(1.0)
        assert cues[0].end == pytest.approx(2.5)
        assert cues[1].start == pytest.approx(3.0)

    def test_read_text(self, tmp_path):
        vtt_file = tmp_path / "test.vtt"
        vtt_file.write_text(self.VTT_CONTENT, encoding="utf-8")
        cues = read_vtt(str(vtt_file))
        assert cues[0].text == "こんにちは"
        assert cues[1].text == "世界"

    def test_read_bom_utf8(self, tmp_path):
        vtt_file = tmp_path / "test_bom.vtt"
        vtt_file.write_bytes(b"\xef\xbb\xbf" + self.VTT_CONTENT.encode("utf-8"))
        cues = read_vtt(str(vtt_file))
        assert len(cues) == 2

    def test_write_roundtrip(self, tmp_path):
        original = [
            VttCue(index=0, start=1.0, end=2.5, text="hello", original_start=1.0, original_end=2.5),
            VttCue(index=1, start=3.0, end=4.0, text="world", original_start=3.0, original_end=4.0),
        ]
        out_file = tmp_path / "out.vtt"
        write_vtt(original, str(out_file))
        restored = read_vtt(str(out_file))
        assert len(restored) == 2
        assert restored[0].start == pytest.approx(1.0)
        assert restored[0].text == "hello"
        assert restored[1].end == pytest.approx(4.0)

    def test_write_starts_with_webvtt(self, tmp_path):
        cues = [VttCue(index=0, start=0.0, end=1.0, text="test", original_start=0.0, original_end=1.0)]
        out_file = tmp_path / "out.vtt"
        write_vtt(cues, str(out_file))
        content = out_file.read_text(encoding="utf-8")
        assert content.startswith("WEBVTT")
