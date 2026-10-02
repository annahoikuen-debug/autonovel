# Contributing to AutoNovel

AutoNovel への貢献を歓迎します。本ドキュメントは開発者向けのガイドラインをまとめたものです。

## 1. 開発環境のセットアップ

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements-dev.txt
py -m pip install -e .
cd frontend; npm install; cd ..
```

`.env.example` を `.env` へコピーし、環境変数を調整します。

## 2. コーディング規約

- **Python**: 3.12+。Ruff (E/F/W/I/C90/UP) でリント (`py -m ruff check src tests`)
- **型ヒント**: モダン記法 `list[X]`, `dict[K, V]`, `X | None`, `from __future__ import annotations`
- **行長**: E501 は無視 (100 文字前後を目安にフォーマッタに委ねる)
- **TypeScript**: `strict: true`, `react-jsx`, `bundler` 解決
- **テスト**: pytest `asyncio_mode=auto`、`--strict-markers`

## 3. ブランチ & コミット運用

- main ブランチは常にグリーン
- feature/bugfix ブランチは `feature/<slug>` / `fix/<slug>` 形式
- コミットメッセージは Conventional Commits 推奨 (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)

## 4. プルリクエスト前の検証

PR を作成する前に以下を全てパスさせてください:

```powershell
# バックエンド
py -m ruff check src tests
py -m pytest -q --tb=short
py scripts\generate_openapi.py --output docs\openapi.json

# フロントエンド
cd frontend
npm run typecheck
npm run lint
npm run test:ci
cd ..
```

CI (`.github/workflows/ci.yml`) で同じ検証が走ります。

## 5. テストを書く

- ユニットテストは `tests/` 以下、結合テストは `tests/integration/`
- DB を使う場合は [`tests/conftest.py`](tests/conftest.py) の `real_db_manager` フィクスチャを利用
- 非同期テストは `@pytest.mark.asyncio` 不要 (asyncio_mode=auto)
- 新規エンドポイントには 200 正常系と 422 バリデーション異常系を必ず追加
- 詳細規約は [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md) の
  「緑が緑を保証しないルール」を必ず読む

### 5.1 書いてはいけないテスト（2026-10-01 追加 / PLAN_H1）

```python
# ❌ 恒真 assert（常に True。何も検査していない）
assert result is not None or result is None
assert isinstance(x, (int, str))

# ❌ ソース文字列 grep を assert にする（存在の検査であって動作の検査ではない）
assert "TODO" in Path("src/foo.py").read_text()

# ❌ assert 0 件（テストしたことにしていない）
def test_x():
    func()
```

**正しくは import して実際の振る舞いを実行する**。
機械で検査できるなら detector を作り、
archangel テスト（`tests/regression/test_H1_tautology_guard.py` など）を併せて追加すること。

## 6. CHANGELOG の更新

ユーザ影響のある変更は [`CHANGELOG.md`](CHANGELOG.md) の Unreleased セクションへ追記:

```
### 追加
- 新機能の簡潔な説明 + `[ filename ](path)`
```

## 7. リリースフロー

1. `pyproject.toml` の `version` を bump
2. `CHANGELOG.md` の該当セクション日付を更新
3. `scripts\release.ps1` を実行し、タグ付与
4. `git push origin <tag>` で公開

## 8. 行動規範

敬意を持ったコミュニケーションを心がけてください。批判は建設的に。
