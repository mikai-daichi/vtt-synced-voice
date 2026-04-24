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
    min_cue_chars: int = 50,
) -> list[VttCue]:
    """過分割されたVttCueを文単位にマージして返す。

    言語ごとに文末検出ロジックを切り替える:
    - ja: Janome 形態素解析で末尾品詞を判定
    - その他: ピリオド/感嘆符/疑問符で判定（略語・省略記号は除外）

    max_cue_seconds を超えるキューは自然な区切りで再分割する。
    min_cue_chars を超えるキューは句点または形態素解析で後処理分割する。
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
        if _contains_sentence_end(cue.text) or is_end(cue.text):
            merged.append(_flush(buffer, len(merged), join_sep))
            buffer = []

    if buffer:
        merged.append(_flush(buffer, len(merged), join_sep))

    # 長すぎるキューを再分割（秒数ベース）
    if language == "ja" and max_cue_seconds > 0:
        merged = _split_long_cues(merged, max_cue_seconds)

    # 長すぎるキューを後処理分割（文字数ベース：句点→形態素解析）
    if language == "ja" and min_cue_chars > 0:
        merged = _split_long_cues_post(merged, min_cue_chars)

    # インデックス振り直し
    if language == "ja":
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


def _split_long_cues_post(cues: list[VttCue], min_chars: int) -> list[VttCue]:
    """min_chars を超えるキューを後処理で分割する。

    フェーズ1: 句点（。！？）が含まれれば全句点で分割。
    フェーズ2: 句点がなければ形態素解析で文末+文頭パターンを検出して分割。
    min_chars 以下のキューは一切変更しない。
    分割後のキューに対して再帰的に適用する。

    末尾断片が短すぎる場合（< min_chars // 5）は次のキューの先頭に連結する。
    """
    min_tail = max(min_chars // 5, 5)

    result: list[VttCue] = []
    # 分割されたキューの位置を記録する（_merge_short_tailの対象を限定するため）
    split_indices: set[int] = set()

    for cue in cues:
        if len(cue.text) <= min_chars:
            result.append(cue)
            continue
        source: list[VttCue] = getattr(cue, "_source_cues", [cue])
        positions = _find_split_positions(cue.text, min_chars)
        if not positions:
            result.append(cue)
            continue
        # 分割後のキューに再帰適用（分割結果がまだ長い場合に対応）
        split = _apply_split_positions(cue.text, source, positions)
        start_idx = len(result)
        result.extend(_split_long_cues_post(split, min_chars))
        for idx in range(start_idx, len(result)):
            split_indices.add(idx)

    # 分割によって生じた短い末尾断片のみを次のキューの先頭に連結する
    # 例: 「...あるよ。」「相手」「がじゃあ...」→「...あるよ。」「相手がじゃあ...」
    if not split_indices:
        return result

    merged: list[VttCue] = []
    carry_text: str = ""
    carry_start: float = 0.0
    carry_original_start: float = 0.0

    for i, cue in enumerate(result):
        text = carry_text + cue.text if carry_text else cue.text
        start = carry_start if carry_text else cue.start
        original_start = carry_original_start if carry_text else cue.original_start
        carry_text = ""

        is_last = (i == len(result) - 1)
        # 分割されたキューが短すぎる場合のみ次へ持ち越す
        if (i in split_indices and not is_last
                and 0 < len(text) < min_tail):
            carry_text = text
            carry_start = start
            carry_original_start = original_start
        else:
            new_cue = VttCue(
                index=cue.index,
                start=start,
                end=cue.end,
                text=text,
                original_start=original_start,
                original_end=cue.original_end,
            )
            if hasattr(cue, "_source_cues"):
                new_cue._source_cues = cue._source_cues
            merged.append(new_cue)

    # carry が残った場合は前のキューに戻す
    if carry_text and merged:
        last = merged[-1]
        merged[-1] = VttCue(
            index=last.index, start=last.start, end=last.end,
            text=last.text + carry_text,
            original_start=last.original_start, original_end=last.original_end,
        )

    return merged


def _find_split_positions(text: str, min_chars: int) -> list[int]:
    """テキスト内の分割位置（文字インデックス）リストを返す。

    フェーズ1: 句点（。！？!?）を全て収集。
    フェーズ2: 句点がなければ形態素解析で文末+文頭パターンを検出。
    いずれも「残り文字数 >= min_chars // 2」のみ有効とする。
    """
    min_remaining = max(min_chars // 5, 10)

    # フェーズ1: 全角句点（。！？）による分割位置
    # 半角 ? ! は話し言葉で文中にも現れるためフェーズ2（形態素解析）に委ねる
    # 残り文字数の制限なし（残り短い場合は呼び出し元で次キューへ連結）
    kuten_positions = [
        m.end() for m in re.finditer(r"[。！？]", text)
        if m.end() < len(text)  # 末尾句点（残り0文字）のみ除外
    ]
    if kuten_positions:
        return kuten_positions

    # フェーズ2: 形態素解析による分割位置
    return _find_morpheme_split_positions(text, min_remaining)


def _find_morpheme_split_positions(text: str, min_remaining: int) -> list[int]:
    """形態素解析で「文末トークン + 文頭らしい次トークン」の位置を返す。

    文末判定: is_end() と同等のルール（ただし除外セットを拡大）
    文頭判定: 次トークンが名詞/一般・固有名詞・数・代名詞、感動詞、接続詞のいずれか
    """
    from janome.tokenizer import Tokenizer
    tokenizer = Tokenizer()
    tokens = list(tokenizer.tokenize(text))

    # 文末になりえない助動詞（文の途中の活用形）
    _EXCLUDE_AUX = frozenset({"な", "ん", "ませ", "でしょ"})

    # 文頭らしい品詞・細分類の組み合わせ
    # 名詞/非自立（「の」「こと」等）と名詞/接尾（「人」「年」等）は除外
    _SENTENCE_START_POS = {
        ("名詞", "一般"),
        ("名詞", "固有名詞"),
        ("名詞", "数"),
        ("名詞", "代名詞"),
        ("名詞", "サ変接続"),   # 「相談」「返金」「結婚」等
        ("感動詞", "*"),
        ("接続詞", "*"),
        ("副詞", "*"),          # 「もう」「ただ」「今」等、話し言葉の文頭に多い
        ("形容詞", "自立"),     # 「やばい」「すごい」等
        ("連体詞", "*"),        # 「その」「こんな」「あの」等
    }

    positions: list[int] = []
    char_pos = 0
    prev_surface = ""

    for i, tok in enumerate(tokens):
        surface = tok.surface
        end_pos = char_pos + len(surface)
        ps = tok.part_of_speech.split(",")
        ps0 = ps[0]
        ps1 = ps[1] if len(ps) > 1 else "*"

        # 文末判定（is_end() と同等、除外セットを拡大）
        is_end_tok = False
        if ps0 == "助動詞" and surface not in _EXCLUDE_AUX:
            if surface == "た":
                is_end_tok = (prev_surface == "まし")
            else:
                is_end_tok = True
        elif ps0 == "動詞" and ps1 == "非自立":
            is_end_tok = True
        elif ps0 == "感動詞":
            is_end_tok = True
        elif ps0 == "助詞" and "終助詞" in ps1:
            is_end_tok = True
        elif ps0 == "助詞" and ps1 == "接続助詞" and surface in _KEREDO_SURFACES:
            is_end_tok = True
        elif ps0 == "接続詞" and surface in _KEREDO_CONJ:
            is_end_tok = True
        elif ps0 == "助詞" and ps1 == "接続助詞" and surface in _KARA_NODE_SURFACES:
            is_end_tok = True
        elif ps0 == "助詞" and ps1 == "格助詞" and surface == "って":
            is_end_tok = True
        elif ps0 == "接続詞" and surface in _SENTENCE_END_CONJ:
            is_end_tok = True
        elif ps0 == "記号" and surface in {"。", "！", "？"}:
            is_end_tok = True

        # 「でしょうか」「ますか」: 助動詞「う」の直後が「か」（副助詞系）で
        # さらにその次が文頭らしいトークンなら、「か」の後を分割点とする
        # （「う」は is_end_tok=True になるが次が「か」の場合は「か」後を優先）
        if (surface == "う" and ps0 == "助動詞"
                and i + 2 < len(tokens)):
            nxt1 = tokens[i + 1]
            nxt2 = tokens[i + 2]
            if nxt1.surface == "か":
                ka_end = end_pos + len(nxt1.surface)
                remaining = len(text) - ka_end
                if remaining >= min_remaining:
                    nxt2_ps = nxt2.part_of_speech.split(",")
                    nxt2_ps0 = nxt2_ps[0]
                    nxt2_ps1 = nxt2_ps[1] if len(nxt2_ps) > 1 else "*"
                    if (nxt2_ps0, nxt2_ps1) in _SENTENCE_START_POS or (nxt2_ps0, "*") in _SENTENCE_START_POS:
                        positions.append(ka_end)

        if is_end_tok and i + 1 < len(tokens):
            remaining = len(text) - end_pos
            if remaining < min_remaining:
                prev_surface = surface
                char_pos = end_pos
                continue

            nxt = tokens[i + 1]
            nxt_ps = nxt.part_of_speech.split(",")
            nxt_ps0 = nxt_ps[0]
            nxt_ps1 = nxt_ps[1] if len(nxt_ps) > 1 else "*"

            if (nxt_ps0, nxt_ps1) in _SENTENCE_START_POS or (nxt_ps0, "*") in _SENTENCE_START_POS:
                positions.append(end_pos)

        prev_surface = surface
        char_pos = end_pos

    return positions


def _merge_short_tail(cues: list[VttCue], min_tail: int) -> list[VttCue]:
    """分割後の末尾断片が短すぎる場合、次のキューの先頭に連結する。

    例: [「...あるよ。」, 「相手」, 「がじゃあ...」]
      → 「相手」(2文字 < min_tail) は次の「がじゃあ...」の先頭へ
      → [「...あるよ。」, 「相手がじゃあ...」]
    """
    if len(cues) <= 1:
        return cues

    result: list[VttCue] = []
    carry_text: str = ""
    carry_start: float = 0.0
    carry_original_start: float = 0.0

    for i, cue in enumerate(cues):
        text = carry_text + cue.text if carry_text else cue.text
        start = carry_start if carry_text else cue.start
        original_start = carry_original_start if carry_text else cue.original_start
        carry_text = ""

        is_last = (i == len(cues) - 1)
        if not is_last and 0 < len(text) < min_tail:
            # 短すぎる → 次キューへ持ち越し
            carry_text = text
            carry_start = start
            carry_original_start = original_start
        else:
            new_cue = VttCue(
                index=cue.index,
                start=start,
                end=cue.end,
                text=text,
                original_start=original_start,
                original_end=cue.original_end,
            )
            if hasattr(cue, "_source_cues"):
                new_cue._source_cues = cue._source_cues
            result.append(new_cue)

    # carry が残った場合（最後のキューが短い）は前のキューに戻す
    if carry_text and result:
        last = result[-1]
        result[-1] = VttCue(
            index=last.index,
            start=last.start,
            end=last.end,
            text=last.text + carry_text,
            original_start=last.original_start,
            original_end=last.original_end,
        )

    return result


def _apply_split_positions(
    text: str,
    source_cues: list[VttCue],
    positions: list[int],
) -> list[VttCue]:
    """分割位置リストに従ってテキストを分割し、タイムスタンプを割り当てる。

    タイムスタンプは source_cues の累積文字数で対応する元キューを特定する。
    分割点が最後の元キュー内に収まる場合は線形補間で時刻を推定する。
    """
    # source_cues の累積文字数マップ
    cumulative: list[int] = []
    acc = 0
    for sc in source_cues:
        acc += len(sc.text)
        cumulative.append(acc)
    total_chars = cumulative[-1]

    def time_at(char_pos: int) -> float:
        """char_pos に対応する時刻を返す。"""
        for i, cum in enumerate(cumulative):
            if cum >= char_pos:
                sc = source_cues[i]
                # このsource_cue内での位置を線形補間
                prev_cum = cumulative[i - 1] if i > 0 else 0
                local_ratio = (char_pos - prev_cum) / max(cum - prev_cum, 1)
                return sc.start + (sc.end - sc.start) * local_ratio
        # char_pos が末尾を超えた場合（念のため）
        return source_cues[-1].end

    result: list[VttCue] = []
    boundaries = [0] + positions + [len(text)]

    for j in range(len(boundaries) - 1):
        seg_text = text[boundaries[j]:boundaries[j + 1]].strip()
        if not seg_text:
            continue
        seg_start = time_at(boundaries[j]) if boundaries[j] > 0 else source_cues[0].start
        seg_end = time_at(boundaries[j + 1]) if boundaries[j + 1] < len(text) else source_cues[-1].end

        cue = VttCue(
            index=0,
            start=seg_start,
            end=seg_end,
            text=seg_text,
            original_start=seg_start,
            original_end=seg_end,
        )
        result.append(cue)

    return result if result else [VttCue(
        index=0,
        start=source_cues[0].start,
        end=source_cues[-1].end,
        text=text,
        original_start=source_cues[0].original_start,
        original_end=source_cues[-1].original_end,
    )]


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
_KARA_NODE_SURFACES = frozenset({"から", "ので", "し"})
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
        # 「か」は Janome で pos1="副助詞／並立助詞／終助詞" になるため "in" で判定
        if pos0 == "助詞" and "終助詞" in pos1:
            return True

        # 接続助詞止め・けど系（けど/けども/が 等）
        # 格助詞の「が」（私が）とはJanomeが区別するため誤検出なし
        if pos0 == "助詞" and pos1 == "接続助詞" and last.surface in _KEREDO_SURFACES:
            return True

        # 接続詞・けれど系（けれど/けれども）
        if pos0 == "接続詞" and last.surface in _KEREDO_CONJ:
            return True

        # 接続助詞止め・から/ので/し系
        # 格助詞の「から」（東京から）とはJanomeが区別するため誤検出なし
        if pos0 == "助詞" and pos1 == "接続助詞" and last.surface in _KARA_NODE_SURFACES:
            return True

        # 格助詞「って」引用止め（〜かって / 〜だって）
        # 話し言葉で文を引用・強調して止める用法
        if pos0 == "助詞" and pos1 == "格助詞" and last.surface == "って":
            return True

        # 接続詞止め（なので/だから/ですから）
        # 「次に」「また」「そして」など文頭に来る接続詞は除外
        if pos0 == "接続詞" and last.surface in _SENTENCE_END_CONJ:
            return True

        # 句点・感嘆符・疑問符・省略記号で終わる（Whisperが付与した句読点）
        if pos0 == "記号" and last.surface in {"。", "！", "？", "…"}:
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
