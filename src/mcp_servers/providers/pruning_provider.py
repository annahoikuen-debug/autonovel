"""Context Pruning Provider - Deterministic context optimization for prompt building."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from src.mcp_servers.pruning_schemas import (
    PruneContextRequest,
    PrunedContextResult,
)

logger = logging.getLogger(__name__)


class ContextPruningProvider:
    """プロットとエピソード設定に基づいて、不要なコンテキストを動的に枝刈りするプロバイダー"""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """日本語および英数混在テキストの推定トークン数を算出（約1.5〜2文字で1トークン）"""
        if not text:
            return 0
        return max(1, len(text.strip()) // 2)

    def prune_context(self, request: PruneContextRequest) -> PrunedContextResult:
        """エピソードのプロット・シーン構成に基づいて全コンテキストをプルーニングする"""
        plot = request.plot_blueprint or ""
        budget = request.target_token_budget
        cur_ep = request.current_episode
        pov = request.pov_character

        # 1. 元のコンテキストトークン数を算出
        original_full_text = self._build_raw_unpruned_text(
            characters=request.characters,
            world_lore=request.world_lore,
            foreshadowings=request.foreshadowings,
        )
        orig_tokens = self.estimate_tokens(original_full_text)

        # 2. キャラクターの枝刈り
        active_chars, peripheral_chars, excluded_char_names = self._filter_characters(
            characters=request.characters,
            plot=plot,
            pov_character=pov,
        )

        # 3. 世界観設定（Lore）の枝刈り
        active_names = {c.get("name", "") for c in active_chars}
        relevant_lore = self._filter_lore(
            world_lore=request.world_lore,
            plot=plot,
            active_character_names=active_names,
        )

        # 4. 伏線の枝刈り
        prioritized_foreshadowings = self._filter_foreshadowings(
            foreshadowings=request.foreshadowings,
            plot=plot,
            current_episode=cur_ep,
        )

        # 5. バジェット調整 & 整形テキストの構築
        formatted_text, final_lore, final_fores = self._pack_and_format(
            active_chars=active_chars,
            peripheral_chars=peripheral_chars,
            relevant_lore=relevant_lore,
            prioritized_foreshadowings=prioritized_foreshadowings,
            budget=budget,
        )

        pruned_tokens = self.estimate_tokens(formatted_text)
        saved = max(0, orig_tokens - pruned_tokens)
        rate = round(saved / max(1, orig_tokens), 4)

        stats = {
            "total_characters_in": len(request.characters),
            "active_characters_count": len(active_chars),
            "peripheral_characters_count": len(peripheral_chars),
            "excluded_characters_count": len(excluded_char_names),
            "total_lore_in": len(request.world_lore),
            "retained_lore_count": len(final_lore),
            "dropped_lore_count": len(request.world_lore) - len(final_lore),
            "total_foreshadowings_in": len(request.foreshadowings),
            "retained_foreshadowings_count": len(final_fores),
            "budget_limit": budget,
        }

        return PrunedContextResult(
            active_characters=active_chars,
            peripheral_characters=peripheral_chars,
            excluded_characters=excluded_char_names,
            relevant_lore=final_lore,
            prioritized_foreshadowings=final_fores,
            formatted_prompt_context=formatted_text,
            original_token_estimate=orig_tokens,
            pruned_token_estimate=pruned_tokens,
            tokens_saved=saved,
            token_reduction_rate=rate,
            stats=stats,
        )

    def _filter_characters(
        self,
        characters: List[Dict[str, Any]],
        plot: str,
        pov_character: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        """登場人物を Active, Peripheral, Excluded に仕分ける"""
        active: List[Dict[str, Any]] = []
        peripheral: List[Dict[str, Any]] = []
        excluded: List[str] = []

        active_relations: Set[str] = set()

        for c in characters:
            name = str(c.get("name", "")).strip()
            if not name:
                continue

            aliases = [str(a) for a in c.get("aliases", []) if a]
            is_pov = bool(pov_character and name == pov_character)

            # プロット内に名前または別名が登場するか
            in_plot = (name in plot) or any(a in plot for a in aliases)

            if is_pov or in_plot:
                active.append(c)
                # 関係のある人物名を記録
                rels = c.get("relationships", {})
                if isinstance(rels, dict):
                    active_relations.update(rels.keys())
            else:
                pass  # 一旦保留し、後で判定

        # 非Activeキャラクターの判定
        active_names = {c.get("name", "") for c in active}
        for c in characters:
            name = str(c.get("name", "")).strip()
            if not name or name in active_names:
                continue

            importance = str(c.get("importance", "mob")).lower()
            # Activeキャラと強い関係性がある、またはメインキャラであれば1行要約枠として保持
            if name in active_relations or importance == "main":
                summary_line = f"役割: {c.get('role', '関係者')} / 性格: {c.get('personality', '不明')}"
                peripheral.append({
                    "name": name,
                    "role": c.get("role", ""),
                    "summary": summary_line,
                })
            else:
                excluded.append(name)

        return active, peripheral, excluded

    def _filter_lore(
        self,
        world_lore: List[Dict[str, Any]],
        plot: str,
        active_character_names: Set[str],
    ) -> List[Dict[str, Any]]:
        """プロットおよび登場人物に関連する世界観設定のみをスコアリング抽出"""
        scored_lore: List[tuple[int, Dict[str, Any]]] = []

        for item in world_lore:
            title = str(item.get("title", ""))
            content = str(item.get("content", ""))
            keywords = [str(k) for k in item.get("keywords", []) if k]
            importance = int(item.get("importance", 1))

            score = 0
            if title and title in plot:
                score += 15

            for kw in keywords:
                if kw in plot:
                    score += 8
                # 登場人物の名前やセリフに関連するか
                if any(kw in name for name in active_character_names):
                    score += 4

            # プロットに含まれる単語との部分一致
            if score > 0 or importance >= 4:
                # 重要度補正
                score += importance * 2
                scored_lore.append((score, item))

        # スコア降順にソート
        scored_lore.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_lore]

    def _filter_foreshadowings(
        self,
        foreshadowings: List[Dict[str, Any]],
        plot: str,
        current_episode: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """伏線を回収ターゲット、キーワード関連度、ステータスに基づき優先順位付け"""
        prioritized: List[tuple[int, Dict[str, Any]]] = []

        for f in foreshadowings:
            status = str(f.get("status", "unresolved")).lower()
            target_ep = f.get("target_episode")
            planted_ep = f.get("planted_episode")
            title = str(f.get("title", ""))
            desc = str(f.get("description", ""))

            # 既に解決済みでプロット言及もないものは除外
            if status == "resolved" and title not in plot:
                continue

            score = 10
            # 本エピソードが回収目標の場合（契約伏線）
            if current_episode is not None and target_ep == current_episode:
                score += 100

            # 本エピソードが設置目標の場合
            if current_episode is not None and planted_ep == current_episode:
                score += 80

            # プロット内にタイトルまたは説明文のキーワードが含まれるか
            if title and title in plot:
                score += 40

            prioritized.append((score, f))

        prioritized.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in prioritized]

    def _pack_and_format(
        self,
        active_chars: List[Dict[str, Any]],
        peripheral_chars: List[Dict[str, Any]],
        relevant_lore: List[Dict[str, Any]],
        prioritized_foreshadowings: List[Dict[str, Any]],
        budget: int,
    ) -> tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """バジェット上限内に収めつつ整形されたプロンプト用コンテキストを構築"""
        sections: List[str] = []

        # 1. 登場キャラクター詳細セクション
        char_lines: List[str] = []
        for c in active_chars:
            name = c.get("name", "名称不明")
            role = c.get("role", "")
            pers = c.get("personality", "")
            speech = c.get("speech_pattern", "")
            secrets = c.get("secrets_and_flaws", "")

            details = [f"【{name}】 役割: {role}"]
            if pers:
                details.append(f"  性格: {pers}")
            if speech:
                details.append(f"  口調/台詞特徴: {speech}")
            if secrets:
                details.append(f"  裏動機・弱点: {secrets}")
            char_lines.append("\n".join(details))

        if peripheral_chars:
            char_lines.append("【関係人物（言及・背景のみ）】")
            for p in peripheral_chars:
                char_lines.append(f"- {p.get('name')}: {p.get('summary')}")

        if char_lines:
            sections.append("### [動的抽出] 登場人物設定\n" + "\n\n".join(char_lines))

        # 2. 世界観・Loreセクション（バジェット超過時は下位から除外または切り詰め）
        selected_lore: List[Dict[str, Any]] = []
        lore_lines: List[str] = []
        for item in relevant_lore:
            title = item.get("title", "")
            content = item.get("content", "")
            # 1項目あたり最大300文字に圧縮
            compact_content = content[:300] + ("..." if len(content) > 300 else "")
            line = f"- 《{title}》 ({item.get('category', '設定')}): {compact_content}"

            # トークン見積もりチェック
            temp_text = "\n\n".join(sections + ["### [動的抽出] 舞台・世界観設定\n" + "\n".join(lore_lines + [line])])
            if self.estimate_tokens(temp_text) > budget:
                break
            lore_lines.append(line)
            selected_lore.append(item)

        if lore_lines:
            sections.append("### [動的抽出] 舞台・世界観設定\n" + "\n".join(lore_lines))

        # 3. 伏線セクション
        selected_fores: List[Dict[str, Any]] = []
        fore_lines: List[str] = []
        for f in prioritized_foreshadowings:
            title = f.get("title", "")
            desc = f.get("description", "")
            target = f.get("target_episode")
            target_str = f" [目標: Ep.{target}]" if target else ""
            line = f"- [伏線] 『{title}』{target_str}: {desc}"

            temp_text = "\n\n".join(sections + ["### [動的抽出] 注目伏線\n" + "\n".join(fore_lines + [line])])
            if self.estimate_tokens(temp_text) > budget and fore_lines:
                break
            fore_lines.append(line)
            selected_fores.append(f)

        if fore_lines:
            sections.append("### [動的抽出] 注目伏線\n" + "\n".join(fore_lines))

        return "\n\n".join(sections), selected_lore, selected_fores

    def _build_raw_unpruned_text(
        self,
        characters: List[Dict[str, Any]],
        world_lore: List[Dict[str, Any]],
        foreshadowings: List[Dict[str, Any]],
    ) -> str:
        """枝刈り前のフルコンテキストテキストを合成して元のトークン見積もり用にする"""
        parts: List[str] = []
        for c in characters:
            parts.append(str(c))
        for l_item in world_lore:
            parts.append(str(l_item))
        for f in foreshadowings:
            parts.append(str(f))
        return "\n".join(parts)
