"""
config/emotional_hook_vocabulary.py — 後方互換エイリアス

語彙集は ``src/config/emotional_hook_vocabulary.py`` に一本化した。
本ファイルは旧 import パスを踏み台として残しているだけの再エクスポートであり、
定義をここに追加しないこと（二重実装が再発する）。

旧版の ``validate_hook`` は末尾で ``len(hook_name.strip()) > 0`` を返しており、
任意の非空文字列が valid 扱いされていた。単一実装化に伴い、実在する
英語キー / 日本語表記のみを valid とする方針に統一した。
"""

from src.config.emotional_hook_vocabulary import (  # noqa: F401
    EMOTIONAL_HOOKS,
    get_hook_peak_tension,
    validate_hook,
)

__all__ = ["EMOTIONAL_HOOKS", "get_hook_peak_tension", "validate_hook"]
