"""book_score 定数・例外・環境変数ヘルパー。

src/engine/book_score/service.py から機能分割（案A+B）により新設。
旧パス ``src/engine/book_score/service.py`` は shim として残す。
"""

from __future__ import annotations

import os
from typing import Dict


class ScoringUnavailableError(RuntimeError):
    """スコア算出に必要なデータが存在しない、または壊れていることを示す。

    「低いスコア」 (``LowScore``) とは区別される。呼び出し側は
    この例外を捕捉して当該次元を判定不能として扱うべきで、
    点数を偽の数値に置き換えてはならない。
    """


#: 判定不能な次元に対して用いる中立スコア。
#: 閾値を下回らせないため 100.0 (満点) を用い、減点理由には含めない。
#: 注意: この値は *次元スコア* の表示値にのみ使われる。
#: 総合スコアへの寄与は :func:`_skip_unavailable_weight` の設定に従う
#: （既定 ON なら欠測次元は重み付き平均から除外される）。
NEUTRAL_SCORE = 100.0

#: 5 次元のキーと、_get_weights() がキーを返さなかったときの既定重み。
DEFAULT_DIMENSION_WEIGHTS: Dict[str, float] = {
    "structure": 25,
    "coherency": 25,
    "factual_grounding": 20,
    "visual_textual_synergy": 15,
    "reader_experience": 15,
}

#: 判定不能（ScoringUnavailableError）な次元を総合スコアの重み付き平均から除外するかの環境変数。
#: 未設定（既定）または truthy なら除外する。 falsy を渡すと旧挙動
#: （NEUTRAL_SCORE=100 を重み付きで加算し、障害が「高評価」に化ける）に戻る。
ENV_SKIP_UNAVAILABLE_WEIGHT = "BOOK_SCORE_SKIP_UNAVAILABLE_WEIGHT"
_FALSY_VALUES = {"0", "false", "off", "no", ""}


def _skip_unavailable_weight() -> bool:
    """欠測次元を重み付き平均から除外するか（既定 True）。"""
    raw = os.getenv(ENV_SKIP_UNAVAILABLE_WEIGHT)
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSY_VALUES
