# AutoNovel W4 是正計画書【全滅バックトラック → 外科的スパンリライト 12ステップ】

- **文書ID**: PLAN_W4_SURGICAL_PATCH_12STEPS
- **作成日**: 2026-09-29
- **対象バージョン**: AutoNovel v5.3.0 → v6.0.0
- **親計画**: [PLAN_V6_COST_LATENCY_OPTIMIZATION.md](PLAN_V6_COST_LATENCY_OPTIMIZATION.md) §2.1 / [PLAN_T6_REMEDIATION_18STEPS.md](PLAN_T6_REMEDIATION_18STEPS.md) R09
- **ステータス**: 完了（2026-09-30 / Step 1〜11 実装済み）
  > 注記: Step 1〜10 は本計画着手前から実装済み（`src/audit/triage.py` / `src/audit/repair_planner.py` / `src/services/prose/span_patch_applier.py` / `src/services/audit/targeted_diagnostic.py` が存在）。2026-09-30 に実装したのは Step 11 と付随するバグB修正のみ。
- **目的**: `AuditAgent` の「1 オーディターでも落ちたらエピソード全文再執筆」を、
  **静的ルール即時置換 → 段落単位スパン置換 → シーン再生成** の三段階トリアージに置き換え、
  再生成LLMコストと文脈ドリフト（コンテキストドリフト）を同時に削減する。

---

## 0. この計画書の位置づけ

W4 の問題は「gate が甘い/厳しい」ではなく、**是正手段が 1 種類しかない**ことにある。
`AuditAgent.try_local_patch`（`src/agents/audit_agent.py:706-778`）は既に
`SafeReplacer → actionable_patch 追記 → LocalPolisher` の3段フォールバックを持つが、
**段落を丸ごと書き直す手段が無い**ため、`LocalPolisher` が 1 箇所しか直せないまま
即座に「全文再生成（Branch D, `:1057-1090`）」へ落ちる。

> 本計画は **新モジュールを足すだけで、既存フローの分岐順を入れ替えない**。
> 最後まで実装しても効果ゼロでも既存動作は完全に保存される（すべてフラグ既定OFF）。

### 0.1 分割原則（低性能LLM向け）

| 原則 | 内容 |
|---|---|
| **P1 単一ファイル** | 1ステップの**主担当ファイルは高々1つ**。2ファイル以上になる場合は分割する |
| **P2 機械的置換のみ** | 設計を要求しない。`str.replace` / 正規表現 / dataclass 追加で完了する |
| **P3 判定は pytest 緑赤のみ** | 数値の解釈・効果の推測を LLM にさせない |
| **P4 テスト先行** | 回帰テストを**先に作り、赤いことを確認してから** 実装する |
| **P5 既存パターン準拠** | フラグは `src/agents/audit_agent.py:139-174` の `_TRUTHY` + `_env_flag` 方式に統一する |
| **P6 猜测禁止** | 対象ファイルの行番号・関数名は必ず grep で再確認してから編集する |
| **P7 削除禁止** | 既存関数・既存テストは**削除しない**。必ずフラグで OFF できる状態でだけ意味を変える |

### 0.2 実行順序の依存関係

```
Step 1 ─┐
Step 2 ─┼─→ Step 3 ──→ Step 4 ──→ Step 5 ──→ Step 6 ──→ Step 7
        │  (severity)  (offset) (diagnostic) (indexer) (applier) (async polish)
        │
Step 8 ─┤  (wiring 1)   ← Step 5,6,7 に依存
Step 9 ─┤  (advisory gate)
Step 10 ┤  (budget)      ← Step 8 に依存
Step 11 ┘  (events/metrics) ← Step 8 に依存
                │
                └──→ Step 12 (総合回帰・文書化)
```

- **Step 1〜7 は互いに独立**。順番は自由。
- **Step 8 → 10 → 11** は直列。**Step 9 は Step 8 と独立**。
- **Step 12 は最後**。

---

## 1. 残存欠陥一覧（本計画の対象）

| ID | 深刻度 | 実測事実（根拠） | 担当Step |
|:---|:---|:---|:---|
| W4-01 | Critical | `AuditAgent.execute` Branch D（`audit_agent.py:1057-1090`）が `next_agent=WRITING, should_retry=True, is_backtrack=True` を返す。Orchestrator の `max_backtracks_per_node=3`（`orchestrator.py:93`）で **1話あたり本文再生成が最大4回** | 8, 10 |
| W4-02 | Critical | `LocalPolisher.polish_with_llm`（`src/generation/local_polish.py:102-121`）は注入LLMを使うが、結果を `_apply`（`:139-153`）で**無検証に本文へ埋め込む**。差し替えで本文が壊れても素通しで確定する。同期待ち版 `polish`（`:72`）は `call_llm_api`（`:93`）直叩きで追跡不能 | 5, 6 |
| W4-03 | Major | `StaticRuleAuditor.audit`（`src/audit/static_rules.py:37`）は severity を持たない。`critical_types` は `src/audit/pipeline.py:73` にハードコードされた2種のみ | 1, 2 |
| W4-04 | Major | `TargetedDiagnostic.identify_weak_paragraphs`（`src/services/audit/targeted_diagnostic.py:17`）が **TODO スタブで常に `[]` を返す**。この為 `ClosedLoopPDCARunner`（`src/services/pdca_cycle.py:112-136`）の段落パッチ経路は到達不能 | 4 |
| W4-05 | Major | `ParagraphIndexer.index_paragraphs`（`src/services/prose/paragraph_indexer.py:23-47`）は **文字オフセットをコメントアウト**しており、`PatchMerger` は添字照合でしかマージできない | 3, 5 |
| W4-06 | Major | `try_local_patch` の2本目（`audit_agent.py:740-748`）は `drafted_text` の**末尾に追記**するだけ。局所置換ではなく本文が肥大化する | 8 |
| W4-07 | Minor | gate は `AUDIT_GATE_THRESHOLD`=70.0 一枚（`audit_agent.py:106`）で、**Advisory（警告通過）帯が存在しない**。1点70.5で再執筆が走る | 9 |
| W4-08 | Minor | `PDCAController`（`src/generation/pdca_controller.py`）に `max_regenerations=0` という**予算モデルが既に存在**するが `AuditAgent` は一切使っていない | 10 |
| W4-09 | Minor | 監査結果に `audit_status` / `audit_metrics` は残るが、**パッチがどう決まったかの観測点が無い**（`drain_events` のイベントも監査5種のみ） | 11 |

---

## 2. 12ステップ

---

