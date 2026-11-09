"""擾乱変換カタログパッケージ (M1)。"""

from src.audit.perturbation.transforms import (
    PerturbationTransform,
    PerturbationKind,
    RemoveEndingHook,
    ShuffleScenes,
    ReplaceCharacterNameOneParagraph,
    InjectAICliches,
    SummarizeDialogueToNarrative,
    RemoveMiddleParagraph,
    DuplicateParagraph,
    RenameCharacterConsistently,
    NormalizePunctuation,
    TRANSFORM_REGISTRY,
    register,
)

__all__ = [
    "PerturbationTransform",
    "PerturbationKind",
    "RemoveEndingHook",
    "ShuffleScenes",
    "ReplaceCharacterNameOneParagraph",
    "InjectAICliches",
    "SummarizeDialogueToNarrative",
    "RemoveMiddleParagraph",
    "DuplicateParagraph",
    "RenameCharacterConsistently",
    "NormalizePunctuation",
    "TRANSFORM_REGISTRY",
    "register",
]
