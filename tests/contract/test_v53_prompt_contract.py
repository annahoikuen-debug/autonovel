"""v5.3 / v6 プロンプト契約テスト（Step 28-30, 34）。

本テストは「レンダリングされたプロンプトが実パース可能であり、
必要な情報が消えていないこと」を機械的に固定化する。

fixed defects:
  - Step 28: `writing_metadata_instruction.j2` の JSON リテラルが
    `"action": "resolved または progressed または mentioned_only"` /
    `"word_count_estimate": 本文の推定文字数（整数）` となり、
    LLM がそのまま echo すると `WritingMetadata` 全体が `None` に化けていた。
  - Step 29: `final_writing_prompt.j2` の `{% if %}/{% elif %}` により
    契約伏線か背景伏線のどちらか一方しか描画されなかった。
  - Step 30: `compose_writing_prompt` が `foreshadowing_ctx` を渡さず、
    伏線IDの描画が dead-letter になっていた。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TEMPLATE_DIR = ROOT_DIR / "prompts" / "templates" / "narrative"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def _brace_delimited_json(rendered: str) -> dict:
    """レンダリング結果から最初の `{`〜最後の `}` を取り出して dict にする。"""
    start = rendered.index("{")
    end = rendered.rindex("}") + 1
    return json.loads(rendered[start:end])


CONTRACT_FORESHADOWINGS = [
    {
        "id": 7,
        "title": "聖剣の封印",
        "description": "古代遺跡で発見された封印された剣",
        "planted_episode": 1,
        "target_episode": 12,
        "scope": "long_term",
    }
]

BACKGROUND_FORESHADOWINGS = [
    {
        "id": 21,
        "title": "黒騎士の紋章",
        "description": "壁に掛けられた古い紋章の出所",
        "planted_episode": 2,
        "target_episode": 30,
        "scope": "short_term",
    }
]


class TestMetadataInstruction:
    """Step 28: メタデータ指示の JSON 妥当性。"""

    def test_metadata_instruction_is_valid_json(self) -> None:
        """契約伏線あり/なしの両方で、レンダリング結果が json.loads を通ること。"""
        tmpl = _env().get_template("writing_metadata_instruction.j2")

        for contract in ([], CONTRACT_FORESHADOWINGS):
            rendered = tmpl.render(episode_number=12, contract_foreshadowings=contract)
            data = _brace_delimited_json(rendered)  # 不正ならここで例外

            assert data["episode_number"] == 12
            assert isinstance(data["word_count_estimate"], int), (
                "word_count_estimate は整数リテラル（例）である必要がある"
            )
            assert isinstance(data["foreshadowings"], list)
            assert len(data["foreshadowings"]) == len(contract)
            for entry in data["foreshadowings"]:
                assert entry["action"] in {
                    "resolved",
                    "progressed",
                    "mentioned_only",
                }, f"action は実 enum 値を1つだけ出力すること: {entry['action']!r}"
                assert isinstance(entry["foreshadowing_id"], int)

    def test_echoed_metadata_parses(self) -> None:
        """LLM がそのまま echo したメタデータが `WritingMetadata` としてパースできること。"""
        from src.services.prose.novel_output_splitter import NovelOutputSplitter

        tmpl = _env().get_template("writing_metadata_instruction.j2")
        rendered = tmpl.render(
            episode_number=12, contract_foreshadowings=CONTRACT_FORESHADOWINGS
        )
        json_block = _brace_delimited_json(rendered)
        # LLM が少し値を変えたケース（action を progressed に、rationale を実際に）
        json_block["foreshadowings"][0]["action"] = "progressed"
        json_block["foreshadowings"][0]["rationale"] = "封印にヒビが入った"
        json_block["word_count_estimate"] = 2310

        raw = "本文のサンプル。\n\n[METADATA_JSON]\n" + json.dumps(
            json_block, ensure_ascii=False
        ) + "\n[/METADATA_JSON]"
        prose, metadata = NovelOutputSplitter.split_novel_output(raw)

        assert metadata is not None, "echo しただけではパースできない"
        assert metadata.episode_number == 12
        assert metadata.word_count_estimate == 2310
        assert len(metadata.foreshadowings) == 1
        assert metadata.foreshadowings[0].foreshadowing_id == 7
        assert metadata.foreshadowings[0].action == "progressed"
        assert "[METADATA_JSON]" not in prose

    def test_one_bad_entry_does_not_null_out_metadata(self) -> None:
        """1件不正なエントリがあっても WritingMetadata 全体が null にならないこと。"""
        from src.services.prose.novel_output_splitter import NovelOutputSplitter

        raw = (
            "本文。\n\n[METADATA_JSON]\n"
            + json.dumps(
                {
                    "episode_number": 5,
                    "foreshadowings": [
                        {
                            "foreshadowing_id": 1,
                            "action": "partially_resolved",  # enum 外
                            "rationale": "x",
                            "excerpt": "y",
                        },
                        {
                            "foreshadowing_id": 2,
                            "action": "resolved",
                            "rationale": "回収された",
                            "excerpt": "封印が解けた",
                        },
                    ],
                    "word_count_estimate": 1800,
                    "unresolved_notes": [],
                },
                ensure_ascii=False,
            )
            + "\n[/METADATA_JSON]"
        )
        _, metadata = NovelOutputSplitter.split_novel_output(raw)

        assert metadata is not None
        assert [r.foreshadowing_id for r in metadata.foreshadowings] == [2]


class TestForeshadowingContractRendering:
    """Step 29: 契約伏線と背景伏線の両方が描画されること。"""

    @pytest.mark.asyncio
    async def test_contract_and_background_both_render(self) -> None:
        from prompts.manager import PromptManager

        pm = PromptManager()
        prompt = await pm.build_final_writing_prompt(
            ep_num=12,
            plot_data={"detailed_blueprint": "简要プロット"},
            script_text="台本",
            target_word_count=2400,
            book_id=None,
            contract_foreshadowings=CONTRACT_FORESHADOWINGS,
            unresolved_foreshadowings=BACKGROUND_FORESHADOWINGS,
        )

        assert "【本話の絶対回収ミッション（契約伏線）】" in prompt
        assert "[伏線ID: 7]" in prompt
        assert "【背景・継続中の未回収伏線（留意事項）】" in prompt
        assert "[伏線ID: 21]" in prompt

    def test_background_block_alone_renders(self) -> None:
        """契約伏線がなくても背景ブロックは描画される（旧 `elif` の逆ecase）。"""
        tmpl = _env().get_template("foreshadowing_contract_instruction.j2")
        rendered = tmpl.render(
            contract_foreshadowings=[],
            background_foreshadowings=BACKGROUND_FORESHADOWINGS,
            background_truncation_note="",
        )
        assert "【背景・継続中の未回収伏線（留意事項）】" in rendered
        assert "[伏線ID: 21]" in rendered

    def test_background_is_capped_with_truncation_summary(self) -> None:
        """上限を超えた場合は「他N件あり（うち期限超過M件）」のサマリが出る。"""
        from prompts.manager import PromptManager

        unresolved = [
            {
                "id": 100 + i,
                "title": f"伏線{i}",
                "description": "d",
                "planted_episode": i,
                "target_episode": i + 5,
                "status": "planted",
            }
            for i in range(1, 31)
        ]
        shown, note = PromptManager._select_background_foreshadowings(
            unresolved_foreshadowings=unresolved,
            contract_foreshadowings=[],
            current_episode=3,
        )
        assert len(shown) == PromptManager.MAX_BACKGROUND_FORESHADOWINGS
        assert note.startswith("他10件あり（うち期限超過0件）")

        tmpl = _env().get_template("foreshadowing_contract_instruction.j2")
        rendered = tmpl.render(
            contract_foreshadowings=[],
            background_foreshadowings=shown,
            background_truncation_note=note,
        )
        assert "他10件あり" in rendered

    def test_contract_ids_are_excluded_from_background(self) -> None:
        from prompts.manager import PromptManager

        shown, note = PromptManager._select_background_foreshadowings(
            unresolved_foreshadowings=CONTRACT_FORESHADOWINGS + BACKGROUND_FORESHADOWINGS,
            contract_foreshadowings=CONTRACT_FORESHADOWINGS,
            current_episode=12,
        )
        assert [f["id"] for f in shown] == [21]
        assert note == ""


class TestPromptComposerForeshadowingWiring:
    """Step 30: `foreshadowing_ctx` が実プロンプトへ到達すること。"""

    @pytest.mark.asyncio
    async def test_foreshadowing_ids_appear_in_prompt(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from src.agents.prompt_composer import PromptComposer

        agent = MagicMock()
        agent.logger = MagicMock()
        agent.prompt_manager = MagicMock()
        agent.prompt_manager.build_final_writing_prompt = AsyncMock(
            side_effect=lambda **kwargs: kwargs["foreshadowing_context"]
        )

        composer = PromptComposer(agent)
        prompt = await composer.compose_writing_prompt(
            book_id=1,
            ep_num=12,
            context={
                "plot": {"detailed_blueprint": "x"},
                "foreshadowing_ctx": "【未回収伏線一覧】\n- **7** 聖剣の封印（第10話回収予定）",
                "contract_foreshadowings": CONTRACT_FORESHADOWINGS,
            },
        )

        assert "[伏線ID" not in prompt  # RAG ではなく ctx の生テキストを渡している
        assert "- **7**" in prompt
        assert "聖剣の封印" in prompt

    @pytest.mark.asyncio
    async def test_rag_is_used_only_as_fallback(self) -> None:
        """`foreshadowing_ctx` が空のときだけ RAG へフォールバックすること。"""
        from unittest.mock import AsyncMock, MagicMock

        from src.agents.prompt_composer import PromptComposer

        agent = MagicMock()
        agent.logger = MagicMock()
        agent.prompt_manager = MagicMock()
        agent.prompt_manager.build_final_writing_prompt = AsyncMock(
            side_effect=lambda **kwargs: kwargs["foreshadowing_context"]
        )
        retriever = MagicMock()
        retriever.retrieve_writing_context = MagicMock(return_value={"x": 1})
        retriever.format_context_for_prompt = MagicMock(return_value="RAG_CTX")
        agent.context_retriever = retriever

        composer = PromptComposer(agent)
        prompt = await composer.compose_writing_prompt(
            book_id=1, ep_num=12, context={"plot": {"detailed_blueprint": "x"}}
        )

        assert "RAG_CTX" in prompt
        retriever.retrieve_writing_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_scene_prompt_receives_contract_and_layers(self) -> None:
        """Step 30: シーンプロンプトにも契約伏線と3層記憶が入る。"""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from src.agents.prompt_composer import PromptComposer
        from src.domain.entities.scene import SceneRole

        agent = MagicMock()
        agent.logger = MagicMock()
        agent.prompt_manager = MagicMock()

        composer = PromptComposer(agent)
        scene = SimpleNamespace(
            role=SceneRole.INTRODUCTION,
            beats=["主人公が目覚める"],
            target_word_count=800,
            tension_start=20,
            tension_end=35,
        )
        prompt = await composer.compose_scene_prompt(
            book_id=1,
            ep_num=12,
            scene=scene,
            context={
                "plot": {"one_line_summary": "目覚め"},
                "contract_foreshadowings": CONTRACT_FORESHADOWINGS,
                "three_layer_context": {
                    "layer1_bible": {"text": "世界观設定"},
                    "layer2_summary": {"text": "第1話: 剣を発見"},
                    "layer3_previous": {"text": "直前の本文"},
                },
            },
        )

        assert "[伏線ID: 7]" in prompt
        assert "聖剣の封印" in prompt
        assert "Layer1" in prompt and "Layer2" in prompt and "Layer3" in prompt


class TestThreeLayerRendering:
    """3層記憶が最終プロンプトへ描画されること。"""

    @pytest.mark.asyncio
    async def test_three_layers_render(self) -> None:
        from prompts.manager import PromptManager

        pm = PromptManager()
        prompt = await pm.build_final_writing_prompt(
            ep_num=12,
            plot_data={"detailed_blueprint": "x"},
            script_text="台本",
            target_word_count=2400,
            book_id=None,
            three_layer_ctx=(
                "【Layer1: 世界観・キャラクター設定（不変）】\nL1\n"
                "【Layer2: 過去の確定事実タイムライン】\nL2\n"
                "【Layer3: 直前エピソードの原文】\nL3"
            ),
        )

        assert "【Layer1: 世界観・キャラクター設定（不変）】" in prompt
        assert "【Layer2: 過去の確定事実タイムライン】" in prompt
        assert "【Layer3: 直前エピソードの原文】" in prompt
        assert "L1" in prompt and "L2" in prompt and "L3" in prompt
