# Shim 段階削除計画 (SHIM_REMOVAL_PLAN.md)

> **目的**: 案B + 改善案C で作成した **141 件の後方互換 shim** を、リスクを管理しながら
> 段階的に削除するための計画。
>
> **前提**: 全 shim は `config/shim_registry.json` に登録済みで、
> `tests/regression/test_new_shims_registered.py` が CI で未登録 shim を検出している。
>
> **原則**: 1 リリースにつき 1 カテゴリまで。削除の 1 リリース以上前から
> DeprecationWarning を表示し、旧パス参照数がゼロであることを CI で確認してから削除する。

---

## 1. 現状（2026-11-07 時点）

| カテゴリ | 件数 | 代表例 | 状態 |
|---------|------|--------|------|
| services ルートファイル shim | 46 | `src/services/rag_service.py` → `src/integrations/rag/rag_service.py` | import * 方式 |
| config shim（ルート config/） | 0（元 28、全削除済み） | `config/container.py` → `src/core/container/` | 全削除済み（R3-1 完了） |
| services サブパッケージ shim | 27 | `src/services/anti_ai/__init__.py` → `src/engine/anti_ai/` | import * + `__getattr__` |
| LLM shim (src/services/llm/) | 20 | `src/services/llm/factory.py` → `src/llm/adapters/factory.py` | 個別 shim ファイル |
| その他（core 移設・API 等） | 20 | `src/core/llm_clients/__init__.py`、`src/api/dashboard.py` 等 | 混在 |
| **合計** | **141** | | 警告付きは **7 / 141 のみ** |

---

## 2. 段階計画

### Phase R0: 観測（現在・即時開始）

**目的**: 「どの shim が実際に import されているか」の使用統計を取得する。

**手順**:
1. CI の `integration-observe` ジョブ（観測モード稼働中）で shim import の DeprecationWarning を集計
2. `tests/regression/test_shim_usage_stats.py` を新規作成し、CI ログに shim 使用件数を出力:
   ```python
   def test_report_shim_usage(caplog):
       """全 shim を import して DeprecationWarning 発生数をレポート（CI 観測用）。"""
   ```

**完了条件**: shim 使用件数の一覧が CI ログで取得できること。

### Phase R1: DeprecationWarning 全面付与（最初のリリース）

**目的**: 134 件の警告なし shim に DeprecationWarning を付与し、利用者に移行を促す。

**手順（各 shim に共通のヘッダパターン）**:
```python
import warnings

warnings.warn(
    "src.services.rag_service is deprecated; use src.integrations.rag instead",
    DeprecationWarning,
    stacklevel=2,
)
```

**テスト**: `tests/regression/test_shim_deprecation_warning.py` を新規作成:
```python
@pytest.mark.parametrize("shim_path", ALL_SHIMS)
def test_shim_emits_deprecation_warning(shim_path):
    """全 shim が import 時に DeprecationWarning を発すること。"""
```

**注意**: テスト自体が shim を import するため、警告は `pytest.ini` の filterwarnings で
抑制済みであること（テスト失敗にしない）。警告は「実アプリのログ」で観測する。

**完了条件**: 141/141 が警告付き。テスト全緑。

### Phase R2: 参照解消（Phase R1 と並行・週単位）

**目的**: リポジトリ内の旧パス参照（`src.services.X` / `config.X`）を新パスへ置換し、
参照数をゼロに近づける。

**手順**:
1. 残存参照の棚卸し:
   ```bash
   for mod in rag_service audit_aggregator book_score_service ...; do
     n=$(grep -rl "services\.$mod\b" src/ tests/ --include="*.py" | grep -v __pycache__ | wc -l)
     [ "$n" -gt 0 ] && echo "$n $mod"
   done
   ```
2. 参照がある箇所は新パスへ置換（テストの monkeypatch 文字列は `importlib.import_module`
   方式へ書き換え — `test_sqlite_rag_embedding.py` の修正パターンを踏襲）
3. `docs/MOVEMENT_MAPPING.md` に残存参照数を週次で記録

