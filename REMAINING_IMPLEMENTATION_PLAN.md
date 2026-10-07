# 伏線自動設置パイプライン - 残タスク実装計画書

作成日: 2026-10-05
対象 worktree: **`E:\autonovel_qa`** (`qa/audit-remediation` @ `7a1875c`)
**既存実装は `a26f3c0` (データ層+設置エンジン) と `d59df76` (コンテキスト配線) で完了済み**

---

## 現状サマリ

| Phase | 内容 | 状態 | コミット |
|---|---|---|---|
| 1 | `keywords` 列追加 + マイグレーション + Repo API | ✅ 完了 | a26f3c0 |
| 2 | 設置エンジン (`plant_from_roadmap`) + `add_many` + KPI保証 | ✅ 完了 | a26f3c0 |
| 3 | 特徴フラグ `FORESHADOW_PLANTING` (既定 False) | ✅ 完了 | a26f3c0 |
| 4 | `generator.py` / `episode_writer.py` コンテキスト配線 | ✅ 完了 | d59df76 |
| 5 | KPI 経路保証 (テストで固定) | ✅ 完了 | a26f3c0 |
| 6 | 結合テスト (プロンプトへのアンカー描画等) | ✅ 完了 | d59df76 |
| **P0** | **`bible_service.py` へのフック統合** | 🔄 **残タスク** | - |

---

## 残タスク: P0 統合フック

### P0-1: `bible_service.py` に設置フックを追加

**ファイル**: `E:\autonovel_qa\src\services\bible_service.py`

**既に追加済み** (working tree に未コミット):
```python
# Line 7-8 (既に追加済み)
from src.services.foreshadowing.flags import is_foreshadowing_planting_enabled
from src.services.foreshadowing.planting_service import plant_from_roadmap
```

**追加が必要な箇所**: `_create_ultra_fast_plan` と `_create_standard_plan` の `save_full_world_bible` 直後

#### 1. `_create_ultra_fast_plan` (約 line 375 直後)

```python
# 既存 line 375:
await self.repo.save_full_world_bible(bible_obj, book_id=book_id)

# ここから追加 (P0-1-a):
# 伏線自動設置 (フラグ OFF なら副作用ゼロ)
if is_foreshadowing_planting_enabled():
    from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # session 取得: self.repo.session は UoW コンテキストでは wrapper 経由で動作
    # ここでは明示的に新セッションを作るか、UoW から取る
    # 簡易: self.repo.db.get_session() で短寿命セッション
    async with self.repo.db.get_session() as session:
        fs_repo = DbForeshadowingRepository(session)
        roadmap = bible_obj.full_story_roadmap or []
        await plant_from_roadmap(
            repo=fs_repo,
            book_id=book_id,
            roadmap_items=roadmap,
            total_episodes=config.target_eps,
            planting_enabled=True,  # flag already checked
        )
        await fs_repo.commit()
```

#### 2. `_create_standard_plan` (約 line 491 直後)

```python
# 既存 line 484-491:
book_id = await self.repo.save_full_world_bible(
    bible_obj,
    cheat_scale=config.cheat_scale,
    growth_curve=config.growth_curve,
    system_assist=config.system_assist,
    cost_severity=config.cost_severity,
    target_eps=config.target_eps,
)

# ここから追加 (P0-1-b):
# 伏線自動設置
if is_foreshadowing_planting_enabled():
    from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
    async with self.repo.db.get_session() as session:
        fs_repo = DbForeshadowingRepository(session)
        roadmap = bible_obj.full_story_roadmap or []
        await plant_from_roadmap(
            repo=fs_repo,
            book_id=book_id,
            roadmap_items=roadmap,
            total_episodes=config.target_eps,
            planting_enabled=True,
        )
        await fs_repo.commit()
```

**注意**: 
- `planting_enabled=True` は「フラグ ON 時のみここを通る」ため明示的に True
- `is_foreshadowing_planting_enabled()` は `flags.py` の `_env_flag("FORESHADOW_PLANTING")` → 既定 False
- 既存トランザクション (`save_full_world_bible`) と**別セッション**で commit する設計 (flushed rows は別トランザクションで永続化)。これは `plant_from_roadmap` docstring "commit しない (flush まで)" と整合

