"""Novel output splitter for isolating novel prose and co-generated metadata."""

import json
import logging
import re
from typing import Tuple, Optional

from src.models.writing_metadata import ForeshadowingReport, WritingMetadata

logger = logging.getLogger(__name__)

# Matches [METADATA_JSON] ... [/METADATA_JSON]
METADATA_TAG_PATTERN = re.compile(
    r"\[METADATA_JSON\]\s*(?:```(?:json)?\s*)?(.*?)(?:```\s*)?\[/METADATA_JSON\]",
    re.DOTALL | re.IGNORECASE,
)

# Secondary fallback: looking for trailing markdown json block at end of response
TRAILING_JSON_BLOCK_PATTERN = re.compile(
    r"```json\s*(\{\s*\"episode_number\".*?\})\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


class NovelOutputSplitter:
    """Splits raw LLM output into clean prose and WritingMetadata."""

    @staticmethod
    def split_novel_output(raw_output: str) -> Tuple[str, Optional[WritingMetadata]]:
        """
        Splits LLM generated text into novel prose and WritingMetadata.

        Args:
            raw_output: Full text output from LLM

        Returns:
            Tuple of (clean_prose, metadata)
        """
        if not raw_output:
            return "", None

        prose = raw_output
        json_str: Optional[str] = None

        # 1. Look for [METADATA_JSON] ... [/METADATA_JSON]
        match = METADATA_TAG_PATTERN.search(raw_output)
        if match:
            json_str = match.group(1).strip()
            # Remove metadata block from prose
            prose = raw_output[: match.start()] + raw_output[match.end() :]
        else:
            # Fallback: check trailing json block
            fallback_match = TRAILING_JSON_BLOCK_PATTERN.search(raw_output)
            if fallback_match:
                json_str = fallback_match.group(1).strip()
                prose = raw_output[: fallback_match.start()]

        # Clean prose (strip trailing separators, whitespace)
        clean_prose = re.sub(r"-{3,}\s*$", "", prose.strip()).strip()

        # Parse JSON into WritingMetadata
        metadata: Optional[WritingMetadata] = None
        if json_str:
            metadata = _parse_metadata(json_str)

        return clean_prose, metadata


def _parse_metadata(json_str: str) -> Optional[WritingMetadata]:
    """JSON文字列を WritingMetadata へ変換する（不正エントリは隔離して破棄する）。

    v5.3 までは `WritingMetadata.model_validate` を1回だけ呼んでいたため、
    `foreshadowings` 配列の1要素が不正（action が enum 外、rationale が数字、ID 欠落など）
    のだけで、伏線回収の報告全体 WritingMetadata が `None` に化けていた。
    長編では契約伏線が数十本並ぶため、1件の型崩れで全話分の報告を失うのは致命的。
    ここでは「配列の要素単位」で検証し、不正な要素だけを落とす。
    """
    try:
        # Remove any remaining triple backticks inside tag
        cleaned_json = re.sub(r"^```(?:json)?\s*", "", json_str).rstrip("` \n")
        data = json.loads(cleaned_json)
    except Exception as e:
        logger.warning(
            f"Failed to json-parse WritingMetadata from LLM output: {e}. Raw json snippet: {json_str[:200]}"
        )
        return None

    if not isinstance(data, dict):
        logger.warning(
            f"WritingMetadata JSON is not an object: {type(data).__name__}. Raw: {json_str[:200]}"
        )
        return None

    entries = data.get("foreshadowings")
    if isinstance(entries, list):
        valid_entries = []
        for index, entry in enumerate(entries):
            try:
                ForeshadowingReport.model_validate(entry)
            except Exception as e:
                logger.warning(
                    f"Dropping malformed foreshadowing entry #{index} in WritingMetadata: {e}"
                )
                continue
            valid_entries.append(entry)
        if len(valid_entries) != len(entries):
            data = {**data, "foreshadowings": valid_entries}

    try:
        return WritingMetadata.model_validate(data)
    except Exception as e:
        logger.warning(
            f"Failed to validate WritingMetadata from LLM output: {e}. Raw json snippet: {json_str[:200]}"
        )
        return None
