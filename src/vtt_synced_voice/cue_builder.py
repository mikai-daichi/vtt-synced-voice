from __future__ import annotations

import re

import numpy as np

from .onset import find_onset
from .vtt_io import VttCue

SENTENCE_END_DURATION = 0.15  # 文末単語の発声時間推定（秒）


def build_cues_from_segments(
    segments: list[dict],
    max_gap_seconds: float,
    audio_normalized: np.ndarray,
    sample_rate: int,
    margin_before: float = 0.0,
    margin_after: float = 0.0,
    silence_threshold: float = 0.001,
) -> tuple[list[VttCue], list[dict]]:
    """WhisperXのsegments（単語タイムスタンプ付き）をVttCueリストに変換する。

    startはfind_onset()でFCP方式の無音境界検出を適用する:
    - CTCのstartから逆スキャンして無音→有音の境界をstartとする
    - end（文末キュー）: 末尾単語のCTC start + SENTENCE_END_DURATION + margin_after
    - end（文中キュー）: 末尾単語のCTC end + margin_after

    endクランプ: margin_afterが次キューのstartを侵食しないよう、
    次キューのstart - 0.1s を上限とし、キュー間に必ず無音区間を確保する。

    戻り値:
        (cues, onset_debug_list)
        onset_debug_list: [{"index": int, "ctc": float, "onset": float, "note": str}, ...]
    """
    cues: list[VttCue] = []
    onset_debug: list[dict] = []
    index = 0

    for seg in segments:
        words = seg.get("words", [])

        if not words:
            text = seg.get("text", "").strip()
            if text:
                ctc_start = float(seg["start"])
                onset_sec, note = find_onset(
                    audio_normalized, sample_rate, ctc_start,
                    silence_threshold=silence_threshold,
                )
                start = max(0.0, onset_sec - margin_before)
                end = float(seg["end"]) + margin_after
                cues.append(VttCue(
                    index=index,
                    start=start,
                    end=end,
                    text=text,
                    original_start=ctc_start,
                    original_end=end,
                ))
                onset_debug.append({"index": index, "ctc": ctc_start, "onset": onset_sec, "note": note})
                index += 1
            continue

        buffer_words: list[dict] = []
        buffer_text: list[str] = []

        def _flush_buffer(is_sentence_end: bool) -> None:
            nonlocal index
            words_clean = list(buffer_words)
            text_parts = list(buffer_text)
            while words_clean and not re.search(r'[\w\u3040-\u9FFF]', text_parts[0]):
                words_clean.pop(0)
                text_parts.pop(0)
            if not words_clean:
                return
            text = "".join(text_parts).strip()
            if not text:
                return
            ctc_start = float(words_clean[0]["start"])
            onset_sec, note = find_onset(
                audio_normalized, sample_rate, ctc_start,
                silence_threshold=silence_threshold,
            )
            start = max(0.0, onset_sec - margin_before)
            if is_sentence_end:
                end = float(buffer_words[-1]["start"]) + SENTENCE_END_DURATION + margin_after
            else:
                end = float(buffer_words[-1]["end"]) + margin_after
            cues.append(VttCue(
                index=index,
                start=start,
                end=end,
                text=text,
                original_start=ctc_start,
                original_end=end,
            ))
            onset_debug.append({"index": index, "ctc": ctc_start, "onset": onset_sec, "note": note})
            index += 1

        for w in words:
            if not buffer_words:
                buffer_words.append(w)
                buffer_text.append(w.get("word", ""))
                continue

            prev_estimated_end = buffer_words[-1]["start"] + SENTENCE_END_DURATION
            gap = w["start"] - prev_estimated_end
            if gap > max_gap_seconds:
                _flush_buffer(is_sentence_end=True)
                buffer_words = [w]
                buffer_text = [w.get("word", "")]
            else:
                buffer_words.append(w)
                buffer_text.append(w.get("word", ""))

        if buffer_words:
            _flush_buffer(is_sentence_end=True)

    # endクランプ: 次キューのstartとの間に0.1秒の無音を確保
    for i in range(len(cues) - 1):
        cues[i].end = min(cues[i].end, cues[i + 1].start - 0.1)
        cues[i].original_end = cues[i].end

    return cues, onset_debug
