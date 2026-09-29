"""プロジェクト全体で使用する定数値"""
from pathlib import Path
from typing import Final

# プロジェクトルートディレクトリ
BASE_DIR: Final[Path] = Path(__file__).parent.parent

# EasyMode
DEFAULT_TARGET_EPISODES: Final[int] = 8
DEFAULT_MAX_REWRITE_ITERATIONS: Final[int] = 3
DEFAULT_TARGET_AUDIT_SCORE: Final[float] = 95.0

# LLM Retry
MAX_LLM_RETRIES: Final[int] = 3
LLM_RETRY_DELAY_SEC: Final[float] = 1.0

# 話数マッピングは絶対値ではなく相対値で表す（config/story_spine の span）。
# 旧: EP_HUMILIATION=2 / EP_TRIGGER=3 / EP_MUSOU_START=4 / EP_FINAL=8 / EP_CLIMAX=7
# これらは 8話固定の前提で、40話や100話の構成にそのまま適用すると構造が破綻する。
# 絶対の話数が必要な箇所は resolve_spine() が相対 span から導出する。
TENSION_THRESHOLD: Final[int] = 75

# 設定デフォルト値 (schemas/config.py から)
ACTOR_CRITIC_ENABLED: Final[bool] = True
ACTOR_CRITIC_MAX_ITERATIONS: Final[int] = 2
ACTOR_CRITIC_SEVERITY_THRESHOLD: Final[str] = "Major"
CONTENT_SEPARATOR: Final[str] = "\n---\n"
COOLDOWN_BASE_DEFAULT: Final[float] = 0.0
COOLDOWN_MAX_DEFAULT: Final[float] = 90.0
COOLDOWN_MIN_DEFAULT: Final[float] = 0.0
COST_INPUT_FLASH: Final[float] = 0.0000375
COST_INPUT_PRO: Final[float] = 0.0035
COST_OUTPUT_FLASH: Final[float] = 0.00015
COST_OUTPUT_PRO: Final[float] = 0.0105
import os

DATABASE_URL: Final[str] = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./autonovel.db")
DB_FILE: Final[str] = "autonovel.db"
DEFAULT_EROTIC_INTENSITY: Final[int] = 2
DEFAULT_GOLDEN_PEAKS: Final[int] = 1
DRAFT_POLISH_ENABLED: Final[bool] = True
EROTIC_INTENSITY_SCALE: Final[int] = 3
GENRE_EROTIC: Final[str] = "ero"
MAX_CONCURRENCY_DEFAULT: Final[int] = 0
MAX_PROMPT_CHARS: Final[int] = 8000
MODEL_CLIMAX: Final[str] = "gemma-4-31b-it"
MODEL_EMBEDDING: Final[str] = "text-embedding-004"
MODEL_PLANNING: Final[str] = "gemini-3.5-flash-lite"
MODEL_PLOT_EXPANSION: Final[str] = "gemma-4-31b-it"
MODEL_FAST_EXPANSION: Final[str] = os.getenv("MODEL_FAST_EXPANSION", "gemini-3.5-flash-lite")
MODEL_STABLE_FALLBACK: Final[str] = "gemma-4-31b-it"
MODEL_ULTRA_STABLE: Final[str] = "gemma-4-31b-it"
MODEL_WRITING: Final[str] = "gemma-4-31b-it"
NSFW_DEFAULT_ENABLED: Final[bool] = False
POLISHING_MIN_CONTENT_RATIO: Final[float] = 0.5
SAFE_APPEND_MODE_DEFAULT: Final[str] = "auto"
SAFE_APPEND_MODE_OPTIONS: Final[list[str]] = ["auto", "warn_only", "error_on_overflow"]
SPECIALIZED_AMPLIFIER_ENABLED: Final[bool] = True
STRESS_CATHARSIS_THRESHOLD: Final[int] = 85
STRESS_CLIMAX_BONUS: Final[int] = 50
STRESS_FILLER_THRESHOLD: Final[int] = 35
STRESS_HATE_GAIN_BASE: Final[int] = 2

# タイムアウト値 (秒)
DEFAULT_API_TIMEOUT_SEC: Final[float] = 120.0
LONG_RUNNING_TIMEOUT_SEC: Final[float] = 300.0
STREAM_TIMEOUT_SEC: Final[float] = 180.0

# レート制限値
RATE_LIMIT_MAX_REQUESTS: Final[int] = 100
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
RATE_LIMIT_STORE_MAX_ENTRIES: Final[int] = 10000
MAX_CONCURRENT_API_CALLS: Final[int] = 5

