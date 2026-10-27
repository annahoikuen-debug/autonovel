import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from src.backend.server import app
from src.backend.config import settings
from src.services.spine_resolver import resolve_spine

# ルーターを事前に含める
from src.backend.routers.plots import router
app.include_router(router)


def _expected_beats(total_eps: int = 20) -> int:
    """この API が返すべき beat 件数を Spine から導出する。

    `/api/plots/expand-beats` は「12件固定」を廃止し、構造テンプレート
    （Spine）が解決した beat 数だけ返す（src/backend/routers/plots.py:415-416）。
    したがって 12 という固定値をハードコードすると、Spine の話数設計を変えた
    だけで本テストが陳腐化する。期待値は常に実装と同じ权威ある源から導く。

    なおリクエストで `pattern_key` / `length_key` / `market_key` が省略された場合は
    エンドポイントが `exile_rise` / `web_volume` / `web` を既定値として使う。
    """
    return len(resolve_spine("exile_rise", "web_volume", "web", total_eps).beats)


@pytest.fixture(autouse=True)
def _auth_disabled(monkeypatch):
    """P2: 認証バイパスをテストスコープに限定（テスト終了後に自動復元）。

    モジュールレベルでの settings 書き換えは同一セッション内の後続テストに
    リークするため、monkeypatch でスコープを限定する。
    """
    monkeypatch.setattr(settings, "AUTH_DISABLED", True)


