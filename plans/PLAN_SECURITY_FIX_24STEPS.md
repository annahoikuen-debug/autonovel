# PLAN: AutoNovel セキュリティ・課金・タスク状態 緊急整改計画（SECURITY-FIX-24STEPS）

**対象ブランチ**: `main` / `develop`（HEAD `0e29468b`）
**策定日**: 2026-11-13（コードレビュー実施に基づく）
**対象件数**: CRITICAL 2 / HIGH 15 / MEDIUM 18（レビュー内主要分類）

## 5 原則（既存計画と整合）

| # | 原則 | 理由 |
|---|---|---|
| P1 | 各ステップは単一ファイル（または単一機能）の変更 + テスト追加で完結し、完了時に関連テストが全緑であること | 並行セッションとの競合と回帰を最小化する |
| P2 | 「実装で直す」を第一選択。allowlist / 機能フラグによる目隠しは理由付き TODO のみ許可 | 既存 allowlist が marketing/collab IDOR を許した前科あり |
| P3 | 生成物（openapi.json / api.generated.ts / var/* / docs/*）は変更時に必ず再生成し差分を確認 | 未再生成は別ゲートで落ちる |
| P4 | コミット前に `git status` / `git log -3` / `tests/security` 実行して並行セッションとの競合を検知 | 直前の外部コミットが契約テストを壊した前科あり |
| P5 | 各 Phase は自分の検証コマンドが green になるまで次へ進まない | 「動くはず」の確認を怠らない |

## 対象サマリ（レビュー結果から）

| セク | 件数 | 代表項目 |
|---|---|---|
| Phase 1: CRITICAL 課金・所有権 | 2 | C1 export-with-data 無認証所有権無し書き換え / C2 `response.choices[0].usage` AttributeError（課金済みトークン廃棄） |
| Phase 2: HIGH セキュリティ | 6 | H1 SSRF＋APIキー流出 / H2-H3 editor/marketing IDOR / H4 Huey pickle RCE / H5 settings.toml キー永続化 / H6 SSE 401 / H7 localStorage 密鑰平文 |
| Phase 3: HIGH 課金・タスク状態 | 5 | H8 クレジット返金 dead code / H9 task_id 不在でDB行が永遠running / H10 DAG Huey署名不整合 / H11 Outbox 二重死 / H12 zombie復旧 TOCTOU |
| Phase 4: HIGH その他 | 4 | H13 asset_pack generate_pack クラッシュ / H14 エクスポート書き出しパス無害化 / H15 novel.py 二重依存 / H13 重複を含む |
| Phase 5: MEDIUM 選択 | 5 | コスト（max_tokens欠如/集計0/ダミーキー/クレジット未消費）、テナント分離（グローバル状態）、開発メトリ露出、Gemini空レスポンス、非スレッド安全 |
| Phase 6: 監視・追加検証 | 1 | リグレッションテストスイートの統合実行と CI 追従 |

## 全体マップ

```
Phase 1: 課金・所有権 CRITICAL  (Steps  1-2)
Phase 2: セキュリティ HIGH      (Steps  3-8)
Phase 3: 課金・タスク状態 HIGH   (Steps  9-13)
Phase 4: HIGH その他              (Steps 14-16)
Phase 5: MEDIUM 選択             (Steps 17-21)
Phase 6: 監視・統合テスト        (Steps 22-24)
```

各ステップの「完了条件」は「該当する回帰テストが全緑」とする。

---

## Phase 1: 課金・所有権 CRITICAL（Steps 1-2）

### Step 1: C1 `POST /easy_mode/export-with-data` に認証＋所有権検証を追加

**背景**: `src/backend/routers/easy_mode.py:633-710` は `get_current_user` / `verify_book_ownership` を欠き、任意の `book_id` で他人の本（タイトル・ジャンル・本文）を上書き可。兄弟エンドポイント `GET /export/{book_id}`（447行目）は両方実装済み。

**手順**:
1. `easy_mode.py` の `export_with_data_endpoint` に `current_user: User = Depends(get_current_user)` を追加
2. DB永続化の直前または直後に `verify_book_ownership(book_id, current_user)` を呼び出す
3. 戻り値のレスポンスボディ（ZIP生成）も `verify_book_ownership` で対象ブックを限定（生成元データの読み取りも所有者のみ）

**完了条件**:
- `tests/security/test_easy_mode_export_with_data_ownership.py` が緑（下記テスト新規作成）

**リグレッションテスト（新規作成）**:
```python
# tests/security/test_easy_mode_export_with_data_ownership.py
from fastapi.testclient import TestClient
from src.backend.server import app
from tests.security.conftest import make_user, authenticate, create_book_for_user
import pytest

client = TestClient(app)

def test_export_with_data_rejects_unauthenticated():
    """認証なしでは 401 を返す（F1）。"""
    resp = client.post("/easy_mode/export-with-data", json={
        "book_id": 999, "title": "x", "genre": "x", "current_text": "x",
    })
    assert resp.status_code == 401

def test_export_with_data_rejects_cross_tenant():
    """他人の book_id では 403 を返す（F1）。"""
    owner = make_user("owner@example.com")
    victim = make_user("victim@example.com")
    book = create_book_for_user(owner, title="Victim Book")
    token_victim = authenticate(victim)
    resp = client.post("/easy_mode/export-with-data", json={
        "book_id": book.id, "title": "Hacked", "genre": "x", "current_text": "x",
    }, headers={"Authorization": f"Bearer {token_victim}"})
    assert resp.status_code == 403

def test_export_with_data_allows_owner():
    """本人の book_id では 200 / 201 を返す（正常系回帰）。"""
    owner = make_user("owner2@example.com")
    book = create_book_for_user(owner, title="My Book")
    token_owner = authenticate(owner)
    resp = client.post("/easy_mode/export-with-data", json={
        "book_id": book.id, "title": "My Book", "genre": "x", "current_text": "x",
    }, headers={"Authorization": f"Bearer {token_owner}"})
    assert resp.status_code in (200, 201)
```

**検証コマンド**:
```bash
pytest tests/security/test_easy_mode_export_with_data_ownership.py -q --timeout=120
```

---

### Step 2: C2 `response.choices[0].usage` → `response.usage`（OpenAI互換クライアント）

**背景**: `src/llm/clients/openai.py:168` は SDK 3.42.1 で `Choice` に `usage` 属性がなく、`AttributeError` で必ず失敗。`retry_decorator.py:184` が AttributeError を fail-fast にするため、課金済みトークンが毎回廃棄される。

**手順**:
1. `src/llm/clients/openai.py` の `usage_metadata = response.choices[0].usage` を `usage_metadata = getattr(response, "usage", None)` に変更
2. `response.choices[0]` への IndexError も gating（空 choices 対策）
3. `MockUsage` への代入経路を保持（既存コスト集計と互換）

**完了条件**:
- `tests/unit/llm/test_openai_client_usage_field.py` が緑（モックではなく実際の SDK 構造を模擬した response オブジェクト）

**リグレッションテスト（新規作成）**:
```python
# tests/unit/llm/test_openai_client_usage_field.py
from openai.types.chat import ChatCompletion, Choice, ChatCompletionMessage
from src.llm.clients.openai import OpenAIApiClient
import pytest

class _FakeClient:
    class chat:
        class completions:
            @staticmethod
            async def create(**kwargs):
                return ChatCompletion(
                    id="cmpl_test",
                    choices=[Choice(finish_reason="stop", index=0, message=ChatCompletionMessage(role="assistant", content="ok"))],
                    created=1, model="gpt-4o-mini",
                    object="chat.completion",
                    usage=None,  # top-level usage absent: client must not crash
                )

@pytest.mark.asyncio
async def test_no_attribute_error_when_usage_absent(monkeypatch):
    """choices[0].usage に触れず、top-level usage なしでもクラッシュしない（C2）。"""
    client = OpenAIApiClient(api_key="sk-test", base_url="http://x")
    client._clients = {}
    monkeypatch.setattr(client, "_get_client", lambda *a, **k: _FakeClient())
    result = await client.generate_text([{"role": "user", "content": "hi"}])
    assert result is not None
```

**検証コマンド**:
```bash
pytest tests/unit/llm/test_openai_client_usage_field.py -q
```

---

## Phase 2: セキュリティ HIGH（Steps 3-8）

### Step 3: H1 `llm_config.base_url` の SSRF＋APIキー流出を遮断

**背景**: `src/llm/adapters/factory.py:55` と `openai.py:29-52` はユーザー指定 `base_url` を無検証で使用。`api_key` 未指定時、`settings.OPENAI_API_KEY` が攻撃者管理ホストに `Authorization: Bearer` で送出される。

**手順**:
1. `src/llm/adapters/factory.py` に `BASE_URL_ALLOWLIST`（公開ドメインのみ、または `localhost` は開発環境のみ）を定義
2. `base_url` が `http://169.254.169.254` 等のメタデータ IP / プライベート IP / 内部ホスト名に一致する場合は 400 を返す
3. `base_url` を指定し `api_key` を指定しない場合（サーバーキー流出リスク）は拒否するか、明示的オプトインフラグを要求

**完了条件**:
- `tests/unit/llm/test_base_url_ssrf_guard.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/llm/test_base_url_ssrf_guard.py
from src.llm.adapters.factory import create_openai_adapter  # 関数名は実装に合わせる
import pytest

def test_private_ip_base_url_rejected():
    """169.254.169.254 や 10.x/192.168.x は拒否（H1）。"""
    with pytest.raises(ValueError, match="base_url"):
        create_openai_adapter(provider="openai", base_url="http://169.254.169.254/latest/meta-data/")

def test_base_url_without_api_key_rejected():
    """base_url 指定時に api_key 未指定ならサーバーキー流出を防ぐ（H1）。"""
    with pytest.raises(ValueError, match="api_key"):
        create_openai_adapter(provider="openai", base_url="https://attacker.example.com/v1")

def test_public_base_url_allowed():
    """通常の公開エンドポイントは通る（正常系回帰）。"""
    adapter = create_openai_adapter(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-test")
    assert adapter is not None
```

**検証コマンド**:
```bash
pytest tests/unit/llm/test_base_url_ssrf_guard.py -q
```

---

### Step 4: H2-H3 `editor.py` / `marketing.py generate` に所有権検証を追加

**背景**:
- `src/backend/routers/editor.py:60-127`: `ask-bible` / `audit-consistency` / `next-beats` が `req.book_id` の所有権を検証せず、他人の bible/本文を読み取り可
- `src/backend/routers/marketing.py:19-50`: `/api/marketing/generate` が `verify_book_ownership` を import しているが呼び出さず、他人 book_id で LLM ワークフロー実行可

**手順**:
1. `editor.py` の 3 ハンドラに `verify_book_ownership(req.book_id, current_user)` を追加
2. `marketing.py` の `generate_marketing` に `verify_book_ownership(req.book_id, current_user)` を追加
3. `graph.py` の `_require_book_scope` パターン（fail-closed）を参照して実装品質を揃える

**完了条件**:
- `tests/security/test_editor_book_id_ownership.py` / `tests/security/test_marketing_generate_ownership.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/security/test_editor_book_id_ownership.py (代表)
from fastapi.testclient import TestClient
from src.backend.server import app
client = TestClient(app)

def test_editor_ask_bible_rejects_cross_tenant():
    owner = make_user("e_owner@example.com")
    victim = make_user("e_victim@example.com")
    book = create_book_for_user(owner)
    token_v = authenticate(victim)
    resp = client.post("/api/editor/ask-bible", json={"book_id": book.id, "question": "..."}, headers={"Authorization": f"Bearer {token_v}"})
    assert resp.status_code == 403

def test_editor_ask_bible_allows_owner():
    resp = client.post("/api/editor/ask-bible", json={"book_id": book.id, "question": "..."}, headers={"Authorization": f"Bearer {authenticate(owner)}"})
    assert resp.status_code == 200
```

**検証コマンド**:
```bash
pytest tests/security/test_editor_book_id_ownership.py tests/security/test_marketing_generate_ownership.py -q --timeout=120
```

---

### Step 5: H4 Huey ペイロードの pickle RCE を JSON シリアライザに移行

**背景**: `src/backend/tasks/huey.py:16-41` は `RedisHuey` / `SqliteHuey` にシリアライザを設定せず、デフォルト pickle。Redis/SQLite ファイルへの書き込み権限があればワーカーで任意コード実行。`llm_config.api_key` や生オブジェクトがキューに平文永続化される。

**手順**:
1. `huey.py` に `huey = RedisHuey(..., serializer=JSONSerializer())`（または `SignedSerializer`）を設定
2. ペイロードに `api_key` を含まないよう `easy_mode.py` / `orchestrated.py` のタスクパラメータから `llm_config.api_key` を除外（またはトークン参照に変更）
3. 既存キュー互換性のため、シリアライザ変更後の既存キュー項目は空にするマイグレーション手順を docs に残す

**完了条件**:
- `tests/unit/tasks/test_huey_json_serializer.py` が緑（pickle ではなく JSON でラウンドトリップされる）

**リグレッションテスト（新規作成）**:
```python
# tests/unit/tasks/test_huey_json_serializer.py
from src.backend.tasks.huey import huey
import json

def test_huey_uses_json_not_pickle():
    """Huey のシリアライザが pickle ではなく JSON である（H4）。"""
    ser = huey.serializer
    # pickle.loads を使わない
    assert type(ser).__name__ != "PickleSerializer"
    data = ser.serialize({"task_id": "abc", "book_id": 1})
    json.loads(data)  # JSON として復元できる

def test_task_payload_excludes_api_key():
    """タスクパラメータに api_key を含まない（H4/H5の一部）。"""
    # 実装に合わせて、params 構築箇所を検査するテストを追加
    ...
```

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_huey_json_serializer.py -q
```

---

### Step 6: H5 APIキーを git追跡ファイル `config/settings.toml` に永続化しない

**背景**: `src/infrastructure/config/project_context.py` は `GlobalConfigModel`（`openai_api_key` 含む）を `config/settings.toml` に書き出し、かつファイルが `git ls-files` で追跡済み。キー設定後の persist で秘密鍵がリポジトリにコミットされ得る。

**手順**:
1. `config/settings.toml` を `.gitignore` に追加（既に追跡済みなら `git rm --cached` + コミット）
2. `project_context.py` の `update()` / `_persist_to_toml()` で `openai_api_key` 等の `*_api_key` フィールドを永続化対象から除外（または環境変数のみに限定）
3. `set_setting()` の `logger.info(f"key = {value!r}")` をマスク化（値を出力しない）

**完了条件**:
- `git ls-files | grep settings.toml` が空
- `tests/regression/test_settings_toml_not_tracked.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/regression/test_settings_toml_not_tracked.py
import subprocess
from pathlib import Path

def test_settings_toml_not_git_tracked():
    """config/settings.toml が git 追跡下にない（H5）。"""
    result = subprocess.run(["git", "ls-files", "config/settings.toml"], capture_output=True, text=True)
    assert result.stdout.strip() == ""

def test_update_excludes_api_keys(monkeypatch, tmp_path):
    """GlobalConfig.update() が openai_api_key を toml に書き出さない（H5）。"""
    ...
```

**検証コマンド**:
```bash
pytest tests/regression/test_settings_toml_not_tracked.py -q
```

---

### Step 7: H6 クラッシュリカバリ SSE に認証トークンを付与（401 不整合の解消）

**背景**: `frontend/src/api/orchestratedApi.ts:56-71` の `EventSource` は Authorization ヘッダを送れず、バックエンド `orchestrated.py:239` は `get_current_user` 必須 → 常に 401。既存の正解パターン（60秒ブックスコープ stream token）を適用。

**手順**:
1. バックエンド `orchestrated.py` の `/events/{correlation_id}` にストリームトークン検証を追加（または `get_current_user` をクエリパラメータのトークン検証に置き換え）
2. フロント `orchestratedApi.ts` で `buildStreamUrl` / `fetchStreamToken` パターンを適用し、`?token=...` を付与
3. `useUnifiedStreaming.ts` に `onError` コールバックを渡し、接続失敗をユーザーに通知

**完了条件**:
- `tests/security/test_orchestrated_sse_stream_token.py`（バックエンド）が緑
- フロント `vitest` で `subscribeToAgentEvents` にトークン付与がテストされる

**検証コマンド**:
```bash
pytest tests/security/test_orchestrated_sse_stream_token.py -q --timeout=120
cd frontend && npm run test:ci -- --run src/api/orchestratedApi.test.ts
```

---

### Step 8: H7 フロントの JWT と LLM API キーを httpOnly Cookie / 非永続化へ移行

**背景**: `frontend/src/context/NovelContext.tsx:189-199` は `llmConfig`（`api_key` 含む）を `localStorage` に平文保存。JWT も `auth_token` で localStorage。XSS 1件で両方窃取。

**手順**:
1. バックエンド認証レスポンスで JWT を `httpOnly; Secure; SameSite=Strict` Cookie に移行（段階的：まずオプトイン、デフォルトは localStorage のまま、段階的に移行）
2. `NovelContext.tsx` の `autonovel_llm_config` 保存を sessionStorage または非保存に変更。APIキーは毎回入力またはメモリ保持のみ
3. `AuthContext.tsx` の raw `fetch` を `apiFetch` に統一し、30sタイムアウトと 401→`clearAuthToken()` を適用

**完了条件**:
- `tests/frontend/...vitest...` で `autonovel_llm_config` への `localStorage.setItem` が呼ばれない（または sessionStorage に変更）ことを確認
- バックエンド Cookie 認証の統合テストが緑

**検証コマンド**:
```bash
cd frontend && npm run test:ci -- --run src/context/NovelContext.test.ts
pytest tests/security/test_auth_cookie_httponly.py -q --timeout=120
```

---

## Phase 3: 課金・タスク状態 HIGH（Steps 9-13）

### Step 9: H8 クレジット返金の UnboundLocalError を修正し失敗時必ず返金する

**背景**: `src/backend/tasks/generation_tasks.py:425` は `credit_service = None` を関数ローカルとし、`else` ブランチ内の `_deduct()` クロージャでのみ代入。課金成功後に生成が失敗すると `credit_service is not None` で `UnboundLocalError` が発生し、返金ブロックが不発。課金されて返金されない。

**手順**:
1. `credit_service` を関数スコープで初期化（`credit_service = None` を `_deduct` 外に置く、または `nonlocal` 宣言）
2. `credits_deducted and user_id is not None` なら、`credit_service` の有無によらず返金セッションを立てて `grant_credits` を実行
3. 返金自体の例外はログのみで、元の失敗エラーをマスクしない

**完了条件**:
- `tests/unit/tasks/test_credit_refund_on_failure.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/tasks/test_credit_refund_on_failure.py
from unittest.mock import AsyncMock, patch
from src.backend.tasks.generation_tasks import generate_chapter_task

@pytest.mark.asyncio
async def test_refund_credits_when_generation_fails_after_deduction():
    """課金済みで生成失敗時、返金が呼ばれる（H8）。"""
    with patch("...CreditService") as mock_cs, patch.object(generate_chapter_task, "_run_async", side_effect=Exception("boom")):
        mock_cs.return_value.deduct_credits = AsyncMock()
        mock_cs.return_value.grant_credits = AsyncMock()
        await generate_chapter_task({"book_id": 1, "task_id": "t1", ...})
        mock_cs.return_value.grant_credits.assert_called_once()
        call_kwargs = mock_cs.return_value.grant_credits.call_args.kwargs
        assert call_kwargs["transaction_type"] == "refund"
```

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_credit_refund_on_failure.py -q
```

---

### Step 10: H9 タスク投入前に task_id を付与しDB行を先に作成する

**背景**: `easy_mode.py:405-426` は Huey に投入してから `task_result.id` を取得し `params["task_id"]` に書き戻すが、Huey は投入時に引数をシリアライズするためワーカー側 `task_id=None`。DB行は投入後に作成されるため、ワーカーは `_update_task_in_db` をスキップし、行は永遠に "running"。

**手順**:
1. Huey 投入前に `huey_task_id` を生成（UUID等）、`params["task_id"]` に設定した上で投入
2. `repo.create_task_async(task_id=..., status="running", ...)` を投入**前**（または投入とほぼ同時に）実行し、ワーカーが更新対象行を持つ
3. `orchestrated.py` も同様に修正

**完了条件**:
- `tests/unit/tasks/test_task_row_created_before_worker_runs.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/tasks/test_task_row_created_before_worker_runs.py
from unittest.mock import patch, AsyncMock
from src.backend.routers.easy_mode import export_with_data_endpoint  # 関数名は実装に合わせる

def test_task_id_in_payload_before_enqueue():
    """Huey投入前に params に task_id が入っている（H9）。"""
    captured = {}
    with patch("src.backend.tasks.generation_tasks.generate_chapter_orchestrated_task", side_effect=lambda **kw: captured.update(kw) or type("R", (), {"id": "huey-1"})()):
        await export_with_data_endpoint(...)
    assert captured.get("task_id") == "huey-1"  # 投入時点で task_id 付与
```

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_task_row_created_before_worker_runs.py -q
```

---

### Step 11: H10 DAG Huey タスク署名の不整合を修正

**背景**: `src/backend/tasks/dag_scheduler.py:394-399` は `execute_agent_node_task(func_name=..., kwargs=..., node_id=...)` で投入。ワーカー `src/backend/tasks/huey.py:46` は `(node_name, payload)`。実行時に `TypeError: unexpected keyword argument` で必ず失敗し、2回リトライ後も失敗。

**手順**:
1. `dag_scheduler.py` の投入呼び出しを `execute_agent_node_task(node_name=task_node.func_name, payload=clean_kwargs)` に統一
2. `clean_kwargs` に `task_node.task_id` を含めるか、別途ペイロードにマージ

**完了条件**:
- `tests/unit/tasks/test_dag_huey_signature_matches_worker.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/tasks/test_dag_huey_signature_matches_worker.py
import inspect
from src.backend.tasks.huey import execute_agent_node_task
from src.backend.tasks.dag_scheduler import DAGScheduler

def test_dag_scheduler_calls_huey_with_worker_signature():
    """DAGスケジューラが Huey ワーカーの (node_name, payload) 署名に合わせて投入する（H10）。"""
    sig = inspect.signature(execute_agent_node_task)
    assert list(sig.parameters) == ["node_name", "payload"]
    # DAGScheduler 内部の投入コードを AST で検査し、キーワード名が一致することを確認
    ...
```

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_dag_huey_signature_matches_worker.py -q
```

---

### Step 12: H11 Outbox パイプラインを有効化（ステージング＋配送）

**背景**: `src/backend/tasks/__init__.py:73-87` はイベントを `done` にマークするだけで `process_vector_event` を呼ばない。`UnitOfWork.stage_chroma_add/delete` の呼び出し元もゼロ。Outbox パターンが no-op で RAG/Chroma 同期が黙って失敗。

**手順**:
1. `uow.py` の `stage_chroma_add/delete` を呼び出す箇所（RAG インデックス更新時等）を特定し、コールを復活
2. `process_outbox_events` プロセッサで `mark_outbox_event_processed` の**前**に `process_vector_event`（`store.add_documents` / `delete_by_id`）を実行
3. 失敗時は `done` にせず `retry` / `failed` 状態にし、メッセージを保持

**完了条件**:
- `tests/unit/tasks/test_outbox_process_dispatches_before_done.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/tasks/test_outbox_process_dispatches_before_done.py
from unittest.mock import AsyncMock, patch
from src.backend.database.uow import UnitOfWork

@pytest.mark.asyncio
async def test_outbox_event_dispatched_before_marked_done():
    """Outboxイベントは mark_done より先に vector へ配送される（H11）。"""
    with patch("...process_vector_event", new_callable=AsyncMock) as mock_dispatch:
        await process_outbox_events()
        # dispatch が呼ばれてから mark_done が呼ばれる順序を確認
        assert mock_dispatch.call_count > 0
```

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_outbox_process_dispatches_before_done.py -q
```

---

### Step 13: H12 Zombie復旧の TOCTOU とマルチワーカー heartbeat 問題を修正

**背景**: `worker_recovery.py` は全ワーカーが全 running タスクの heartbeat を更新し、`detect_zombie_tasks` は `heartbeat_at` だけで判定 → 生きているワーカーが1つあれば死んだワーカーのタスクは永遠に復旧されない。検知とリセットが別セッションの TOCTOU で完了済みタスクを再実行し得る。

**手順**:
1. `task_wal_logs` に `worker_id` カラムを追加（マイグレーション）し、heartbeat 更新は自分のタスクのみに限定
2. `detect_zombie_tasks` とリセットを単一トランザクションの `UPDATE ... WHERE state='running' AND heartbeat_at < X` にまとめる
3. `/api/tasks/admin/recover` と `_recovery_loop` の同時実行に排他ロックを追加

**完了条件**:
- `tests/unit/tasks/test_zombie_recovery_no_double_execute.py` が緑
- マイグレーションファイルが `alembic upgrade head` で適用される

**検証コマンド**:
```bash
pytest tests/unit/tasks/test_zombie_recovery_no_double_execute.py -q
alembic upgrade head
```

---

## Phase 4: HIGH その他（Steps 14-16）

### Step 14: H13 `asset_pack.generate_pack` の `create_ebook_exporter` シグネチャ不整合を修正

**背景**: `src/easy_mode/phase3/asset_pack.py:88`（と438）は `create_ebook_exporter(self.genre, self.preset)` を呼び出すが、正シグネチャは `(EbookMetadata, output_dir: Path)`。`multimedia_service.py:383` には修正済みの正解実装があるが波及しておらず、Phase3アセットパック生成は常に `AttributeError` でクラッシュ。

**手順**:
1. `asset_pack.py` の `_init_components` を `EbookMetadata(title=series.title, genre=...)` を生成して渡す形に修正
2. 438行目の `_generate_ebooks` も同様に修正

**完了条件**:
- `tests/unit/easy_mode/test_asset_pack_generate_pack_does_not_crash.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/easy_mode/test_asset_pack_generate_pack_does_not_crash.py
from src.easy_mode.phase3.asset_pack import AssetPackGenerator

def test_generate_pack_does_not_raise_attribute_error():
    """create_ebook_exporter に正しい引数を渡し、AttributeError を出さない（H13）。"""
    gen = AssetPackGenerator(genre="fantasy", preset="default")
    series = SeriesResult(title="T", episodes=[...])
    # output_dir は tmp_path を使う
    ...
```

**検証コマンド**:
```bash
pytest tests/unit/easy_mode/test_asset_pack_generate_pack_does_not_crash.py -q
```

---

### Step 15: H14 エクスポート書き出しパスにパス無害化を追加（Path Traversal対策）

**背景**: `src/backend/multimedia_service.py:397-412` 等は `out_dir / f"{series.title}_ep{...}.{fmt}"` を無害化せず書き出し。読み取り側は `_safe_path_under_base` で完璧にガード済みなのに書き出し側が無防備。タイトルに `../` が入ると出力ディレクトリ外への書き出し（制限付き任意ファイル書き込み）。日本語タイトルの `/` でもクラッシュ。

**手順**:
1. `multimedia_service.py`, `asset_pack.py`, `ebook_export.py` の書き出しパス生成に `sanitize_filename(title)` を適用（`..` `/` 除去または置換）
2. `series.title` は DB（`POST /books`）からのユーザー制御値であることを前提に、書き出し直前に無害化

**完了条件**:
- `tests/unit/export/test_export_path_sanitization.py` が緑

**リグレッションテスト（新規作成）**:
```python
# tests/unit/export/test_export_path_sanitization.py
from pathlib import Path
import tempfile

def test_title_with_dotdot_does_not_escape_output_dir():
    """タイトル '../evil' でも書き出し先は output_dir 内に留まる（H14）。"""
    with tempfile.TemporaryDirectory() as out_dir:
        base = sanitize_filename("../evil") + "_ep1.epub"
        path = Path(out_dir) / base
        assert path.resolve().parent == Path(out_dir).resolve()
        path.write_bytes(b"x")
        assert path.exists()
```

**検証コマンド**:
```bash
pytest tests/unit/export/test_export_path_sanitization.py -q
```

---

### Step 16: H15 `novel.py` の二重依存とプロジェクトID無視を修正

**背景**: `src/backend/routers/novel.py:51-56` は `get_current_user` と `require_api_key` の両方必須 → JWTユーザーは自分のタスクを停止不可。`produce` は `project_id=1` ハードコードでレート制限なし。`status/episodes/report` は `project_id` を無視しグローバルプロデューサー状態を返す。

**手順**:
1. `novel.py` の `produce` / `stop_task` から `require_api_key` を外し、`get_current_user` のみにする（APIキー保持者は別経路で管理オペレーション）
2. `get_novel_status` 等で `project_id` を使用し、所有権を検証
3. `DELETE /easy_mode/task/{task_id}` に所有権検証を追加（APIキー保持者が他人のタスクを削除できないよう）

**完了条件**:
- `tests/unit/routers/test_novel_ownership_and_project_id.py` が緑

**検証コマンド**:
```bash
pytest tests/unit/routers/test_novel_ownership_and_project_id.py -q --timeout=120
```

---

## Phase 5: MEDIUM 選択（Steps 17-21）

### Step 17: LLM コスト制御（max_tokens / 集計0 / ダミーキー / クレジット未消費）

**背景**:
- `src/llm/clients/openai.py:130-138` と `gemini.py:332-336` に `max_tokens` / `max_output_tokens` なし
- `src/core/llm_gateway.py:155-158` は `prompt_tokens` ではなく `prompt_token_count` を参照し、常に0集計
- `src/llm/clients/openai.py:74` は未設定時に `"dummy"` をリモート OpenRouter に送信
- editor/viral-titles等でクレジット消費なし（IP制限のみ）

**手順**:
1. OpenAI/Gemini エンジンクライアントに `max_tokens=2000`（設定可能）を追加
2. `LLMGateway._usage_metric` を `prompt_token_count` / `candidates_token_count` に合わせる
3. `factory.py` で `api_key` 未指定＋`base_url` 指定時は拒否（Step 3 と整合）
4. `editor.py` / `marketing_ctr.py` 等にクレジット消費を追加、または明示的に「無料枠」と文書化

**完了条件**:
- `tests/unit/llm/test_max_tokens_and_cost_accounting.py` が緑

---

### Step 18: テナント分離（グローバル状態のスコープ化）

**背景**: `agent_memory` / `dashboard` / `conflicts` / `subtext` がグローバル状態を読み書きし、他テナントのデータを読み・共有YAMLを書き換え可。

**手順**:
1. 各 router に `current_user` / `verify_book_ownership` を追加し、ストレージに `user_id` または `book_id` スコープを導入
2. `subtext.py` の YAML書き込みをユーザー/ブックスコープのファイルまたはDBに移行

**完了条件**:
- `tests/security/test_global_state_tenant_isolation.py` が緑

---

### Step 19: 開発メトリ・ドキュメント露出の本番制限

**背景**: `/metrics` `/docs` `/openapi.json` が本番でも公開。`/api/system/models/info` がプロバイダ設定を任意ユーザーに開示。

**手順**:
1. `auth_middleware.py` の `PUBLIC_EXACT_PATHS` から `/docs` `/redoc` `/openapi.json` を本番（APP_ENV=production）で除外
2. `/api/system/models/info` を admin/ロール制限、または設定有無のブール値を隠蔽

**完了条件**:
- `tests/security/test_production_hides_dev_endpoints.py` が緑

---

### Step 20: Gemini空レスポンスと非スレッド安全性の修正

**背景**: `gemini.py:292-297` は空レスポンスで `TypeError` fail-fast。`ExecutorManager` / リトライカウンタ / OpenAIクライアントキャッシュが非スレッド安全（FastAPI+Hueyマルチスレッドと不整合）。

**手順**:
1. `generate_text` に `generate_json` と同じ None ガードを追加
2. `ExecutorManager` とリトライカウンタにロックを追加。`_clients` キャッシュにもロック

**完了条件**:
- `tests/unit/llm/test_gemini_empty_response_retry.py` / `tests/unit/core/test_executor_manager_thread_safety.py` が緑

---

## Phase 6: 監視・統合テスト（Steps 22-24）

### Step 21: リグレッションテストスイートの統合とCI追従

**背景**: 本計画で新規作成したテストが分散しているため、実行エントリポイントを整理し、CI で必ず実行する。

**手順**:
1. `tests/security/` と `tests/unit/tasks/`、`tests/unit/llm/` の新規テストを `pytest` でまとめて実行するコマンドを Makefile に追加（`make test-security`）
2. `.github/workflows/ci.yml` の `test` ジョブに `make test-security` を追加（`continue-on-error: false`）
3. `tests/security/test_idor_regression.py` の `NO_OWNERSHIP_NEEDED` から `easy_mode` を削除（Step 1 で修正済みのため）

**完了条件**:
- `make test-security` が green
- CI の `test` ジョブが green

---

### Step 22: 完了条件チェックリスト（コミット前）

| 項目 | コマンド | 判定 |
|---|---|---|
| 全テスト | `pytest -q -m "not integration and not perf and not slow" --cov=src --cov-fail-under=60 --timeout=120` | green |
| セキュリティ | `pytest tests/security -q --timeout=120` | green |
| リグレッション | `pytest tests/regression/ -v --timeout=120` | green |
| フロント | `cd frontend && npm run test:ci` | green |
| 静的解析 | `make lint` | gate not increased |
| 型チェック | `make typecheck` | no new errors |
| マイグレーション | `alembic upgrade head` | 適用成功 |
| 並行競合 | `git status` / `git log -3` | 未コミット変更なし・HEAD確認 |

### Step 23: ドキュメント・生成物の再生成（P3）

| 生成物 | 再生成コマンド |
|---|---|
| `docs/openapi.json` | `make openapi` |
| `frontend/src/types/api.generated.ts` | OpenAPI 生成スクリプト |
| `var/import_graph.json` | `python scripts/generate_import_graph.py` |
| `CHANGELOG.md` | v7.0.x エントリ追加 |

### Step 24: コミット前の最終確認（P4）

```bash
git status --short
git log --oneline -5
pytest tests/security tests/regression/test_*.py -q --timeout=120
```

---

## 見積もり（目安）

| Phase | ステップ | 工数目安 |
|---|---|---|
| Phase 1 | Steps 1-2 | 0.5 人日 |
| Phase 2 | Steps 3-8 | 2 人日 |
| Phase 3 | Steps 9-13 | 2.5 人日 |
| Phase 4 | Steps 14-16 | 1 人日 |
| Phase 5 | Steps 17-20 | 2 人日 |
| Phase 6 | Steps 21-24 | 1 人日 |
| **合計** | **24 ステップ** | **約 9 人日** |

各ステップは独立してPRを切ることも可能。CRITICAL（Steps 1-2）は最優先でマージすること。


---

---

---

---