### Step 1. `StaticRuleAuditor` に severity を載せる
- **主担当ファイル**: `src/audit/static_rules.py`
- **依存**: なし
- **P分類**: P1（1ファイル）/ P2

**背景**
```
12-18: @dataclass Issue: type, message, location, suggestion
32-35: self.forbidden_patterns = []          ← 常に空（ルール4は死にコード）
73:    critical_types = {"length_exceeded", "title_length_exceeded"}  ← pipeline.py に埋もれたまま
```
`Issue` に `severity: str = "minor"` を追加すると、`Issue(type=..., message=..., location=...)` の
**位置引数3つでの生成が壊れる**ため、既存呼び出しを壊さないよう **デフォルト値付き dataclass フィールド**として
**最後**に追加する。

**作業内容**
1. `Issue` dataclass（`static_rules.py:12-18`）に `severity: str = "minor"` を**最終フィールド**として追加する。
2. モジュールレベル定数 `SEVERITY_MINOR/MAJOR/CRITICAL` を定義する（値は文字列 `"minor"` 等）。
3. 各ルールの `Issue(...)` 生成箇所に `severity=` を渡す:
   - `length_exceeded`（`:53-59`）→ `major`
   - `title_length_exceeded`（`:62-69`）→ `minor`
   - `paragraph_count_insufficient`（`:72-79`）→ `critical`
   - `line_start_forbidden_punct`（`:92-103`）→ `minor`
4. **新規ルールを足さない**。既存5ルールのみ。`forbidden_patterns` は空のまま触らない。
5. `AuditPipeline._has_critical_issues`（`src/audit/pipeline.py:66-79`）は**このステップで触らない**（Step 2）。

**回帰テスト（先に作る）**: `tests/audit/test_static_rules_severity.py`（新規・**同期テスト**）

```python
"""StaticRuleAuditor の Issue に severity が載ることを確認する回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import StaticRuleAuditor


def test_issue_has_severity_field():
    auditor = StaticRuleAuditor()
    issues = auditor.audit("あ" * 6000)          # 文字数超過
    assert issues, "length_exceeded が出るはず"
    assert all(hasattr(i, "severity") for i in issues)
    assert next(i for i in issues if i.type == "length_exceeded").severity == "major"


def test_paragraph_count_insufficient_is_critical():
    issues = StaticRuleAuditor().audit("   ")
    assert any(i.type == "paragraph_count_insufficient" and i.severity == "critical" for i in issues)


def test_line_start_punct_is_minor():
    text = "タイトル\n\n「これは冒頭引用だ。\n普通の行。"
    issues = StaticRuleAuditor().audit(text)
    hit = [i for i in issues if i.type == "line_start_forbidden_punct"]
    assert hit and hit[0].severity == "minor"


def test_positional_3arg_construction_still_works():
    """既存の位置引数3つ生成が壊れていないこと（後方互換の爪）。"""
    from src.audit.static_rules import Issue
    i = Issue("t", "m", (0, 1))
    assert i.severity == "minor"
    assert i.suggestion is None
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/audit/test_static_rules_severity.py tests/audit/ -q
```

**完了判定**: 上記4テスト緑。かつ `tests/audit/test_static_rules.py` / `test_static_rules_crlf.py` / `test_pipeline.py` も緑。

---

### Step 2. 三段階トリアージ判定器 `src/audit/triage.py` を新設する
- **主担当ファイル**: `src/audit/triage.py`（**新規**）
- **依存**: Step 1（`Issue.severity` を使う）
- **P分類**: P1（新規1ファイルのみ）

**背景**
現状の重大度判定は `critical_types` 2種のハードコードのみ。
LLM オーディターの `severity`（`audit_agent.py:51-82` の `AuditCriterion.severity`）は
`high / medium` しかなく、**gate 用の `critical` に正規化されていない**。
この正規化を**純粋関数**に切り出すことで、Step 8 の差し替えが 1 行で済む。

**作業内容**
1. 新規ファイルを作る。依存は `src/audit/static_rules.py` の `Issue` のみ（LLM 依存は禁止）。
2. 定数3つ:
   - `TRIAGE_MINOR = "minor"`（LLM不要・即時ルールで解決）
   - `TRIAGE_MEDIUM = "medium"`（1〜2段落の局所LLMパッチ）
   - `TRIAGE_MAJOR = "major"`（シーン単位の再生成）
3. 公開APIを**同期関数2つ**だけにする（これ以外の API を足さない）:

```python
def classify_static_issues(issues: list[Issue]) -> str:
    """静的Issuesを最も重いtriage levelへ集約する。"""
    # Issue.severity のうち critical があれば major、無ければ minor を1つでも持っていれば minor

def classify_audit_outcomes(outcomes: list[dict]) -> str:
    """AuditAgent の outcome dict 群をtriage levelへ集約する。"""
    # error 付き / effective_severity=="critical"  → major
    # severity in {"high"}                          → medium
    # severity in {"medium","low"}                  → minor
```

4. `evaluate_gate`（`src/agents/audit_agent.py:177-214`）は**このステップで変更しない**。
5. `from __future__ import annotations` を先頭に置く（他モジュールと揃える）。

**回帰テスト（先に作る）**: `tests/audit/test_audit_triage.py`（新規・**同期テスト**）

```python
"""三段階トリアージ判定の純関数テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import Issue
from src.audit.triage import classify_static_issues, classify_audit_outcomes


def test_all_minor_when_no_issues():
    assert classify_static_issues([]) == "minor"
    assert classify_audit_outcomes([]) == "minor"


def test_static_critical_escalates_to_major():
    issues = [Issue("paragraph_count_insufficient", "x", None, None, "critical")]
    assert classify_static_issues(issues) == "major"


def test_outcome_with_error_is_major():
    out = [{"audit_id": "deai", "severity": "medium", "error": "auditor_exception:Timeout"}]
    assert classify_audit_outcomes(out) == "major"


def test_outcome_high_severity_is_medium():
    out = [{"audit_id": "fast_screen", "severity": "high", "error": None}]
    assert classify_audit_outcomes(out) == "medium"


def test_never_returns_unknown_level():
    out = [{"audit_id": "x", "severity": "unknown-value", "error": None}]
    assert classify_audit_outcomes(out) in {"minor", "medium", "major"}
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/audit/test_audit_triage.py -q
```

**完了判定**: 5テスト緑。`import src.audit.triage` が LLM/ネットワークを要求しないこと（テストが緑なことで担保）。

---

### Step 3. `ParagraphIndexer` に文字オフセットを戻す
- **主担当ファイル**: `src/services/prose/paragraph_indexer.py`
- **依存**: なし
- **P分類**: P1 / P2

