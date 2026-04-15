# vtt-synced-voice

音声/動画ファイルから、タイムスタンプが音声波形に正確に合ったVTT字幕を生成します。

## 特徴

- WhisperX（Whisper + wav2vec2 forced alignment）による単語レベルのタイムスタンプ取得
- FCPスタイルのピーク正規化により録音レベルに依存しない無音判定を実現
- 双方向onsetスキャン：CTC startが有音区間内なら後退、無音区間なら前進
- キュー間に最低100msの無音を保証

## インストール

```bash
pip install vtt-synced-voice
```

### 1. ffmpeg をインストール

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

### 2. PyTorch をインストール

WhisperXはPyTorch上で動作します。GPU（CUDA）はCPUに比べて書き起こし速度が大幅に速くなります（目安として10〜20倍）。使用環境に合ったビルドをインストールしてください。

**macOS** — CPUのみ（macOSはCUDA非対応）
```bash
pip install torch torchaudio
```

**Windows — CUDA 12.8**（RTX 30xx / 40xx以降・推奨）
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Windows — CUDA 11.8**（GTX 10xx / 20xx など旧世代GPU）
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Windows — CPUのみ**（NVIDIAのGPUがない場合）
```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

**Linux — CUDA 12.8**（RTX 30xx / 40xx以降・推奨）
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

**Linux — CUDA 11.8**（GTX 10xx / 20xx など旧世代GPU）
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**Linux — CPUのみ**（NVIDIAのGPUがない場合）
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

> CUDAバージョンの確認方法: `nvidia-smi`（Windows/Linux）。NVIDIAのGPUがない場合はCPUビルドを使用してください。
> ビルド一覧は [PyTorch公式インストールガイド](https://pytorch.org/get-started/locally/) を参照してください。

### 3. vtt-synced-voice をインストール

```bash
pip install vtt-synced-voice
```

## 使い方

```python
from vtt_synced_voice import transcribe

transcribe(
    audio_file="sample.m4a",
    output_file="output.vtt",
    language="ja",           # "ja" / "en" など
    model="large-v2",        # "small" / "medium" / "large-v2"
    device="cpu",            # "cpu" / "cuda"
    margin_before=0.066,     # onset検出後、さらに早める秒数（デフォルト: 30fps×2フレーム）
    margin_after=0.0,        # 終了時刻を延ばす秒数
    silence_threshold=0.001, # ピーク正規化後のRMS閾値
    verbose=True,
)
```

### `silence_threshold` について

ピーク正規化後、完全無音 ≈ 0.0、発話 ≈ 0.05〜1.0 になります。
デフォルトの `0.001` はノイズのないクリーンな録音で有効です。
`verbose=True` でonset検出結果を確認しながら調整してください。

## 動作要件

- Python 3.10+
- ffmpeg（システムインストール必須）
- numpy
- whisperx

---

## 開発者向け

### セットアップ

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

### ユニットテストの実行

```bash
python -m pytest tests/ -v
```

`vtt_io`・`onset`・`cue_builder` モジュールをカバーする33本のテストが含まれます。

### ローカル音声ファイルでの手動テスト

`audio_input/` に音声ファイルを置いてから実行：

```bash
python test_run.py
```

出力は `vtt_output/test_package.vtt` に書き出されます。

### プロジェクト構成

```
src/vtt_synced_voice/
├── __init__.py       # transcribe() を公開APIとしてエクスポート
├── transcriber.py    # transcribe() エントリポイント、ffmpeg変換、WhisperX呼び出し
├── onset.py          # find_onset() — 双方向voice onset検出
├── cue_builder.py    # build_cues_from_segments() — WhisperX結果 → VttCue変換
└── vtt_io.py         # VttCue dataclass、read_vtt()、write_vtt()、format_timestamp()
```
