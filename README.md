# vtt-synced-voice

Generate VTT subtitles with timestamps precisely snapped to voice onset using WhisperX forced alignment.

[日本語版 README はこちら](https://github.com/mikai-daichi/vtt-synced-voice/blob/main/README.ja.md)

## Features

- Word-level timestamp alignment via WhisperX (Whisper + wav2vec2 forced alignment)
- FCP-style peak normalization for recording-level-independent silence detection
- Bidirectional onset detection: backward scan when CTC start is inside voice, forward scan when in silence
- Guaranteed silence gap between cues (100ms minimum)

## Installation

### 1. Install ffmpeg

**macOS**
```bash
brew install ffmpeg
```

**Windows**
```powershell
winget install ffmpeg
```

**Linux (Debian / Ubuntu)**
```bash
sudo apt install ffmpeg
```

### 2. Install PyTorch

WhisperX runs on PyTorch. GPU (CUDA) is significantly faster than CPU for transcription (roughly 10–20x). Install the build that matches your environment.

**macOS** — CPU only (no CUDA support on macOS)
```bash
pip install torch torchaudio
```

**Windows — CUDA 12.8** (recommended for RTX 30xx / 40xx and newer)
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Windows — CUDA 11.8** (for older GPUs such as GTX 10xx / 20xx)
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Windows — CPU only** (no NVIDIA GPU)
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

**Linux — CUDA 12.8** (recommended for RTX 30xx / 40xx and newer)
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Linux — CUDA 11.8** (for older GPUs such as GTX 10xx / 20xx)
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Linux — CPU only** (no NVIDIA GPU)
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

> To check your CUDA version: `nvidia-smi` (Windows/Linux). If you don't have an NVIDIA GPU, use the CPU build.
> For the full list of builds, see the [PyTorch installation guide](https://pytorch.org/get-started/locally/).

### 3. Install vtt-synced-voice

```bash
pip install vtt-synced-voice
```

## Usage

```python
from vtt_synced_voice import transcribe

transcribe(
    audio_file="sample.m4a",
    output_file="output.vtt",
    language="ja",           # "ja" / "en" / etc.
    model="large-v2",        # "small" / "medium" / "large-v2"
    device="cpu",            # "cpu" / "cuda"
    margin_before=0.066,     # seconds to shift start earlier after onset detection
    margin_after=0.0,        # seconds to extend end
    silence_threshold=0.001, # RMS threshold after peak normalization
    verbose=True,
)
```

### `silence_threshold`

After peak normalization, complete silence ≈ 0.0 and voiced speech ≈ 0.05–1.0.
The default `0.001` works well for clean recordings with no background noise.
Use `verbose=True` to inspect onset detection results and adjust if needed.

## Requirements

- Python 3.10+
- ffmpeg (system)
- numpy
- whisperx

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

33 tests covering `vtt_io`, `onset`, and `cue_builder` modules.

### Manual test with a local audio file

Place an audio file in `audio_input/`, then run:

```bash
python test_run.py
```

Output is written to `vtt_output/test_package.vtt`.

### Project structure

```
src/vtt_synced_voice/
├── __init__.py       # exports transcribe()
├── transcriber.py    # transcribe() entry point, ffmpeg conversion, WhisperX calls
├── onset.py          # find_onset() — bidirectional voice onset detection
├── cue_builder.py    # build_cues_from_segments() — WhisperX result → VttCue
└── vtt_io.py         # VttCue dataclass, read_vtt(), write_vtt(), format_timestamp()
```
