"""cue_merger モジュールのユニットテスト。"""
from __future__ import annotations

import pytest

from vtt_synced_voice.vtt_io import VttCue
from vtt_synced_voice.cue_merger import (
    merge_cues,
    _is_end_punctuation,
    _contains_sentence_end,
    _split_by_natural_boundary,
)


def make_cue(index: int, start: float, end: float, text: str) -> VttCue:
    return VttCue(index=index, start=start, end=end, text=text,
                  original_start=start, original_end=end)


# ---------------------------------------------------------------------------
# 日本語マージ
# ---------------------------------------------------------------------------

class TestMergeCuesJapanese:
    def test_single_cue_sentence_end(self):
        cues = [make_cue(0, 0.0, 1.0, "読み込み完了です")]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1
        assert result[0].text == "読み込み完了です"

    def test_merge_two_into_one_sentence(self):
        cues = [
            make_cue(0, 0.0, 1.0, "オートトリムが"),
            make_cue(1, 1.2, 2.5, "インストール済みのファイナルカットプロが開いています"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1
        assert result[0].text == "オートトリムがインストール済みのファイナルカットプロが開いています"
        assert result[0].start == 0.0
        assert result[0].end == 2.5

    def test_two_sentences_stay_separate(self):
        cues = [
            make_cue(0, 0.0, 1.0, "読み込み完了です"),
            make_cue(1, 2.0, 3.5, "次にVTTファイルを下のドロップゾーンに移動します"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_rentaikei_ta_not_sentence_end(self):
        """「た」単体（連体修飾）は文末と判定しない。"""
        cues = [
            make_cue(0, 0.0, 1.0, "新しく作成された"),
            make_cue(1, 1.2, 2.5, "オートトリムイベントを開きます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1
        assert result[0].text == "新しく作成されたオートトリムイベントを開きます"

    def test_mashita_is_sentence_end(self):
        """「ました」は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "これまでエクステンション版を説明してきました"),
            make_cue(1, 2.0, 3.0, "次にVTTファイルを移動します"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_split_word_rejoined(self):
        """途中で分断された単語（VTTファ／イルを）が結合される。"""
        cues = [
            make_cue(0, 0.0, 0.5, "次に"),
            make_cue(1, 0.6, 0.8, "VTTファ"),
            make_cue(2, 7.0, 7.5, "イルを"),
            make_cue(3, 7.8, 9.0, "下のドロップゾーンに移動します"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1
        assert "VTTファイルを" in result[0].text

    def test_empty_input(self):
        assert merge_cues([], language="ja") == []

    def test_index_renumbered(self):
        """マージ後のキューのインデックスが0から振り直されている。"""
        cues = [
            make_cue(0, 0.0, 1.0, "読み込み完了です"),
            make_cue(1, 2.0, 3.0, "クリックします"),
        ]
        result = merge_cues(cues, language="ja")
        assert [c.index for c in result] == list(range(len(result)))

    # --- 終助詞 ---

    def test_yo_is_sentence_end(self):
        """「よ」終助詞は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.0, "本当だよ"),
            make_cue(1, 1.5, 2.5, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_ne_is_sentence_end(self):
        """「ね」終助詞は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.0, "いいですね"),
            make_cue(1, 1.5, 2.5, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_na_is_sentence_end(self):
        """「な」終助詞は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.0, "難しいな"),
            make_cue(1, 1.5, 2.5, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_jan_is_sentence_end(self):
        """「じゃん」終助詞は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.0, "いいじゃん"),
            make_cue(1, 1.5, 2.5, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_final_particle_merges_before_split(self):
        """終助詞が文末にないキューはマージされる。"""
        cues = [
            make_cue(0, 0.0, 0.5, "アイデアを出す"),
            make_cue(1, 0.6, 1.5, "タイプの人なんだよな"),
            make_cue(2, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2
        assert result[0].text == "アイデアを出すタイプの人なんだよな"

    # --- 接続助詞止め・けど系 ---

    def test_kedo_is_sentence_end(self):
        """「けど」接続助詞止めは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "難しいんですけど"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_ga_setsuzoku_is_sentence_end(self):
        """接続助詞の「が」は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "そうなんですが"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_ga_kakujoshi_not_sentence_end(self):
        """格助詞の「が」（私が）は文末と判定しない。"""
        cues = [
            make_cue(0, 0.0, 1.0, "私が"),
            make_cue(1, 1.2, 2.5, "説明します"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1

    # --- 接続助詞止め・から/ので系 ---

    def test_kara_setsuzoku_is_sentence_end(self):
        """接続助詞の「から」（理由）は文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "忙しいから"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_kara_kakujoshi_not_sentence_end(self):
        """格助詞の「から」（東京から）は文末と判定しない。"""
        cues = [
            make_cue(0, 0.0, 1.0, "東京から"),
            make_cue(1, 1.2, 2.5, "来ました"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1

    def test_node_is_sentence_end(self):
        """「ので」接続助詞止めは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "急ぐので"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    # --- 接続助詞止め・し系 ---

    def test_shi_is_sentence_end(self):
        """「し」接続助詞止めは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "お金も貯まるし"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_shi_mid_sentence_merges(self):
        """「〜ないし」が文中のキュー末尾の場合はマージされる。"""
        cues = [
            make_cue(0, 0.0, 1.0, "悪くないし"),
            make_cue(1, 1.2, 2.5, "問題もないし進めます"),
        ]
        result = merge_cues(cues, language="ja")
        # 「悪くないし」は文末と判定されフラッシュされるため2キューになる
        assert len(result) == 2

    # --- 格助詞「って」引用止め ---

    def test_tte_citation_is_sentence_end(self):
        """格助詞「って」引用止めは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "困るかって"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    # --- 接続詞止め ---

    def test_dakara_is_sentence_end(self):
        """「だから」接続詞止めは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "難しいんだ、だから"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_tsugini_not_sentence_end(self):
        """「次に」のような文頭接続詞は文末と判定しない。"""
        cues = [
            make_cue(0, 0.0, 0.5, "次に"),
            make_cue(1, 0.6, 1.5, "説明します"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 1

    # --- 省略記号 ---

    def test_ellipsis_is_sentence_end(self):
        """「…」で終わるキューは文末と判定する。"""
        cues = [
            make_cue(0, 0.0, 1.5, "時間がどんどん…"),
            make_cue(1, 2.0, 3.0, "次に進みます"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2

    def test_no_stale_buffer_merge(self):
        """文末でないキューがバッファに残っていても次の文末キューで誤結合しない。

        バグ再現: 「…」終わりキューがバッファ残留 → 次の「か」終わりキューで
        バッファ全体がフラッシュされ「皆さん」が分割されていた。
        """
        cues = [
            make_cue(0, 3.4, 5.9, "皆さんテロップ作業で消耗していませんか"),
            make_cue(1, 7.3, 10.5, "ファイナルカットプロでテロップを打っていると時間がどんどん…"),
            make_cue(2, 13.5, 15.8, "皆さんテロップ作業で消耗していませんか"),
            make_cue(3, 17.1, 21.4, "ファイナルカットプロでテロップを打っていると時間がどんどん溶けていきます"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 4
        assert result[0].text == "皆さんテロップ作業で消耗していませんか"
        assert result[1].text == "ファイナルカットプロでテロップを打っていると時間がどんどん…"
        assert result[2].text == "皆さんテロップ作業で消耗していませんか"
        assert result[3].text == "ファイナルカットプロでテロップを打っていると時間がどんどん溶けていきます"

    # --- continuation（前キューの続き）マージ ---

    def test_desuyo_merges_with_prev(self):
        """「ですよ」は前キューの続きとしてマージされる。"""
        cues = [
            make_cue(0, 0.0, 1.3, "なかなかできない"),
            make_cue(1, 1.8, 2.0, "ですよ"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 1
        assert result[0].text == "なかなかできないですよ"

    def test_continuation_chain_desuyone(self):
        """「ですよ」「ね」と連続するcontinuationが全てマージされる。"""
        cues = [
            make_cue(0, 0.0, 1.3, "なかなかできない"),
            make_cue(1, 1.8, 2.0, "ですよ"),
            make_cue(2, 6.4, 6.5, "ね"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 1
        assert result[0].text == "なかなかできないですよね"

    def test_continuation_u_ne(self):
        """「うね」（でしょうね の分断）は前キューとマージされる。"""
        cues = [
            make_cue(0, 0.0, 2.4, "メンバーの中にいるからこそなんでしょ"),
            make_cue(1, 2.9, 3.4, "うね"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 1
        assert result[0].text == "メンバーの中にいるからこそなんでしょうね"

    def test_continuation_tta_node(self):
        """「ったので」は前キューの続きとしてマージされる。"""
        cues = [
            make_cue(0, 0.0, 3.0, "帰識庁だ"),
            make_cue(1, 3.5, 4.2, "ったので"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 1
        assert result[0].text == "帰識庁だったので"

    def test_continuation_ka(self):
        """「か」は前キューの続きとしてマージされる。"""
        cues = [
            make_cue(0, 0.0, 2.0, "こっちし"),
            make_cue(1, 2.5, 2.8, "か"),
        ]
        result = merge_cues(cues, language="ja", min_cue_chars=0)
        assert len(result) == 1
        assert result[0].text == "こっちしか"

    # --- 句点内部検出 ---

    def test_interior_kuten_splits(self):
        """キュー内部に句点（。）があれば分割される。"""
        cues = [
            make_cue(0, 0.0, 2.0, "完了です。次に進みますが"),
            make_cue(1, 2.5, 3.5, "準備してください"),
        ]
        result = merge_cues(cues, language="ja")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 英語マージ
# ---------------------------------------------------------------------------

class TestMergeCuesEnglish:
    def test_merge_until_period(self):
        cues = [
            make_cue(0, 0.0, 0.5, "I'm"),
            make_cue(1, 0.6, 0.9, "a"),
            make_cue(2, 1.0, 1.8, "happiness scientist,"),
            make_cue(3, 2.0, 2.5, "and"),
            make_cue(4, 2.6, 3.0, "I've been here for years."),
        ]
        result = merge_cues(cues, language="en")
        assert len(result) == 1
        assert result[0].text == "I'm a happiness scientist, and I've been here for years."

    def test_question_mark_splits(self):
        cues = [
            make_cue(0, 0.0, 1.0, "How do we study that?"),
            make_cue(1, 2.0, 3.0, "Well,"),
            make_cue(2, 3.2, 4.0, "in 1998."),
        ]
        result = merge_cues(cues, language="en")
        assert len(result) == 2

    def test_interior_question_mark_splits(self):
        """キュー内部に?がある場合も分割される。"""
        cues = [
            make_cue(0, 0.0, 1.5, "cananyonebecomehappier?Now,"),
            make_cue(1, 1.8, 2.5, "howdoweevenstudysomethinglikethat?"),
        ]
        result = merge_cues(cues, language="en")
        assert len(result) == 2

    def test_abbreviation_not_split(self):
        """略語のピリオドでは分割しない。"""
        cues = [
            make_cue(0, 0.0, 1.0, "Dr."),
            make_cue(1, 1.1, 2.0, "Smith said hello,"),
            make_cue(2, 2.2, 3.0, "and left."),
        ]
        result = merge_cues(cues, language="en")
        assert len(result) == 1

    def test_english_words_joined_with_space(self):
        """英語はスペース区切りで結合される。"""
        cues = [
            make_cue(0, 0.0, 0.5, "Hello"),
            make_cue(1, 0.6, 1.0, "world."),
        ]
        result = merge_cues(cues, language="en")
        assert result[0].text == "Hello world."


# ---------------------------------------------------------------------------
# _is_end_punctuation
# ---------------------------------------------------------------------------

class TestIsEndPunctuation:
    @pytest.mark.parametrize("text", ["years.", "Thank you!", "like that?"])
    def test_sentence_end(self, text):
        assert _is_end_punctuation(text) is True

    @pytest.mark.parametrize("text", ["Mr.", "Dr. Jones", "etc.", "U.S.", "..."])
    def test_abbreviation_not_end(self, text):
        assert _is_end_punctuation(text) is False

    def test_empty(self):
        assert _is_end_punctuation("") is False


# ---------------------------------------------------------------------------
# _contains_sentence_end
# ---------------------------------------------------------------------------

class TestContainsSentenceEnd:
    def test_interior_question_mark(self):
        assert _contains_sentence_end("cananyonebecomehappier?Now,") is True

    def test_trailing_question_not_interior(self):
        assert _contains_sentence_end("howdidthatreallyfeel?") is False

    def test_us_abbreviation_not_interior(self):
        assert _contains_sentence_end("U.S.policymatters,") is False

    def test_interior_period(self):
        assert _contains_sentence_end("He left. She stayed,") is True


# ---------------------------------------------------------------------------
# 長キュー分割（_split_by_natural_boundary）
# ---------------------------------------------------------------------------

class TestSplitByNaturalBoundary:
    def _make_sources(self, texts: list[str], start: float = 0.0, dur_each: float = 2.0):
        cues = []
        t = start
        for i, text in enumerate(texts):
            cues.append(make_cue(i, t, t + dur_each, text))
            t += dur_each
        return cues

    def test_short_cue_not_split(self):
        """max_seconds 以下のキューは分割しない。"""
        source = self._make_sources(["短いテキスト"], dur_each=5.0)
        result = _split_by_natural_boundary("短いテキスト", source, max_seconds=15.0)
        assert len(result) == 1
        assert result[0].text == "短いテキスト"

    def test_split_at_kuten(self):
        """句点で長いキューを2つに分割する。"""
        texts = ["Aが来た。", "Bが行った。", "Cが残った。", "Dが戻った。", "Eが動いた。"]
        source = self._make_sources(texts, dur_each=4.0)
        full_text = "".join(texts)
        result = _split_by_natural_boundary(full_text, source, max_seconds=15.0)
        assert len(result) >= 2
        reconstructed = "".join(c.text for c in result)
        assert reconstructed == full_text

    def test_split_timestamps_from_source(self):
        """分割されたキューのタイムスタンプが元キューから正確に設定される。"""
        source = self._make_sources(["前半のテキストで、", "後半のテキストです。"], dur_each=10.0)
        full_text = "前半のテキストで、後半のテキストです。"
        result = _split_by_natural_boundary(full_text, source, max_seconds=15.0)
        assert len(result) == 2
        assert result[0].start == 0.0
        assert result[1].end == 20.0

    def test_no_candidate_splits_at_midpoint(self):
        """区切り文字がない場合は元キュー境界の中央で分割する。"""
        source = self._make_sources(["AAAA", "BBBB", "CCCC", "DDDD"], dur_each=5.0)
        full_text = "AAAABBBBCCCCDDDD"
        result = _split_by_natural_boundary(full_text, source, max_seconds=15.0)
        assert len(result) >= 2
        assert "".join(c.text for c in result) == full_text

    def test_no_timestamp_overlap_when_kuten_in_last_source(self):
        """句点が最後の元キュー内部にある場合、タイムスタンプが重複しない。"""
        source = [
            make_cue(0, 0.0, 2.0, "その味を醤油味につければ"),
            make_cue(1, 2.0, 8.0, "肉じゃがになるし、カレーになるそんなだけのことなんだよね。だから、"),
        ]
        text = "その味を醤油味につければ肉じゃがになるし、カレーになるそんなだけのことなんだよね。だから、"
        result = _split_by_natural_boundary(text, source, max_seconds=5.0)
        for i in range(len(result) - 1):
            assert result[i].end <= result[i + 1].start, (
                f"キュー{i}のend({result[i].end}) > キュー{i+1}のstart({result[i+1].start})"
            )

    def test_kuten_preferred_over_touten(self):
        """句点と読点が両方ある場合、句点が優先して選ばれる。"""
        source = self._make_sources(
            ["Aが来た。", "Bがいて、", "Cが動いた。", "Dで終わる"],
            dur_each=4.0,
        )
        full_text = "Aが来た。Bがいて、Cが動いた。Dで終わる"
        # max_seconds=8.0 で16秒を分割 → 分割点が句点（。）で選ばれることを確認
        result = _split_by_natural_boundary(full_text, source, max_seconds=8.0)
        assert len(result) >= 2
        # 分割点が読点（、）ではなく句点（。）で切られているか確認：
        # 読点優先なら "Aが来た。Bがいて、" と "Cが動いた。Dで終わる" に分かれる
        # 句点優先なら "Aが来た。" と "Bがいて、Cが動いた。Dで終わる" に分かれる
        assert result[0].text == "Aが来た。"

    def test_index_sequential_after_long_split(self):
        """merge_cues の長キュー分割後にインデックスが連番になる。"""
        cues = [
            make_cue(0, 0.0, 4.0, "Aです。"),
            make_cue(1, 4.5, 8.0, "Bです。"),
            make_cue(2, 8.5, 12.0, "Cです。"),
            make_cue(3, 12.5, 16.0, "Dです。"),
            make_cue(4, 16.5, 20.0, "Eです。"),
        ]
        result = merge_cues(cues, language="ja", max_cue_seconds=10.0)
        assert [c.index for c in result] == list(range(len(result)))
