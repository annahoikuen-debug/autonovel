from __future__ import annotations
import json
import logging
import re
from typing import Any
from src.services.auditors.rule_based_metrics import (
    calculate_sentence_rhythm,
    calculate_dialogue_ratio,
    detect_ai_cliches,
    evaluate_cliffhanger_ending,
)
from src.models.unified_audit import UnifiedAuditReport, QualitativeAudit, ConflictItemSchema

logger = logging.getLogger(__name__)


def _resolve_audit_llm() -> Any:
    """監査用 LLM を設定から解決する。

    ``mock`` / 未設定の場合は ``None`` を返す。Mock の応答で品質ゲートを
    通過させてはならないため、意図的に実プロバイダのみを受け付ける。
    """
    try:
        from src.backend.config import settings
        from src.services.llm.factory import get_llm_adapter

        provider = (settings.LLM_PROVIDER or "").strip().lower()
        if provider in ("", "mock"):
            logger.warning(
                "LLM_PROVIDER=%r のため監査は実行されません（品質ゲートは"
                "degraded として不合格になります）。実プロバイダを設定してください。",
                provider or "(empty)",
            )
            return None
        return get_llm_adapter(provider)
    except Exception as e:
        logger.error("監査用 LLM の解決に失敗しました: %r", e)
        return None

