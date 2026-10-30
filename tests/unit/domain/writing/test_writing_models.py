"""Unit tests for writing domain models."""

from src.domain.writing.models import (
    WritingGenerationContext,
    clean_writing_response,
)


class TestCleanWritingResponse:
    """Tests for clean_writing_response."""

    def test_removes_thinking_blocks(self):
        """思考ログ (<thinking>...</thinking>) が除去される."""
        text = "本文<thinking>思考ログ</thinking>続き"
        assert clean_writing_response(text) == "本文続き"

    def test_strips_whitespace(self):
        """前後の空白が除去される."""
        assert clean_writing_response("  本文  ") == "本文"

    def test_unchanged_when_no_thinking(self):
        """思考ログがない場合は変更されない."""
        assert clean_writing_response("ただの本文") == "ただの本文"


class TestWritingGenerationContext:
    """Tests for WritingGenerationContext."""

    def test_build_sys_inst_default(self):
        """デフォルトでは空文字列を返す."""
        ctx = WritingGenerationContext()
        assert ctx.build_sys_inst() == ""

    def test_build_sys_inst_with_parts(self):
        """sys_inst / pov_instruction / feedback_patch が結合される."""
        ctx = WritingGenerationContext(
            sys_inst="system instruction",
            pov_instruction="pov instruction",
            feedback_patch="feedback patch",
        )
        result = ctx.build_sys_inst()
        assert "system instruction" in result
        assert "pov instruction" in result
        assert "🚨自己評価フィードバックパッチ" in result
        assert "feedback patch" in result

    def test_build_fw_prompt_default(self):
        """デフォルトでは空文字列を返す."""
        ctx = WritingGenerationContext()
        assert ctx.build_fw_prompt() == ""

    def test_build_fw_prompt_with_parts(self):
        """fw_prompt / pov_instruction / expanded_beats / suffix が結合される."""
        ctx = WritingGenerationContext(
            fw_prompt="fw prompt",
            pov_instruction="pov instruction",
            expanded_beats="beat 1",
        )
        result = ctx.build_fw_prompt(suffix="suffix")
        assert "fw prompt" in result
        assert "pov instruction" in result
        assert "📝 物理動作ビート分解" in result
        assert "beat 1" in result
        assert "suffix" in result
