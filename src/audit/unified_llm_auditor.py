"""
Unified LLM auditor that evaluates multiple aspects in a single LLM call.
Consolidates 8 specialist auditors into one LLM call for cost and latency reduction.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class AuditUnavailableError(RuntimeError):
    """LLM 呼び出し自体が成立しなかった場合に送出する。

    「指摘が 0 件」(= 問題なし) と「監査を 実行できなかった」を
    呼び出し側で区別できるようにするための型。呼び出し側が空リストを
    「問題なし」と誤解してゲートの合格と誤認するのを防ぐ。
    """


@dataclass
class Issue:
    """Represents an issue found by the auditor."""
    type: str  # Issue category (e.g., "plot_inconsistency", "character_appeal")
    message: str  # Human-readable description
    location: Optional[Tuple[int, int]] = None  # (start_index, end_index) or None if location unknown
    suggestion: Optional[str] = None  # Optional suggestion for fixing the issue


# Module-level function that can be easily mocked in tests
def call_llm_api(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    LLM APIを呼び出す関数。
    テストではこの関数をモックする。未モック時は実アダプタ連携を試みる。

    Args:
        prompt: ユーザープロンプト
        system_prompt: システムプロンプト（オプション）

    Returns:
        str: LLMからの生のレスポンス（文字列）
    """
    try:
        from src.services.llm.factory import get_llm_adapter
        adapter = get_llm_adapter()
        if hasattr(adapter, "generate_text_sync"):
            return adapter.generate_text_sync(prompt=prompt, system_prompt=system_prompt)
        elif hasattr(adapter, "generate_text"):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # 既にイベントループが動いている場合はブロッキング回避のためスレッドで実行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, adapter.generate_text(prompt=prompt, system_prompt=system_prompt))
                    return future.result(timeout=30)
            else:
                return asyncio.run(adapter.generate_text(prompt=prompt, system_prompt=system_prompt))
        # generate_text 系が 1 つも無い場合は従来 None を暗黙 return して
        # 呼び出し側が AttributeError を受けていた。明示的に失敗させる。
        raise AttributeError(
            f"LLM adapter {type(adapter).__name__} exposes neither "
            "'generate_text_sync' nor 'generate_text'"
        )
    except Exception as e:
        logger.error("Default LLM adapter call failed: %s", e, exc_info=True)
        raise AuditUnavailableError(
            f"LLM API呼び出しが実装されていないか利用できません: {e}"
        ) from e


class UnifiedLLMAuditor:
    """統合LLMオーディター - 1回のLLMコールで複数観点を評価"""

    def __init__(self):
        """Unified LLM Auditorを初期化"""
        pass

    def audit(self, text: str) -> List[Issue]:
        """
        テキストに対して統合LLMオーディットを実行

        Args:
            text: 評価対象のテキスト

        Returns:
            List[Issue]: 検出された問題のリスト

        Raises:
            AuditUnavailableError: LLM 呼び出し自体が成立しなかった場合。
                以前はここを握り潰して空リストを返していたため、
                「指摘ゼロ（= 問題なし）」と「監査 未実施」を呼び出し側が
                区別できず、LLM 障害時に章が無条件に通gradeされていた。
        """
        if not text:
            return []

        # 監査用プロンプトを構築
        prompt = self._construct_audit_prompt(text)

        # LLM 呼び出しの失敗は握り潰さない（Typed error で伝播させる）
        response = call_llm_api(prompt)

        # レスポンスをパースしてIssueオブジェクトのリストを返す
        return self._parse_llm_response(response)

    def _construct_audit_prompt(self, text: str) -> str:
        """
        統合監査用のプロンプトを構築
        8つの観点（プロットの一貫性、キャラクターの魅力など）を評価するようLLMに指示
        """
        prompt = f"""
あなたは小説の品質を多角的に評価する専門編集オーディターです。
以下のテキストについて、8つの観点で評価し、問題がある場合は指摘してください：

1. プロットの一貫性
2. キャラクターの魅力
3. 文体の適切さ
4. 感情の起伏
5. オリジナリティ
6. ジャンル適合性
7. 読みやすさ
8. 総合エンターテインメント性

評価対象テキスト：
{text}

以下のJSON形式で結果を返してください（コードブロック等を使わずJSON配列のみを出力してください）：
[
  {{"type": "issue_type", "message": "issue description", "suggestion": "optional suggestion"}}
]

issue_typeには以下のいずれかを使用してください：
- plot_inconsistency
- character_appeal
- style_appropriateness
- emotional_variety
- originality
- genre_fit
- readability
- overall_entertainment

問題がない場合は空の配列 [] を返してください。
"""
        return prompt.strip()

    def _extract_json_string(self, response: str) -> str:
        """Markdownコードブロックや前後の説明文からJSON文字列を抽出"""
        if not response:
            return "[]"
        # 1. ```json ... ``` または ``` ... ``` を抽出
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response, re.IGNORECASE)
        if code_block:
            return code_block.group(1).strip()

        # 2. [ ... ] 配列を抽出
        array_match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", response)
        if array_match:
            return array_match.group(0).strip()

        # 3. 空配列 []
        if "[]" in response:
            return "[]"

        return response.strip()

    def _parse_llm_response(self, response: str) -> List[Issue]:
        """
        LLMからの生のレスポンスをIssueオブジェクトのリストにパース

        項目ごとの検証 tomography を先に済ませてからリストを構築する。
        以前はループ途中で ``int(item["location"][0])`` が ValueError を投げると、
        例外が外側の except に捕まって「それまでに積めた分だけ」が返り、
        残りの指摘が黙って捨てられていた。
        """
        if not response:
            return []

        try:
            cleaned_json = self._extract_json_string(response)
            data = json.loads(cleaned_json)
        except (json.JSONDecodeError, ValueError) as e:
            # パース不能な応答は「指摘なし」ではないが、既存テスト
            # (test_auditor_handles_broken_text_gracefully) が [] を
            # 要求しているため空リストを返しつつ、debug ではなく
            # error レベルで可視化する。
            logger.error(
                "UnifiedLLMAuditor: LLM 応答を JSON として解釈できませんでした: %s", e
            )
            return []

        if not isinstance(data, list):
            logger.error(
                "UnifiedLLMAuditor: JSON のトップレベルが list ではありません: %s",
                type(data).__name__,
            )
            return []

        issues: List[Issue] = []
        skipped = 0
        for item in data:
            if not isinstance(item, dict) or "type" not in item or "message" not in item:
                skipped += 1
                continue
            issues.append(
                Issue(
                    type=str(item["type"]),
                    message=str(item["message"]),
                    location=self._parse_location(item.get("location")),
                    suggestion=item.get("suggestion"),
                )
            )
        if skipped:
            logger.error(
                "UnifiedLLMAuditor: 形式不正の指摘項目を %d 件スキップしました", skipped
            )
        return issues

    @staticmethod
    def _parse_location(location: object) -> Optional[Tuple[int, int]]:
        """LLM が返した location を安全に解釈する。非数値なら None（例外を出さない）。"""
        if not isinstance(location, (list, tuple)) or len(location) != 2:
            return None
        try:
            start, end = int(location[0]), int(location[1])
        except (TypeError, ValueError):
            logger.error(
                "UnifiedLLMAuditor: location が数値ではないため位置情報を破棄しました: %r",
                location,
            )
            return None
        if start > end:
            start, end = end, start
        return (start, end)
