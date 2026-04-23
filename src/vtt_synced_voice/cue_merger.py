from __future__ import annotations

import re

from .vtt_io import VttCue

# ピリオドで終わるが文末ではない英語パターン（大文字小文字を区別しない）
# 末尾がこれらにマッチする場合は文末と判定しない
_EN_NON_SENTENCE_END_PATTERNS = re.compile(
    r"""
    (?:
        # 敬称・肩書
        Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.|Sr\.|Jr\.|Rev\.|Gen\.|Sgt\.|Lt\.|Cpl\.|
        # 学位・資格
        Ph\.D\.|M\.D\.|B\.A\.|M\.A\.|M\.B\.A\.|LL\.B\.|LL\.M\.|
        # 略語（組織・地名）
        U\.S\.|U\.K\.|U\.N\.|E\.U\.|U\.S\.A\.|D\.C\.|
        # etc.
        etc\.|e\.g\.|i\.e\.|vs\.|cf\.|al\.|
        # 省略記号
        \.\.\.
    )$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def merge_cues(cues: list[VttCue], language: str) -> list[VttCue]:
    """過分割されたVttCueを文単位にマージして返す。

    言語ごとに文末検出ロジックを切り替える:
    - ja: Janome 形態素解析で末尾品詞を判定
    - その他: ピリオド/感嘆符/疑問符で判定（略語・省略記号は除外）
    """
    if not cues:
        return []

    if language == "ja":
        is_end = _make_ja_detector()
        join_sep = ""
    else:
        is_end = _is_end_punctuation
        join_sep = " "

    merged: list[VttCue] = []
    buffer: list[VttCue] = []

    for cue in cues:
        buffer.append(cue)
        # キュー自身のテキスト内部に文末記号があれば即フラッシュ（英語の複数文混入を防ぐ）
        # バッファ全体の末尾も合わせて判定
        if _contains_sentence_end(cue.text) or is_end(join_sep.join(c.text for c in buffer)):
            merged.append(_flush(buffer, len(merged), join_sep))
            buffer = []

    if buffer:
        merged.append(_flush(buffer, len(merged), join_sep))

    return merged


def _flush(buffer: list[VttCue], index: int, join_sep: str) -> VttCue:
    words = join_sep.join(c.text for c in buffer)
    # 英語はトークン間スペースを正規化（WhisperXが単語を連結して出力する場合の対策）
    if join_sep == " ":
        words = re.sub(r" {2,}", " ", words).strip()
    text = words
    return VttCue(
        index=index,
        start=buffer[0].start,
        end=buffer[-1].end,
        text=text,
        original_start=buffer[0].original_start,
        original_end=buffer[-1].original_end,
    )


_KEREDO_SURFACES = frozenset({"けど", "けども", "が"})
_KARA_NODE_SURFACES = frozenset({"から", "ので"})
_SENTENCE_END_CONJ = frozenset({"なので", "だから", "ですから"})
_KEREDO_CONJ = frozenset({"けれど", "けれども"})


def _make_ja_detector():
    """Janome を使った日本語文末判定クロージャを返す。"""
    from janome.tokenizer import Tokenizer
    tokenizer = Tokenizer()

    def is_end(text: str) -> bool:
        tokens = list(tokenizer.tokenize(text))
        if not tokens:
            return False
        last = tokens[-1]
        pos = last.part_of_speech.split(",")
        pos0 = pos[0]
        pos1 = pos[1] if len(pos) > 1 else "*"

        # 助動詞（です/ます/ました/ません 等）
        # 「た」単体は連体修飾（「作成された」「使った」）と文末が区別できないため
        # 直前トークンが「まし」なら文末の「ました」、それ以外は連体修飾とみなしスキップ
        if pos0 == "助動詞":
            if last.surface == "た":
                prev_surface = tokens[-2].surface if len(tokens) >= 2 else ""
                return prev_surface == "まし"
            return True

        # 動詞・非自立（ください/てごらん 等）
        if pos0 == "動詞" and pos1 == "非自立":
            return True

        # 感動詞（ああ/はい 等）
        if pos0 == "感動詞":
            return True

        # 終助詞（よ/ね/な/わ/ぞ/ぜ/さ/か/かな/っけ/もん/じゃん 等）
        if pos0 == "助詞" and pos1 == "終助詞":
            return True

        # 接続助詞止め・けど系（けど/けども/が 等）
        # 格助詞の「が」（私が）とはJanomeが区別するため誤検出なし
        if pos0 == "助詞" and pos1 == "接続助詞" and last.surface in _KEREDO_SURFACES:
            return True

        # 接続詞・けれど系（けれど/けれども）
        if pos0 == "接続詞" and last.surface in _KEREDO_CONJ:
            return True

        # 接続助詞止め・から/ので系
        # 格助詞の「から」（東京から）とはJanomeが区別するため誤検出なし
        if pos0 == "助詞" and pos1 == "接続助詞" and last.surface in _KARA_NODE_SURFACES:
            return True

        # 接続詞止め（なので/だから/ですから）
        # 「次に」「また」「そして」など文頭に来る接続詞は除外
        if pos0 == "接続詞" and last.surface in _SENTENCE_END_CONJ:
            return True

        # 句点・感嘆符・疑問符で終わる（Whisperが付与した句読点）
        if pos0 == "記号" and last.surface in {"。", "！", "？"}:
            return True

        return False

    return is_end


def _contains_sentence_end(text: str) -> bool:
    """テキスト内部（末尾以外）に文末記号があるか判定。略語・省略記号は除外。"""
    stripped = text.rstrip()
    if len(stripped) < 2:
        return False
    interior = stripped[:-1]
    # 日本語句点
    if "。" in interior:
        return True
    for ch in "!?":
        if ch in interior:
            return True
    # ピリオドは略語でないものだけ: 各ピリオドの前後を含む単語全体で判定
    for m in re.finditer(r"[A-Za-z.]+\.", interior):
        candidate = m.group(0)
        if _EN_NON_SENTENCE_END_PATTERNS.search(candidate) is None:
            return True
    return False


def _is_end_punctuation(text: str) -> bool:
    """英語等：ピリオド/感嘆符/疑問符で文末判定。略語・省略記号は除外。"""
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped[-1] in "!?":
        return True
    if stripped[-1] == ".":
        return _EN_NON_SENTENCE_END_PATTERNS.search(stripped) is None
    return False
