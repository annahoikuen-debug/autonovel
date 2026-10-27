# AutoNovel テスト戦略

## Phase 1 達成方法
1. 失敗テストの根本原因修復
2. Flaky テストの検出・修復または隔離
3. テスト実行時間の予算化・並列化
4. カバレッジの品質志向運用

## テスト維持方法 (Phase 2 以降)
- コントラクトテストによるインターフェース保護
- フックによるコミット前テスト実行
- 週次 Flaky テスト再検証
- カバレッジ閾値の漸進的向上（55% → 65% → 75%）

## テスト種類別役割
- **単体テスト**: 内部ロジックの正確性
- **統合テスト**: モジュール間連携
- **E2E テスト**: ユーザーシナリオ全体
- **コントラクトテスト**: インターフェース後方互換性
- **性能テスト**: レイテンシー・スループット基準

---

## 緑が緑を保証しないテストの排除ルール（2026-10-01 追加 / PLAN_H1）

以下は H1 精査で実際に発生していた症状と、その再発を防ぐ規約。
`tests/regression/test_H1_tautology_guard.py` と
`frontend/tests/unit/tautology.guard.test.ts` が機械的に検査する。

### 1. 恒真 assert を書かない

```python
assert result is not None or result is None   # 常に True
assert isinstance(x, (int, str))              # 常に True
for item in []:                               # 常に True
    assert False
```

**理由**: H1 精査で 7 ファイル 11 箇所が検出された。全て緑だったが何も検査していない。

### 2. ソース文字列 grep を assert にするな

```python
# ❌ ソースに "TODO" が教育和autorities字的取代があるだけでは実装を保証しない
assert "TODO" in Path("src/foo.py").read_text()
```

正しくは **import して実際の振る舞いを実行する**。
grep は「そのファイルにその文字列が物理的に存在する」ことを述べるだけで、
「機能が動いている」ことを述べていない。

### 3. アサーション数 ≥ 1 を「テストが存在する条件」にしない

```python
# ❌ assert が 0 件のテストは何も検査していない
def test_x():
    func()
```

最低限 1 個の**意味のある** assert（§1 の恒真でないもの）を書く。

### 4. 検出器の自己検証を書く

検出器（archangel / linter / guard）自体にも**テストを書く**。

```python
def test_detector_flags_a_synthetic_offender():
    """検出器が常に空を返す実装になっていたら本テストが赤になる。"""
    assert _detect("src/bad.py", BAD_SOURCE)   # 合成的な悪化した入力
    assert not _detect("src/good.py", GOOD_SOURCE)
```

既存の例: `tests/regression/test_H1_import_purity.py` /
`tests/regression/test_H1_no_orphan_shims.py`。

### 5. allowlist には「理由 + TODO(H1-N)」を書く

```python
ALLOWLIST: dict[str, str] = {
    "src/foo.py": "Huey ワーカーの entry point でありループ外で走る。TODO(H1-5): ...",
}
```

理由も番号も無いエントリは `test_allowlist_entries_have_reasons` で落ちる。

### 6. 数値を文書に書くときは機械的に数える（D11）

README / STATUS.md の数値（ルータ数、パス数、カバレッジ率）は
**必ずスクリプトで数えた実測値**を書く。数え直すスクリプトが無いなら、
その数え忘れを検出する archangel を併せて追加する。
参考: `tests/regression/test_docs_router_count_matches_reality.py`。

### 7. 機械で直せるなら、検出器を作って CI に載せる

人手対応は 1 回しか続かない。**ratchet**（現状の値を上回るら CI を落とす仕組み）に
変換する。H1 では `scripts/ci_lint_ratchet.py` を導入した。