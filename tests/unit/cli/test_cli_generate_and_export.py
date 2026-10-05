"""CLI の `generate` / `export` サブコマンドと、その土台となる

- ``src.services.export_service.ExportService``
- ``src.backend.database.pipeline_repo.PipelineRepoCompat``
- ``src.backend.orchestrator_engine_adapter.PlannerAdapter``

の単体テスト。既存の ``tests/unit/cli/test_cli_*.py`` はモジュールを
``sys.modules`` に差し替えて引数検証だけを行うため、実物が動くことは
検証していない。ここでは fake リポジトリで実ファイルを書き出せるかを見る。
"""

from __future__ import annotations

import asyncio
import json
import types
import zipfile
from pathlib import Path

import pytest

from src.backend.database.pipeline_repo import wrap_repo
from src.backend.orchestrator_engine_adapter import (
    LLMJsonBridge,
    OrchestratorEngineAdapter,
    PlannerAdapter,
)
from src.cli.generate_command import ConsoleReporter, add_generate_parser, cmd_generate
from src.cli.main import build_parser, main
from src.services.export_service import ExportError, ExportService
from src.services.llm.mock_adapter import _MOCK_JSON_PAYLOAD


# --------------------------------------------------------------------- fake repo


class _FakeBook:
    def __init__(self, book_id: int = 7) -> None:
        self.id = book_id
        self.title = "テスト作品"
        self.genre = "ファンタジー"
        self.target_eps = 2


class _FakeChapter:
    def __init__(self, ep_num: int, title: str, content: str) -> None:
        self.ep_num = ep_num
        self.title = title
        self.content = content
        self.is_anchor = False


class _FakePlot:
    def __init__(self, ep_num: int) -> None:
        self.ep_num = ep_num
        self.title = f"第{ep_num}話 タイトル"
        self.one_line_summary = f"第{ep_num}話のあらすじ"
        self.summary = ""


class _FakeBible:
    settings = {"world": "魔法がonitor Blowのする世界"}


class _FakeCharacter:
    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role
        self.personality = "頑固"
        self.ability = "魔術"


class _FakeRepo:
    """ExportService が使う同期リポジトリ接口の最小実装。"""

    def __init__(self, book: _FakeBook | None = None) -> None:
        self._book = book or _FakeBook()

    def get_book(self, book_id: int):
        return self._book if self._book.id == book_id else None

    def get_all_non_anchor_chapters(self, book_id: int):
        return [_FakeChapter(1, "第1話", "一行目\n二行目"), _FakeChapter(2, "第2話", "三行目")]

    def get_all_characters(self, book_id: int):
        return [_FakeCharacter("アルト", "主人公")]

    def get_latest_bible(self, book_id: int):
        return _FakeBible()

    def get_all_plots(self, book_id: int, branch_id: int = 1):
        return [_FakePlot(1), _FakePlot(2)]


# ----------------------------------------------------------------- ExportService


