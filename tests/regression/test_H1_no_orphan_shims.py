"""import 元がゼロのシムが新たに増えないことの archangel。

``src/services/writing_services.py``（複数形）と ``src/services/writing_service.py``（単数形）は
どちらも ``src.domain.writing`` への再エクスポートシムで、import 元が 0 件だった（R2 で削除済み）。

残る既知の orphan は R2 のファイル所有表の外にあるため、削除せず
「理由 + TODO(H1-N)」付きで明示する（PLAN_H1 §9）。
"""
from __future__ import annotations

import ast
import glob
import os

SHIM_DIR = "src/services"

# ファイル名を除外するもの（構造的にシムではない）。
NEVER_ORPHAN = {"__init__"}

# 「import 元が無いのに残している」既知の orphan（キーは拡張子なしのモジュール名）。
# TODO(H1-N) の理由 必须。
KNOWN_ORPHANS: dict[str, str] = {
    "ncs_calibration": (
        "NarrativeCoherenceScorer。import 元 0 件だが R2 のファイル所有表の"
        "対象外のため削除しない。TODO(H1-8): 使うか消すかを設計側で決定"
    ),
    "data_loader": (
        "DataLoader（JSON 設定のローダ）。import 元 0 件だが R2 のファイル所有表の"
        "対象外のため削除しない。TODO(H1-8): rule 外部化の導入可否を設計側で決定"
    ),
    "age_client": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "audit_aggregator": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "audit_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "auto_workflow_pipeline": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "bible_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "blind_review": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "book_score_mapping": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "book_score_mapping": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "book_score_models": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "book_score_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "cadence_reformatter": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "chunk_ingestion": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "conflict_report_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "cost_analytics": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "cost_analytics": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "cost_budget_guard": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "data_loader": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "default_plot_expander": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "embedding_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "episode_context": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "episode_writer": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "erotic_afterglow_evaluator": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "erotic_density_controller": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "erotic_diversity_score": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "experiment_allocator": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "extraction_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "foreshadowing_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "graph_pipeline": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "hook_diagnoser": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "hybrid_retriever": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "image_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "llm_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "llm_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "marketing": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "next_beats_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "pdca_cycle": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "pipeline_base": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "quality_scorer": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "query_reformulator": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "rag_prefetch_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "rag_service": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "reflective_rag": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "reranker": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "rrf_fusion": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "semantic_cache": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "sparse_retriever": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "style_distiller": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
    "text_chunker": (
        '後方互換 shim（案B/C で新パスへ移設）。外部利用者の旧 import 経路維持のためリポジトリ内は新パスを直接使い shim 自体は orphan になる。削除は docs/SHIM_REMOVAL_PLAN.md の Phase R3 に従う。TODO(H1-9): 当該 shim の旧パス参照数がゼロになったリリースで削除'
    ),
}

SCAN_ROOTS = ("src", "tests", "scripts", "config")


def _imported_module_names() -> set[str]:
    names: set[str] = set()
    for root in SCAN_ROOTS:
        for p in glob.glob(f"{root}/**/*.py", recursive=True):
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module)
    return names


def _find_orphans(imported: set[str], files: list[str], is_package_dir) -> list[str]:
    orphans: list[str] = []
    for p in sorted(files):
        base = os.path.splitext(os.path.basename(p))[0]
        if base in NEVER_ORPHAN:
            continue
        dotted = f"src.services.{base}"
        if dotted in imported or base in KNOWN_ORPHANS:
            continue
        # 同名パッケージ（ディレクトリ）が存在する場合はシムではない。
        if is_package_dir(base):
            continue
        orphans.append(p)
    return orphans


def test_no_new_orphan_shim_in_services():
    files = glob.glob(f"{SHIM_DIR}/*.py")
    orphans = _find_orphans(
        _imported_module_names(),
        files,
        lambda base: os.path.isdir(os.path.join(SHIM_DIR, base)),
    )
    assert not orphans, (
        f"import 元がゼロのシムがある: {orphans}\n"
        " 削除するか、import 元を追加するか、KNOWN_ORPHANS に理由付きで列挙すること。"
    )


def test_detector_flags_a_synthetic_orphan():
    """archangel 自身が検出力を持つことの証明（P4: 検出器をメタ検証する）。"""
    files = [
        f"{SHIM_DIR}/kept.py",
        f"{SHIM_DIR}/orphan.py",
        f"{SHIM_DIR}/__init__.py",
        f"{SHIM_DIR}/pkg_dir.py",
    ]
    found = _find_orphans(
        {"src.services.kept", "src.services.pkg_dir"},
        files,
        lambda base: base == "pkg_dir",
    )
    assert found == [f"{SHIM_DIR}/orphan.py"], found


def test_known_orphans_have_reasons_and_numbers():
    for name, reason in KNOWN_ORPHANS.items():
        assert reason.strip(), f"{name} の KNOWN_ORPHANS エントリに理由が無い"
        assert "TODO(H1-" in reason, (
            f"{name} の KNOWN_ORPHANS エントリに TODO(H1-N) の番号が無い（§9: 数値外れ禁止）"
        )


def test_known_orphans_still_exist():
    """KNOWN_ORPHANS が削除済みだと archangel が空振りになるので検出する。"""
    present = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(f"{SHIM_DIR}/*.py")}
    stale = sorted(n for n in KNOWN_ORPHANS if n not in present)
    assert not stale, f"KNOWN_ORPHANS に載ったファイルが存在しない: {stale}"
