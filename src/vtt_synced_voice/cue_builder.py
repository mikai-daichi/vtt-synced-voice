from __future__ import annotations

import re

import numpy as np

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
    language: str = "ja",
) -> list[VttCue]:
    """WhisperXのsegments（単語タイムスタンプ付き）をVttCueリストに変換する。

    onset補正・endクランプは行わない。apply_onset_to_cues() に委ねる。
    start / original_start ともに CTC start をそのまま設定する。
    end（文末）: 末尾単語の CTC start + SENTENCE_END_DURATION
    end（文中）: 末尾単語の CTC end
    """
    word_sep = "" if language == "ja" else " "

    cues: list[VttCue] = []
    index = 0

    for seg in segments:
        words = seg.get("words", [])

        if not words:
            text = seg.get("text", "").strip()
            if text:
                ctc_start = float(seg["start"])
                end = float(seg["end"])
                cues.append(VttCue(
                    index=index,
                    start=ctc_start,
                    end=end,
                    text=text,
                    original_start=ctc_start,
                    original_end=end,
                ))
                index += 1
            continue

        buffer_words: list[dict] = []
        buffer_text: list[str] = []

        def _flush_buffer(is_sentence_end: bool) -> None:
            nonlocal index
            words_clean = list(buffer_words)
            text_parts = list(buffer_text)
            while words_clean and not re.search(r'[\w぀-鿿]', text_parts[0]):
                words_clean.pop(0)
                text_parts.pop(0)
            if not words_clean:
                return
            text = word_sep.join(text_parts).strip()
            if not text:
                return
            ctc_start = float(words_clean[0]["start"])
            if is_sentence_end:
                end = float(buffer_words[-1]["start"]) + SENTENCE_END_DURATION
            else:
                end = float(buffer_words[-1]["end"])
            cues.append(VttCue(
                index=index,
                start=ctc_start,
                end=end,
                text=text,
                original_start=ctc_start,
                original_end=end,
            ))
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

    return cues
