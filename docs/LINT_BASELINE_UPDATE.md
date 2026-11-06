# lint ratchet ベースライン更新手順 (LINT_BASELINE_UPDATE.md)

> **目的**: モジュール移動に伴い `config/ci_lint_baseline.json` の値が変わる場合の、
> 意図的な更新手順を定義し、意図しない悪化を検出する。

---

## 現在のベースライン値

`config/ci_lint_baseline.json`:

```json
{
  "ruff_errors": 90,
  "mypy_errors": 1122,
  "format_files": 759
}
```

---

## 更新手順

モジュール移動（例: LLM 統合）により ruff/mypy/format のエラー数が変わった場合:

### 1. 現状を確認

```bash
# ruff エラー数
.venv/bin/python3 -m ruff check src config tests 2>&1 | tail -1

# mypy エラー数
.venv/bin/python3 -m mypy src 2>&1 | tail -1

# format 未適用ファイル数
.venv/bin/python3 -m ruff format --check src config tests 2>&1 | tail -1
```

### 2. 新しいベースラインを計算して更新

```bash
# スクリプトで自動更新（作成予定）
# または手動で config/ci_lint_baseline.json を編集
```

### 3. テストで確認

```bash
.venv/bin/python3 -m pytest tests/regression/test_lint_budget.py -v
.venv/bin/python3 -m pytest tests/regression/test_lint_baseline_integrity.py -v
```

---

## 更新ルール

| ルール | 内容 |
|--------|------|
| **悪化禁止** | 移動によりエラー数が増えてはならない |
| **意図的な減少** | shim 削除等でエラー数が減った場合は、ベースライン値を下げる |
| **CI で固定** | `tests/regression/test_lint_budget.py` で上限値を固定し、増加を機械的に検出 |

---

## 関連ファイル

- `config/ci_lint_baseline.json` — ベースライン値
- `tests/regression/test_lint_budget.py` — lint 残存数の回帰テスト
- `tests/regression/test_lint_baseline_integrity.py` — ベースライン整合性テスト（Step 4 で作成）
- `scripts/ci_lint_ratchet.py` — CI 用 ratchet スクリプト（既存）