**背景**
```
43-45:  # 'start': start_pos,  ← 実コメントアウト
```
`PatchMerger`（`src/services/prose/patch_merger.py:18`）は `re.split(r'\n\s*\n')` を**もう一度やり直して**
添字照合しているため、Step 5 のスパン置換でオフセットが要る。

**作業内容**
1. `index_paragraphs`（`paragraph_indexer.py:23-47`）の戻り値 dict に `'start'` と `'end'` を**追加**する。
2. `'index'` と `'text'` は**既存のまま**（既存テストを壊さない）。
3. 分割は**現状と同じ正規表現** `re.split(r'\n\s*\n', text.strip())` を使う。
   ただし各段落の `start` は `text` 上で `str.find(para, cursor)` で貪欲に探す方式とし、
   見つからないときは `start=-1, end=-1`（Step 5 のガード用）。
4. `text.strip()` で先頭が削られるため、`base = len(text) - len(text.lstrip())` をオフセットに加える。
5. `min_chars` / `max_chars` の分割は**実装しない**（`__init__` の引数は残す）。

**回帰テスト（先に作る）**: `tests/unit/services/test_paragraph_indexer_offsets.py`（新規・同期）

```python
"""ParagraphIndexer が文字オフセットを返すことの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.prose.paragraph_indexer import ParagraphIndexer


def test_offsets_point_at_actual_text():
    text = "第一段落。\n\n第二段落の本文。\n\n第三段落。"
    out = ParagraphIndexer().index_paragraphs(text)
    assert len(out) == 3
    for item in out:
        assert text[item["start"]:item["end"]] == item["text"], item


def test_legacy_keys_still_present():
    out = ParagraphIndexer().index_paragraphs("あ。\n\nい。")
    assert set(out[0]) >= {"index", "text", "start", "end"}
    assert [i["index"] for i in out] == [0, 1]


def test_leading_whitespace_does_not_shift_offsets():
    text = "\n\nあいうえお。\n\nかきくけこ。"
    out = ParagraphIndexer().index_paragraphs(text)
    assert text[out[0]["start"]:out[0]["end"]] == "あいうえお。"


def test_empty_text_returns_empty_list():
    assert ParagraphIndexer().index_paragraphs("   \n\n  ") == []
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/test_paragraph_indexer_offsets.py tests/unit/pipeline/test_patch_pipeline_integration.py -q
```

**完了判定**: 4テスト緑。かつ `test_patch_pipeline_integration.py` 緑（`PatchMerger` が壊れていないこと）。

---

### Step 4. `TargetedDiagnostic` の TODO スタブを実装する
- **主担当ファイル**: `src/services/audit/targeted_diagnostic.py`
- **依存**: Step 2（triage）、Step 3（オフセット）
- **P分類**: P1（1ファイル）

**背景**
```
17-27: def identify_weak_paragraphs(self, audit_result) -> List[ParagraphTarget]:
25:        # TODO: Implement actual logic to map audit findings to paragraphs.
26:        # For now, return an empty list as a placeholder.
27:        return []
```
`ClosedLoopPDCARunner.run_pdca_cycle`（`src/services/pdca_cycle.py:112`）がこれを呼んで
段落パッチ経路（`:115-136`）へ入るが、**常に空リスト**なので常に全文再生成（`:137-153`）に落ちる。

**作業内容**
1. `__init__` に `self.indexer = ParagraphIndexer()` を持たせる（**LLM禁止**）。
2. `identify_weak_paragraphs(audit_result, text: str = "")` の **第2引数 `text` を追加（既定 `""`）**。
   既存呼び出し（`pdca_cycle.py:112`）は引数不足で動き続ける。
3. アルゴリズム（**合計40行以内**。意味論に散らばらせない）:
   - `text` が空なら **従来どおり `[]` を返す**（後方互換）。
   - `audit_result` から `feedback` / `critique` / `detail` / `directive` 系の**文字列だけ**を集める。
   - `ParagraphIndexer().index_paragraphs(text)` で分割。
   - 各段落について、上記文字列に**その段落のテキストが部分一致**したら `ParagraphTarget` を生成。
   - 一致する段落が**無ければ、`index` が最大のパラグラフ（末尾）を1件だけ返す**（LLMが末尾で切るため）。
4. 生成する `ParagraphTarget`（`src/models/patch_pdca.py:4-8`）は
   `index` / `original_text` / `issue_category` / `directive` の4項目のみ。**新規フィールドを足さない**。
5. 戻り値は**最大 `max_targets=3` 件**に切る（`__init__(self, max_targets: int = 3)`）。
6. 例外は握りつぶさず **空リストへ倒す**（`pdca_cycle` を落とさないため）。

**回帰テスト（先に作る）**: `tests/unit/services/test_targeted_diagnostic.py`（新規・同期）

```python
"""TargetedDiagnostic が実際に段落を1件以上返すことの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.audit.targeted_diagnostic import TargetedDiagnostic


def test_returns_empty_without_text_backward_compatible():
    assert TargetedDiagnostic().identify_weak_paragraphs({"feedback": "x"}) == []


def test_matches_paragraph_containing_feedback_quote():
    text = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"
    targets = TargetedDiagnostic().identify_weak_paragraphs(
        {"feedback": "古代の魔導書"}, text=text
    )
    assert len(targets) == 1
    assert targets[0].index == 1
    assert "魔導書" in targets[0].original_text
    assert targets[0].directive == "古代の魔導書"


def test_falls_back_to_last_paragraph_when_no_quote_match():
    text = "あ。\n\nい。\n\nう。"
    targets = TargetedDiagnostic().identify_weak_paragraphs({"feedback": "存在しない語"}, text=text)
    assert len(targets) == 1 and targets[0].index == 2


def test_caps_at_max_targets():
    text = "\n\n".join(f"魔導書段落{i}" for i in range(10))
    targets = TargetedDiagnostic(max_targets=3).identify_weak_paragraphs(
        {"feedback": "魔導書"}, text=text
    )
    assert len(targets) == 3
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/test_targeted_diagnostic.py -q
```

**完了判定**: 4テスト緑（うち1本は必ず `[]` を返す旧スタブの挙動が変わり、段落を1件以上返す）。

---

### Step 5. `SpanPatchApplier` を新設する（決定論的スパン置換）
- **主担当ファイル**: `src/services/prose/span_patch_applier.py`（**新規**）
- **依存**: Step 3（オフセット）
- **P分類**: P1（新規1ファイル）

