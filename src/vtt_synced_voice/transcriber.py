from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .cue_builder import build_cues_from_segments
from .vtt_io import VttCue, format_timestamp, write_vtt

SAMPLE_RATE              = 16000      # Hz、モノラル
WHISPERX_MAX_GAP_SECONDS = 0.4        # 文分割の無音ギャップ閾値（秒）


def transcribe(
    audio_file: str,
    output_file: str,
    language: str = "ja",
    model: str = "large-v2",
    device: str = "cpu",
    margin_before: float = 0.066,
    margin_after: float = 0.0,
    silence_threshold: float = 0.001,
    max_gap_seconds: float = WHISPERX_MAX_GAP_SECONDS,
    verbose: bool = False,
    dry_run: bool = False,
) -> list[VttCue]:
    """音声/動画ファイルを書き起こし、タイムスタンプ補正済みのVTTを生成する。

    Args:
        audio_file: 入力音声/動画ファイルのパス（.mp4, .mov, .mp3, .m4a, .wav 等）
        output_file: 出力VTTファイルのパス
        language: 書き起こし言語コード（例: "ja", "en"）
        model: WhisperXモデル名（"small" / "medium" / "large-v2"）
        device: 推論デバイス（"cpu" / "cuda"）
        margin_before: onset検出後、さらに開始時刻を早める余白（秒）
        margin_after: 終了時刻を延ばす余白（秒）。次キューとの間に0.1秒の無音を確保
        silence_threshold: 無音判定のRMS閾値（ピーク正規化後）。
                           完全無音≈0.0、発話≈0.05〜1.0が目安。
                           録音環境によって異なるためverbose=Trueで確認して調整
        max_gap_seconds: 文分割の無音ギャップ閾値（秒）
        verbose: Trueなら各キューのタイムスタンプ補正結果を表示
        dry_run: Trueならファイルを書き出さずVttCueリストのみ返す

    Returns:
        生成されたVttCueのリスト
    """
    audio_path = Path(audio_file)
    if not audio_path.exists():
        raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        if verbose:
            print(f"音声抽出中: {audio_path}")
        if not _extract_audio_to_wav(str(audio_path), wav_path):
            raise RuntimeError("音声抽出に失敗しました（ffmpegを確認してください）")

        if verbose:
            print("WhisperX実行中...")
        segments, words, audio_raw = _run_whisperx(
            wav_path,
            model_name=model,
            device=device,
            language=language,
            verbose=verbose,
        )

        if not words:
            raise RuntimeError("WhisperXが単語を検出できませんでした")

        if verbose:
            print(f"  {len(segments)} セグメント / {len(words)} 単語を取得")

        peak = float(np.max(np.abs(audio_raw)))
        audio_normalized = audio_raw / peak if peak > 0 else audio_raw
        if verbose:
            print(f"  ピーク正規化完了 (peak={peak:.4f})")

        if verbose:
            print("VTTキュー生成中...")
        cues, onset_debug = build_cues_from_segments(
            segments, max_gap_seconds, audio_normalized, SAMPLE_RATE,
            margin_before, margin_after, silence_threshold,
        )
        if verbose:
            print(f"  {len(cues)} キュー生成完了")

        if verbose:
            _print_verbose(cues, onset_debug, segments, silence_threshold)

        if not dry_run:
            write_vtt(cues, output_file)
            if verbose:
                print(f"\n出力完了: {output_file}")
        elif verbose:
            print("\n[DRY RUN] ファイルへの書き出しをスキップしました")

        return cues

    finally:
        Path(wav_path).unlink(missing_ok=True)


def _extract_audio_to_wav(src: str, dst: str, sample_rate: int = SAMPLE_RATE) -> bool:
    """ffmpegで音声をモノラルWAVに変換。成功すればTrue。"""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", str(sample_rate), dst],
        capture_output=True,
    )
    return result.returncode == 0


def _run_whisperx(
    wav_path: str,
    model_name: str,
    device: str,
    language: str,
    verbose: bool = False,
) -> tuple[list[dict], list[dict], np.ndarray]:
    """WhisperXで書き起こしとforced alignmentを実行する。"""
    import whisperx

    if verbose:
        print(f"  WhisperXモデル読み込み中: {model_name}")
    model = whisperx.load_model(model_name, device, language=language)

    if verbose:
        print("  書き起こし中...")
    audio = whisperx.load_audio(wav_path)
    result = model.transcribe(audio, language=language)
    segments = result["segments"]

    if verbose:
        print("  アライメント実行中...")
    model_a, metadata = whisperx.load_align_model(
        language_code=language,
        device=device,
    )
    aligned = whisperx.align(
        segments,
        model_a,
        metadata,
        audio,
        device,
        return_char_alignments=True,
    )

    aligned_segments = aligned["segments"]

    words: list[dict] = []
    for seg in aligned_segments:
        for w in seg.get("words", []):
            if "start" in w and "end" in w:
                words.append({
                    "word": w.get("word", ""),
                    "start": float(w["start"]),
                    "end": float(w["end"]),
                })

    return aligned_segments, words, audio


def _print_verbose(
    cues: list[VttCue],
    onset_debug: list[dict],
    segments: list[dict],
    silence_threshold: float,
) -> None:
    """VERBOSE表示: 各キューのCTC→onset補正量と音素タイムスタンプを出力する。"""
    # 音素タイムスタンプの逆引き用マップを構築
    char_map: dict[float, list[dict]] = {}
    for seg in segments:
        seg_chars = [
            c for c in (seg.get("chars") or [])
            if c.get("start") is not None and c.get("start") != -1
        ]
        for w in seg.get("words", []):
            if "start" not in w:
                continue
            w_start = float(w["start"])
            w_end = float(w["end"])
            word_chars = [
                c for c in seg_chars
                if c.get("start") is not None and w_start <= float(c["start"]) <= w_end
            ]
            if word_chars:
                char_map[round(w_start, 3)] = word_chars

    onset_map = {d["index"]: d for d in onset_debug}

    print(f"\n--- キュー一覧 (SILENCE_THRESHOLD={silence_threshold}) ---")
    for cue in cues:
        dur = cue.end - cue.start
        od = onset_map.get(cue.index, {})
        ctc_str = format_timestamp(od.get("ctc", cue.original_start))
        note = od.get("note", "")
        print(
            f"  [{cue.index:3d}] "
            f"CTC={ctc_str}  onset={format_timestamp(cue.start)} ({note})  "
            f"--> {format_timestamp(cue.end)}  (dur={dur:.3f}s)  「{cue.text[:20]}」"
        )
        chars = char_map.get(round(od.get("ctc", cue.original_start), 3))
        if chars:
            char_line = "  ".join(
                f"{c['char']}[{format_timestamp(c['start'])}→{format_timestamp(c['end'])}]"
                for c in chars
            )
            print(f"         先頭単語音素: {char_line}")
