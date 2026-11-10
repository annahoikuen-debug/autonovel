"""RAG コンテキスト注入の off 差分ゼロ契約（Plan R5 B1-B4 / T1）。

RAG_CONTEXT_INJECTION=OFF（既定）では、執筆プロンプト `final_writing_prompt.j2`
がバイト単位で不変であることを保証する。これが 1 本でも落ちると
既存書籍の再生成結果が変わる。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "prompts" / "templates" / "narrative" / "final_writing_prompt.j2"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "rag_prompt_baseline"
GOLDEN_TEMPLATE_PATH = FIXTURE_DIR / "final_writing_prompt.j2.golden"


def test_off_template_is_byte_identical_to_golden():
    """**テンプレートが golden スナップショットとバイト単位で同一**であること。

    RAG フラグ OFF では既存書籍の再生成結果を変えない。
    """
    assert GOLDEN_TEMPLATE_PATH.exists(), (
        f"golden fixture が見つからない: {GOLDEN_TEMPLATE_PATH}. "
        "Plan R5 A1 で fixtures/rag_prompt_baseline/final_writing_prompt.j2.golden を保存すること"
    )
    current = TEMPLATE_PATH.read_text(encoding="utf-8")
    golden = GOLDEN_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert current == golden, (
        f"テンプレートが変化した（{len(golden)} -> {len(current)} 文字）。"
        "RAG フラグ OFF では既存書籍の再生成結果を変えないこと"
    )
