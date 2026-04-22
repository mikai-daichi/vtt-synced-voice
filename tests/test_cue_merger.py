"""cue_merger モジュールのユニットテスト。"""
from __future__ import annotations

import pytest

from vtt_synced_voice.vtt_io import VttCue
from vtt_synced_voice.cue_merger import (
    merge_cues,
    _is_end_punctuation,
    _contains_sentence_end,
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
