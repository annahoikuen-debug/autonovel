"""PLAN_S1 P4: 伏線 LLM 第 4 票の影 (shadow) 記録。

mainline への切替判断 (R3) のため、LLM 投票を**本線判定に加算せず** JSONL に記録する
(改善 #9 ``shadow_audit.py`` パターン踏襲)。DB スキーマ変更はしない。

記録先: ``logs/foreshadow_vote_shadow.jsonl``
分析: ``python -m scripts.analyze_foreshadow_vote_agreement``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_SHADOW_PATH = Path("logs/foreshadow_vote_shadow.jsonl")

# LLM 投票アクション → 判定ステータスの対応 (一致率計算の契約)
ACTION_TO_STATUS = {
    "resolved": "RESOLVED",
    "progressed": "PROGRESSED",
    "unmentioned": "PLANTED",
}


def record_vote_shadow(
    book_id: Optional[int],
    episode_num: int,
    foreshadowing_id: int,
    foreshadowing_title: str,
    llm_action: Optional[str],
    judgment_status: str,
    metadata_action: Optional[str] = None,
    syntax_score: int = 0,
    output_path: Optional[Path] = None,
) -> bool:
    """LLM 投票と本線判定を JSONL に追記する。**決して例外を投げない** (P3)。"""
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "book_id": book_id,
            "episode_num": episode_num,
            "foreshadowing_id": foreshadowing_id,
            "foreshadowing_title": foreshadowing_title,
            "llm_action": llm_action,
            "llm_expected_status": ACTION_TO_STATUS.get(llm_action or "", "PLANTED"),
            "judgment_status": judgment_status,
            "agree": ACTION_TO_STATUS.get(llm_action or "", "PLANTED") == judgment_status,
            "metadata_action": metadata_action,
            "metadata_over_report": (
                metadata_action == "resolved" and (llm_action or "unmentioned") == "unmentioned"
            ),
            "syntax_score": syntax_score,
        }
        path = Path(output_path) if output_path else DEFAULT_SHADOW_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 - P3: 記録の失敗で回収処理を止めない
        logger.debug("Foreshadowing vote shadow recording skipped: %s", exc)
        return False


def analyze_shadow_log(path: Optional[Path] = None) -> dict[str, Any]:
    """shadow 記録を集計する (一致率・過大申告率)。

    空ログや存在しないファイルでも例外にせず、件数 0 の結果を返す (Q10 契約)。
    """
    shadow_path = Path(path) if path else DEFAULT_SHADOW_PATH
    result: dict[str, Any] = {
        "total": 0,
        "agreements": 0,
        "agreement_rate": 0.0,
        "metadata_over_reports": 0,
        "metadata_over_report_rate": 0.0,
        "llm_action_counts": {},
        "path": str(shadow_path),
    }
    if not shadow_path.exists():
        return result

    records = 0
    agreements = 0
    over_reports = 0
    with_metadata = 0
    action_counts: dict[str, int] = {}
    try:
        with open(shadow_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records += 1
                if data.get("agree"):
                    agreements += 1
                llm_action = data.get("llm_action")
                if llm_action:
                    action_counts[llm_action] = action_counts.get(llm_action, 0) + 1
                if data.get("metadata_action") is not None:
                    with_metadata += 1
                    if data.get("metadata_over_report"):
                        over_reports += 1
    except OSError as exc:
        logger.debug("shadow log read failed: %s", exc)
        return result

    result["total"] = records
    result["agreements"] = agreements
    result["agreement_rate"] = round(agreements / records, 4) if records else 0.0
    result["metadata_over_reports"] = over_reports
    result["metadata_over_report_rate"] = round(over_reports / with_metadata, 4) if with_metadata else 0.0
    result["llm_action_counts"] = action_counts
    return result


__all__ = [
    "ACTION_TO_STATUS",
    "DEFAULT_SHADOW_PATH",
    "analyze_shadow_log",
    "record_vote_shadow",
]