**完了条件**: カテゴリごとに「src/tests 内の旧パス参照数 == 0」を達成。

### Phase R3: 段階削除（4 バッチ・リリース単位）

削除条件（各バッチ共通）: **Phase R2 で当該カテゴリの旧パス参照数 == 0**、かつ
**DeprecationWarning 表示が 1 リリース以上経過**。

| バッチ | 対象 | 件数 | 削除の根拠 |
|--------|------|------|-----------|
| 第1弾 | config shim（ルート config/） | 28 | `config/` は YAML 純化済み。Python コードは `src/config/` 等に移設済み |
| 第2弾 | services サブパッケージ shim | 27 | 実体は全て `src/engine|publishing|integrations/` |
| 第3弾 | services ルートファイル shim | 46 | 実体は全て新パス。参照解消は Phase R2 で完了 |
| 第4弾 | LLM shim + その他 | 40 | 最後に削除（外部ツール・ドキュメントの参照が残りやすい） |

**削除時の実装手順（各バッチ共通）**:
1. `pytest tests/regression/test_shim_reference_gate.py -q` が green であること（該当 shim の baseline エントリが無いこと = Phase R2 参照解消完了）
2. `pytest tests/regression/test_shim_removal_detection.py` の `REMOVED_SHIMS` に当該 shim を追加する
3. 旧パス参照数がゼロであることを確認（Phase R2 の棚卸しコマンド）
4. shim ファイルを `git rm`
5. `config/shim_registry.json` から該当エントリを除去
6. **削除検出テスト**を `tests/regression/test_shim_removal_detection.py` に追加:
   ```python
   def test_removed_shims_no_longer_importable():
       """削除済み shim が旧パスで import されないこと（意図的な破壊を CI が検知）。"""
       with pytest.raises(ModuleNotFoundError):
           importlib.import_module("src.services.rag_service")
   ```
7. `docs/MOVEMENT_MAPPING.md` のステータスを「削除済み」に更新

**完了条件**: 各バッチで CI 全緑（unit + regression + integration-observe）。

### Phase R4: 完了（全バッチ削除後）

- `tests/regression/test_new_shims_registered.py` の registry が空になる
- `tests/regression/test_services_root_unification_complete.py` の
  `test_services_root_file_count_within_budget` の上限を 0（`__init__.py` のみ）に引き下げ
- `config/shim_registry.json` 自体を削除（説明文書のみ残す）

---

## 3. 安全策

| リスク | 対策 |
|--------|------|
| 外部利用者（フォーク・ツール）が旧パスを使用 | Phase R1 の警告 + CHANGELOG に移行ガイドを記載、1 リリース猶予 |
| 参照数の計測漏れ（文字列結合 import 等） | CI の `integration-observe` で実行時エラーを観測。動的 import は Phase R2 で手動レビュー |
| 削除バッチ間の相互依存 | 1 リリース 1 カテゴリ。削除前後に unit + regression 全緑を必須化 |
| テストの monkeypatch が旧パスを指す | Phase R2 で monkeypatch 文字列を `importlib.import_module` 方式に統一（既存修正パターンを踏襲） |
| 削除後の回帰 | Phase R3 手順4の「削除検出テスト」で旧パス使用を即座に検知 |

---

## 4. 進捗チェックリスト

| Phase | 内容 | ステータス |
|-------|------|-----------|
| R0 | shim 使用統計の観測基盤 | 未着手 |
| R1 | DeprecationWarning 全面付与（134件） | 未着手 |
| R2 | 旧パス参照解消（カテゴリ別ゼロ化） | 完了（config カテゴリ / services 系は未完了） |
| R3-1 | config shim 23件削除（元計画 28件） | 完了 |
| R3-2 | services サブパッケージ shim 27件削除 | 未着手 |
| R3-3 | services ルートファイル shim 46件削除 | 未着手 |
| R3-4 | LLM + その他 shim 40件削除 | 未着手 |
| R4 | registry 空化・ラチェット引き下げ | 未着手 |
