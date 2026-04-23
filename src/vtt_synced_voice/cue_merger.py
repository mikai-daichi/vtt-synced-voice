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

# 日本語の自然な区切り文字（長キュー分割の候補）
_JA_SPLIT_CHARS = re.compile(r"[、。！？]|(?<=[よねなわぞぜさか])")


def merge_cues(
    cues: list[VttCue],
    language: str,
    max_cue_seconds: float = 15.0,
) -> list[VttCue]:
    """過分割されたVttCueを文単位にマージして返す。

    言語ごとに文末検出ロジックを切り替える:
    - ja: Janome 形態素解析で末尾品詞を判定
    - その他: ピリオド/感嘆符/疑問符で判定（略語・省略記号は除外）

    max_cue_seconds を超えるキューは自然な区切りで再分割する。
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
        if _contains_sentence_end(cue.text) or is_end(join_sep.join(c.text for c in buffer)):
            merged.append(_flush(buffer, len(merged), join_sep))
            buffer = []

    if buffer:
        merged.append(_flush(buffer, len(merged), join_sep))

    # 長すぎるキューを再分割
    if language == "ja" and max_cue_seconds > 0:
        merged = _split_long_cues(merged, max_cue_seconds)
        # インデックス振り直し
        for i, c in enumerate(merged):
            c.index = i

    return merged


def _flush(buffer: list[VttCue], index: int, join_sep: str) -> VttCue:
    words = join_sep.join(c.text for c in buffer)
    if join_sep == " ":
        words = re.sub(r" {2,}", " ", words).strip()
    cue = VttCue(
        index=index,
        start=buffer[0].start,
        end=buffer[-1].end,
        text=words,
        original_start=buffer[0].original_start,
        original_end=buffer[-1].original_end,
    )
    # 元キューのリストを保持（長キュー分割でタイムスタンプ復元に使用）
    cue._source_cues = list(buffer)
    return cue


def _split_long_cues(cues: list[VttCue], max_seconds: float) -> list[VttCue]:
    """max_seconds を超えるキューを自然な区切りで再分割する。"""
    result: list[VttCue] = []
    for cue in cues:
        if cue.end - cue.start <= max_seconds:
            result.append(cue)
            continue
        source: list[VttCue] = getattr(cue, "_source_cues", [cue])
        split = _split_by_natural_boundary(cue.text, source, max_seconds)
        result.extend(split)
    return result


def _split_by_natural_boundary(
    text: str,
    source_cues: list[VttCue],
    max_seconds: float,
) -> list[VttCue]:
    """テキストを自然な区切りで分割し、元キューのタイムスタンプを割り当てる。

    元キューの累積文字数でテキスト上の位置を特定し、
    分割点に最も近い元キューの境界をタイムスタンプとして使用する。
    """
    total_dur = source_cues[-1].end - source_cues[0].start
    if total_dur <= max_seconds or len(text) < 2:
        cue = VttCue(
            index=0,
            start=source_cues[0].start,
            end=source_cues[-1].end,
            text=text,
            original_start=source_cues[0].original_start,
            original_end=source_cues[-1].original_end,
        )
        cue._source_cues = source_cues
        return [cue]

    # 元キューの文字数累積マップを構築
    # cumulative[i] = source_cues[0..i] のテキストを結合した文字数
    cumulative: list[int] = []
    acc = 0
    for sc in source_cues:
        acc += len(sc.text)
        cumulative.append(acc)
    total_chars = cumulative[-1]

    # 目標分割位置（秒・文字数の両面で中央に近い点を探す）
    target_seconds = total_dur / 2
    target_chars = total_chars // 2

    # 区切り候補を収集（句点・読点・終助詞直後）
    # 句点（。！？）と読点（、）を分けて管理し、句点を優先する
    strong: list[int] = []  # 句点・感嘆符・疑問符
    weak: list[int] = []    # 読点・終助詞直後
    for m in _JA_SPLIT_CHARS.finditer(text):
        pos = m.end()
        if 0 < pos < len(text):
            if text[pos - 1] in "。！？":
                strong.append(pos)
            else:
                weak.append(pos)

    if not strong and not weak:
        # 区切りが見つからない場合は元キュー境界の中央で分割
        mid_idx = len(source_cues) // 2
        split_char_pos = cumulative[mid_idx - 1]
        weak = [split_char_pos]

    # 句点があれば最寄りの句点を選ぶ、なければ中央に最も近い読点を選ぶ
    pool = strong if strong else weak
    best_pos = min(pool, key=lambda p: abs(p - target_chars))

    # best_pos が属する元キューを特定してタイムスタンプを決める
    split_source_idx = 0
    for i, cum in enumerate(cumulative):
        if cum >= best_pos:
            split_source_idx = i
            break

    split_time = source_cues[split_source_idx].end

    text_a = text[:best_pos].strip()
    text_b = text[best_pos:].strip()

    if not text_a or not text_b:
        cue = VttCue(
            index=0,
            start=source_cues[0].start,
            end=source_cues[-1].end,
            text=text,
            original_start=source_cues[0].original_start,
            original_end=source_cues[-1].original_end,
        )
        cue._source_cues = source_cues
        return [cue]

    source_a = source_cues[:split_source_idx + 1]
    source_b = source_cues[split_source_idx + 1:]
    if not source_b:
        # 分割点が最後の元キュー内に収まり、text_b に割り当てる元キューがない
        # タイムスタンプが重複するため分割せずそのまま返す
        cue = VttCue(
            index=0,
            start=source_cues[0].start,
            end=source_cues[-1].end,
            text=text,
            original_start=source_cues[0].original_start,
            original_end=source_cues[-1].original_end,
        )
        cue._source_cues = source_cues
        return [cue]

    # 再帰的に分割（まだ長い場合）
    parts_a = _split_by_natural_boundary(text_a, source_a, max_seconds)
    parts_b = _split_by_natural_boundary(text_b, source_b, max_seconds)

    return parts_a + parts_b


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