class TestExportService:
    def test_unknown_format_rejected(self, tmp_path: Path):
        svc = ExportService(repo=_FakeRepo(), output_dir=tmp_path)
        with pytest.raises(ExportError, match="未対応"):
            svc.export(7, "pdf")

    def test_missing_book_raises(self, tmp_path: Path):
        svc = ExportService(repo=_FakeRepo(book=None), output_dir=tmp_path)
        with pytest.raises(ExportError, match="作品が見つかりません"):
            svc.export(999, "zip")

    def test_zip_contains_documented_files(self, tmp_path: Path):
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "zip")
        assert result["status"] == "done"
        assert result["episodes"] == 2
        path = Path(result["path"])
        assert path.exists() and path.stat().st_size == result["bytes"]

        with zipfile.ZipFile(path) as z:
            assert z.namelist() == [
                "01_本文.txt",
                "02_キャラクター・世界観設定集.txt",
                "03_プロット概要.txt",
                "04_データダンプ.json",
            ]
            body = z.read("01_本文.txt").decode("utf-8-sig")
            assert "第1話 第1話" in body
            assert "一行目\r\n二行目" in body  # Windows 向け CRLF

            dump = json.loads(z.read("04_データダンプ.json").decode("utf-8"))
            assert dump["title"] == "テスト作品"
            assert [c["ep_num"] for c in dump["chapters"]] == [1, 2]
            assert dump["characters"][0]["name"] == "アルト"

    def test_txt_has_bom_and_all_chapters(self, tmp_path: Path):
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "txt")
        raw = Path(result["path"]).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        assert "総話数: 2" in text
        assert "三行目" in text

    def test_epub_is_valid_ocf(self, tmp_path: Path):
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "epub")
        with zipfile.ZipFile(result["path"]) as z:
            names = z.namelist()
            # OCF 仕様: mimype は先頭かつ非圧縮（stored）
            assert names[0] == "mimetype"
            assert z.infolist()[0].compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype") == b"application/epub+zip"
            assert "META-INF/container.xml" in names
            assert "OEBPS/content.opf" in names
            assert "OEBPS/chapter0001.xhtml" in names
            assert "OEBPS/chapter0002.xhtml" in names
            chapter = z.read("OEBPS/chapter0001.xhtml").decode("utf-8")
            assert "<p>一行目</p>" in chapter

    def test_out_dir_overrides_constructor(self, tmp_path: Path):
        other = tmp_path / "nested" / "deeper"
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "txt", output_dir=other)
        assert Path(result["path"]).parent == other

    def test_out_path_is_used_verbatim(self, tmp_path: Path):
        target = tmp_path / "my" / "novel"
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "txt", out_path=target)
        assert Path(result["path"]) == target.with_suffix(".txt")
        assert Path(result["path"]).exists()

    def test_out_path_suffix_follows_format(self, tmp_path: Path):
        target = tmp_path / "novel.zip"
        result = ExportService(repo=_FakeRepo(), output_dir=tmp_path).export(7, "epub", out_path=target)
        assert Path(result["path"]) == tmp_path / "novel.epub"


class TestCmdExport:
    def test_export_wires_service(self, tmp_path: Path, monkeypatch, capsys):
        calls = {}

        class FakeService:
            def __init__(self, *a, **kw):
                calls["init"] = True

            def export(self, book_id, fmt, output_dir=None, out_path=None):
                calls["args"] = (book_id, fmt, output_dir, out_path)
                return {"status": "done"}

        module = types.ModuleType("src.services.export_service")
        module.ExportService = FakeService
        monkeypatch.setitem(__import__("sys").modules, "src.services.export_service", module)

        parser = build_parser()
        args = parser.parse_args(["export", "-b", "3", "-f", "txt", "--out-dir", str(tmp_path)])
        assert args.func(args) == 0
        assert calls["args"] == (3, "txt", str(tmp_path), None)
        assert "[export] completed" in capsys.readouterr().out

    def test_export_out_flag_becomes_out_path(self, tmp_path: Path, monkeypatch):
        calls = {}

        class FakeService:
            def __init__(self, *a, **kw):
                pass

            def export(self, book_id, fmt, output_dir=None, out_path=None):
                calls["out_path"] = out_path
                return {"status": "done"}

        module = types.ModuleType("src.services.export_service")
        module.ExportService = FakeService
        monkeypatch.setitem(__import__("sys").modules, "src.services.export_service", module)

        target = tmp_path / "book.epub"
        args = build_parser().parse_args(["export", "-b", "9", "--out", str(target)])
        assert args.func(args) == 0
        assert calls["out_path"] == str(target)


# ------------------------------------------------------------- PipelineRepoCompat


