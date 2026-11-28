# AutoNovel タスク一覧 (TODO)

プランナー役: 直近コミットのレビュー・課題修正・コミット。

## 完了
- [x] fix(play): review-loop Round 1 指摘の修正 (commit `2555b44a`)
- [x] ruff format 適用 (8 ファイルのフォーマット不整合を解消)
- [x] ruff lint クリーン (`All checks passed!`)

## 未完了 (>=10 タスク維持)
- [ ] バックエンドテスト実行 (`make test`) で回帰確認
- [ ] 契約テスト実行 (`make test-contract`)
- [ ] mypy typecheck 実行 (mypy==2.3.1、ラチェット 450 件以内か確認)
- [ ] 4層アーキテクチャ境界チェック (`make lint-layers`)
- [ ] OpenAPI スナップショット再生成 (`make openapi`、API 変更があれば)
- [ ] フロントエンド型同期 (`npm run type:sync`、API 変更があれば)
- [ ] フロントエンドテスト・lint (`make frontend-test`, `make frontend-lint`)
- [ ] バージョン SSOT 整合確認 (`tests/regression/test_v5_version_consistency.py`)
- [ ] CHANGELOG.md Unreleased セクションへユーザー向け変更を追記
- [ ] `make verify` (ci-parity + lint-layers + typecheck + test-contract + test-migration)
- [ ] すべての変更をコミットし main をグリーンに保つ
