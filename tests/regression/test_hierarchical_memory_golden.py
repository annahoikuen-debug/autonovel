"""プロンプト黄金スナップショットテスト (PLAN_M1 Step 2).

`PromptManager.build_final_writing_prompt` の出力が、フラグ全 off 時
(`pinned_head` / `pinned_tail` 未指定または空) で現行とバイト同一である
ことを golden ファイルと比較する。

以降のフェーズで `pinned_*` ブロックをテンプレートに追加しても、off 時は
この golden と完全に一致しなければならない（後方互換の絶対条件）。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from jinja2 import Environment, FileSystemLoader
import pytest

from prompts.manager import PromptManager

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_FILE = GOLDEN_DIR / "writing_prompt_baseline.txt"


def _build_manager() -> PromptManager:
    """Jinja2 環境を直接注入した PromptManager を構築。"""
    return PromptManager(
        jinja_env=Environment(loader=FileSystemLoader("prompts"))
    )


async def _build_prompt(manager: PromptManager) -> str:
    """最小フィクスチャで執筆プロンプトを構築。

    `pinned_head` / `pinned_tail` は渡さない（デフォルト空文字）。
    `book_id=None` で感情コンテキスト生成（Redis/ベクトルストア）をスキップ。
    """
    return await manager.build_final_writing_prompt(
        ep_num=1,
        plot_data={
            "scenes": [],
            "current_chain_phase": "Hate",
            "detailed_blueprint": "",
        },
        script_text="",
        target_word_count=2000,
        book_id=None,
        char_static_ctx="テストキャラクター設定",
        char_dynamic_ctx="テスト動的状態",
        prev_ctx="テスト前文脈",
        pov_character_name="テスト主人公",
        dialogue_profiles={},
        density_level="Standard",
        style_tag=None,
        foreshadowing_context="",
        contract_foreshadowings=[],
        unresolved_foreshadowings=[],
        emotional_context="",
        rag_context_block="",
        quota_inst="",
        show_tell_inst="",
        forbidden_inst="",
        hook_inst="",
        assertion_inst="",
        blueprint="",
        tone_inst="",
    )


@pytest.mark.asyncio
async def test_writing_prompt_matches_golden():
    """flag off 時のプロンプト出力が golden と一致する。"""
    manager = _build_manager()

    # `_build_forbidden_section` はランダムに禁忌語を選択するため、
    # golden 比較の安定性のため固定値を返すようにモック化する。
    manager._build_forbidden_section = AsyncMock(
        return_value="【🚨禁忌語・強制置換🚨】\nテスト用固定禁忌語指示\n"
    )

    prompt = await _build_prompt(manager)

    # Golden ファイルが存在しない場合は初回作成（CI ではコミット済み前提）。
    if not GOLDEN_FILE.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        GOLDEN_FILE.write_text(prompt, encoding="utf-8")
        pytest.skip(
            "Golden ファイルを初期作成しました。次回実行で比較を行います。"
        )

    expected = GOLDEN_FILE.read_text(encoding="utf-8")
    assert prompt == expected, (
        "プロンプト出力が golden と不一致です。flag off 時は現行出力とバイト同一である必要があります。"
    )