class _InnerRepo:
    """DataRepositoryFacade 相当の「メソッド名を引くだけの」委譲."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return f"{name}-result"

    def __getattr__(self, name):
        async def wrapper(*args, **kwargs):
            return await self._record(name, *args, **kwargs)

        return wrapper


class TestPipelineRepoCompat:
    def test_wrap_is_idempotent(self):
        inner = _InnerRepo()
        once = wrap_repo(inner)
        assert wrap_repo(once) is once
        assert wrap_repo(None) is None

    def test_unknown_attrs_delegate_to_inner(self):
        inner = _InnerRepo()
        compat = wrap_repo(inner)
        assert asyncio.run(compat.get_book(7)) == "get_book-result"
        assert inner.calls[-1][0] == "get_book"

    def test_branch_id_defaults_to_one_and_pins_book(self):
        inner = _InnerRepo()
        compat = wrap_repo(inner)
        asyncio.run(compat.episode.get_by_book_and_number(7, 3))
        name, args, kwargs = inner.calls[-1]
        assert name == "get_chapter"
        assert args == (1, 3)
        assert kwargs == {"book_id": 7}

    def test_plot_namespace_passes_book_id(self):
        inner = _InnerRepo()
        compat = wrap_repo(inner)
        asyncio.run(compat.plot.get_all_plots(1, book_id=7))
        name, args, kwargs = inner.calls[-1]
        assert name == "get_all_plots"
        assert kwargs["branch_id"] == 1
        assert kwargs["book_id"] == 7

    def test_update_content_signature_translated(self):
        inner = _InnerRepo()
        compat = wrap_repo(inner)
        asyncio.run(compat.episode.update_content(7, 2, "本文"))
        name, args, kwargs = inner.calls[-1]
        assert name == "update_chapter_content"
        assert args == (1, 2, "本文")
        assert kwargs == {"book_id": 7}

    def test_bible_namespace(self):
        inner = _InnerRepo()
        compat = wrap_repo(inner)
        assert asyncio.run(compat.bible.get_by_book_id(7)) == "get_latest_bible-result"


# ---------------------------------------------------------------- LLMJsonBridge


class _JsonAdapter:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.seen: list[dict] = []

    async def generate_text(
        self, prompt, system_prompt=None, max_tokens=2000, temperature=0.7, response_format=None, **kwargs
    ):
        self.seen.append({"prompt": prompt, "response_format": response_format})
        return self.payload


class TestLLMJsonBridge:
    def test_parses_plain_json(self):
        bridge = LLMJsonBridge(_JsonAdapter('{"a": 1}'))
        result = asyncio.run(bridge.generate_json("m", "prompt"))
        assert result.success is True
        assert result.get("success") is True
        assert result.get("metadata") == {"a": 1}

    def test_strips_markdown_fence(self):
        bridge = LLMJsonBridge(_JsonAdapter('```json\n{"a": 2}\n```'))
        result = asyncio.run(bridge.generate_json("m", "prompt"))
        assert result.get("metadata") == {"a": 2}

    def test_extracts_json_from_surrounding_text(self):
        bridge = LLMJsonBridge(_JsonAdapter('以下です。\n{"a": 3}\n以上。'))
        assert asyncio.run(bridge.generate_json("m", "p")).get("metadata") == {"a": 3}

    def test_invalid_json_is_reported_not_raised(self):
        bridge = LLMJsonBridge(_JsonAdapter("JSON ではない"))
        result = asyncio.run(bridge.generate_json("m", "p"))
        assert result.success is False
        assert result.get("success") is False

    def test_adapter_exception_is_reported(self):
        class Boom(_JsonAdapter):
            async def generate_text(self, *a, **kw):
                raise RuntimeError("HTTP 401")

        result = asyncio.run(LLMJsonBridge(Boom("")).generate_json("m", "p"))
        assert result.success is False
        assert "401" in (result.error_message or "")

    def test_purpose_style_call_is_supported(self):
        """PlanningAgent は ``generate_json(purpose=..., prompt=...)`` で呼ぶ."""
        bridge = LLMJsonBridge(_JsonAdapter('{"a": 4}'))
        result = asyncio.run(bridge.generate_json(purpose="planning", prompt="プロンプト"))
        assert result.get("metadata") == {"a": 4}

    def test_json_object_response_format_is_requested(self):
        adapter = _JsonAdapter('{"a": 5}')
        asyncio.run(LLMJsonBridge(adapter).generate_json("m", "p"))
        assert adapter.seen[0]["response_format"] == {"type": "json_object"}


# ------------------------------------------------------------------- PlannerAdapter


class TestPlannerAdapter:
    def test_planner_works_without_orchestrator(self):
        """以前は Orchestrator 未設定で必ず RuntimeError になっていた."""
        engine = OrchestratorEngineAdapter(repo=object(), db=object(), llm=_JsonAdapter("{}"))
        assert engine.orchestrator is None
        planner = engine.planner
        assert isinstance(planner, PlannerAdapter)
        # 遅延生成されるが、 Orchestrator が無くてもインスタンス化できる。
        assert engine.planner is planner

    def test_planner_delegates_to_bible_generator(self):
        adapter = OrchestratorEngineAdapter(repo=object(), db=object(), llm=_JsonAdapter("{}"))
        planner = adapter.planner

        async def fake_create(**kwargs):
            return 42, types.SimpleNamespace(title="生成タイトル")

        # bible_generator は遅延構築される read-only プロパティなので、
        # キャッシュ済みの内部スロットを差し替える。
        planner._bible_generator = types.SimpleNamespace(create_hegemony_plan=fake_create)
        book_id, bible = asyncio.run(planner.create_hegemony_plan(genre="x"))
        assert book_id == 42
        assert bible.title == "生成タイトル"

    def test_plan_auditor_defaults_to_none(self):
        engine = OrchestratorEngineAdapter(repo=object(), db=object(), llm=_JsonAdapter("{}"))
        assert engine.planner.plan_auditor is None


# ------------------------------------------------------------------- mock payload


class TestMockLLMPayload:
    @pytest.mark.parametrize(
        "model_path",
        [
            "src.models:UltraFastWorldBible",
            "src.models:UltraFastPlotBatch",
            "src.models.graph_schemas:GraphExtractionResult",
        ],
    )
    def test_payload_validates_against_consumers(self, model_path: str):
        """モック JSON は全ての主要消費側のスキーマを通る必要がある.

        近年 ``WorldBibleGenerator`` が ``UltraFastWorldBible`` を要求するため、
        エンティティ抽出用の JSON しか返せなくなると
        ``autonovel generate --provider mock`` が企画段階で落ちる。
        """
        import importlib

        module_name, attr = model_path.split(":")
        model = getattr(importlib.import_module(module_name), attr)
        model.model_validate(_MOCK_JSON_PAYLOAD)


# ----------------------------------------------------------------- generate CLI


class TestGenerateCli:
    def test_subcommand_registered(self):
        args = build_parser().parse_args(["generate", "--episodes", "3"])
        assert hasattr(args, "func")
        assert args.episodes == 3
        assert args.chars == 2000

    def test_audit_is_opt_in(self):
        """監査リライト既定は無効。有効だと LLM 無駄撃ちする（engine.auditor 未設時は常に 85 点）。"""
        args = build_parser().parse_args(["generate"])
        assert args.audit is False
        assert args.audit_score == 85.0
        assert args.max_rewrites == 0

        assert build_parser().parse_args(["generate", "--audit"]).audit is True

    def test_add_generate_parser_is_idempotent_safe(self):
        import argparse

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        add_generate_parser(sub)
        assert "generate" in sub.choices

    def test_reporter_state_supports_should_stop(self):
        reporter = ConsoleReporter(quiet=True)
        assert reporter.state.should_stop() is False

    def test_reporter_report_is_quiet_when_asked(self, capsys):
        reporter = ConsoleReporter(quiet=True)
        reporter.report("無音", "error")
        reporter.update_progress(1, 2, "進捗", "補足")
        assert capsys.readouterr().out == ""

    def test_unknown_provider_exits_nonzero(self, monkeypatch):
        """未設定キーだと get_llm_adapter が RuntimeError を投げる."""
        monkeypatch.setattr("src.services.llm.factory.get_llm_adapter", _raise_config_error)
        args = build_parser().parse_args(["generate", "--provider", "gemini"])
        with pytest.raises(RuntimeError):
            cmd_generate(args)

    def test_main_generate_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["generate", "--help"])
        assert exc.value.code == 0


def _raise_config_error(**kwargs):
    raise RuntimeError("GEMINI_API_KEY が未設定です。")
