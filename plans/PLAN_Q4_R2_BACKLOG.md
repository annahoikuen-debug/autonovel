# PLAN_Q4-R2: Phase 5 持ち出しバックログ (設計課題・別計画)

> PLAN_Q4_REVIEW_REMEDIATION_24STEPS.md の Phase 5（Step 24）で「実装しない / 後続計画に持ち出す」と判断した項目を記録した。
>
> 各項目は「現状」「判断（なぜ今回は実装しないか）」「次計画での推奨対応」を含む。

---

## 1. format ゲート範囲の拡大（`tests` + `config` + `scripts`）

### 現状
- `ruff format --check src` → 0 ファイル未整形（ゲート対象、green）
- `ruff format --check tests config scripts` → **935 ファイル未整形**（ゲート対象外）
- Makefile `format-check` と ci.yml の `ruff format ratchet` は `src` のみ

### 判断
現状維持（今回は実装しない）。`tests/config/scripts` を一括 `ruff format` すると diff が巨大化し、レビュー負荷が高まるため。

### 次計画での推奨対応
`tests/config/scripts` を段階的に `ruff format` 適用し、`ci_lint_baseline.json` の `format_files` に `tests config scripts` を追加。`make verify` の `format-check` も `src tests config scripts` に拡大。

---

## 2. conftest.py のグローバル monkeypatch DB フィクスチャ

### 現状
- `tests/conftest.py:116-209` で `db_module.engine = test_engine`（行 153、`# type: ignore[assignment]`）、`db_core.DATABASE_URL = test_url`（行 146）をモジュールグローバルへ直接代入し、finally で復元
- pytest-xdist 等の並列化で競合し得る設計（レビュー Medium 指摘）

### 判断
今回は実装しない。`pytest-xdist` 未導入のため即座の障害にはならず、大規模な refactor が必要。

### 次計画での推奨対応
`dependency_overrides` 注入に統一。`pytest-xdist` 導入可否と併せて判断。

---

## 3. pytest.ini の `flaky` マーカー

### 現状
- `pytest.ini:27` で `flaky` マーカーを定義しているが、`pytest-rerunfailures` 未導入のため「記録のみ」
- レビュー Low 指摘

### 判断
未導入ならマーカー削除、導入なら `--reruns` を CI に追加。どちらかを次計画で決定。

### 次計画での推奨対応
`pytest-rerunfailures` を `requirements.txt` dev 依存に追加し、CI の `test` ジョブで `--reruns 2` を追加するか、マーカーを削除する。

---

## 4. lint 債務の ratchet 単位（モジュール級）

### 現状
- `scripts/ci_lint_ratchet.py` は総数ベース（ruff 163 / mypy 1164 / format 748 を「増加のみ検出」で恒常許容）
- モジュール単位の劣化が見えない（レビュー Medium 指摘）
- Phase 2 で `invalid-ignore` カウンタは新設済み（`config/ci_lint_baseline.json` に `invalid_ignore_errors: 0`）

### 判断
今回は `invalid-ignore` カウンタのみ新設。モジュール別 ratchet は別計画。

### 次計画での推奨対応
`ci_lint_baseline.json` にモジュール別 count（例: `mypy_errors_by_module`）を追加し、top-N の劣化を常時表示。`ci_lint_ratchet.py` に `--module` オプションを追加。

---

## 関連コミット

- `fix/q1-red-gate-recovery` ブランチの Phase 1-4 コミット（`2020b421`, `6773dbad`）
- Phase 5 Step 22-24 は本バックログに持ち出し
