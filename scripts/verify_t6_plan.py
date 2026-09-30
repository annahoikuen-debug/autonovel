"""T6 是正計画 18 ステップの完了条件を機械的に確認する検証スクリプト（読み取り専用）。"""

from __future__ import annotations

import ast
import pathlib
import sys
import tomllib

sys.stdout.reconfigure(encoding="utf-8")

RESULTS: list[tuple[str, bool]] = []


def check(name: str, cond: bool) -> None:
    RESULTS.append((name, bool(cond)))


def read(rel: str) -> str:
    return pathlib.Path(rel).read_text(encoding="utf-8")


# --- Step 1: finalize の単一実行点 -----------------------------------------
_src = read("src/agents/writing/episode_writer.py")
_tree = ast.parse(_src)
_cls = [n for n in ast.walk(_tree) if isinstance(n, ast.ClassDef) and n.name == "EpisodeWriter"][0]
_fns = {
    n.name: n
    for n in _cls.body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
}
# コメントは ast.unparse に残らないため、**呼び出しそのもの**を数える
_callers = [
    name
    for name, fn in _fns.items()
    if "_post_episode_finalize" in ast.unparse(fn) and name != "_post_episode_finalize"
]
check("S1 呼び出し元が run() のみ", _callers == ["run"])
check(
    "S1 write_beat_to_scene に呼び出しなし",
    "_post_episode_finalize" not in ast.unparse(_fns["write_beat_to_scene"]),
)

# --- Step 2: デッドガード 0 件 --------------------------------------------
# コメント中の文字列は判定に影響しないため、AST で実コードを数える
def _count_dead_guards(path: str) -> int:
    count = 0
    for node in ast.walk(ast.parse(read(path))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "hasattr"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "logger"
        ):
            count += 1
    return count


_guards = sum(
    _count_dead_guards(p)
    for p in ("src/agents/context_builder_agent.py", "src/agents/writing/episode_writer.py")
)
check("S2 hasattr(self,'logger') 0件（AST）", _guards == 0)
check("S2 context_builder に logger 定義", "logger = logging.getLogger(__name__)" in read("src/agents/context_builder_agent.py"))

# --- Step 3: _resolve_session 単一定義 ------------------------------------
_defs = [
    str(p)
    for p in pathlib.Path("src").rglob("*.py")
    if "def _resolve_session" in p.read_text(encoding="utf-8")
]
check("S3 _resolve_session 定義1箇所", len(_defs) == 1)

# --- Step 4: IllustrationAgent チェーン -----------------------------------
check("S4 _make_execute_node 定義", "def _make_execute_node" in read("src/agents/orchestrator.py"))
check("S4 generation_tasks が使用", "_make_execute_node" in read("src/backend/tasks/generation_tasks.py"))

# --- Step 5: 未知モデルの可視化 -------------------------------------------
_co = read("src/config/cost_optimization.py")
check("S5 resolve_pricing / UnknownModelPricingError", "def resolve_pricing" in _co and "class UnknownModelPricingError" in _co)
check("S5 token_tracker が利用", "resolve_pricing" in read("src/services/token_tracker.py"))

# --- Step 6: コスト CLI ---------------------------------------------------
check("S6 CLI 存在", pathlib.Path("scripts/report_episode_cost.py").exists())

# --- Step 7: LocalPolisher の LLM 注入 -----------------------------------
_lp = read("src/generation/local_polish.py")
_aa = read("src/agents/audit_agent.py")
check("S7 polish_with_llm 存在", "def polish_with_llm" in _lp)
check("S7 audit_agent が注入 LLM を渡す", "polish_with_llm(" in _aa)
check("S7 try_local_patch が async", "async def try_local_patch" in _aa)

# --- Step 8: update_chapter_content --------------------------------------
_ag = read("src/agents/writing/agent.py")
check("S8 3引数呼び出しが2箇所", _ag.count("update_chapter_content(branch_id, ep_num, rewritten_text)") == 2)
check("S8 chapter.id 呼び出し 0件", "update_chapter_content(chapter.id" not in _ag)

# --- Step 9: version ------------------------------------------------------
_v = tomllib.loads(read("pyproject.toml"))["project"]["version"]
check("S9 pyproject 6.0.0", _v == "6.0.0")
check("S9 CLI / backend 一致", "6.0.0" in read("src/cli/main.py") and "6.0.0" in read("src/backend/__init__.py"))
check("S9 frontend / docker 一致", "6.0.0" in read("frontend/package.json") and "6.0.0" in read("docker-compose.prod.yml"))
check("S9 README バッジ", "version-6.0.0" in read("README.md"))

# --- Step 10: lint -------------------------------------------------------
check("S10 pyproject に残存の記録", "T6 Step 10 の残存" in read("pyproject.toml"))

# --- Step 11: 隔離とログ --------------------------------------------------
check("S11 ダイジェスト隔離+警告", "ダイジェスト永続化でエラー" in _src)

# --- Step 12/13/14: 計測 --------------------------------------------------
check("S12 再執筆率を実測比較", "_measure_regeneration_ratio" in read("tests/contract/test_v6_audit_gate_thresholds.py"))
check("S13 実測関数", "def measure_real_audit_calls" in read("tests/perf/test_v6_llm_call_budget.py"))
check("S14 レイテンシ実測", "test_audit_latency_measured_parallel_vs_serial" in read("tests/perf/test_v6_audit_latency_and_regen.py"))

# --- Step 15: 効果測定表 -------------------------------------------------
_st = read("docs/STATUS.md")
check("S15 効果測定節", "v6 効果測定" in _st)
check("S15 未計測明記", "未計測" in _st)

# --- Step 16-18: 回帰・docs ----------------------------------------------
check("S18 CHANGELOG T6 記載", "PLAN_T6_REMEDIATION_18STEPS" in read("CHANGELOG.md"))
check("S18 README に二重実行の記載", "test_episode_finalize_called_once.py" in read("README.md"))

for name, passed in RESULTS:
    print(f"{'OK  ' if passed else 'NG  '}{name}")

failed = [n for n, p in RESULTS if not p]
print()
print(f"完了 {len(RESULTS) - len(failed)} / {len(RESULTS)}")
if failed:
    print("未達:")
    for n in failed:
        print(f"  - {n}")