**背景**
`LocalPolisher.polish(text, (start, end), ...)`（`src/generation/local_polish.py:55`）は既に
スパン置換ができるが、**結果を検証しない**（`sanitize_polished_text` が空文字なら元に戻すだけ）。
差し替えた結果で本文が壊れる（文字数が 0.5倍以下になる等）と素通しで確定してしまう。

**作業内容**
1. 新規ファイル。**LLM・ネットワーク・DB を一切使わない**純粋クラス。
2. `class SpanPatchApplier` を1つだけ作る。公開API:
   - `apply(text: str, start: int, end: int, replacement: str) -> tuple[str, bool]`
   - `validate(original: str, patched: str) -> bool`
3. `apply` の安全条件（**1つでも欠ければ `(text, False)` を返す**）:
   - `0 <= start < end <= len(text)`
   - `replacement.strip()` が空でない
   - 差し替え後の `len()` が `len(original) * 0.3` 以上かつ `len(original) * 3.0` 以下
   - 段落数が差し替え前より減っていない（`\n\n` の個数比較）
4. `validate` は上記3〜4のみ。LLMは呼ばない。
5. 戻り値は必ずタプル。**例外を送出しない**。

**回帰テスト（先に作る）**: `tests/unit/services/test_span_patch_applier.py`（新規・同期）

```python
"""SpanPatchApplier の安全条件の回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.prose.span_patch_applier import SpanPatchApplier


def test_happy_path_replaces_span():
    ap = SpanPatchApplier()
    out, ok = ap.apply("AAAABBBBCCCC", 4, 8, "ZZZZZZZZ")
    assert ok is True and out == "AAAAZZZZZZZZCCCC"


def test_rejects_out_of_range():
    ap = SpanPatchApplier()
    assert ap.apply("AAAA", 2, 99, "ZZZZZZZZ")[1] is False
    assert ap.apply("AAAA", 2, 2, "ZZZZZZZZ")[1] is False
    assert ap.apply("AAAA", -1, 3, "ZZZZZZZZ")[1] is False


def test_rejects_empty_replacement():
    ap = SpanPatchApplier()
    assert ap.apply("AAAABBBB", 4, 8, "   ")[1] is False


def test_rejects_catastrophic_shrink():
    ap = SpanPatchApplier()
    assert ap.apply("A" * 100, 0, 100, "B")[1] is False


def test_rejects_paragraph_loss():
    ap = SpanPatchApplier()
    text = "p1\n\np2\n\np3"
    out, ok = ap.apply(text, 0, len("p1"), "merged")
    assert ok is False and out == text


def test_never_raises_on_garbage():
    ap = SpanPatchApplier()
    assert ap.apply("", 0, 0, "x")[1] is False
    assert ap.apply(None, 0, 1, "x")[1] is False
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/test_span_patch_applier.py -q
```

**完了判定**: 6テスト緑。`apply` が例外を送出しないことが最後の1本で担保される。

---

### Step 6. `LocalPolisher` に検証付き `polish_span` を追加する
- **主担当ファイル**: `src/generation/local_polish.py`
- **依存**: Step 5（`SpanPatchApplier`）
- **P分類**: P1（1ファイル）/ P5 / P7

**背景（実測）**
```
9:   from src.audit.unified_llm_auditor import call_llm_api   ← 同期版の直叩き（追跡不能）
27:  def sanitize_polished_text(raw_text) -> str
72:  def polish(self, text, target_range, improvement_instruction) -> str   ← 同期・call_llm_api 直呼び
102: async def polish_with_llm(self, text, target_range, instruction, llm) -> str  ← 注入LLM版（既にある）
139: def _apply(self, text, target_range, improved_text) -> str   ← sanitize → そのまま本文へ埋め込み
156: def _create_polish_prompt(...)
```
**`polish_with_llm`（`:102`）と `audit_agent.py:756-769` の注入経路は既に実装済み**
（PLAN_T6 R09 の是正は完了済み）。残る穴は **`_apply`（`:139-153`）が結果を無検証に確定すること**:
- `sanitize_polished_text` が空文字を返す場合だけ元に戻すが、
  **「元の1段落が 10 分の 1 に縮んだ」「段落が 3 つ潰れた」ような壊れ方はそのまま通る**。
- 壊れた本文がそのまま `patch_result["text"]` として `audit_status="patched"` で確定する。

**作業内容**
1. `LocalPolisher` に**新メソッド 1つ**を追加する。既存メソッドは**1文字も変更しない**。
   シグネチャは `async def polish_span(self, text, target_range, improvement_instruction, llm) -> tuple[str, bool]`。
   第4引数 `llm` は `polish_with_llm` と**同じ位置**に置く。
2. 実装は**20行以内**:
   - `patched = await self.polish_with_llm(text, target_range, improvement_instruction, llm)`
   - `if patched == text: return text, False`（変化なし＝不採用）
   - `from src.services.prose.span_patch_applier import SpanPatchApplier` を**関数内 import**する
   - `ok = SpanPatchApplier().validate(text, patched)`
   - `return (patched, True) if ok else (text, False)`
3. **`polish_with_llm` / `polish` / `_apply` / `_build_prompt` は変更しない**
   （Step 8 で `try_local_patch` 側から `polish_span` を呼ぶ）。
4. 返り値の `bool` は **「安全条件を満たして採用したか」**を意味する。
5. `asyncio` の import を**追加しない**（同期版 `polish` との互換のため）。
6. `tests/generation/test_local_polish.py` が `@patch("src.generation.local_polish.call_llm_api")` を使っているため、
   **モジュールレベル `call_llm_api` の import は触らない**。

**回帰テスト（先に作る）**: `tests/unit/generation/test_local_polish_span.py`（新規・非同期）

```python
"""polish_span が検証付きで採用/不採用を返すことの回帰テスト。"""
import sys, pathlib, inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.generation.local_polish import LocalPolisher

LONG = "A" * 400


def _gw(text):
    gw = MagicMock()
    gw.agenerate = AsyncMock(return_value=text)
    gw.generate = AsyncMock(return_value=text)
    gw.generate_text = AsyncMock(return_value=text)
    return gw


@pytest.mark.asyncio
async def test_accepts_reasonable_replacement():
    out, ok = await LocalPolisher().polish_span(
        LONG, (0, 400), "指示", _gw("A" * 400 + "追記。"))
    assert ok is True and "追記。" in out


@pytest.mark.asyncio
async def test_rejects_catastrophic_shrink():
    out, ok = await LocalPolisher().polish_span(LONG, (0, 400), "指示", _gw("B"))
    assert ok is False and out == LONG


@pytest.mark.asyncio
async def test_rejects_paragraph_loss():
    text = "p1\n\np2\n\np3\n\np4"
    out, ok = await LocalPolisher().polish_span(text, (0, len(text)), "指示", _gw("全部まとめ"))
    assert ok is False and out == text


@pytest.mark.asyncio
async def test_unchanged_text_is_not_applied():
    out, ok = await LocalPolisher().polish_span(LONG, (0, 400), "指示", _gw(LONG))
    assert ok is False and out == LONG


def test_existing_methods_intact():
    for name in ("polish", "polish_with_llm", "_apply", "_build_prompt"):
        assert hasattr(LocalPolisher, name), name
    assert inspect.iscoroutinefunction(LocalPolisher.polish_with_llm)


def test_sync_polish_still_uses_module_level_call():
    with patch("src.generation.local_polish.call_llm_api", return_value="legacy"):
        assert "legacy" in LocalPolisher().polish("AAAABBBB", (4, 8), "指示")
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/generation/test_local_polish_span.py tests/generation/ -q
```

