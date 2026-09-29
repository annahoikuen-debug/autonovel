"""
src/services/token_tracker.py — トークン使用量追跡サービス
"""

import time
from typing import Any

from src.models.report import TokenUsageReport


class TokenTracker:
    """トークン使用量を追跡するサービス

    v5.3 / Step 2: 本番スキル経路でも計測できるよう、
    ``add_usage`` に ``task_type``（planning / writing / audit など）を追加し、
    スキル別・モデル別の集計とUSDコスト算出を提供する。

    v6 / Step 27: ``add_usage`` に ``tier`` を追加し、tier ごとの
    コスト比較（``get_tier_breakdown``）を可能にした。``tier`` 未指定時は
    ``model_name`` から ``ROUTING_TIERS`` を逆引きして自動分類する。
    既存の呼び出し（``tier`` を渡さない）は従来どおりの集計になる。
    """

    def __init__(self):
        """初期状態を作成"""
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.episode_count = 0
        self.episode_usages: list[dict[str, Any]] = []
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.last_model_name: str | None = None
        self.last_agent_name: str | None = None
        #: タスク種別ごとの使用量（v5.3 追加）
        self.usage_by_task: dict[str, dict[str, Any]] = {}
        #: タスク種別ごとの LLM 呼び出し回数（v5.3 追加）
        self.call_count_by_task: dict[str, int] = {}
        #: tier ごとの使用量（v6 / Step 27 追加）。tier 別のコスト比較用。
        self.usage_by_tier: dict[str, dict[str, Any]] = {}
        #: tier ごとの LLM 呼び出し回数（v6 / Step 27 追加）
        self.call_count_by_tier: dict[str, int] = {}

    def start(self):
        """追跡を開始"""
        self.start_time = time.time()

    def add_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        ep_num: int | None = None,
        model_name: str | None = None,
        agent_name: str | None = None,
        task_type: str | None = None,
        tier: str | None = None,
    ):
        """使用量を加算

        Args:
            input_tokens: 入力トークン数
            output_tokens: 出力トークン数
            ep_num: エピソード番号（任意）
            model_name: 使用モデル名（任意）
            agent_name: エージェント名（任意）
            task_type: タスク種別（任意）。``planning`` / ``writing`` / ``audit``
                など。指定すると種別ごとの.calls とトークンが集計される。
            tier: コスト最適化の tier（``tier1_light`` / ``tier2_standard`` /
                ``tier3_premium``、任意）。未指定かつ ``task_type`` があるときは
                ``model_name`` から逆引きする（v6 / Step 27）。
        """
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

        if model_name:
            self.last_model_name = model_name
        if agent_name:
            self.last_agent_name = agent_name

        if tier is None and task_type:
            tier = self._infer_tier(model_name)

        if task_type:
            bucket = self.usage_by_task.setdefault(
                task_type,
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "models": {},
                },
            )
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["total_tokens"] += input_tokens + output_tokens
            bucket["cost_usd"] = round(
                bucket["cost_usd"] + self.estimate_cost_usd(
                    input_tokens, output_tokens, model_name
                ),
                8,
            )
            if model_name:
                model_bucket = bucket["models"].setdefault(
                    model_name,
                    {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0},
                )
                model_bucket["input_tokens"] += input_tokens
                model_bucket["output_tokens"] += output_tokens
                model_bucket["total_tokens"] += input_tokens + output_tokens
                model_bucket["calls"] += 1
            self.call_count_by_task[task_type] = (
                self.call_count_by_task.get(task_type, 0) + 1
            )

        if task_type or tier:
            self._record_tier(
                tier or "unrouted",
                input_tokens,
                output_tokens,
                model_name,
            )

        if ep_num is not None:
            self.episode_usages.append(
                {
                    "ep_num": ep_num,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "model_name": model_name,
                    "agent_name": agent_name,
                    "task_type": task_type,
                    "tier": tier,
                }
            )

    @staticmethod
    def _infer_tier(model_name: str | None) -> str | None:
        """モデルIDから tier 名を逆引きする（``src.config.cost_optimization``）。"""
        if not model_name:
            return None
        try:
            from src.config.cost_optimization import tier_for_model

            return tier_for_model(model_name)
        except Exception:  # pragma: no cover - 設定不備でも計測は止めない
            return None

    def _record_tier(
        self,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        model_name: str | None,
    ) -> None:
        """tier バケットへ使用量とコストを加算する。"""
        bucket = self.usage_by_tier.setdefault(
            tier,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "calls": 0,
                "models": {},
            },
        )
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += input_tokens + output_tokens
        bucket["cost_usd"] = round(
            bucket["cost_usd"]
            + self.estimate_cost_usd(input_tokens, output_tokens, model_name),
            8,
        )
        bucket["calls"] += 1
        if model_name:
            model_bucket = bucket["models"].setdefault(
                model_name,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0},
            )
            model_bucket["input_tokens"] += input_tokens
            model_bucket["output_tokens"] += output_tokens
            model_bucket["total_tokens"] += input_tokens + output_tokens
            model_bucket["calls"] += 1
        self.call_count_by_tier[tier] = self.call_count_by_tier.get(tier, 0) + 1

    @staticmethod
    def estimate_cost_usd(
        input_tokens: int, output_tokens: int, model_name: str | None
    ) -> float:
        """1Mトークンあたりの単価からUSDコストを推定する。

        ``src/config/cost_optimization.py`` の ``MODEL_PRICING`` を参照する。
        未知のモデルは 0.0 を返す（推定而非」を明示的にゼロで示す）。
        """
        if not model_name:
            return 0.0
        try:
            from src.config.cost_optimization import MODEL_PRICING

            pricing = MODEL_PRICING.get(model_name)
            if pricing is None:
                return 0.0
            return round(
                (input_tokens / 1_000_000) * pricing.get("input", 0.0)
                + (output_tokens / 1_000_000) * pricing.get("output", 0.0),
                8,
            )
        except Exception:  # pragma: no cover - 設定不備でも計測は止めない
            return 0.0

    def get_total_cost_usd(self) -> float:
        """計測済み全体の推定USDコストを返す。"""
        return round(sum(b["cost_usd"] for b in self.usage_by_task.values()), 8)

    def get_task_breakdown(self) -> dict[str, dict[str, Any]]:
        """タスク種別ごとのaggregations（呼び出し回数・トークン・コスト）を返す。"""
        return {
            task: {
                "calls": self.call_count_by_task.get(task, 0),
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "total_tokens": bucket["total_tokens"],
                "cost_usd": bucket["cost_usd"],
                "models": dict(bucket["models"]),
            }
            for task, bucket in self.usage_by_task.items()
        }

    def get_tier_breakdown(self) -> dict[str, dict[str, Any]]:
        """tier ごとの使用量（呼び出し回数・トークン・コスト）を返す。

        v6 / Step 27: ``tier1_light`` / ``tier2_standard`` / ``tier3_premium``
        のコストを定量比較するためのAPI。ルーティングが無効な呼び出しは
        ``unrouted`` バケットに集約される。
        """
        return {
            tier: {
                "calls": self.call_count_by_tier.get(tier, 0),
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "total_tokens": bucket["total_tokens"],
                "cost_usd": bucket["cost_usd"],
                "models": dict(bucket["models"]),
            }
            for tier, bucket in self.usage_by_tier.items()
        }

    def increment_episode_count(self):
        """エピソード数をインクリメント"""
        self.episode_count += 1

    def stop(self):
        """追跡を終了"""
        self.end_time = time.time()

    def get_report(self) -> TokenUsageReport:
        """レポートを取得

        Returns:
            TokenUsageReport: トークン使用量レポート
        """
        generation_time = 0.0
        if self.start_time and self.end_time:
            generation_time = self.end_time - self.start_time
        elif self.start_time:
            generation_time = time.time() - self.start_time

        return TokenUsageReport(
            total_tokens=self.total_tokens,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            episode_count=self.episode_count,
            generation_time_seconds=generation_time,
        )

    def get_episode_usages(self) -> list[dict[str, Any]]:
        """エピソード毎の使用量を取得

        Returns:
            List[Dict[str, Any]]: エピソード毎の使用量リスト
        """
        return self.episode_usages.copy()

    def reset(self):
        """状態をリセット"""
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.episode_count = 0
        self.episode_usages = []
        self.start_time = None
        self.end_time = None
        self.last_model_name = None
        self.last_agent_name = None
        self.usage_by_task = {}
        self.call_count_by_task = {}
        self.usage_by_tier = {}
        self.call_count_by_tier = {}

    async def log_cost_consumption(
        self,
        book_id: int,
        agent_name: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        chapter_number: int | None = None,
        session: Any = None,
    ) -> float | None:
        """LLM呼び出し完了時に ``CostLogModel`` へ自動コミットするフック。

        ``CostCalculator`` で推定コストを算出し、``session`` が渡された場合は
        ``CostLogModel`` レコードを作成して flush する。

        Args:
            book_id: 作品ID
            agent_name: エージェント名
            model_name: 使用モデル名
            input_tokens: 入力トークン数
            output_tokens: 出力トークン数
            chapter_number: 章番号（任意）
            session: 非同期DBセッション（任意）。未指定時はコストのみ返す。

        Returns:
            推定コスト（USD）。``session`` が未指定または flush 失敗時は ``None``。
        """
        from src.services.cost_analytics import CostCalculator

        cost_calculator = CostCalculator()
        cost_usd = cost_calculator.calculate(input_tokens, output_tokens, model_name)

        if session is None:
            return cost_usd

        from src.backend.database.models import CostLogModel

        log_entry = CostLogModel(
            book_id=book_id,
            chapter_number=chapter_number,
            agent_name=agent_name,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        try:
            session.add(log_entry)
            await session.flush()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to log cost consumption for book_id=%s", book_id, exc_info=True
            )
            return cost_usd
        return cost_usd
