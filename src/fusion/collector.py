"""Collector for emotional vectors from multiple namespaces."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.fusion.config import FusionConfig, load_fusion_config
from src.fusion.models import SourceVector
from src.pipeline.emotional_residue import EmotionalVector
from src.stores.vector_store import VectorStore


class VectorCollector:
    """3ネームスペース (annotation, rule_engine, pipeline) から感情ベクトルを収集するクラス"""

    DEFAULT_NAMESPACES = ["annotation", "rule_engine", "pipeline"]

    def __init__(
        self,
        vector_store: VectorStore,
        config: Optional[FusionConfig] = None,
        namespaces: Optional[List[str]] = None,
    ):
        self.vector_store = vector_store
        self.config = config or load_fusion_config()
        self.namespaces = namespaces or self.DEFAULT_NAMESPACES

    def collect_all(
        self,
        pair: Tuple[str, str],
        episode: Optional[int] = None,
    ) -> List[SourceVector]:
        """指定ペアに対して、利用可能なネームスペースから最新の感情ベクトルを収集する。

        Args:
            pair: (主体キャラクター, 対象キャラクター)
            episode: 指定がある場合、そのエピソードのベクトルを探す

        Returns:
            収集された SourceVector のリスト
        """
        collected: List[SourceVector] = []

        for ns in self.namespaces:
            vec: Optional[EmotionalVector] = None
            if episode is not None:
                # エピソード指定がある場合は、そのエピソードのベクトルだけを使う。
                # get_latest は常に最新エピソードを返すため、別エピソードの値と
                # 混線すると偽の矛盾として仲裁結果や融合結果に書き込まれる。
                vec = self.vector_store.get_by_episode(ns, episode, pair)
            else:
                vec = self.vector_store.get_latest(ns, pair)

            if vec is not None:
                confidence = self.config.source_confidence.get(ns, 0.5)
                source_vec = SourceVector(
                    namespace=ns,
                    vector=vec,
                    confidence=confidence,
                    timestamp=datetime.now(timezone.utc),
                )
                collected.append(source_vec)

        return collected
