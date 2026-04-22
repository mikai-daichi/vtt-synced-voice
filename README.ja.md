# vtt-synced-voice

音声/動画ファイルから、タイムスタンプが音声波形に正確に合ったVTT字幕を生成します。

## 特徴

- WhisperX（Whisper + wav2vec2 forced alignment）による単語レベルのタイムスタンプ取得
- FCPスタイルのピーク正規化により録音レベルに依存しない無音判定を実現
- 双方向onsetスキャン：CTC startが有音区間内なら後退、無音区間なら前進
- キュー間に最低100msの無音を保証
- 文単位のキューマージ：過分割されたキューを自然な文単位に結合
  - 日本語：Janome 形態素解析で文末表現（です・ます・ました・くださいなど）を検出
  - その他の言語：ピリオド・感嘆符・疑問符を文末として検出（略語・省略記号は除外）

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
    language="ja",            # "ja" / "en" など
    model="large-v2",         # "small" / "medium" / "large-v2"
    device="cpu",             # "cpu" / "cuda"
    margin_before=0.066,      # onset検出後、さらに早める秒数（デフォルト: 30fps×2フレーム）
    margin_after=0.0,         # 終了時刻を延ばす秒数
    silence_threshold=0.001,  # ピーク正規化後のRMS閾値
    merge_sentences=True,     # 文単位にキューをマージする（デフォルト: True）
    verbose=True,
)
```

既存の VTT ファイルに対して後からマージを適用することもできます：

```python
from vtt_synced_voice import read_vtt, merge_cues, write_vtt

cues = read_vtt("input.vtt")
merged = merge_cues(cues, language="ja")
write_vtt(merged, "output_merged.vtt")
```

### `merge_sentences` について

`True`（デフォルト）の場合、WhisperX が生成した過分割キューを書き起こし後に文単位へマージします：

- **日本語（`language="ja"`）**：Janome 形態素解析で文末品詞を判定します。`です`・`ます`・`ました`・`ください` などを文末として検出し、`作成された` のような連体修飾の `た` は除外します。
- **その他の言語**：`.` / `!` / `?` を文末として検出します。`Mr.`・`Dr.`・`U.S.`・`e.g.`・`etc.`・`...` などの略語・省略記号は誤検出を防ぐため除外します。

マージを無効にして WhisperX のアライメント結果をそのまま受け取るには `merge_sentences=False` を指定してください。

### 文単位マージの言語対応状況

| 言語 | 対応状況 | 備考 |
|---|---|---|
| 日本語 | 対応済み | Janome 形態素解析 |
| 英語 | 対応済み | 句読点ベース（`.` `!` `?`） |
| フランス語 | 対応済み | 句読点ベース |
| ドイツ語 | 対応済み | 句読点ベース |
| スペイン語 | 対応済み | 句読点ベース（文末の `!` `?` のみ検出、文頭の `¡` `¿` は無視） |
| イタリア語 | 対応済み | 句読点ベース |
| ポルトガル語 | 対応済み | 句読点ベース |
| オランダ語 | 対応済み | 句読点ベース |
| その他ラテン文字系言語 | おそらく対応 | 句読点ベース |
| 中国語（簡体・繁体） | 今後の予定 | 句点が `。` — コントリビューション歓迎 |
| 韓国語 | 今後の予定 | 句読点の慣習が混在 — コントリビューション歓迎 |
| アラビア語・ヘブライ語・タイ語など | 未対応 | 句読点体系が異なる |

### `max_gap_seconds`

文単位マージの前段階で音声をキューに分割する際の閾値です。単語間の無音ギャップがこの秒数を超えると新しいキューに分割されます。

- **デフォルト**: `0.4` 秒
- **のんびり話す人・間が多い収録**: 大きくする（例: `0.4`〜`0.5`）
- **早口・マシンガントーク**: 小さくする（例: `0.1`〜`0.2`）
- **推奨範囲**: `0.01`〜`0.5`

`merge_sentences=True` の場合、分割後に文末判定でキューをまとめ直すため、`max_gap_seconds` を小さくしても最終的な出力が過剰に細分化されるわけではありません。

### 前提：カット編集前の生音声に適用すること

このパッケージは **カット編集前の生音声** に適用することを前提としています：

```
生音声 → vtt-synced-voice → VTT生成 → FCPに読み込んでカット編集
```

**カット編集済みの音声には適用しないでください。** カット編集によって文間の無音が除去されており、以下の2つの処理が正しく動作しません：

1. **ギャップによるキュー分割**：`max_gap_seconds`（デフォルト0.4秒）を超える無音ギャップでキューを分割しますが、カット編集済み音声では文間の無音が除去されているため、異なる文の単語が隣接して並びます。ギャップが検出されず、本来は別々の文が1つのキューに結合されてしまいます。

2. **発声オンセット検出**：`find_onset()` は CTC タイムスタンプから逆スキャンして無音→有音の境界を探しますが、カット編集済み音声ではその無音区間が存在しないため、境界が見つからずオンセット検出の精度が失われます。

### `silence_threshold` について

ピーク正規化後、完全無音 ≈ 0.0、発話 ≈ 0.05〜1.0 になります。
デフォルトの `0.001` はノイズのないクリーンな録音で有効です。
`verbose=True` でonset検出結果を確認しながら調整してください。

## 動作要件

- Python 3.10+
- ffmpeg（システムインストール必須）
- numpy
- whisperx
- janome

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
├── __init__.py       # transcribe()・merge_cues() を公開APIとしてエクスポート
├── transcriber.py    # transcribe() エントリポイント、ffmpeg変換、WhisperX呼び出し
├── onset.py          # find_onset() — 双方向voice onset検出
├── cue_builder.py    # build_cues_from_segments() — WhisperX結果 → VttCue変換
├── cue_merger.py     # merge_cues() — 文単位キューマージ（日本語・その他言語対応）
└── vtt_io.py         # VttCue dataclass、read_vtt()、write_vtt()、format_timestamp()
```