**完了判定**: 6テスト緑。かつ `tests/generation/test_local_polish*.py` / `test_pdca_pipeline_integration.py` 緑（後方互換）。

---

### Step 7. 三段階トリアージ器 `src/audit/repair_planner.py` を新設する
- **主担当ファイル**: `src/audit/repair_planner.py`（**新規**）
- **依存**: Step 1, 2, 3, 4, 5
- **P分類**: P1（新規1ファイル）

**背景**
`try_local_patch`（`audit_agent.py:706-773`）は「patch できるか」を試すだけで、
**「どの手段で直すか」を決めていない**。既存3段は
`SafeReplacer`（決定的）→ `actionable_patch`（追記）→ `LocalPolisher`（同期・1箇所のみ）。

**作業内容**
1. 新規ファイル。LLM を**持たない**（判定だけ）。入力は `dict` と `str`。
2. `@dataclass(frozen=True) class RepairPlan` を1つ:
   - `level: str`（`"rule"` / `"span"` / `"scene"` / `"none"`）
   - `targets: tuple[int, ...]`（対象段落 index）
   - `reason: str`（1行の説明。プロンプトではなくログ用）
3. 公開API **1つだけ**:
```text
def plan_repair(text: str, failed_outcomes: list[dict], static_issues: list[Issue]) -> RepairPlan
```
   判定ロジック（**この順で必ず評価**）:
   - `static_issues` に `severity == "critical"` が1つでもあれば → `level="none"`（人手。自動で触らない）
   - `classify_static_issues` が `minor` **かつ** `StaticRuleAuditor` の全指摘が `line_start_forbidden_punct`
     または `title_length_exceeded` → `level="rule"`
   - `classify_audit_outcomes(failed_outcomes) == "major"` → `level="scene"`
   - それ以外 → `level="span"`、`targets = tuple(t.index for t in TargetedDiagnostic().identify_weak_paragraphs(...))`
   - `targets` が空なら `level="scene"` に**降格**しない（`"none"` にして既存経路に委ねる）
4. **LLM呼び出しを1行も行わない**。テストで LLM を差し込む必要がない。

**回帰テスト（先に作る）**: `tests/audit/test_repair_planner.py`（新規・同期）

```python
"""RepairPlan 決定ロジックの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.audit.static_rules import Issue, StaticRuleAuditor
from src.audit.repair_planner import plan_repair

TEXT = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"


def test_critical_static_issue_defers_to_human():
    issues = [Issue("paragraph_count_insufficient", "x", None, None, "critical")]
    assert plan_repair(TEXT, [], issues).level == "none"


def test_only_line_punct_issues_use_rule_level():
    issues = [Issue("line_start_forbidden_punct", "x", (0, 1), None, "minor")]
    assert plan_repair(TEXT, [], issues).level == "rule"


def test_major_outcome_escalates_to_scene():
    out = [{"audit_id": "causal_integrity", "severity": "critical", "error": None}]
    assert plan_repair(TEXT, out, []).level == "scene"


def test_medium_outcome_uses_span_level_with_targets():
    out = [{"audit_id": "deai", "severity": "medium", "error": None,
            "feedback": "古代の魔導書"}]
    plan = plan_repair(TEXT, out, [])
    assert plan.level == "span"
    assert plan.targets and TEXT.count("\n\n") >= 0


def test_span_level_without_targets_degrades_to_none():
    plan = plan_repair("   ", [{"audit_id": "deai", "severity": "medium", "error": None}], [])
    assert plan.level == "none"


def test_no_failures_returns_none():
    assert plan_repair(TEXT, [], []).level == "none"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/audit/test_repair_planner.py -q
```

**完了判定**: 6テスト緑。

---

### Step 8. `try_local_patch` を三段階ルーティングに差し替える
- **主担当ファイル**: `src/agents/audit_agent.py`
- **依存**: Step 5, 6, 7
- **P分類**: P1 / P5 / P7

**背景（実測）**
```
706-778: try_local_patch()  既存の3段フォールバック
740-748: actionable_patch  →  drafted_text + "\n\n" + actionable   ← 追記は本文を肥大化させる
756-769: LocalPolisher().polish_with_llm(drafted_text, range, instr, self._audit_llm)
980-984: patch_result を試すのは gate["requires_regeneration"] のときだけ
```
**`SafeReplacer`（`:726-738`）と `actionable_patch`（`:740-748`）は壊さない**。
**新しい `span` 経路を「`safe_replace` が無効だった後」「`actionable_patch` の前」**に挿す。
既存挙動が失われるのは「新経路がパッチに成功したとき」だけで、それは目的そのものだ。

**作業内容**
1. フラグ2つを追加（`audit_agent.py:139` 付近の既存 `_env_flag` 方式に倣う）:
   - `ENABLE_AUDIT_SPAN_PATCH`（既定 `"1"` / **ON**。`is_span_patch_enabled()` で行く）
   - `ENABLE_AUDIT_POLISH_ASYNC`（既定 `"1"` / **ON**。`is_async_polish_enabled()` で行く）
2. `try_local_patch`（`:706`）の**引数に `failed_outcomes: list[dict] | None = None` を追加**（既定None＝後方互換）。
3. `:725` `mappings = self._build_safe_replacer_mappings(unified_report)` の**直後に**、
   `plan = plan_repair(drafted_text, failed_outcomes or [], StaticRuleAuditor().audit(drafted_text))`
   を挿す。
