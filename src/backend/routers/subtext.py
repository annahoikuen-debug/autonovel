"""
FastAPI Router for Writer Subtext Management (PLAN_Y1 Step 23, PLAN_Y2 Step 20, PLAN_Y3 Step 20).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import yaml

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.narrative.subtext_engine.engine import SubtextEngine
from src.narrative.subtext_engine.models import DialogueBlock, RewriteRuleModel, SubtextContext
from src.narrative.subtext_engine.rules import RegexRule
from src.narrative.subtext_templates.loader import TemplateLoader
from src.narrative.subtext_templates.renderer import TemplateRenderer
from src.narrative.subtext_tokens.expander import TokenExpander
from src.narrative.subtext_tokens.formatter import DialogueFormatter
from src.pipeline.generation import GenerationPipeline

logger = logging.getLogger("backend.routers.subtext")

router = APIRouter(prefix="/subtext", tags=["subtext"])

# Singleton instances for API
engine_instance = SubtextEngine.create_default()
template_loader = TemplateLoader()
template_renderer = TemplateRenderer(loader=template_loader)
token_expander = TokenExpander()
formatter_instance = DialogueFormatter(expander=token_expander)
pipeline_instance = GenerationPipeline(
    engine=engine_instance,
    renderer=template_renderer,
    formatter=formatter_instance,
)


class ProcessRequest(BaseModel):
    text: str = Field(..., description="Dialogue text to process")
    mode: str = Field(default="hybrid", description="rule, template, token, hybrid, off")
    context: Optional[SubtextContext] = None
    seed: Optional[int] = None


class ProcessResponse(BaseModel):
    original: str
    processed: str
    mode: str


# ==============================================================================
# 1. Rules API (PLAN_Y1 Step 23)
# ==============================================================================

@router.get("/rules", response_model=List[RewriteRuleModel])
async def list_rules() -> List[RewriteRuleModel]:
    rules = engine_instance.registry.list_rules()
    return [r.to_model() for r in rules]


@router.post("/rules", response_model=RewriteRuleModel, status_code=status.HTTP_201_CREATED)
async def create_or_update_rule(
    rule_model: RewriteRuleModel,
    _current_user: User = Depends(get_current_user),
) -> RewriteRuleModel:
    """ルールレジストリ（プロセス共有）を更新する。"""
    new_rule = RegexRule(
        rule_id=rule_model.id,
        pattern=rule_model.pattern,
        replacement=rule_model.replacement,
        name=rule_model.name,
        priority=rule_model.priority,
        final=rule_model.final,
        skip_if_matched=rule_model.skip_if_matched,
        enabled=rule_model.enabled,
        tags=rule_model.tags,
        description=rule_model.description,
    )
    engine_instance.registry.register(new_rule, overwrite=True)
    return new_rule.to_model()


# ==============================================================================
# 2. Templates API (PLAN_Y2 Step 20)
# ==============================================================================

class TemplateCreateRequest(BaseModel):
    id: str
    category: str = "general"
    content: str
    weight: int = 100
    tags: List[str] = Field(default_factory=list)


@router.get("/templates")
async def list_templates() -> Dict[str, Any]:
    templates = template_loader.load_all()
    return {
        "count": len(templates),
        "templates": [
            {
                "id": c.id,
                "category": c.metadata.category,
                "weight": c.metadata.weight,
                "tags": c.metadata.tags,
            }
            for c in templates.values()
        ],
    }


# 許可するテンプレートカテゴリ（ディレクトリ名は必ずこの中に限定する）
ALLOWED_TEMPLATE_CATEGORIES: frozenset[str] = frozenset(
    {
        "action",
        "betrayal",
        "comedy",
        "dialogue",
        "fallback",
        "general",
        "grief",
        "monologue",
        "narration",
        "power_play",
        "romance",
        "subtext",
    }
)

# テンプレート ID に使用を許可する文字（英数字・ドット・アンダースコア・ハイフン）
_TEMPLATE_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def _resolve_template_path(category: str, template_id: str) -> Path:
    """テンプレート書き込み先を `template_dir` 配下に限定して解決する。

    `category` は許可リストで検証し、テンプレート ID は英数字等に制限したうえで
    解決済みパスが base_dir の配下にあることを保証する。
    `Path.__truediv__` は右辺が絶対パスだと base を完全に捨ててしまうため、
    単純な `base / user_input` では base 配下から外れたパスを書けてしまう。
    """
    if category not in ALLOWED_TEMPLATE_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(ALLOWED_TEMPLATE_CATEGORIES)}",
        )
    if not _TEMPLATE_ID_RE.match(template_id):
        raise HTTPException(
            status_code=422,
            detail="id must be alphanumeric with '.', '_' or '-' only (max 128 chars)",
        )

    # ファイル名は従来どおり ID の最終セグメントを使う（既存テンプレートの命名規則に合わせる）
    segments = [p for p in template_id.split(".") if p]
    if not segments:
        raise HTTPException(status_code=422, detail="id must contain at least one name segment")
    stem = segments[-1]

    base = template_loader.template_dir.resolve()
    target = (base / category / f"{stem}.j2").resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid template path")
    return target


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    req: TemplateCreateRequest,
    _current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """サブテキストテンプレートを生成する。

    書き込み先は必ず `template_loader.template_dir` 配下に限定する。
    """
    target_file = _resolve_template_path(req.category, req.id)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = f"""---
id: {req.id}
category: {req.category}
tags: {req.tags}
weight: {req.weight}
---
{req.content}
"""
    target_file.write_text(frontmatter, encoding="utf-8")
    template_loader.load_all(force_reload=True)
    return {"status": "created", "id": req.id, "path": str(target_file)}


# ==============================================================================
# 3. Tokens API (PLAN_Y3 Step 20)
# ==============================================================================

class TokenPreviewRequest(BaseModel):
    text: str
    context: Optional[SubtextContext] = None
    seed: Optional[int] = 42


@router.get("/tokens")
async def get_token_dictionary() -> Dict[str, Any]:
    token_expander.load_dictionary()
    return token_expander._dict


@router.put("/tokens")
async def update_token_dictionary(
    content: Dict[str, Any],
    _current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """トークン辞書（プロセス共有）を更新する。"""
    token_expander._dict = content
    try:
        token_expander.dict_path.write_text(
            yaml.dump(content, allow_unicode=True), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"Failed to persist token dictionary: {e}")
    return {"status": "updated"}


@router.post("/tokens/preview")
async def preview_token_expansion(req: TokenPreviewRequest) -> Dict[str, Any]:
    expanded = token_expander.expand(req.text, context=req.context, seed=req.seed)
    return {"raw": req.text, "expanded": expanded}


# ==============================================================================
# 4. Master Process Endpoint
# ==============================================================================

@router.post("/process", response_model=ProcessResponse)
async def process_dialogue(
    req: ProcessRequest,
    _current_user: User = Depends(get_current_user),
) -> ProcessResponse:
    """台本をサブテキスト処理パイプラインに通す。"""
    pipeline_instance.set_mode(req.mode)
    res = pipeline_instance.process_text(req.text, context=req.context, seed=req.seed)
    return ProcessResponse(original=req.text, processed=res, mode=req.mode)
