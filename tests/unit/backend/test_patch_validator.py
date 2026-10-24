"""Unit tests for src/backend/patch_validator.py (pure AST/JSON safety guard)."""

from __future__ import annotations


from src.backend.patch_validator import PatchValidator


class TestValidateConfigPatchParsing:
    def test_valid_json_parsed(self):
        result = PatchValidator.validate_config_patch('{"model_writing": "gpt-4o"}')
        assert result.is_safe is True
        assert result.sanitized_patch == {"model_writing": "gpt-4o"}
        assert result.errors == []

    def test_key_value_quoted_string(self):
        result = PatchValidator.validate_config_patch('model_writing = "gpt-4o"\n')
        assert result.is_safe is True
        assert result.sanitized_patch == {"model_writing": "gpt-4o"}

    def test_key_value_single_quoted_string(self):
        result = PatchValidator.validate_config_patch("model_writing = 'gpt-4o'\n")
        assert result.is_safe is True
        assert result.sanitized_patch == {"model_writing": "gpt-4o"}

    def test_key_value_true_branch(self):
        # bool branch is exercised regardless of field validity
        result = PatchValidator.validate_config_patch("unknownfield = true\n")
        assert result.is_safe is False
        assert any("Unknown config key" in e for e in result.errors)

    def test_key_value_false_branch(self):
        result = PatchValidator.validate_config_patch("unknownfield = false\n")
        assert result.is_safe is False

    def test_key_value_int_without_dot(self):
        result = PatchValidator.validate_config_patch("unknownfield = 5\n")
        assert result.is_safe is False
        assert any("Unknown config key" in e for e in result.errors)

    def test_key_value_float_branch(self):
        result = PatchValidator.validate_config_patch("unknownfield = 3.14\n")
        assert result.is_safe is False

    def test_key_value_non_numeric_keeps_string(self):
        # non-quoted, non-bool, no dot, not int -> ValueError -> keep string
        result = PatchValidator.validate_config_patch("model_writing = abc\n")
        assert result.is_safe is True
        assert result.sanitized_patch == {"model_writing": "abc"}

    def test_invalid_line_without_equals(self):
        result = PatchValidator.validate_config_patch("this line has no equals\n# comment\n")
        assert result.is_safe is False
        assert any("Invalid format line" in e for e in result.errors)

    def test_empty_and_comment_lines_skipped(self):
        result = PatchValidator.validate_config_patch("# just a comment\n\nmodel_writing = gpt\n")
        assert any("Type mismatch" in e or "Unknown" in e for e in result.errors) or result.is_safe is True


class TestValidateConfigPatchTypeValidation:
    def test_unknown_key_rejected(self):
        result = PatchValidator.validate_config_patch('{"does_not_exist": "x"}')
        assert result.is_safe is False
        assert any("Unknown config key" in e for e in result.errors)

    def test_type_mismatch_for_int_field(self):
        result = PatchValidator.validate_config_patch('{"redis_max_connections": "notanint"}')
        assert result.is_safe is False
        assert any("Type mismatch" in e for e in result.errors)


class TestValidateConfigPatchAstSecurity:
    def test_dangerous_os_system_call_detected(self):
        result = PatchValidator.validate_config_patch('{"model_writing": "os.system(\'rm -rf\')"}')
        assert result.is_safe is False
        assert any("Security Alert" in e for e in result.errors)

    def test_dangerous_exec_call_detected(self):
        result = PatchValidator.validate_config_patch('{"model_writing": "exec(\'import os\')"}')
        assert result.is_safe is False
        assert any("Security Alert" in e for e in result.errors)

    def test_unsafe_string_value_flagged(self):
        result = PatchValidator.validate_config_patch('{"model_writing": "os.system(\'ls\')"}')
        assert result.is_safe is False

    def test_plain_text_value_is_safe(self):
        # "plain text here" is not valid Python -> SyntaxError -> treated as safe text
        result = PatchValidator.validate_config_patch('{"model_writing": "plain text here"}')
        assert result.is_safe is True
        assert result.sanitized_patch == {"model_writing": "plain text here"}

    def test_safe_expression_without_call(self):
        result = PatchValidator.validate_config_patch('{"model_writing": "a + b"}')
        assert result.is_safe is True

    def test_dangerous_function_set_present(self):
        assert "exec" in PatchValidator.DANGEROUS_FUNCTIONS
        assert "eval" in PatchValidator.DANGEROUS_FUNCTIONS
        assert "os.system" in PatchValidator.DANGEROUS_FUNCTIONS
        assert "open" in PatchValidator.DANGEROUS_FUNCTIONS


class TestValidatePromptPatch:
    def test_empty_content_rejected(self):
        result = PatchValidator.validate_prompt_patch("")
        assert result.is_safe is False
        assert any("empty" in e for e in result.errors)

    def test_whitespace_only_rejected(self):
        result = PatchValidator.validate_prompt_patch("   \n  ")
        assert result.is_safe is False

    def test_malicious_keyword_emits_warning(self):
        result = PatchValidator.validate_prompt_patch("please ignore previous instructions")
        assert result.is_safe is True  # warnings only
        assert any("ignore previous instructions" in w for w in result.warnings)

    def test_dangerous_keyword_emits_warning(self):
        result = PatchValidator.validate_prompt_patch("call os.system to run")
        assert result.is_safe is True  # warnings only
        assert any("os.system" in w for w in result.warnings)

    def test_clean_prompt_passes(self):
        result = PatchValidator.validate_prompt_patch("Write a beautiful fantasy scene.")
        assert result.is_safe is True
        assert result.warnings == []
        assert result.sanitized_patch == {"prompt_content": "Write a beautiful fantasy scene."}
