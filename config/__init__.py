"""
config パッケージ
アプリケーション全体の設定・定数・ドメインプロファイルを一元管理します。
"""

# 1. 分割された定数群のインポート
from src.config.archetypes_new import (
    ARCHETYPE_KEY_ALIASES,
    CHEAT_DESCRIPTIONS,
    COST_DESCRIPTIONS,
    DEBUFF_PROFILES,
    EASY_GENRES,
    EASY_MODE_KEYWORDS_MAP,
    STORY_ARCHETYPES,
    VILLAIN_STRATEGIES,
    WIZARD_ARCHETYPE_LABELS,
    WIZARD_GENRE_OPTIONS,
    resolve_archetype_key,
)
from src.config.constants import (
    ACTOR_CRITIC_ENABLED,
    ACTOR_CRITIC_MAX_ITERATIONS,
    ACTOR_CRITIC_SEVERITY_THRESHOLD,
    BASE_DIR,
    CONTENT_SEPARATOR,
    COOLDOWN_BASE_DEFAULT,
    COOLDOWN_MAX_DEFAULT,
    COOLDOWN_MIN_DEFAULT,
    COST_INPUT_FLASH,
    COST_INPUT_PRO,
    COST_OUTPUT_FLASH,
    COST_OUTPUT_PRO,
    DATABASE_URL,
    DB_FILE,
    DEFAULT_EROTIC_INTENSITY,
    DEFAULT_GOLDEN_PEAKS,
    DRAFT_POLISH_ENABLED,
    EROTIC_INTENSITY_SCALE,
    GENRE_EROTIC,
    MAX_CONCURRENCY_DEFAULT,
    MAX_PROMPT_CHARS,
    MODEL_CLIMAX,
    MODEL_EMBEDDING,
    MODEL_PLANNING,
    MODEL_PLOT_EXPANSION,
    MODEL_STABLE_FALLBACK,
    MODEL_ULTRA_STABLE,
    MODEL_WRITING,
    NSFW_DEFAULT_ENABLED,
    POLISHING_MIN_CONTENT_RATIO,
    SAFE_APPEND_MODE_DEFAULT,
    SAFE_APPEND_MODE_OPTIONS,
    SPECIALIZED_AMPLIFIER_ENABLED,
    STRESS_CATHARSIS_THRESHOLD,
    STRESS_CLIMAX_BONUS,
    STRESS_FILLER_THRESHOLD,
    STRESS_HATE_GAIN_BASE,
)

# 3. Streamlit アダプター（必要に応じてクライアントがインポート）
# from .streamlit_adapter import StreamlitConfig
# 4. サブモジュールのエクスポート
from src.config.domain_profile_manager import DomainProfileManager, DomainProfileService

# 官能/NSFWモジュール
from src.nsfw.erotic_pacing import EroticBeat, EroticCurve
from src.nsfw.erotic_platform_presets import PLATFORM_PRESETS, get_preset, get_preset_names
from src.nsfw.erotic_vocabulary import (
    METAPHOR_BANK,
    ONOMATOPOEIA_BANK,
    PSYCHOLOGY_TEMPLATES,
    VOCABULARY_TIERS,
    get_vocabulary_for_tier,
)
from schemas.config import GlobalConfigModel

# 2. project_context から新しいシステム中枢クラスと定数を上書きエクスポート
from src.infrastructure.config.project_context import PROMPT_TEMPLATES, get_config, set_config

__all__ = [
    "GlobalConfigModel",
    "set_config",
    "get_config",
    "PROMPT_TEMPLATES",
    "DomainProfileManager",
    "DomainProfileService",
    "EroticBeat",
    "EroticCurve",
    "get_vocabulary_for_tier",
    "get_preset",
    "get_preset_names",
    # 後方互換（Phase R3: shim 削除後の移行猶予）。
    #   アクセスされた時だけ実体を解決して返す（PEP 562 __getattr__）。
    #   即時再エクスポートはしない（import config のたびにサブモジュールを
    #   読み込むコストを避け、shim 削除の成果を維持する）。
    #   `import config.constants` / `import config.project_context` は従来どおり
    #   ModuleNotFoundError のまま（submodule import は __getattr__ を経由しない）。
    "constants",
    "FORBIDDEN_SUMMARY_PATTERNS",
    "FORBIDDEN_WORD_REPLACEMENTS",
    "project_context",
]

# 属性名 -> (実体モジュール, モジュールから取り出す属性名。None ならモジュール自身)
_COMPAT_LAZY_ATTRS: dict[str, tuple[str, str | None]] = {
    "constants": ("src.config.constants", None),
    "project_context": ("src.infrastructure.config.project_context", None),
    "FORBIDDEN_SUMMARY_PATTERNS": ("src.domain.styles", "FORBIDDEN_SUMMARY_PATTERNS"),
    "FORBIDDEN_WORD_REPLACEMENTS": ("src.domain.styles", "FORBIDDEN_WORD_REPLACEMENTS"),
}


def __getattr__(name: str):
    """後方互換の遅延解決。未知の名前は AttributeError（PLOT_STRUCTURES 等の維持）。

    モジュールレベル import を行わず、アクセスされた時だけ実体を読み込む。
    2 回目以降は globals() にキャッシュして __getattr__ を呼ばない。
    """
    target = _COMPAT_LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib
    import warnings

    module_name, attr = target
    module = importlib.import_module(module_name)
    value = module if attr is None else getattr(module, attr)
    warnings.warn(
        f"config.{name} は非推奨です。{module_name} から直接 import してください",
        DeprecationWarning,
        stacklevel=2,
    )
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_COMPAT_LAZY_ATTRS))