class UnifiedAuditor:
    """二層ハイブリッド監査エンジン (v5.0 Hybrid-Lean)
    - 第1層: 静的ルール解析 (0ms, 0コスト)
    - 第2層: 単一LLMによる定性・キャラクター心理・プロット引き判定
    """

    def __init__(self, llm_gateway: Any = None):
        # 明示注入がなければ設定から実 LLM を解決する。
        # 4 つの本番呼び出し点がすべて引数なしで UnifiedAuditor() を生成しており、
        # これが未設定のままibatると llm=None → degraded → 品質ゲートが
        # 全章节で不合格になっていた。
        self.llm = llm_gateway if llm_gateway is not None else _resolve_audit_llm()

    async def _call_llm(self, prompt: str) -> str:
        """LLM 呼び出しを統一する。

        LLM 実装ごとにメソッド名が異なる（LLMGateway 系は ``generate``、
        ``*Adapter`` 系は ``generate_text``）。両方を受け付け、
        どちらにも無い場合は明示的な例外にする（黙って握り潰さない）。
        """
        if self.llm is None:
            raise RuntimeError("監査用 LLM が未設定です")

        for name in ("generate", "generate_text"):
            fn = getattr(self.llm, name, None)
            if callable(fn):
                try:
                    return await fn(prompt=prompt, temperature=0.2)
                except TypeError:
                    # temperature を位置引数で取らない実装への保険
                    return await fn(prompt)

        raise AttributeError(
            f"{type(self.llm).__name__} は generate / generate_text のどちらを"
            "持ってもいません。監査は実行できません。"
        )

    def audit_quantitative(self, text: str) -> tuple[float, dict[str, Any]]:
        """静的ルールベースの定量的スコア（0ms, 0コスト）を算出"""
        rhythm = calculate_sentence_rhythm(text)
        dialogue = calculate_dialogue_ratio(text)
        cliches = detect_ai_cliches(text)
        cliff = evaluate_cliffhanger_ending(text)

        # 静的スコアの加重平均
        score = (rhythm.score * 0.3) + (dialogue.score * 0.3) + (cliff * 0.4)
        if cliches:
            score = max(0.0, score - len(cliches) * 5.0)

        meta = {
            "rhythm_score": rhythm.score,
            "dialogue_ratio": dialogue.ratio,
            "cliches": cliches,
            "cliffhanger_score": cliff,
        }
        return score, meta

    async def audit_qualitative(
        self,
        text: str,
        character_profiles: str = "",
        plot_spec: str = "",
    ) -> QualitativeAudit:
        """LLMによる定性的評価を1回のみ実行（公開 API。署名は互換のため維持）"""
        qual, _degraded = await self._audit_qualitative_with_status(
            text, character_profiles, plot_spec
        )
        return qual

    async def _audit_qualitative_with_status(
        self,
        text: str,
        character_profiles: str = "",
        plot_spec: str = "",
    ) -> tuple[QualitativeAudit, bool]:
        """定性評価を実行し、(結果, 評価是否=degraded) を返す。

        degraded=True は「評価そのものが成立していない」ことを意味する
        （LLM 未設定 / 呼び出し失敗 / JSON パース失敗）。この場合 return される
        スコアは評価結果ではなくプレースホルダであり、降雨ゲートはこれを
        根拠に MUST fail-closed としなければならない。

        以前は失敗時も 70.0 を返し、総合ゲートが ``final >= 70.0`` だったため
        「LLM がタイムアウトした/認証失敗した/JSON が壊れた」章が
        ちょうど合格点ちょうどで承認されていた。
        """
        if self.llm is None:
            logger.error(
                "UnifiedAuditor: LLM が未設定のため定性評価を実施できません。"
                "監査結果は degraded（不合格）として扱われます。"
            )
            return self._failed_qualitative("LLM未設定のため定性評価を実施できません"), True

        from src.agents.prompts.unified_audit_prompt import UNIFIED_AUDIT_PROMPT_TEMPLATE

        prompt = UNIFIED_AUDIT_PROMPT_TEMPLATE.format(
            character_profiles=character_profiles or "主人公: 標準設定",
            plot_spec=plot_spec or "標準構成",
            draft_text=text[:3000],
        )
        try:
            resp = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"UnifiedAuditor LLM call failed: {e!r}")
            return self._failed_qualitative(f"LLM呼び出し失敗: {e}"), True

        try:
            json_match = re.search(r"\{.*\}", resp, re.DOTALL)
            if not json_match:
                raise ValueError("LLM 応答に JSON オブジェクトが含まれていません")
            data = json.loads(json_match.group(0))
            if not isinstance(data, dict):
                raise ValueError(f"JSON のトップレベルが dict ではありません: {type(data)!r}")
            return QualitativeAudit(**data), False
        except Exception as e:
            logger.error(f"UnifiedAuditor LLM response parse failed: {e!r}")
            return self._failed_qualitative(f"LLM応答パース失敗: {e}"), True

    @staticmethod
    def _failed_qualitative(reason: str) -> QualitativeAudit:
        """評価不成立時のプレースホルダ。スコアは 0.0（= 合格不能）とする。"""
        return QualitativeAudit(
            hook_score=0.0,
            emotional_score=0.0,
            character_consistency=0.0,
            overall_score=0.0,
            critique=f"[監査未実施] {reason}",
            actionable_patch=None,
        )

    def _build_conflicts(self, meta: dict[str, Any], qual: QualitativeAudit) -> list[ConflictItemSchema]:
        """静的ルール解析および定性評価からUI表示用の指摘項目リストを生成"""
        conflicts: list[ConflictItemSchema] = []

        # 1. AI定型表現の指摘
        for cliche in meta.get("cliches", []):
            conflicts.append(
                ConflictItemSchema(
                    category="cliche",
                    severity="medium",
                    title=f"AI定型表現の検出: {cliche}",
                    description=f"頻出・陳腐化表現「{cliche}」が含まれています。オリジナリティのある描写への置換を推奨します。",
                    current_value=cliche,
                    suggested_value="",
                    confidence=0.95,
                )
            )

        # 2. 会話文比率の指摘
        dialogue_ratio = meta.get("dialogue_ratio", 0.0)
        if dialogue_ratio < 0.10:
            conflicts.append(
                ConflictItemSchema(
                    category="dialogue",
                    severity="low",
                    title="会話文比率の低下",
                    description=f"会話文比率が {round(dialogue_ratio * 100, 1)}% と低めです。登場人物同士の台詞を挟むことでテンポを向上させられます。",
                    confidence=0.85,
                )
            )
        elif dialogue_ratio > 0.65:
            conflicts.append(
                ConflictItemSchema(
                    category="dialogue",
                    severity="low",
                    title="地の文の不足（台詞過多）",
                    description=f"会話文比率が {round(dialogue_ratio * 100, 1)}% と高めです。台詞だけでなく行動や情景描写を追加して状況を補強してください。",
                    confidence=0.85,
                )
            )

        # 3. 文長リズムの指摘
        rhythm_score = meta.get("rhythm_score", 100.0)
        if rhythm_score < 60.0:
            conflicts.append(
                ConflictItemSchema(
                    category="rhythm",
                    severity="medium",
                    title="文長リズムの偏り",
                    description="文末の長さや接続詞のパターンが偏っています。長文と短文を交互に配置し、読みのリズムを整えてください。",
                    confidence=0.80,
                )
            )

        # 4. 定性評価からの推奨パッチ
        if qual.actionable_patch:
            conflicts.append(
                ConflictItemSchema(
                    category="hook" if qual.hook_score < 70 else "character",
                    severity="high" if qual.overall_score < 70 else "medium",
                    title="AI編集者による推奨パッチ",
                    description=qual.critique or "文章の引き込みと一貫性を強化するためのパッチです。",
                    suggested_value=qual.actionable_patch,
                    confidence=0.90,
                )
            )

        return conflicts

    async def audit(
        self,
        text: str,
        character_profiles: str = "",
        plot_spec: str = "",
    ) -> UnifiedAuditReport:
        """二層ハイブリッド監査を実行し総合判定を下す"""
        q_score, meta = self.audit_quantitative(text)
        qual, degraded = await self._audit_qualitative_with_status(
            text, character_profiles, plot_spec
        )

        # 総合得点 = 定量40% + 定性60%
        final = (q_score * 0.4) + (qual.overall_score * 0.6)
        # 定量スコアだけで合格させないよう、定性評価が成立しなかった場合は
        # 必ず不合格とする（fail-closed）。
        is_ok = (not degraded) and final >= 70.0 and len(meta["cliches"]) < 3
        conflicts = self._build_conflicts(meta, qual)

        if degraded:
            logger.error(
                "UnifiedAuditor: 定性評価が成立しなかったため不合格判定 "
                "(q_score=%.1f final=%.1f): %s",
                q_score,
                final,
                qual.critique,
            )
            conflicts.append(
                ConflictItemSchema(
                    category="hook",
                    severity="critical",
                    title="監査が未実施のため不合格",
                    description=(
                        "AI編集者による定性評価が完了しませんでした"
                        f"（{qual.critique}）。"
                        "本章は未評価として扱われます。"
                    ),
                    confidence=1.0,
                )
            )

        return UnifiedAuditReport(
            is_acceptable=is_ok,
            final_score=round(final, 1),
            quantitative_score=round(q_score, 1),
            qualitative=qual,
            detected_cliches=meta["cliches"],
            dialogue_ratio=meta["dialogue_ratio"],
            conflicts=conflicts,
        )