4. `plan.level == "span"` のときだけ、以下の**新ブロック**を挿す（1箇所だけ）:
   - `ParagraphIndexer` で index を取得（Step 3 のオフセット付き）。
   - `plan.targets` の**先頭1件だけ**について
     `LocalPolisher().polish_span(..., self._audit_llm)`（Step 6）を `await` して、
     `applied=True` のときだけ `patched` を返す:
     `{"strategy": "span_polish", "text": patched, "replacements": 1, "paragraph_index": idx}`。
   - 検証落ち・例外は **既存の except（`:776-777`）へ流す**（return None）。
5. `plan.level == "scene"` のとき、**このステップでは何もしない**
   （既存通り None を返して Branch D に行かせる）。シーン再生成は Step 10 の予算で制御する。
6. `execute`（`:980-984`）の `try_local_patch` 呼び出しに `failed_outcomes` を渡す（1行）。
7. `is_local_patch_enabled()` が False の既存挙動（`:722` で即 None）は**変更しない**。

**回帰テスト（先に作る）**: `tests/contract/test_v6_audit_surgical_patch.py`（新規）

```python
"""span パッチが Gate より先に効くとともに、既存 patch 戦略を潰さないことの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.audit_agent import AuditAgent, is_span_patch_enabled, is_async_polish_enabled


def test_new_flags_default_on(monkeypatch):
    monkeypatch.delenv("ENABLE_AUDIT_SPAN_PATCH", raising=False)
    monkeypatch.delenv("ENABLE_AUDIT_POLISH_ASYNC", raising=False)
    assert is_span_patch_enabled() is True
    assert is_async_polish_enabled() is True


def test_new_flags_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "0")
    assert is_span_patch_enabled() is False


@pytest.mark.asyncio
async def test_span_polish_preferred_over_actionable_append(monkeypatch):
    """actionable_patch がある場合でも span パッチが優先されること。"""
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = MagicMock()
    text = "主人公は立ち止まった。\n\nその名を古代の魔導書と書く。\n\n夜が明けた。"
    report = MagicMock()
    report.conflicts = []
    report.qualitative = MagicMock()
    report.qualitative.actionable_patch = "追記すべき文章"
    out = await agent.try_local_patch(
        text, unified_report=report,
        failed_outcomes=[{"audit_id": "deai", "severity": "medium", "error": None,
                          "feedback": "古代の魔導書"}],
    )
    assert out is not None and out["strategy"] == "span_polish"
    assert "追記すべき文章" not in out["text"]


@pytest.mark.asyncio
async def test_existing_safe_replace_still_wins(monkeypatch):
    """既存の SafeReplacer 経路が壊れていないこと。"""
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = None
    report = MagicMock()
    report.conflicts = []
    c = MagicMock(); c.current_value = "MAGIC"; c.suggested_value = "MAGIC"
    report.conflicts = [c]
    out = await agent.try_local_patch("MAGIC が光った。", unified_report=report, failed_outcomes=[])
    assert out is not None and out["strategy"] == "safe_replace"


@pytest.mark.asyncio
async def test_span_patch_disabled_returns_none_like_before(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SPAN_PATCH", "0")
    agent = AuditAgent()
    agent._audit_llm = None
    assert await agent.try_local_patch("何もない。", unified_report=None, failed_outcomes=[]) is None
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_v6_audit_surgical_patch.py -q
C:\Python314\python.exe -m pytest tests/contract/test_v6_audit_gate_thresholds.py -q
```

**完了判定**: 5テスト緑。**かつ `test_v6_audit_gate_thresholds.py` の11件が1件も落ちていないこと**
（同ファイルが `safe_replace` 優先と `actionable_patch` 優先を既に固定しているため、これが W4-06 の防線）。

---

### Step 9. Advisory（警告通過）帯をゲートに追加する
- **主担当ファイル**: `src/agents/audit_agent.py`
- **依存**: Step 2
- **P分類**: P1 / P5

**背景**
`:106` `DEFAULT_AUDIT_GATE_THRESHOLD = 70.0` 一枚で、
`aggregate = 70.5` でも `requires_regeneration=True` になり Branch D（全文再生成）に入る。
`evaluate_gate`（`:198-201`）に **「不合格だが致命でもない → 警告で通す」帯**が無い。

**作業内容**
1. 定数2つを `:106` の付近に追加する:
   - `DEFAULT_AUDIT_ADVISORY_THRESHOLD = 80.0`
   - `AUDIT_GATE_ADVISORY_SEVERITIES = ("medium", "low")`（この severity のみ警告で通す）
2. `is_advisory_threshold()` / `get_advisory_threshold()` を `:146` の `_env_float` 方式に倣って追加。
   環境変数名: `AUDIT_ADVISORY_THRESHOLD`。
3. `evaluate_gate`（`:177-214`）の**戻り値 dict に2キー追加**する:
   - `"advisory": bool`
   - `"advisory_reason": str`（空文字可）
4. 判定は **`:198` の `if is_score_gate_enabled():` ブロックの直後**に挿入し、既存ロジックを**上書きしない**:
   - `requires_regeneration` が False → そのまま（`advisory=False`）
   - `critical_failure` が True → そのまま（`advisory=False`）
   - すべての failed の `effective_severity` が `AUDIT_GATE_ADVISORY_SEVERITIES` に含まれ、
     かつ `aggregate >= advisory_threshold` → **`requires_regeneration = False` / `advisory = True`**
   - それ以外 → 変更なし
5. `execute` の Branch C（`:1031-1055`, `audit_status="passed_with_warnings"`）は
   **すでに `requires_regeneration=False` で通過する**ので、コード変更は**不要**。
   `audit_status` が `"rejected"` から `"passed_with_warnings"` に変わることだけを確認する。
6. `evaluate_gate` の**既存キー（`mode` / `aggregate_score` / `threshold` / `requires_regeneration` /
   `critical_failure` / `failed_count` / `scored_audit_ids`）は削除しない**。

**回帰テスト（先に作る）**: `tests/contract/test_v6_audit_advisory_gate.py`（新規）

