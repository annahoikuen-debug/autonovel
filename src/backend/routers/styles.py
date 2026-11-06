"""Styles REST API Router（旧パス互換の配線 shim）。

TRACK-A8 / F3: ルーター実体は ``src/interfaces/api/styles.py`` にあり、
蒸留（/distill）エンドポイントは具象サービスを必要とするため、本モジュール
（旧レイヤー＝コンポジションルート）が ``StyleDistillerService`` を注入して
組み立てる。旧 import 経路 ``src.backend.routers.styles.router`` は
全パスを提供し続ける。
"""

from __future__ import annotations

from fastapi import APIRouter

from src.interfaces.api.styles import build_distill_router, router as styles_router
from src.publishing.formatters.style_distiller import style_distiller_service

# FastAPI 0.141+ の include_router は遅延展開 (_IncludedRouter) を持つため、
# 旧契約テスト (tests/contract/test_router_paths.py) が APIRoute を直接列挙
# できるよう、ルートをフラットに合成する。
router = APIRouter()
router.routes.extend(styles_router.routes)
router.routes.extend(build_distill_router(distiller=style_distiller_service).routes)

__all__ = ["router"]
