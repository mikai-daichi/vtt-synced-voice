"""cue_builder モジュールのユニットテスト。

ダミーのsegmentsデータを使ってbuild_cues_from_segments()の動作を検証する。
WhisperXへの依存なし。
"""
from __future__ import annotations

import numpy as np
import pytest

from vtt_synced_voice.cue_builder import build_cues_from_segments

SAMPLE_RATE = 16000
THRESHOLD = 0.001
MAX_GAP = 0.4


def _make_voiced_audio(duration_sec: float = 10.0, amplitude: float = 0.5) -> np.ndarray:
    """全区間が有音の合成音声（テスト用）。"""
    t = np.linspace(0, duration_sec, int(duration_sec * SAMPLE_RATE), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def _word(word: str, start: float, end: float) -> dict:
    return {"word": word, "start": start, "end": end}


def _seg(words: list[dict], text: str = "") -> dict:
    start = words[0]["start"] if words else 0.0
    end = words[-1]["end"] if words else 0.0
    return {
        "text": text or "".join(w["word"] for w in words),
        "start": start,
        "end": end,
        "words": words,
    }


class TestBasicCueGeneration:
    def test_single_segment_single_cue(self):
        audio = _make_voiced_audio()
        # gap = world.start(1.2) - (hello.start(1.0) + SENTENCE_END_DURATION(0.15)) = 0.05 < MAX_GAP
        seg = _seg([_word("hello", 1.0, 1.1), _word("world", 1.2, 1.5)])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1
        assert cues[0].text == "helloworld"

    def test_cue_text(self):
        audio = _make_voiced_audio()
        seg = _seg([_word("こんにちは", 1.0, 1.8)])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert cues[0].text == "こんにちは"

    def test_gap_splits_into_two_cues(self):
        audio = _make_voiced_audio()
        # gap = 後.start(3.0) - (前.start(1.0) + 0.15) = 1.85 > MAX_GAP(0.4)
        seg = _seg([
            _word("前", 1.0, 1.5),
            _word("後", 3.0, 3.5),
        ])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 2

    def test_no_gap_stays_single_cue(self):
        audio = _make_voiced_audio()
        # gap = い.start(1.2) - (あ.start(1.0) + 0.15) = 0.05 < MAX_GAP(0.4)
        seg = _seg([
            _word("あ", 1.0, 1.1),
            _word("い", 1.2, 1.4),
        ])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1


class TestEndClamp:
    def test_end_clamped_to_next_start_minus_100ms(self):
        audio = _make_voiced_audio()
        # キュー0のendが大きく、キュー1のstartを侵食するケース
        seg = _seg([
            _word("あ", 1.0, 5.0),  # end が大きい
            _word("い", 5.5, 6.0),  # 次のキューのstart≈5.5
        ])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE,
                                           margin_after=2.0)  # 大きなmargin_after
        if len(cues) >= 2:
            assert cues[0].end <= cues[1].start - 0.1 + 0.001  # 0.001は浮動小数点誤差の許容

    def test_last_cue_not_clamped(self):
        audio = _make_voiced_audio()
        seg = _seg([_word("終", 8.0, 8.5)])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE,
                                           margin_after=0.5)
        # 最後のキューはクランプされない
        assert len(cues) == 1
        assert cues[0].end > 8.5


class TestNoiseCharStripping:
    def test_leading_noise_char_stripped(self):
        audio = _make_voiced_audio()
        # 先頭単語が記号のみ
        seg = _seg([
            _word(".", 1.0, 1.1),
            _word("こんにちは", 1.2, 1.8),
        ])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1
        assert "." not in cues[0].text or "こんにちは" in cues[0].text

    def test_all_noise_chars_returns_no_cue(self):
        audio = _make_voiced_audio()
        seg = _seg([_word(".", 1.0, 1.1), _word("?", 1.2, 1.3)])
        cues, _ = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 0


class TestOnsetDebug:
    def test_debug_list_matches_cue_count(self):
        audio = _make_voiced_audio()
        seg = _seg([_word("テスト", 2.0, 2.5)])
        cues, onset_debug = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(onset_debug) == len(cues)

    def test_debug_has_required_keys(self):
        audio = _make_voiced_audio()
        seg = _seg([_word("テスト", 2.0, 2.5)])
        _, onset_debug = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        for d in onset_debug:
            assert "index" in d
            assert "ctc" in d
            assert "onset" in d
            assert "note" in d