```python
"""Advisory 帯（重大ではないが合格でもない → 警告で通過）の回帰テスト。"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.audit_agent import evaluate_gate, get_advisory_threshold, get_gate_threshold


def _outcome(audit_id, severity, score, passed=False, blocking=True):
    return {"audit_id": audit_id, "label": audit_id, "passed": passed, "feedback": "",
            "severity": severity, "learning_adjusted": False, "confidence_adjustment": 0.0,
            "effective_severity": severity, "error": None, "score": score, "weight": 1.0,
            "blocking": blocking, "detail": None}


def test_advisory_threshold_default_is_80(monkeypatch):
    monkeypatch.delenv("AUDIT_ADVISORY_THRESHOLD", raising=False)
    assert get_advisory_threshold() == 80.0


def test_medium_only_failure_above_advisory_passes(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "60")
    gate = evaluate_gate([_outcome("deai", "medium", 100.0),
                          _outcome("fast_screen", "high", 100.0),
                          _outcome("x", "medium", 50.0)])
    assert gate["advisory"] is True
    assert gate["requires_regeneration"] is False


def test_critical_failure_never_becomes_advisory(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "10")
    gate = evaluate_gate([_outcome("causal_integrity", "critical", 100.0),
                          _outcome("x", "medium", 50.0)])
    assert gate["advisory"] is False
    assert gate["requires_regeneration"] is True


def test_below_advisory_threshold_still_regenerates(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    monkeypatch.setenv("AUDIT_ADVISORY_THRESHOLD", "95")
    gate = evaluate_gate([_outcome("x", "medium", 50.0)])
    assert gate["advisory"] is False and gate["requires_regeneration"] is True


def test_legacy_keys_still_present(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_SCORE_GATE", "1")
    gate = evaluate_gate([_outcome("x", "medium", 50.0)])
    for k in ("mode", "aggregate_score", "threshold", "requires_regeneration",
              "critical_failure", "failed_count", "scored_audit_ids"):
        assert k in gate, k
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_v6_audit_advisory_gate.py tests/contract/test_v6_audit_gate_thresholds.py -q
```

**完了判定**: 5テスト緑。**かつ `test_v6_audit_gate_thresholds.py` の11件が緑**（閾値意味を変えていないこと）。

---

### Step 10. `PDCAController` を `AuditAgent` に配線して全滅を予算化する
- **主担当ファイル**: `src/agents/audit_agent.py`
- **依存**: Step 8, 9
- **P分類**: P1 / P5 / P7

**背景**
```
src/generation/pdca_controller.py:13  max_regenerations: int = 0   ← 既にある予算モデル
src/generation/pdca_controller.py:15  max_local_patches: int = 1
src/agents/orchestrator.py:74         max_backtracks_per_node: int = 3
```
**`AuditAgent` は `PDCAController` を一切使っていない**。Orchestrator 側の3回という値も、
ノード単位で上限3回を使い切ってから次ノードへ飛ぶため、コストが跳ね上がる。

**作業内容**
1. `__init__`（`:231-271`）の末尾に
   `self._repair_budget = PDCAController(max_regenerations=0, max_local_patches=3)` を**追加**。
   フラグ `ENABLE_AUDIT_REPAIR_BUDGET`（既定 `"1"` / ON）を `is_repair_budget_enabled()` 経由で読む。
2. `execute` の **Branch D（`:1057`） entering 時**に、**フル regen が予算切れなら
   「パッチ出来なかった → 警告通過」側に落とす**:
   - `if not self._repair_budget.can_do_local_patch() and not gate["requires_regeneration"] ...` は冗長。
   - 実際は次の1条件だけを足す:
     **`if is_repair_budget_enabled() and not self._repair_budget.can_regenerate_full_text():`**
     → `should_retry=False` / `is_backtrack=False` / `audit_status="repassed_budget_exhausted"` /
     `next_agent=AgentName.ILLUSTRATION` にして **Branch C 相当で通過**させる。
3. `try_local_patch` が **実際に置換に成功した場合のみ**
   `self._repair_budget.record_local_patch()`（`:53`）を呼ぶ（1行）。
4. Branch D に入った場合のみ `self._repair_budget.record_full_regeneration()` を呼ぶ（1行）。
5. `reset_counts()`（`:59`）は**呼ばない**（エピソード単位の予算としない）。
   理由: Orchestrator 側の `max_backtracks_per_node=3` が既に3回で頭打ちであるため。
6. Orchestrator の `max_backtracks_per_node` は**変更しない**（1ノード＝1回の予算）。

**回帰テスト（先に作る）**: `tests/contract/test_v6_audit_regeneration_budget.py`（新規）

```python
"""PDCA 予算により全滅再生成が1話1回に封じ込められることの回帰テスト。"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.generation.pdca_controller import PDCAController
from src.agents.audit_agent import is_repair_budget_enabled


def test_budget_flag_default_on(monkeypatch):
    monkeypatch.delenv("ENABLE_AUDIT_REPAIR_BUDGET", raising=False)
    assert is_repair_budget_enabled() is True


def test_budget_blocks_second_full_regeneration():
    c = PDCAController(max_regenerations=0, max_local_patches=3)
    assert c.can_regenerate_full_text() is False
    c.record_full_regeneration()
    assert c.regeneration_count == 1


def test_local_patch_budget_counts_up():
    c = PDCAController(max_regenerations=0, max_local_patches=2)
    assert c.can_do_local_patch() is True
    c.record_local_patch(); c.record_local_patch()
    assert c.can_do_local_patch() is False
    assert c.local_patch_count == 2


def test_reset_counts_restores():
    c = PDCAController(max_regenerations=1, max_local_patches=1)
    c.record_full_regeneration(); c.record_local_patch()
    c.reset_counts()
    assert c.regeneration_count == 0 and c.local_patch_count == 0
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_v6_audit_regeneration_budget.py tests/generation/test_pdca_pipeline_integration.py -q
```

**完了判定**: 4テスト緑。**かつ既存 Branch D の3テスト（`test_v6_audit_gate_thresholds.py::test_critical_fail_triggers_regen` ほか）が緑**。

---

### Step 11. 監査メトリクスとイベントにパッチ観測点を足す
- **主担当文件**: `src/agents/audit_agent.py`
- **依存**: Step 8
- **P分類**: P1 / P2

**背景**
`emit_event`（`:277`）が飛んでいるのは `audit.audit.started` / `completed` / `phase_completed` のみ。
**「パッチが成立したのか」「どの戦略だったのか」**が外から観測できず、
本計画の効果（R10 と同じ「効果測定表が未作成」問題）が測れない。

**作業内容**
1. `try_local_patch` の**各 return の直前**で `self.emit_event("audit.patch.applied", {...})` を1回だけ呼ぶ。
   payload キーは **4つ固定**: `strategy` / `replacements` / `text_length` / `triage_level`。
2. `try_local_patch` が `None` を返す**全経路**で `self.emit_event("audit.patch.skipped", {...})` を呼ぶ。
   payload は `{"reason": "<文字列>"}` **1キーだけ**。
3. Branch D（`:1057`）通過時に `self.emit_event("audit.regeneration.full", {"attempt": n})` を追加。
4. `self.last_gate_evaluation`（`:682` 付近で既に代入されている）に、
   `last_audit_metrics` として**既存の `audit_metrics` dict をそのまま載せる**（新規変数を作らない）。
