"""onset モジュールのユニットテスト。

合成音声波形を使ってfind_onset()の動作を検証する。
WhisperXへの依存なし。
"""
from __future__ import annotations

import numpy as np
import pytest

from vtt_synced_voice.onset import find_onset

SAMPLE_RATE = 16000
THRESHOLD = 0.001


def _make_audio(silence_sec: float, voice_sec: float, voice_amplitude: float = 0.5) -> np.ndarray:
    """無音区間 + 有音区間の合成音声を生成する。"""
    silence = np.zeros(int(silence_sec * SAMPLE_RATE), dtype=np.float32)
    t = np.linspace(0, voice_sec, int(voice_sec * SAMPLE_RATE), endpoint=False)
    voice = (voice_amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.concatenate([silence, voice])


class TestFindOnsetBackward:
    """フェーズ2a: CTC startが有音区間にある場合、逆方向スキャンでonsetを見つける。"""

    def test_finds_onset_before_ctc(self):
        # 0.2秒無音 + 0.5秒有音、CTCは有音区間の中間（0.45秒）
        audio = _make_audio(silence_sec=0.2, voice_sec=0.5)
        ctc_start = 0.45
        onset_sec, note = find_onset(audio, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        # onsetはCTC startより前（無音→有音の境界≈0.2秒）
        assert onset_sec < ctc_start
        assert onset_sec == pytest.approx(0.2, abs=0.02)

    def test_note_is_backward(self):
        audio = _make_audio(silence_sec=0.2, voice_sec=0.5)
        _, note = find_onset(audio, SAMPLE_RATE, 0.45, silence_threshold=THRESHOLD)
        assert note.startswith("←")

    def test_ctc_at_voice_start(self):
        # CTC startがちょうど有音開始直後
        audio = _make_audio(silence_sec=0.1, voice_sec=0.5)
        ctc_start = 0.105  # 無音直後
        onset_sec, _ = find_onset(audio, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        assert onset_sec <= ctc_start + 0.01


class TestFindOnsetForward:
    """フェーズ2b: CTC startが無音区間にある場合、前方スキャンでonsetを見つける。"""

    def test_finds_onset_after_ctc(self):
        # 0.3秒無音 + 0.5秒有音、CTCは無音区間（0.1秒）
        audio = _make_audio(silence_sec=0.3, voice_sec=0.5)
        ctc_start = 0.1
        onset_sec, note = find_onset(audio, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        # onsetはCTC startより後（無音→有音の境界≈0.3秒）
        assert onset_sec > ctc_start
        assert onset_sec == pytest.approx(0.3, abs=0.02)

    def test_note_is_forward(self):
        audio = _make_audio(silence_sec=0.3, voice_sec=0.5)
        _, note = find_onset(audio, SAMPLE_RATE, 0.1, silence_threshold=THRESHOLD)
        assert note.startswith("→")

    def test_no_voice_found_returns_ctc(self):
        # 全て無音の場合はCTC startをそのまま返す
        audio = np.zeros(int(1.0 * SAMPLE_RATE), dtype=np.float32)
        ctc_start = 0.2
        onset_sec, note = find_onset(audio, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        assert onset_sec == pytest.approx(ctc_start, abs=0.01)
        assert "±0" in note


class TestFindOnsetEdgeCases:
    def test_ctc_at_audio_start(self):
        audio = _make_audio(silence_sec=0.0, voice_sec=0.5)
        onset_sec, _ = find_onset(audio, SAMPLE_RATE, 0.0, silence_threshold=THRESHOLD)
        assert onset_sec >= 0.0

    def test_ctc_near_audio_end(self):
        audio = _make_audio(silence_sec=0.0, voice_sec=0.5)
        ctc_start = 0.49
        onset_sec, _ = find_onset(audio, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        assert onset_sec >= 0.0

    def test_no_silence_before_voice(self):
        # 最初から有音、逆スキャンしても無音が見つからない → CTCをそのまま返す
        voice = (0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, SAMPLE_RATE))).astype(np.float32)
        ctc_start = 0.5
        onset_sec, _ = find_onset(voice, SAMPLE_RATE, ctc_start, silence_threshold=THRESHOLD)
        assert onset_sec == pytest.approx(ctc_start, abs=0.01)
