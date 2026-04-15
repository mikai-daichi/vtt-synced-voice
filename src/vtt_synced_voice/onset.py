from __future__ import annotations

import numpy as np

ONSET_SEARCH_SEC = 0.3   # CTC startから遡る/進む最大時間（秒）
ONSET_FRAME_SEC  = 0.005  # RMS計算のフレームサイズ（秒）= 5ms


def find_onset(
    audio_normalized: np.ndarray,
    sample_rate: int,
    ctc_start: float,
    search_sec: float = ONSET_SEARCH_SEC,
    frame_sec: float = ONSET_FRAME_SEC,
    silence_threshold: float = 0.001,
) -> tuple[float, str]:
    """CTC startから無音→有音の境界（onset）を検出して返す。

    FCP方式：音声全体をピーク正規化してからRMSを計算することで、
    録音レベルに依存しない絶対閾値による無音判定を実現する。
    呼び出し側で audio_normalized = audio / max(abs(audio)) を適用すること。

    2フェーズ処理:
        フェーズ1: CTC start付近（3フレーム = 15ms）の最大RMSで有音/無音を判定
        フェーズ2a（有音）: 逆方向スキャンで無音フレームを探す → その終端 = onset
        フェーズ2b（無音）: 前方スキャンで有音フレームを探す → その先頭 = onset

    戻り値:
        (onset_sec, debug_note)
        debug_note: "←-XXXms"（後退）/ "→+XXXms"（前進）/ "→±0ms"（変化なし）
    """
    frame_size = max(1, int(frame_sec * sample_rate))
    search_samples = int(search_sec * sample_rate)
    ctc_sample = int(ctc_start * sample_rate)

    def _rms(start: int, end: int) -> float:
        frame = audio_normalized[start:end]
        if len(frame) == 0:
            return 0.0
        return float(np.sqrt(np.mean(frame ** 2)))

    def _note(onset_sec: float) -> str:
        delta_ms = (onset_sec - ctc_start) * 1000
        if delta_ms < -0.5:
            return f"←{delta_ms:+.0f}ms"
        elif delta_ms > 0.5:
            return f"→{delta_ms:+.0f}ms"
        return "→±0ms"

    # フェーズ1: CTC start付近（3フレーム = 15ms）の最大RMSで有音/無音を判定
    ctc_rms = max(
        _rms(ctc_sample, ctc_sample + frame_size),
        _rms(ctc_sample + frame_size, ctc_sample + frame_size * 2),
        _rms(ctc_sample + frame_size * 2, ctc_sample + frame_size * 3),
    )
    ctc_is_silent = ctc_rms <= silence_threshold

    if not ctc_is_silent:
        # フェーズ2a: 有音 → 逆方向スキャンで最初の無音フレームを探す
        search_start = max(0, ctc_sample - search_samples)
        pos = ctc_sample
        onset_sample = ctc_sample
        while pos - frame_size >= search_start:
            pos -= frame_size
            if _rms(pos, pos + frame_size) <= silence_threshold:
                onset_sample = pos + frame_size
                break
        onset_sec = onset_sample / sample_rate
        return onset_sec, _note(onset_sec)
    else:
        # フェーズ2b: 無音 → 前方スキャンで最初の有音フレームを探す
        search_end = min(len(audio_normalized), ctc_sample + search_samples)
        pos = ctc_sample
        onset_sample = ctc_sample
        while pos + frame_size <= search_end:
            if _rms(pos, pos + frame_size) > silence_threshold:
                onset_sample = pos
                break
            pos += frame_size
        onset_sec = onset_sample / sample_rate
        return onset_sec, _note(onset_sec)
