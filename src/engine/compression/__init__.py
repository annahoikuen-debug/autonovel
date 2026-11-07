"""Four-Layer Context Compression Package."""

from __future__ import annotations

from src.engine.compression.models import (
    SceneType,
    SudachiConfig,
    CompressionConfig,
    ProtectedContext,
    RawTextLayerOutput,
    SubgraphLayerOutput,
    AbstractionLayerOutput,
    TrimmedContextOutput,
    CompressedContextResult,
    CompressionResult,
    load_compression_config,
    get_compression_config,
    ReversibleEntityFact,
    CompressionQualityMetrics,
    SceneFlowHistory,
)
from src.engine.compression.metrics import calculate_consistency_metrics
from src.engine.compression.layer1_keywords import (
    Layer1KeywordExtractor,
    extract_keyphrases,
    count_tokens,
    create_extractor,
    KeyphraseExtractor,
    TFIDFExtractor,
    BM25Extractor,
    KeyBERTExtractor,
)
from src.engine.compression.layer2_subgraph import (
    Layer2SubgraphExtractor,
    RELATION_WEIGHTS,
)
from src.engine.compression.layer3_abstraction import (
    Layer3ConceptAbstractor,
    DEFAULT_CATEGORIES,
    CONCEPT_TAXONOMY,
)
from src.engine.compression.layer4_trimming import (
    Layer4SceneTrimmer,
    SCENE_CATEGORY_WEIGHTS,
    SCENE_TRANSITION_MATRIX,
)
from src.engine.compression.cache import CompressionCache
from src.engine.compression.compressor import FourLayerCompressor

ContextCompressionPipeline = FourLayerCompressor

__all__ = [
    "SceneType",
    "SudachiConfig",
    "CompressionConfig",
    "ProtectedContext",
    "RawTextLayerOutput",
    "SubgraphLayerOutput",
    "AbstractionLayerOutput",
    "TrimmedContextOutput",
    "CompressedContextResult",
    "CompressionResult",
    "load_compression_config",
    "get_compression_config",
    "ReversibleEntityFact",
    "CompressionQualityMetrics",
    "SceneFlowHistory",
    "calculate_consistency_metrics",
    "Layer1KeywordExtractor",
    "extract_keyphrases",
    "count_tokens",
    "create_extractor",
    "KeyphraseExtractor",
    "TFIDFExtractor",
    "BM25Extractor",
    "KeyBERTExtractor",
    "Layer2SubgraphExtractor",
    "RELATION_WEIGHTS",
    "Layer3ConceptAbstractor",
    "DEFAULT_CATEGORIES",
    "CONCEPT_TAXONOMY",
    "Layer4SceneTrimmer",
    "SCENE_CATEGORY_WEIGHTS",
    "SCENE_TRANSITION_MATRIX",
    "CompressionCache",
    "FourLayerCompressor",
    "ContextCompressionPipeline",
]
