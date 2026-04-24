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
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1
        assert cues[0].text == "helloworld"

    def test_cue_text(self):
        audio = _make_voiced_audio()
        seg = _seg([_word("こんにちは", 1.0, 1.8)])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert cues[0].text == "こんにちは"

    def test_gap_splits_into_two_cues(self):
        audio = _make_voiced_audio()
        # gap = 後.start(3.0) - (前.start(1.0) + 0.15) = 1.85 > MAX_GAP(0.4)
        seg = _seg([
            _word("前", 1.0, 1.5),
            _word("後", 3.0, 3.5),
        ])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 2

    def test_no_gap_stays_single_cue(self):
        audio = _make_voiced_audio()
        # gap = い.start(1.2) - (あ.start(1.0) + 0.15) = 0.05 < MAX_GAP(0.4)
        seg = _seg([
            _word("あ", 1.0, 1.1),
            _word("い", 1.2, 1.4),
        ])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1

    def test_original_start_equals_ctc_start(self):
        """build_cues_from_segments は onset 補正なし: start == original_start == CTC start。"""
        audio = _make_voiced_audio()
        seg = _seg([_word("テスト", 2.0, 2.5)])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert cues[0].start == 2.0
        assert cues[0].original_start == 2.0


class TestEndClamp:
    def test_end_clamp_done_by_apply_onset(self):
        """endクランプは apply_onset_to_cues() の責務: build 後はクランプ前の値のまま。"""
        audio = _make_voiced_audio()
        seg = _seg([
            _word("あ", 1.0, 1.1),
            _word("い", 3.0, 3.5),
        ])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        # 2キューに分割され、それぞれ end は未クランプ
        assert len(cues) == 2

    def test_last_cue_end_is_sentence_end_duration(self):
        """文末キューの end は 末尾単語の start + SENTENCE_END_DURATION。"""
        from vtt_synced_voice.cue_builder import SENTENCE_END_DURATION
        audio = _make_voiced_audio()
        seg = _seg([_word("終", 8.0, 8.5)])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1
        assert abs(cues[0].end - (8.0 + SENTENCE_END_DURATION)) < 0.001


class TestNoiseCharStripping:
    def test_leading_noise_char_stripped(self):
        audio = _make_voiced_audio()
        # 先頭単語が記号のみ
        seg = _seg([
            _word(".", 1.0, 1.1),
            _word("こんにちは", 1.2, 1.8),
        ])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 1
        assert "." not in cues[0].text or "こんにちは" in cues[0].text

    def test_all_noise_chars_returns_no_cue(self):
        audio = _make_voiced_audio()
        seg = _seg([_word(".", 1.0, 1.1), _word("?", 1.2, 1.3)])
        cues = build_cues_from_segments([seg], MAX_GAP, audio, SAMPLE_RATE)
        assert len(cues) == 0
