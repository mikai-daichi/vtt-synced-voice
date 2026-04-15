# vtt-synced-voice — 新チャットへの引き継ぎ

## このドキュメントの目的

`vtt-synced-voice` パッケージの開発経緯・設計判断・解決済み問題をまとめる。
新しい Claude Code チャットでこのファイルを読めば、即座に開発を継続できる。

---

## プロジェクト概要

**何をするパッケージか:**
音声/動画ファイルから、タイムスタンプが音声波形に正確に合ったVTT字幕を生成する。

**なぜこのパッケージが必要か:**
WhisperやZoomが生成するVTTのタイムスタンプには行ごとにランダムなズレがある。
このズレにより、FCP（Final Cut Pro）での字幕カット編集を毎回手動でトリムし直す必要があった。
これを自動補正することが目的。

**公開API:**
```python
from vtt_synced_voice import transcribe

transcribe(
    audio_file="audio_input/sample.m4a",
    output_file="vtt_output/sample.vtt",
    language="ja",
    model="large-v2",
    device="cpu",
    margin_before=0.066,   # 30fps × 2フレーム
    margin_after=0.0,
    silence_threshold=0.001,
    verbose=True,
    dry_run=False,
)
```

---

## パッケージ構成

```
vtt-synced-voice/
├── src/vtt_synced_voice/
│   ├── __init__.py        # transcribe() を公開APIとしてエクスポート
│   ├── transcriber.py     # transcribe() / _run_whisperx() / _print_verbose()
│   ├── onset.py           # find_onset() — 音声波形onset検出
│   ├── cue_builder.py     # build_cues_from_segments() — WhisperX結果→VttCue変換
│   └── vtt_io.py          # VttCue dataclass / read_vtt() / write_vtt() / format_timestamp()
├── tests/
│   ├── test_vtt_io.py     # 14テスト
│   ├── test_onset.py      # 9テスト
│   └── test_cue_builder.py # 10テスト
├── audio_input/           # 手動テスト用音声置き場（.gitignoreで素材除外）
├── vtt_output/            # 手動テスト用出力先（.gitignoreで成果物除外）
├── test_run.py            # 手動テスト用スクリプト
├── pyproject.toml         # hatchling / Python>=3.10 / 依存: numpy, whisperx
└── README.md
```

---

## 処理フロー

```
transcribe()
  ↓
ffmpegで音声をモノラルWAV 16kHzに変換
  ↓
WhisperX: load_model → transcribe → align（return_char_alignments=True）
  ↓ aligned_segments（単語・音素タイムスタンプ付き）
ピーク正規化: audio_normalized = audio_raw / max(abs(audio_raw))
  ↓
build_cues_from_segments()
  - 単語間gapがmax_gap_seconds(0.4s)を超えたら新キューに分割
  - 先頭ノイズ文字（?、. 等）を除去し、次の有意語のCTC startを使用
  - find_onset() で各キューのstart時刻を補正
  - endクランプ: cues[i].end = min(end, cues[i+1].start - 0.1)
  ↓
write_vtt() → .vttファイル出力
```

---

## 核心アルゴリズム: find_onset()

### 背景と問題

WhisperXのCTC（Connectionist Temporal Classification）が出力する `word["start"]` は、
定義上すでに有音区間の中にある。そのためFCPのタイムラインで見ると
「クリップのstartが波の立ち上がりより後ろにある（有音部分に食い込んでいる）」状態になる。

### 解決アプローチ: FCP方式ピーク正規化 + 双方向onsetスキャン

FCPの波形表示はピーク正規化された振幅を表示する。
これをPythonで再現することで録音レベルに依存しない絶対閾値判定を実現。

```
audio_normalized = audio_raw / max(abs(audio_raw))
完全無音 = 0.000000 RMS
発話     = 0.05〜1.0 RMS
閾値     = 0.001（1オーダー以上のマージンがある）
```