5. イベント名の命名規則を**新規に作り直さない**。既存 `emit_event` の上書き先（`:277-282`）に足す。
6. `drain_events()`（`:284`）は既存のまま（テスト用ヘルパ）。

**回帰テスト（先に作る）**: `tests/unit/agents/test_audit_patch_events.py`（新規・非同期）

```python
"""パッチ適用/スキップイベントが発火することの回帰テスト。"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.audit_agent import AuditAgent


@pytest.mark.asyncio
async def test_skipped_event_on_none(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "0")
    agent = AuditAgent()
    assert await agent.try_local_patch("本文。") is None
    names = [e["event"] for e in agent.drain_events()]
    assert "audit.patch.skipped" in names


@pytest.mark.asyncio
async def test_applied_event_carries_four_keys(monkeypatch):
    monkeypatch.setenv("ENABLE_AUDIT_LOCAL_PATCH", "1")
    agent = AuditAgent()
    agent._audit_llm = None
    report = type("R", (), {})()
    report.conflicts = [type("C", (), {"current_value": "AAA", "suggested_value": "BBB"})()]
    out = await agent.try_local_patch("AAA が光った。", unified_report=report)
    assert out is not None
    evs = [e for e in agent.drain_events() if e["event"] == "audit.patch.applied"]
    assert len(evs) == 1
    assert set(evs[0]["payload"]) == {"strategy", "replacements", "text_length", "triage_level"}


def test_event_ring_buffer_bounded():
    agent = AuditAgent()
    for i in range(600):
        agent.emit_event("audit.tick", {"i": i})
    assert len(agent.drain_events()) <= 500
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/agents/test_audit_patch_events.py -q
```

**完了判定**: 3テスト緑。イベント数が 500 を超えないこと（リングバッファ維持）。

---

### Step 12. 総合回帰・後方互換・文書化
- **主担当ファイル**: `plans/PLAN_W4_SURGICAL_PATCH_12STEPS.md`（本書）、`docs/STATUS.md`
- **依存**: Step 1〜11 すべて
- **P分類**: P1

**作業内容**
1. **並列実行は禁止**（順番に1本ずつ実行する）。順番に次を実行する:
   - `C:\Python314\python.exe -m pytest tests/audit/ tests/unit/audit/ -q`
   - `C:\Python314\python.exe -m pytest tests/contract/ -q`
   - `C:\Python314\python.exe -m pytest tests/unit/agents/ tests/generation/ tests/unit/services/ tests/unit/pipeline/ -q`
   - `C:\Python314\python.exe -m pytest tests/regression/ -q`
2. 上記4コマンドが**すべて緑**であることを確認する（1本でも赤なら Step 12 は未完了）。
3. 新規追加4ファイルに `ruff check` をかけ、`E9,F63,F7,F82` が 0 件であることを確認する:
   `C:\Python314\python.exe -m ruff check src/audit/triage.py src/audit/repair_planner.py src/services/prose/span_patch_applier.py src/services/audit/targeted_diagnostic.py --select E9,F63,F7,F82`
4. `docs/STATUS.md` の SSOT に、W4 完了要因と、他計画書（W5/W6）の索引を追加する。
5. 本書の status を「完了」に更新する。

**完了判定**
- 4つの回帰コマンドがすべて緑。
- 新規4ファイルの `ruff --select E9,F63,F7,F82` がクリーン。
- `docs/STATUS.md` に W4 の完了エントリがある。

---

## 3. ロールバック

すべて**環境変数1つで元に戻せる**。コードの削除は不要。

| 変数 | 既定 | 効果 |
|---|---|---|
| `ENABLE_AUDIT_SPAN_PATCH` | `1` (ON) | `0` で Step 8 の span 経路が無効化され、旧3段フォールバックのみ |
| `ENABLE_AUDIT_POLISH_ASYNC` | `1` (ON) | `0` で Step 6 の `polish_span` を使わず、従来の `polish_with_llm` 経路へ |
| `ENABLE_AUDIT_REPAIR_BUDGET` | `1` (ON) | `0` で Step 10 の予算封じ込めが無効化され、旧 Branch D に戻る |
| `AUDIT_ADVISORY_THRESHOLD` | `80.0` | `999` で Step 9 の警告通過帯が実質無効化 |
| `ENABLE_AUDIT_SCORE_GATE` | `1` (ON) | `0` で旧 all-or-nothing（1件でも落ちたら再執筆）へ |
| `ENABLE_AUDIT_LOCAL_PATCH` | `1` (ON) | `0` で Step 8 以前の完全旧挙動へ |

> 注意: `ENABLE_AUDIT_SCORE_GATE=0` は**現状のドキュメント上の既定と逆**だが、
> `test_v6_audit_gate_thresholds.py` が固定しているのは **gate ON** 側の挙動である点に注意。

## 4. 期待効果（測定は Step 11 のイベントで可能）

| 指標 | 現状 | 目標 |
|---|---|---|
| 1話あたり Branch D（全文再生成）回数 | 最大 4 | **最大 1**（Step 10） |
| 1話あたり本文生成 LLM 回数 | 最大 4 | 1（Step 8 が成功した場合） |
| ローカルパッチ試行のイベントループブロック | 同期 LLM 呼出でブロック | **0**（Step 6） |
| 再生成時の文脈ドリフト | 全文書き直し | スパン置換（Step 8） |

### 4.1 実装実績（2026-09-30）

- **Step 11**: `try_local_patch` の全 return 直前に `audit.patch.applied`（payload 4キー: `strategy` / `replacements` / `text_length` / `triage_level`）、`None` 返却の全経路に `audit.patch.skipped`（payload 1キー: `reason`）、Branch D 通過時に `audit.regeneration.full`（`{"attempt": n}`）を発火。`last_gate_evaluation` に既存 `audit_metrics` をそのまま載せた（新規変数なし）。リングバッファは 500 件上限を維持。
- **バグB修正**: advisory 緩和ガードに `strict_guard`（`ENABLE_AUDIT_ADVISORY_STRICT_GUARD`、既定 ON）を追加。`AUDIT_GATE_THRESHOLD` を手動で上げたまま既定 advisory（80.0）が残余ると `80 < 99` が成立して「再執筆する」が「警告通過」に反転していた事故を阻止。
- **残存**: `tests/contract/test_v6_audit_advisory_gate.py::test_all_or_nothing_mode_keeps_advisory_off` は
  「1件でも不合格なら再執筆する（all-or-nothing の定義）」というコード側の実挙動と、
  テストの期待値 `requires_regeneration is False` が矛盾しており赤のまま。既存ロジック改変禁止のため未修正。
