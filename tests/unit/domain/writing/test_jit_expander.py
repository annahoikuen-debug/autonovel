"""src/domain/writing/jit_expander.py (JITBeatExpander / EditorMetrics) の単体テスト."""

from __future__ import annotations

from src.domain.writing.jit_expander import EditorMetrics, JITBeatExpander


class TestEditorMetrics:
    """EditorMetrics のテスト."""

    def test_default_values(self):
        """デフォルトインスタンスは全項目ゼロ/空である."""
        metrics = EditorMetrics()
        assert metrics.char_count == 0
        assert metrics.dialogue_char_count == 0
        assert metrics.dialogue_ratio == 0.0
        assert metrics.ruby_count == 0


class TestJITBeatExpander:
    """JITBeatExpander のテスト."""

    def test_calculate_metrics_empty_text(self):
        """空文字列はゼロメトリクスを返す."""
        metrics = JITBeatExpander.calculate_metrics("")
        assert isinstance(metrics, EditorMetrics)
        assert metrics.char_count == 0
        assert metrics.dialogue_char_count == 0
        assert metrics.dialogue_ratio == 0.0
        assert metrics.ruby_count == 0

    def test_calculate_metrics_with_dialogue(self):
        """「...」で囲まれた会話文の文字数と割合を計算する."""
        text = "彼は「こんにちは」と言った。"
        metrics = JITBeatExpander.calculate_metrics(text)
        assert metrics.char_count == len(text)
        assert metrics.dialogue_char_count == len("こんにちは")
        assert metrics.dialogue_ratio == round(len("こんにちは") / len(text), 3)
        assert 0.0 < metrics.dialogue_ratio < 1.0

    def test_calculate_metrics_no_dialogue(self):
        """会話文が無い場合は dialogue_char_count は 0."""
        text = "本文だけの文章です。"
        metrics = JITBeatExpander.calculate_metrics(text)
        assert metrics.char_count == len(text)
        assert metrics.dialogue_char_count == 0
        assert metrics.dialogue_ratio == 0.0

    def test_calculate_metrics_with_ruby(self):
        """|漢字《ルビ》記法のルビ数を計算する."""
        text = "|漢字《かんじ》と |仮名《かな》"
        metrics = JITBeatExpander.calculate_metrics(text)
        assert metrics.ruby_count == 2

    def test_calculate_metrics_no_ruby(self):
        """ルビ記法が無い場合は ruby_count は 0."""
        text = "ルビの無い文章です。"
        metrics = JITBeatExpander.calculate_metrics(text)
        assert metrics.ruby_count == 0

    def test_calculate_metrics_carriage_return_removed(self):
        """改行コード \r は文字数から除外される."""
        text = "行1\r行2"
        metrics = JITBeatExpander.calculate_metrics(text)
        assert metrics.char_count == len(text.replace("\r", ""))

    def test_sync_editor_content_with_beats(self):
        """エディタ本文とビートリストの同期結果を返す."""
        editor_text = "本文です。続きです。"
        beats = [
            {"beat_id": 1, "title": "ビート1"},
            {"beat_id": 2, "title": "ビート2"},
        ]
        result = JITBeatExpander.sync_editor_content_with_beats(editor_text, beats)
        assert result["is_synchronized"] is True
        assert "metrics" in result
        assert "updated_beats" in result
        updated = result["updated_beats"]
        assert len(updated) == 2
        for beat in updated:
            assert "current_chars" in beat
            assert "completed" in beat
            assert beat["beat_id"] in (1, 2)

    def test_sync_editor_content_with_empty_beats(self):
        """ビートリストが空でも同期結果を返す（total_beats=1 フォールバック）."""
        result = JITBeatExpander.sync_editor_content_with_beats("テキスト", [])
        assert result["is_synchronized"] is True
        assert result["updated_beats"] == []
        assert result["metrics"]["char_count"] == len("テキスト")

    def test_sync_editor_content_marks_completion(self):
        """文字数が十分あれば各ビートの completed フラグが立つ."""
        editor_text = "あ" * 100
        beats = [{"beat_id": 1}, {"beat_id": 2}]
        result = JITBeatExpander.sync_editor_content_with_beats(editor_text, beats)
        allocated = 100 // 2
        assert result["updated_beats"][0]["current_chars"] == allocated
        assert result["updated_beats"][0]["completed"] is True
        assert result["updated_beats"][1]["completed"] is True
