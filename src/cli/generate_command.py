"""``autonovel generate`` — サーバー無しで小説を生成する CLI 実装。

以往はブラウザ（FastAPI + Huey）を介さない生成手段が無く、CLI には
``balance / export / init-db / check-env / plugins`` しか無かった。
ここでは既存の統合パイプライン（``AutoWorkflowPipeline`` /
``EasyModeWorkflow`` と同じ Step 構成）をそのままヘッドレスで実行する。

::

    autonovel generate --genre ファンタジー --keywords "...." --episodes 10
    autonovel generate --provider mock --episodes 2   # LLM 無しで配線を smoke test

本文は DB（``chapters`` テーブル）に永続化されるので、生成後は
``autonovel export --book-id <id>`` で本文・設定集・プロットを取り出せる。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

__all__ = ["cmd_generate", "add_generate_parser", "ConsoleReporter"]


class _ReporterState:
    """``reporter.state.should_stop()`` 互換の最小状態オブジェクト。

    ステップは ``reporter.state.should_stop()`` を無条件に呼ぶため、
    ``state`` が None を返すと AttributeError でパイプラインが落ちる。
    CLI は中断シグナルを拾えないので常に False を返す。
    """

    def should_stop(self) -> bool:
        return False


class ConsoleReporter:
    """パイプラインが必要とする進捗報告インターフェースの端末実装。"""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self._state = _ReporterState()
        # 日本語 Windows の既定コンソールは cp932 で、絵文字や「·」を出すと
        # UnicodeEncodeError でパイプライン自体が落ちる。UTF-8 に付け替える。
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (ValueError, OSError):  # pragma: no cover - 端末依存
                    pass

    def report(self, message: str, level: str = "info") -> None:
        if self.quiet:
            return
        prefix = {"info": "·", "warning": "!", "error": "x"}.get(level, "·")
        print(f"{prefix} {message}", flush=True)

    def update_progress(self, current: int, total: int, text: str = "", sub_text: str = "") -> None:
        if self.quiet or not text:
            return
        pct = int(current / total * 100) if total else 0
        suffix = f" — {sub_text}" if sub_text else ""
        print(f"[{pct:3d}%] {text}{suffix}", flush=True)

    @property
    def state(self) -> Any:
        return self._state


def _resolve_llm(args: argparse.Namespace) -> Any:
    """``get_llm_adapter`` で LLM アダプタを組み立てる。"""
    from src.services.llm.factory import get_llm_adapter

    return get_llm_adapter(
        provider=args.provider,
        api_key=args.api_key or None,
        model_name=args.model or None,
        base_url=args.base_url or None,
    )


def _ensure_schema() -> None:
    """``books`` テーブルが無ければマイグレーションを走らせる。"""
    from sqlalchemy import create_engine, inspect

    from src.backend.config import settings
    from src.backend.database.core import get_db_manager, init_db

    # DatabaseManager を先に実体化して、以降のリポジトリ参照と同一 URL になるようにする。
    get_db_manager()

    url = getattr(settings, "DATABASE_URL", None) or "sqlite:///storage/autonovel.db"
    # ``core.engine`` はプロキシオブジェクトなので inspect() できない。
    # 設定 URL から独立した read-only エンジンで存在確認する。
    probe = create_engine(url)
    try:
        if inspect(probe).has_table("books"):
            return
    finally:
        probe.dispose()

    # ``scripts.init_db.run_migrations`` はリポジトリ直下の ``autonovel.db`` を
    # 対象にしており、DATABASE_URL を差し替えた実行では別の DB に
    # migration を適用してしまう。ここでは DATABASE_URL を見る実装
    # （``database.core.init_db``）を使う。
    print("[generate] DB にテーブルが無いためマイグレーションを実行します...", flush=True)
    init_db()


def _build_engine(llm: Any) -> Any:
    """パイプラインが期望する engine を組み立てる。

    ``repo`` は旧 API（``repo.plot`` / ``repo.episode`` ...）を足した
    互換シェルで包む。``db`` は ``WorldBibleGenerator`` が
    ``UnitOfWork(self.repo.db)`` を開くに必要。
    """
    from src.backend.database.pipeline_repo import wrap_repo
    from src.backend.database.core import get_db_manager
    from src.backend.database.repository import DataRepositoryFacade
    from src.backend.orchestrator_engine_adapter import OrchestratorEngineAdapter

    db = get_db_manager()
    engine = OrchestratorEngineAdapter(
        repo=wrap_repo(DataRepositoryFacade(db)),
        db=db,
        llm=llm,
    )
    return engine


async def _run(args: argparse.Namespace) -> int:
    from src.services.auto_workflow_pipeline import create_easy_mode_pipeline
    from src.services.pipeline_param_mapper import map_easymode_kwargs_to_context
    from src.services.progress_reporter import ProgressReporterAdapter

    llm = _resolve_llm(args)
    engine = _build_engine(llm)

    ctx = map_easymode_kwargs_to_context(
        genre=args.genre,
        keywords=[k.strip() for k in (args.keywords or "").split(",") if k.strip()],
        protagonist_type=args.protagonist,
        target_episodes=args.episodes,
        words_per_episode=args.chars,
        enable_audit=args.audit,
        max_rewrites=args.max_rewrites,
        start_ep=args.start_ep,
        end_ep=args.end_ep,
        concept=args.concept or "",
        user_prompt=args.prompt or "",
        title=args.title or "",
    )

    pipeline = create_easy_mode_pipeline(
        genre=args.genre,
        target_episodes=args.episodes,
        enable_spice_guard=args.audit,
        max_rewrite_iterations=args.max_rewrites,
        target_audit_score=args.audit_score,
        enable_marketing=True,
    )

    reporter = ProgressReporterAdapter(ConsoleReporter(quiet=args.quiet), is_easy_mode=True)
    result = await pipeline.execute(ctx, engine, reporter)

    book_id = getattr(result, "book_id", None)
    title = getattr(result, "title", "") or ""
    print("")
    print(f"[generate] book_id={book_id}  title={title!r}")
    print(f"[generate] 総文字数={getattr(result, 'chars_count', 0)}  失敗話={getattr(result, 'failed_episodes', [])}")
    if args.audit and getattr(result, "average_audit_score", None):
        print(f"[generate] 平均監査スコア={result.average_audit_score}")

    if book_id is None:
        print("[generate] 企画段階で book_id が得られなかったため中断します。", file=sys.stderr)
        return 1

    _dump_chapters(book_id, args)
    return 0


def _dump_chapters(book_id: int, args: argparse.Namespace) -> None:
    """生成された各話的文字数（と必要なら本文）を表示する。"""
    from src.backend import database
    from src.backend.database.models import Chapter
    from sqlalchemy import select

    session = database.SessionLocal()
    try:
        rows = (
            session.execute(
                select(Chapter).where(Chapter.book_id == book_id).where(Chapter.branch_id == 1).order_by(Chapter.ep_num)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()

    if not rows:
        print("[generate] chapters テーブルに本文がありません。")
        return

    total = 0
    for row in rows:
        chars = len(row.content or "")
        total += chars
        print(f"  第{row.ep_num}話  {chars:>6}字  {row.title or ''}")
    print(f"[generate] {len(rows)}話 / 計{total}字")
    print(f"[generate] 取り出し: autonovel export --book-id {book_id} --format zip")

    if args.out_txt:
        from pathlib import Path

        path = Path(args.out_txt)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n\n".join(f"第{r.ep_num}話 {r.title or ''}\n\n{r.content or ''}" for r in rows)
        path.write_text(body, encoding="utf-8")
        print(f"[generate] 本文を {path} に書き出しました。")


def cmd_generate(args: argparse.Namespace) -> int:
    """ヘッドレスで小説を生成する。"""
    _ensure_schema()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n[generate] interrupted.", file=sys.stderr)
        return 130


def add_generate_parser(subparsers: Any) -> None:
    """``generate`` サブコマンドをパーサーに登録する。"""
    parser = subparsers.add_parser(
        "generate",
        help="generate a novel headlessly (no server required)",
        description=(
            "サーバー無しで統合パイプラインを実行し、小説を生成する。"
            "本文は DB に保存され、autonovel export で取り出せる。"
            "--provider mock は LLM を呼ばない配線の smoke test 用（固定の短い文章しか出ない）。"
        ),
    )
    parser.add_argument("--genre", default="ファンタジー", help="ジャンル（既定: ファンタジー）")
    parser.add_argument("--keywords", default="", help='キーワード（カンマ区切り 例: "ダンジョン, 転生"）')
    parser.add_argument("--protagonist", default="チート主人公", help="主人公タイプ（既定: チート主人公）")
    parser.add_argument("--episodes", type=int, default=10, help="生成する話数（既定: 10）")
    parser.add_argument("--chars", type=int, default=2000, help="1話あたりの目標文字数（既定: 2000）")
    parser.add_argument("--title", default="", help="タイトル（省略時は AI が決定）")
    parser.add_argument("--concept", default="", help="企画コンセプト")
    parser.add_argument("--prompt", default="", help="1行のプロンプト（kick-off）")
    parser.add_argument("--start-ep", type=int, default=1, help="開始話数（既定: 1）")
    parser.add_argument("--end-ep", type=int, default=None, help="終了話数（既定: target_eps）")

    parser.add_argument(
        "--provider",
        default=None,
        help="LLM プロバイダ（openai / gemini / claude / ollama / vllm / openrouter / mock）。"
        "既定は .env の LLM_PROVIDER。",
    )
    parser.add_argument("--model", default="", help="モデル名（既定はプロバイダの既定）")
    parser.add_argument("--api-key", default="", help="API キー（既定は .env）")
    parser.add_argument("--base-url", default="", help="OpenAI 互換エンドポイント（既定は .env）")

    parser.add_argument(
        "--audit",
        action="store_true",
        help="監査・リライト工程を有効にする（既定は無効）。有効にすると監査スコアが "
        "--audit-score 未満の話を書き直す。engine.auditor が未設定の場合は "
        "フォールバックスコア 85.0 で判定される点に注意",
    )
    parser.add_argument("--audit-score", type=float, default=85.0, help="目標監査スコア（既定: 85）")
    parser.add_argument("--max-rewrites", type=int, default=0, help="1話あたりのリライト上限（既定: 0）")

    parser.add_argument("--out-txt", default="", help="生成した本文をこのファイルにも書き出す")
    parser.add_argument("--quiet", action="store_true", help="進捗表示を抑制する")
    parser.set_defaults(func=cmd_generate)