@pytest.mark.asyncio
async def test_expand_commercial_beats_success():
    """商業ビート生成APIの正常系テスト"""
    transport = ASGITransport(app=app)

    # LLMゲートウェイをモック
    with patch("src.backend.routers.plots.LLMGateway") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm

        # LLMの応答をモック（有効なJSON）
        mock_response = MagicMock()
        mock_response.story_content = '''[
            {"episode": 1, "title": "日常の崩壊", "outline": "主人公の平穏な日常が崩れる", "cliffhanger_type": "New Crisis", "sensory_focus": ["visual", "auditory"], "foreshadowing_notes": "不穏な予兆"},
            {"episode": 2, "title": "運命の告知", "outline": "使命が課せられる", "cliffhanger_type": "Shocking Truth", "sensory_focus": ["tactile", "metaphor"], "foreshadowing_notes": "古い予言"},
            {"episode": 3, "title": "覚悟の決意", "outline": "立ち向かうことを決意", "cliffhanger_type": "Quiet Foreshadowing", "sensory_focus": ["visual", "gustatory"], "foreshadowing_notes": "師匠の言葉"},
            {"episode": 4, "title": "最初の試練", "outline": "強敵と遭遇", "cliffhanger_type": "New Crisis", "sensory_focus": ["auditory", "olfactory"], "foreshadowing_notes": "敵の弱点"},
            {"episode": 5, "title": "力の代償", "outline": "肉体・精神に負荷", "cliffhanger_type": "Shocking Truth", "sensory_focus": ["tactile", "metaphor"], "foreshadowing_notes": "禁忌の存在"},
            {"episode": 6, "title": "仲間との絆", "outline": "拠点を確保", "cliffhanger_type": "Quiet Foreshadowing", "sensory_focus": ["visual", "auditory"], "foreshadowing_notes": "仲間の秘密"},
            {"episode": 7, "title": "無双の快進撃", "outline": "次々と強敵を薙ぎ倒す", "cliffhanger_type": "New Crisis", "sensory_focus": ["visual", "gustatory"], "foreshadowing_notes": "影の黒幕"},
            {"episode": 8, "title": "中間地点の真実", "outline": "衝撃の事実が判明", "cliffhanger_type": "Shocking Truth", "sensory_focus": ["olfactory", "metaphor"], "foreshadowing_notes": "世界の秘密"},
            {"episode": 9, "title": "追い詰められる", "outline": "逆襲が始まる", "cliffhanger_type": "New Crisis", "sensory_focus": ["auditory", "tactile"], "foreshadowing_notes": "最後の切り札"},
            {"episode": 10, "title": "全てを失って", "outline": "奈落の底へ", "cliffhanger_type": "Quiet Foreshadowing", "sensory_focus": ["visual", "metaphor"], "foreshadowing_notes": "過去の伏線回収"},
            {"episode": 11, "title": "闇夜の決意", "outline": "真の強さに目覚める", "cliffhanger_type": "Shocking Truth", "sensory_focus": ["tactile", "gustatory"], "foreshadowing_notes": "真の敵"},
            {"episode": 12, "title": "決戦の夜明け", "outline": "クライマックスへ", "cliffhanger_type": "Quiet Foreshadowing", "sensory_focus": ["visual", "auditory", "metaphor"], "foreshadowing_notes": "エピローグへ"}
        ]'''
        mock_llm.generate_text.return_value = mock_response

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/plots/expand-beats",
                json={
                    "title": "テスト作品",
                    "genre": "fantasy",
                    "synopsis": "テストあらすじ",
                    "target_chapters": 20,
                    "cheat_scale": 4,
                    "growth_curve": "最初からカンスト(無双)",
                    "system_assist": 70,
                    "cost_severity": 2,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            # LLM が 12 件返しても、Spine が決めた beat 数で切り詰められる
            assert len(data) == _expected_beats()
            assert data[0]["episode"] == 1
            assert data[0]["title"] == "日常の崩壊"
            assert data[0]["cliffhanger_type"] == "New Crisis"
            assert "visual" in data[0]["sensory_focus"]

            # 企画パラメータが LLM プロンプトへ確実に渡っていることの検証。
            # （旧テストは fallback 経路の `data[3]["outline"]` に "チート能力" を
            #  期待していたが、fallback は現在 Spine の duty を使うため
            #  その前提自体が陳腐化していた。反映経路を実装に即した形で固定する）
            prompt = mock_llm.generate_text.await_args.kwargs["prompt"]
            assert "【チート度 (1-5)】4" in prompt
            assert "【成長曲線】最初からカンスト(無双)" in prompt
            assert "【システム支援度 (0-100)】70" in prompt
            assert "【代償・リスク過酷度 (1-5)】2" in prompt


@pytest.mark.asyncio
async def test_expand_commercial_beats_llm_failure_returns_502():
    """LLM 呼び出し失敗は縮退せず 502 を返すことのテスト。

    意図として、LLM 障害・認証エラー・レート制限・タイムアウトを
    「縮退 beat」で握り潰すと、クライアントは「モデルが出力した」と
    「API キーが無効」を区別できなくなる。そのため 502 で失敗Berikut。
    （src/backend/routers/plots.py:422-430 の設計意図）

    したがって縮退（フォールバック）は LLM 障害ではなく
    「応答は得たが JSON 整形に失敗した」場合だけ起作用する。
    その経路は `test_expand_commercial_beats_edge_cases` が検証する。
    """
    transport = ASGITransport(app=app)

    # LLMゲートウェイをモック（例外を投げる）
    with patch("src.backend.routers.plots.LLMGateway") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.generate_text.side_effect = Exception("LLM Error")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/plots/expand-beats",
                json={
                    "title": "テスト作品",
                    "genre": "fantasy",
                    "synopsis": "テストあらすじ",
                    "target_chapters": 20,
                    "cheat_scale": 4,
                    "growth_curve": "最初からカンスト(無双)",
                    "system_assist": 70,
                    "cost_severity": 2,
                },
            )
            assert resp.status_code == 502
            assert "beat 生成に失敗" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_expand_commercial_beats_malformed_json_degrades():
    """整形失敗時は Spine 由来の縮退 beat を返すことのテスト。

    LLM 障害（502）とは区別して、「応答はбовьえたが JSON で壊れている」場合は
    縮退して 200 を返す契約を守る。
    """
    transport = ASGITransport(app=app)

    with patch("src.backend.routers.plots.LLMGateway") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        mock_response = MagicMock()
        mock_response.story_content = "これは JSON ではないただの文章です"
        mock_llm.generate_text.return_value = mock_response

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/plots/expand-beats",
                json={
                    "title": "テスト作品",
                    "genre": "fantasy",
                    "synopsis": "テストあらすじ",
                    "target_chapters": 20,
                    "cheat_scale": 4,
                    "growth_curve": "最初からカンスト(無双)",
                    "system_assist": 70,
                    "cost_severity": 2,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == _expected_beats()
            assert data[0]["episode"] == 1


@pytest.mark.asyncio
async def test_expand_commercial_beats_invalid_input():
    """不正な入力パラメータのテスト"""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 必須フィールド欠落
        resp = await client.post(
            "/api/plots/expand-beats",
            json={
                "genre": "fantasy",
            },
        )
        assert resp.status_code == 422  # Validation error

        # チート度が範囲外
        resp = await client.post(
            "/api/plots/expand-beats",
            json={
                "title": "テスト",
                "genre": "fantasy",
                "cheat_scale": 10,  # 範囲外
            },
        )
        assert resp.status_code == 422

        # 成長曲線が空
        resp = await client.post(
            "/api/plots/expand-beats",
            json={
                "title": "テスト",
                "genre": "fantasy",
                "growth_curve": "",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_expand_commercial_beats_edge_cases():
    """エッジケーステスト（極端な値、空の入力など）"""
    transport = ASGITransport(app=app)

    with patch("src.backend.routers.plots.LLMGateway") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        mock_response = MagicMock()
        mock_response.story_content = '[]'  # 空の配列
        mock_llm.generate_text.return_value = mock_response

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 最小限の入力
            resp = await client.post(
                "/api/plots/expand-beats",
                json={
                    "title": "最小",
                    "genre": "fantasy",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            # フォールバックが使われるため、Spine が解決した beat 件数が返る
            assert len(data) == _expected_beats()

            # 最大話数
            resp = await client.post(
                "/api/plots/expand-beats",
                json={
                    "title": "最大",
                    "genre": "fantasy",
                    "target_chapters": 100,
                    "cheat_scale": 5,
                    "system_assist": 100,
                    "cost_severity": 5,
                },
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_expand_commercial_beats_regression():
    """既存のビート生成ロジックに対するリグレッションテスト"""
    transport = ASGITransport(app=app)

    with patch("src.backend.routers.plots.LLMGateway") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        mock_response = MagicMock()
        mock_response.story_content = '''[
            {"episode": 1, "title": "Test", "outline": "Outline", "cliffhanger_type": "New Crisis", "sensory_focus": ["visual"], "foreshadowing_notes": "Note"}
        ]'''
        mock_llm.generate_text.return_value = mock_response

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 既存のエンドポイントが影響を受けないことを確認
            resp = await client.get("/api/plots/1")
            # 404または200（本の所有権チェックで失敗する可能性もあるが、エンドポイント自体は存在する）
            assert resp.status_code in (200, 404, 403)

            # 他のエンドポイントも確認
            resp = await client.post("/api/plots/plan_generation", json={"params": {}})
            # 422: PlanGenerationRequest は api_key 必須のためバリデーションエラーは正常
            assert resp.status_code in (200, 400, 401, 403, 422)