### 2フェーズ処理

**フェーズ1: CTC start付近が有音か無音かを判定**
- 3フレーム（15ms）の最大RMSを使う
- 1フレームだけだとフレーム境界のズレで有音を無音と誤判定する問題があったため3フレームに拡張

**フェーズ2a（有音と判定）: 逆方向スキャン**
- CTC startから最大0.3秒遡って最初の無音フレームを探す
- その無音フレームの終端 = onset
- 典型例: CTC=3.550s → onset=3.515s（←-35ms）

**フェーズ2b（無音と判定）: 前方スキャン**
- CTC startから最大0.3秒進んで最初の有音フレームを探す
- その有音フレームの先頭 = onset
- 典型例: WhisperXがCTC startを次の発話の少し前に置くケース（→+70ms等）

### margin_before

onset検出後、さらに `margin_before`（デフォルト0.066秒 = 30fps×2フレーム）分だけ早める。
FCPで確認したところ、onset検出位置から1フレーム前が波の立ち上がりポイントに一致した。

---

## 設計上の重要な決定事項

### end時刻の計算

WhisperXは文末単語の `end` を次の発話開始まで引き伸ばす挙動がある。
そのため文末単語の `end` は使わず:
```python
end = word[-1]["start"] + SENTENCE_END_DURATION(0.15s) + margin_after
```

### endクランプ

`margin_after` が次キューの `start` を侵食しないよう制限:
```python
cues[i].end = min(cues[i].end, cues[i+1].start - 0.1)
```
`cues[i+1].start` はすでに onset + margin_before が適用済みの値を使う（正しい実装）。

### silence_threshold はユーザー設定値

録音環境（マイクの品質・環境音）によって無音のRMS値が変わるため、
`transcribe()` の引数として公開している。`verbose=True` で補正結果を確認しながら調整する。

### ノイズ文字の除去

WhisperXは一部キューの先頭に `?` や `.` を付加することがある。
これをキュー開始時刻の再計算とセットで処理:
```python
while words_clean and not re.search(r'[\w\u3040-\u9FFF]', text_parts[0]):
    words_clean.pop(0)
    text_parts.pop(0)
# 除去後の先頭単語のCTC startをonset探索の起点とする
ctc_start = float(words_clean[0]["start"])
```

---

## 失敗したアプローチ（やり直し不要）

1. **相対RMS閾値（max_rms比）**: max_rms≈0のセグメントでゼロ除算・誤判定が発生。廃止。
2. **VAD/seg_startアプローチ**: WhisperXが54秒の音声を2セグメントしか生成しないケースで完全に失敗。廃止。
3. **フェーズ1を1フレームで判定**: フレーム境界のズレでキュー3,6,7が誤って無音判定され前方スキャンしてしまった。3フレームの最大RMSに変更して解決。

---

## テスト実行

```bash
cd /path/to/vtt-synced-voice
pip install -e .
python -m pytest tests/ -v
# 33 passed
```

## 手動テスト

```bash
# audio_input/ に音声ファイルを配置してから:
python test_run.py
# vtt_output/test_package.vtt に出力される
```

---

## 次にやること（未着手）

1. **GitHub新リポジトリ作成・push**
   ```bash
   cp -r packages/vtt-synced-voice ~/GitHub/vtt-synced-voice
   cd ~/GitHub/vtt-synced-voice
   git init && git add . && git commit -m "Initial commit"
   gh repo create imin-minnade/vtt-synced-voice --public --source=. --push
   ```

2. **PyPI登録**
   ```bash
   pip install build twine
   python -m build
   twine upload dist/*
   ```

3. **GitHub Actions CI** （オプション）
   - push時に `pytest` を自動実行するワークフロー追加

---

## 依存関係

- `numpy >= 1.24`
- `whisperx >= 3.1`（PyPI公開済み）
- `ffmpeg`（システムインストール必須）
- Python >= 3.10
