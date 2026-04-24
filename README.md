# vtt-synced-voice

Generate VTT subtitles with timestamps precisely snapped to voice onset using WhisperX forced alignment.

[日本語版 README はこちら](https://github.com/mikai-daichi/vtt-synced-voice/blob/main/README.ja.md)

## Features

- Word-level timestamp alignment via WhisperX (Whisper + wav2vec2 forced alignment)
- FCP-style peak normalization for recording-level-independent silence detection
- Bidirectional onset detection: backward scan when CTC start is inside voice, forward scan when in silence
- Guaranteed silence gap between cues (100ms minimum)
- Sentence-level cue merging: over-split cues are merged into natural sentence units
  - Japanese: morphological analysis (Janome) detects sentence-ending verb forms (including colloquial endings such as `よ`, `ね`, `けど`, `し`, `って`)
  - Other languages: period / exclamation mark / question mark detection (with abbreviation exclusions)
- Long cue re-splitting at natural boundaries (`max_cue_seconds`, default 15 s)
- Post-merge splitting of overly long cues (`min_cue_chars`, default 50 chars): splits at all full-width punctuation first; if none, uses morphological analysis to detect sentence-end + sentence-start patterns
- Automatic misrecognition correction (`replacements`): pre-register proper nouns and technical terms that Whisper tends to mishear
- Voice-only output (`voice_only=True`): plain `.txt` without timestamps, for adding subtitles to cut-edited video

## Installation

### macOS

On macOS, only ffmpeg needs to be installed manually. PyTorch and all other dependencies are installed automatically.

```bash
brew install ffmpeg
pip install vtt-synced-voice
```

### Windows / Linux

On Windows and Linux, if you have an NVIDIA GPU, install the CUDA build of PyTorch **before** installing vtt-synced-voice. pip's dependency resolution cannot select the correct CUDA build automatically.

**1. Install ffmpeg**

**Windows**
```powershell
winget install ffmpeg
```

**Linux (Debian / Ubuntu)**
```bash
sudo apt install ffmpeg
```

**2. Install PyTorch (GPU only — skip if using CPU)**

WhisperX runs on PyTorch. GPU (CUDA) is roughly 10–20x faster than CPU for transcription.

**Windows — CUDA 12.8** (recommended for RTX 30xx / 40xx and newer)
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Windows — CUDA 11.8** (for older GPUs such as GTX 10xx / 20xx)
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Linux — CUDA 12.8** (recommended for RTX 30xx / 40xx and newer)
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Linux — CUDA 11.8** (for older GPUs such as GTX 10xx / 20xx)
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

> To check your CUDA version: `nvidia-smi`. If you don't have an NVIDIA GPU, skip this step.
> For the full list of builds, see the [PyTorch installation guide](https://pytorch.org/get-started/locally/).

**3. Install vtt-synced-voice**

```bash
pip install vtt-synced-voice
```

## Usage

```python
from vtt_synced_voice import transcribe

transcribe(
    audio_file="sample.m4a",
    output_file="output.vtt",
    language="ja",            # "ja" / "en" / etc.
    model="large-v2",         # "small" / "medium" / "large-v2"
    device="cpu",             # "cpu" / "cuda"
    margin_before=0.066,      # seconds to shift start earlier after onset detection
    margin_after=0.0,         # seconds to extend end
    silence_threshold=0.001,  # RMS threshold after peak normalization
    merge_sentences=True,     # merge over-split cues into sentence units (default: True)
    min_cue_chars=50,         # post-merge: split cues longer than this (0 to disable)
    voice_only=False,         # output plain .txt without timestamps (default: False)
    verbose=True,
)
```

### `max_gap_seconds`

Controls how finely the audio is split into cues before sentence merging. When the silence gap between two words exceeds this value, a new cue begins.

- **Default**: `0.4` seconds
- **Slow speaker / many pauses**: increase (e.g. `0.4`–`0.5`)
- **Fast speaker / machine-gun delivery**: decrease (e.g. `0.1`–`0.2`)
- **Recommended range**: `0.01`–`0.5`

After splitting, `merge_sentences=True` merges the resulting cues back into natural sentence units, so a smaller `max_gap_seconds` produces more fine-grained intermediate cues that are then merged — it does not make the final output more fragmented.

### Intended use: raw audio before cut editing

This package is designed to be applied to **raw, unedited audio** before cut editing in Final Cut Pro:

```
Raw audio → vtt-synced-voice → VTT → Import into FCP → Cut edit using VTT timestamps
```

**Do not apply to audio that has already been cut-edited.** Cut-edited audio has had silence removed between sentences, which breaks two core assumptions:

1. **Cue splitting by gap**: The algorithm splits cues where silence gaps exceed `max_gap_seconds` (default 0.4s). In cut-edited audio, inter-sentence silences have been removed, so words from different sentences appear adjacent. The gap threshold finds no boundaries and merges unrelated sentences into a single cue.

2. **Voice onset detection**: `find_onset()` scans backward from the CTC timestamp to locate the silence→voice boundary. In cut-edited audio, that silence no longer exists, so the scan finds no boundary and onset detection loses its accuracy.

### `silence_threshold`

After peak normalization, complete silence ≈ 0.0 and voiced speech ≈ 0.05–1.0.
The default `0.001` works well for clean recordings with no background noise.
Use `verbose=True` to inspect onset detection results and adjust if needed.

You can also apply sentence merging to an existing VTT file:

```python
from vtt_synced_voice import read_vtt, merge_cues, write_vtt

cues = read_vtt("input.vtt")
merged = merge_cues(cues, language="ja")
write_vtt(merged, "output_merged.vtt")
```

### `merge_sentences`

When `True` (default), over-split cues produced by WhisperX are merged into natural sentence units after transcription:

- **Japanese (`language="ja"`)**: Uses Janome morphological analysis to detect sentence-ending forms (`です`, `ます`, `ました`, `ください`, etc.). Adjunctive `た` (e.g. `作成された`) is correctly excluded.
- **Other languages**: Detects `.` / `!` / `?` as sentence boundaries. Common abbreviations (`Mr.`, `Dr.`, `U.S.`, `e.g.`, `etc.`, `...`) are excluded to avoid false splits.

Set `merge_sentences=False` to disable merging and receive the raw WhisperX-aligned cues.

### `min_cue_chars`

After sentence merging, splits any cue whose text exceeds this character count (default: `50`). Cues at or below the threshold are never touched.

**Phase 1 (punctuation)**: If the text contains `。` `！` `？`, splits at every occurrence.

**Phase 2 (morphological analysis)**: If no punctuation is found, uses Janome to detect positions where a sentence-ending token (e.g. `です`, `ます`, `た`, `よ`) is immediately followed by a sentence-starting token (noun, pronoun, interjection, conjunction, etc.).

Set to `0` to disable post-merge splitting entirely.

### `voice_only`

When `True`, outputs a plain `.txt` file instead of a `.vtt` file. Timestamps are omitted and trailing punctuation (`。`, `！`, `？`, `.`, `!`, `?`) is stripped from each line.

This is intended for **cut-edited video** where VTT timestamps are meaningless. The typical workflow:

```
Cut-edited audio → vtt-synced-voice (voice_only=True) → .txt → paste into subtitle tool
```

You can also convert an existing VTT file directly:

```python
from vtt_synced_voice import read_vtt, write_txt

cues = read_vtt("input.vtt")
write_txt(cues, "output.txt")
```

> Note: `voice_only=True` automatically changes the output file extension to `.txt` regardless of the `output_file` argument.

### Language support for sentence merging

| Language | Status | Notes |
|---|---|---|
| Japanese | Supported | Janome morphological analysis |
| English | Supported | Punctuation-based (`.` `!` `?`) |
| French | Supported | Punctuation-based |
| German | Supported | Punctuation-based |
| Spanish | Supported | Punctuation-based (sentence-ending `!` `?` only; leading `¡` `¿` are ignored) |
| Italian | Supported | Punctuation-based |
| Portuguese | Supported | Punctuation-based |
| Dutch | Supported | Punctuation-based |
| Other Latin-script languages | Likely supported | Punctuation-based |
| Chinese (Simplified / Traditional) | Planned | Uses `。` as sentence terminator — contributions welcome |
| Korean | Planned | Mixed punctuation conventions — contributions welcome |
| Arabic, Hebrew, Thai, etc. | Not supported | Different punctuation systems |

## Requirements

- Python 3.10+
- ffmpeg (system)
- numpy
- whisperx
- janome

---

## Development

### Setup

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Running tests

```bash
python -m pytest tests/ -v
```

88 tests covering `vtt_io`, `onset`, `cue_builder`, and `cue_merger` modules.

### Manual test with a local audio file

Place an audio file in `audio_input/`, then run:

```bash
python test_run.py
```

Output is written to `vtt_output/test_package.vtt`.

### Project structure

```
src/vtt_synced_voice/
├── __init__.py       # exports transcribe(), merge_cues()
├── transcriber.py    # transcribe() entry point, ffmpeg conversion, WhisperX calls
├── onset.py          # find_onset() — bidirectional voice onset detection
├── cue_builder.py    # build_cues_from_segments() — WhisperX result → VttCue
├── cue_merger.py     # merge_cues() — sentence-level cue merging (Japanese / other)
└── vtt_io.py         # VttCue dataclass, read_vtt(), write_vtt(), format_timestamp()
```
