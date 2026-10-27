"""STORY_SPINE: 閉じたビート語彙の定義（契約凍結 2026-09-29）。

方針:
- すべての位置は **相対**（span は 0.0-1.0）。絶対話数を持たない。
- duty はプロンプトに注入される。1文・命令形・60字以内・句点で終える。
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("hook", "engine", "reversal", "climax", "close", "filler")
ARTIFACTS = ("scene", "reversal", "reveal", "hook")


@dataclass(frozen=True)
class Beat:
    """パターンに依存しない、閉じたビート語彙の1エントリ。"""

    key: str
    label: str
    role: str
    span: tuple[float, float]
    duty: str
    tension: float
    artifact: str
    optional: bool = False


@dataclass(frozen=True)
class BeatInstance:
    """話単位に量子化した 1 エントリ。"""

    ep_start: int
    ep_end: int
    key: str
    label: str
    role: str
    duty: str
    tension: float
    artifact: str


@dataclass(frozen=True)
class Spine:
    """1 作品分の構造。"""

    pattern: str
    length: str
    market: str
    total_eps: int
    beats: list[BeatInstance] = field(default_factory=list)

    def at(self, ep: int) -> BeatInstance | None:
        for b in self.beats:
            if b.ep_start <= ep <= b.ep_end:
                return b
        return None

    @property
    def keys(self) -> list[str]:
        return [b.key for b in self.beats]


def _b(
    key: str,
    label: str,
    role: str,
    span: tuple[float, float],
    duty: str,
    tension: float,
    artifact: str,
    optional: bool = False,
) -> Beat:
    return Beat(key, label, role, span, duty, tension, artifact, optional)


BEAT_LIST: tuple[Beat, ...] = (
    # --- hook: つかみ ---
    _b("cold_open", "日常の提示", "hook", (0.00, 0.05),
       "主人公の日常を提示し、物語が動く前の空気感を作る。", 0.15, "scene"),
    _b("inciting", "発端", "hook", (0.02, 0.10),
       "物語の針が回り始める出来事を、主人公に遭遇させる。", 0.45, "scene"),
    _b("humiliation", "理不尽な不遇", "hook", (0.05, 0.12),
       "理不尽な不遇を五感で強調し、主人公の怒りを具体化する。", 0.80, "scene"),
    _b("revelation", "能力・事実の提示", "hook", (0.10, 0.18),
       "能力または決定的事実を提示する。ただし無双の状態にはしない。", 0.55, "reveal"),
    # --- engine: 駆動 ---
    _b("promise", "約束・取引の提示", "engine", (0.12, 0.22),
       "主人公と相手の約束や取引を提示し、読者にも必達対象を示す。", 0.50, "scene"),
    _b("first_win", "初の成功", "engine", (0.18, 0.30),
       "初めて形になる成功を描く。明確なカタルシスを読者に与える。", 0.70, "scene"),
    _b("rising_tension", "抵抗の高まり", "engine", (0.28, 0.44),
       "反対勢力の抵抗を強め、現在の手段の限界を明示する。", 0.60, "scene"),
    _b("foreshadow", "伏線の設置", "engine", (0.20, 0.40),
       "後の回収につながる不穏な兆しを、控えめにひとつ設置する。", 0.40, "scene"),
    _b("deepening", "関係の深化", "engine", (0.30, 0.48),
       "重要な他者との関係を深め、以前と態度が変わることを示す。", 0.45, "scene"),
    _b("comic_relief", "息抜き", "engine", (0.34, 0.42),
       "緊張を一度解く場面を入れ、登場人物の人間味を見せる。", 0.20, "scene"),
    _b("failure", "手直しへの失敗", "engine", (0.38, 0.47),
       "策謀や訓練が失敗し、主人公の強がりを見透かさせる。", 0.65, "scene"),
    _b("daily_loop", "日常的反復", "engine", (0.25, 0.40),
       "繰り返しの日常を描き、蓄積や変化の土台を積み上げる。", 0.25, "scene"),
    _b("training", "訓練・習得", "engine", (0.22, 0.38),
       "地道な訓練や修行を描き、到達への兆しを段階的に出す。", 0.35, "scene"),
    _b("expansion", "領域・基盤の拡大", "engine", (0.25, 0.45),
       "支配範囲や事業、領地、居場所を広げていく様子を描く。", 0.50, "scene"),
    _b("gossip", "噂・情報の流通", "engine", (0.30, 0.45),
       "噂が他者を経由して広がり、主人公の名が知れ渡っていく。", 0.40, "scene"),
    _b("stream_reaction", "配信・反応", "engine", (0.30, 0.46),
       "配信や記録を媒介し、観客や聴衆の反応を描写する。", 0.55, "scene"),
    # --- reversal: 転 ---
    _b("midpoint_reversal", "中点反転", "reversal", (0.48, 0.56),
       "これまでの前提を覆す事実を提示し、物語の軸を折る。", 0.90, "reversal"),
    _b("stakes_raise", "状況の悪化", "reversal", (0.44, 0.54),
       "状況を一段悪化させ、失うものの大きさを読者に伝える。", 0.75, "scene"),
    _b("betrayal", "裏切り・離反", "reversal", (0.46, 0.56),
       "味方か重要人物の裏切り、または離反を提示する。", 0.85, "reveal"),
    _b("dark_night", "闇夜・絶望", "reversal", (0.52, 0.66),
       "主人公が自分の弱さを直視し、絶望の底まで落ちる。", 0.70, "scene"),
    _b("decision", "決断", "reversal", (0.58, 0.70),
       "主人公が覚悟を固め、踏み出す場面を描く。", 0.60, "scene"),
    _b("turn_of_tide", "追い詰めの破綻", "reversal", (0.60, 0.72),
       "追い詰めた側の構図が崩れ、逆転の糸口を見せる。", 0.95, "reversal"),
    _b("all_is_lost", "全面的な敗北", "reversal", (0.62, 0.74),
       "主人公が全面的な敗北を受け止め、手中に何も残らない中で方針を立て直す。",
       0.50, "scene"),
    # --- climax: 局面の決着 ---
    _b("last_stand", "最後の戦い", "climax", (0.74, 0.84),
       "最後の戦いを開始する。ここまでの積み上げを総動員させる。", 0.98, "scene"),
    _b("truth_reveal", "黒幕・真相の提示", "climax", (0.75, 0.83),
       "黒幕の正体と、これまでに伏せていた事実を一挙に示す。", 0.92, "reveal"),
    _b("final_choice", "最終選択", "climax", (0.78, 0.88),
       "主人公が代価を懸けて選択し、結末の向きを確定させる。", 0.90, "scene"),
    _b("climax", "クライマックス", "climax", (0.82, 0.94),
       "これまでの矛盾がすべて解ける。約束したカタルシスを最大級で引き出す。",
       1.00, "scene"),
    # --- close: 結び ---
    _b("aftermath", "爪跡", "close", (0.88, 0.94),
       "戦いの余波と、変化した後の世界を示す。", 0.40, "scene"),
    _b("payoff", "約束の回収", "close", (0.84, 0.94),
       "序盤で提示した約束や伏線を、確実につぶして回収する。", 0.60, "scene"),
    _b("residue", "伏線の残存処理", "close", (0.90, 0.96),
       "回収し切らなかった軽微な伏線の扱い、または棚上げを示す。", 0.30, "scene"),
    _b("denouement", "結末", "close", (0.92, 0.98),
       "主人公と周囲の関係を落ち着かせ、物語を閉じる。", 0.25, "scene"),
    _b("volume_hook", "次の引き", "close", (0.94, 1.00),
       "未解決の大きな問いを提示し、次への強い引きを作る。", 0.55, "hook"),
    _b("coda", "最終話のみ・余韻", "close", (0.97, 1.00),
       "静かに締め直し、日常の余韻だけを残す。", 0.10, "scene"),
    _b("interlude", "幕間・視点切替", "close", (0.40, 0.50),
       "別視点の場面をひとつ挿み、視野を広げて情報量を増やす。", 0.20, "scene"),
)

BEAT_VOCABULARY: dict[str, Beat] = {b.key: b for b in BEAT_LIST}

__all__ = [
    "ARTIFACTS",
    "BEAT_LIST",
    "BEAT_VOCABULARY",
    "ROLES",
    "Beat",
    "BeatInstance",
    "Spine",
]