---

### P0-2: 回帰テスト実行 (Tier1 緑確認)

```bash
cd E:\autonovel_qa
python -m pytest tests/unit/services/test_bible_service.py tests/unit/services/test_foreshadowing_planting.py tests/unit/database/test_foreshadowing_repo_keywords.py tests/integration/test_v53_long_form_wiring_e2e.py tests/regression/test_v53_context_wiring_reachability.py -q --tb=line
```

**期待**: すべて pass (新規失敗 0 件)

---

### P0-3: Ratchet 確認 (新規失敗が無いこと)

```bash
cd E:\autonovel_qa
python scripts/ci_tier_ratchet.py
```

**期待**: `NEW FAILURES: 0` / `REGRESSIONS: 0`

---

## 実装上の注意点

### 1. セッション取得の既存パターン
`bible_service.py` 内の `create_setting_snapshot` (line 117-118) が `self.repo.session.execute(...)` を使っているが、これは **UoW コンテキストがある場合のみ** 動作する。`_create_*_plan` は `OrchestratorEngineAdapter` 経由で呼ばれるため UoW がある想定だが、安全のため **明示的な `self.repo.db.get_session()` コンテキストマネージャ** を使うのが確実。

### 2. インポートの循環回避
`plant_from_roadmap` は `DbForeshadowingRepository` を型ヒントで受けるが実行時に `isinstance` チェックはしない (duck typing)。フック内でローカルインポートすれば循環回避可能。

### 3. エラーハンドリング
設置失敗で Bible 生成全体を落とさないよう `try/except` で包み、ログのみ出力して継続するのが安全:

```python
try:
    if is_foreshadowing_planting_enabled():
        async with self.repo.db.get_session() as session:
            fs_repo = DbForeshadowingRepository(session)
            roadmap = bible_obj.full_story_roadmap or []
            await plant_from_roadmap(
                repo=fs_repo,
                book_id=book_id,
                roadmap_items=roadmap,
                total_episodes=config.target_eps,
                planting_enabled=True,
            )
            await fs_repo.commit()
except Exception as e:
    logger.warning(f"Foreshadowing planting failed (non-fatal): book_id={book_id} error={e}")
```

### 4. `roadmap` の型
`bible_obj.full_story_roadmap` は `List[RoadmapItem]` (pydantic) または `List[dict]`。`plant_from_roadmap` の `_get()` ヘルパーが両対応済み。

---

## 検証項目 (手動確認含む)

| 項目 | 確認方法 |
|---|---|
| フラグ OFF で DB 副作用なし | `FORESHADOW_PLANTING=0` で Bible 生成 → `foreshadowings` テーブル行数不変 |
| フラグ ON で伏線行ができる | `FORESHADOW_PLANTING=1` で Bible 生成 → `foreshadowings` に行追加 |
| 冪等性 | 同一 roadmap で 2 回 Bible 生成 → 行数増えない |
| KPI 増加 | `foreshadowing_planted_total` メトリクスが設置数だけ増える |
| 既存 Bible 生成テスト通過 | `test_bible_service.py` 全 pass |

---

## ファイル変更まとめ

| ファイル | 変更内容 |
|---|---|
| `src/services/bible_service.py` | 2 箇所にフック追加 (上記 P0-1-a, P0-1-b) |

**推定行数**: 約 30〜40 行 (try/except/import 含む)

---

## 次の AI への引き継ぎ事項

1. **worktree は `E:\autonovel_qa` を使うこと** (`E:\autonovel` は他プロセスが使用中)
2. 既存実装はコミット済み (`a26f3c0`, `d59df76`) — 変更不要
3. `bible_service.py` に imports だけ入っている (working tree 変更)
4. **フックを 2 箇所に追加するだけ**でパイプライン完成
5. テストコマンドは上記の通り
6. 完了後 `git add src/services/bible_service.py && git commit -m "feat(bible): 伏線自動設置フックを追加 (P0統合)"`