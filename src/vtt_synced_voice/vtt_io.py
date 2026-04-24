from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class VttCue:
    index: int
    start: float        # 秒
    end: float          # 秒
    text: str
    original_start: float  # 補正前（ログ用）
    original_end: float    # 補正前（ログ用）


def _parse_timestamp(ts: str) -> float:
    """'HH:MM:SS.mmm' → 秒(float)"""
    ts = ts.strip()
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def format_timestamp(seconds: float) -> str:
    """秒 → 'HH:MM:SS.mmm' 形式"""
    seconds = max(0.0, seconds)
    millis = int(round(seconds * 1000))
    h, rem = divmod(millis, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def read_vtt(path: str) -> list[VttCue]:
    """VTTファイルをパースしてVttCueリストを返す。BOM付きUTF-8に対応。"""
    text = Path(path).read_text(encoding="utf-8-sig")
    blocks = text.strip().split("\n\n")

    cues: list[VttCue] = []
    index = 0

    for block in blocks:
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        if lines[0].startswith("WEBVTT"):
            continue

        time_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                time_idx = i
                break
        if time_idx is None:
            continue

        time_line = lines[time_idx]
        parts = time_line.split("-->")
        if len(parts) != 2:
            continue

        start = _parse_timestamp(parts[0])
        end = _parse_timestamp(parts[1])
        text = "\n".join(lines[time_idx + 1:]).strip()

        if not text:
            continue

        cues.append(VttCue(
            index=index,
            start=start,
            end=end,
            text=text,
            original_start=start,
            original_end=end,
        ))
        index += 1

    return cues


def write_vtt(cues: list[VttCue], path: str) -> None:
    """VttCueリストをVTTフォーマットで書き出す。"""
    lines = ["WEBVTT", ""]
    for cue in cues:
        lines.append(f"{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}")
        lines.append(cue.text.rstrip(_TRAILING_PUNCT))
        lines.append("")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


_TRAILING_PUNCT = "。．！？、!?,"


def apply_replacements(
    cues: list[VttCue],
    replacements: list[list[str]],
) -> list[VttCue]:
    """キューテキストに置換リストを順番に適用する。"""
    for cue in cues:
        for before, after in replacements:
            cue.text = cue.text.replace(before, after)
    return cues


def write_txt(cues: list[VttCue], path: str) -> None:
    """VttCueリストをタイムスタンプなし・句点なしのテキストで書き出す。"""
    lines = [cue.text.rstrip(_TRAILING_PUNCT) for cue in cues]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
