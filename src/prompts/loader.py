import logging
import os
import re
import threading
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# テンプレート名として許容する形式。
# (version, template_name) の双方がこれを満たさない場合は読み込みを拒否する。
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PromptLoader:
    """
    プロンプトテンプレートをロードし、変数を置換するローダー。
    バージョン指定、フォールバック、キャッシュ機能を提供。
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        プロンプトローダーを初期化。

        Args:
            base_path: プロンプトファイルのベースディレクトリ。
                      Noneの場合は、このファイルの親ディレクトリの親の「prompts」を使用。
        """
        if base_path is None:
            # このファイルの場所から推測: src/prompts/loader.py -> src/prompts -> src -> プロジェクトルート
            # そしてプロジェクトルートの prompts ディレクトリ
            current_file = Path(__file__).resolve()
            self.base_path = current_file.parent.parent.parent / "prompts"
        else:
            self.base_path = Path(base_path)

        # 解決済みベースパス（パス検証に使う）
        self._resolved_base = self.base_path.resolve()

        # キャッシュ: {(template_name, version): (template_string, mtime)}
        self._cache: Dict[tuple, tuple] = {}
        self._cache_lock = threading.Lock()

        # 利用可能なバージョンを検出
        self._available_versions = self._detect_versions()

    def _detect_versions(self) -> list:
        """利用可能なバージョンディレクトリを検出"""
        versions = []
        skip = {"base", "latest", "__pycache__"}
        if self.base_path.exists():
            for item in self.base_path.iterdir():
                if item.is_dir() and item.name not in skip:
                    versions.append(item.name)
        # ベースとlatestは常に利用可能とみなす
        if (self.base_path / "base").exists():
            versions.append("base")
        if (self.base_path / "latest").exists():
            versions.append("latest")
        return sorted(list(set(versions)))

    def _validate_segments(self, template_name: str, version: str) -> None:
        """テンプレート名/バージョン名は base_path 配下に解決されなければならない。

        以前は ``base_path / version / f"{name}.yaml"`` を無検証で組み立てて
        いたため、``version="../../secrets"`` 等でベース外を参照できた。
        """
        for label, value in (("template_name", template_name), ("version", version)):
            if not _SAFE_SEGMENT.match(value) or value in {".", ".."}:
                raise ValueError(
                    f"Unsafe {label}: {value!r} "
                    "(allowed: letters, digits, dot, underscore, hyphen)"
                )

    def _get_template_path(self, template_name: str, version: str) -> Path:
        """テンプレートファイルのフルパスを取得（ベース外への脱出を拒否）"""
        self._validate_segments(template_name, version)
        candidate = (self.base_path / version / f"{template_name}.yaml").resolve()
        try:
            candidate.relative_to(self._resolved_base)
        except ValueError as exc:
            raise ValueError(
                f"Resolved template path escapes base_path: {candidate}"
            ) from exc
        return candidate

    def _is_cache_fresh(self, cache_key: tuple, template_path: Path) -> bool:
        """キャッシュの mtime がDiskの mtime と一致するか（＝無効化されていないか）"""
        with self._cache_lock:
            entry = self._cache.get(cache_key)
        if entry is None:
            return False
        _content, cached_mtime = entry
        try:
            return os.path.getmtime(template_path) == cached_mtime
        except OSError:
            return False

    def load(
        self, template_name: str, version: str = "latest", *, strict: bool = True
    ) -> str:
        """
        テンプレートをロードし、生の文字列を返す（変数は置換しない）。

        Args:
            template_name: テンプレート名（拡張子なし、例: "system"）
            version: バージョン名（デフォルト: "latest"）
            strict: True（既定）の場合、指定バージョンが存在しなければ
                    他のバージョンへフォールバックせず FileNotFoundError を出す。

        Returns:
            テンプレートの生の文字列

        Raises:
            ValueError: テンプレート名/バージョンが安全でない場合
            FileNotFoundError: テンプレートが見つからない場合
        """
        # 検証を先に行う（不正な version で base_path へ出る前に弾く）
        self._validate_segments(template_name, version)

        if strict:
            # 指定バージョン目录下のみ探索する。
            # 存在しないバージョンを別バージョンで黙って代用しない。
            template_path = self._get_template_path(template_name, version)
            if not template_path.exists():
                raise FileNotFoundError(
                    f"テンプレートが見つかりません: {template_name}.yaml "
                    f"(バージョン: {version}, パス: {template_path})"
                )
            return self._read_cached(template_name, version, template_path)

        # 明示的に lenient を指定された場合のみレガシーチェーンを使う。
        # ここでは必ず警告を出して、どの版に退避したかを残す。
        fallback_versions = [version, "base"] + [
            v for v in self._available_versions if v not in [version, "base"]
        ]
        for ver in fallback_versions:
            template_path = self._get_template_path(template_name, ver)
            if not template_path.exists():
                continue
            if ver != version:
                logger.warning(
                    "Requested prompt version %r not found for %r; "
                    "falling back to %r (the rendered prompt will NOT match "
                    "the requested version).",
                    version,
                    template_name,
                    ver,
                )
            return self._read_cached(template_name, ver, template_path)

        raise FileNotFoundError(
            f"テンプレートが見つかりません: {template_name}.yaml "
            f"(バージョン: {version}, 試したバージョン: {fallback_versions})"
        )

    def _read_cached(self, template_name: str, version: str, template_path: Path) -> str:
        """mtime を検証しつつキャッシュから読み込む（編集があれば自動で失効）。"""
        cache_key = (template_name, version)
        if self._is_cache_fresh(cache_key, template_path):
            with self._cache_lock:
                return self._cache[cache_key][0]

        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        with self._cache_lock:
            try:
                mtime = os.path.getmtime(template_path)
            except OSError:
                mtime = 0.0
            self._cache[cache_key] = (content, mtime)
        return content

    def render(
        self, template_name: str, version: str = "latest", *, strict: bool = True, **variables
    ) -> str:
        """
        テンプレートをロードして変数を置換して返す。
        置換は 1 パスで一括して行い、値の入れ子を再解釈しない。

        Args:
            template_name: テンプレート名（拡張子なし）
            version: バージョン名（デフォルト: "latest"）
            strict: バージョン不在時にフォールバックしない
            **variables: テンプレート内の{変数}を置換するためのキーワード引数

        Returns:
            変数が置換されたレンダリング済み文字列
        """
        template = self.load(template_name, version, strict=strict)
        if not variables:
            return template

        # 1 パス置換: str.replace を変数ごとに順番に呼ぶと、
        # ある変数の「値」の中に {別のキー} が含まれると次のループで
        # さらに置換されて「入れ子置換」が起きていた。
        pattern = re.compile(
            "|".join(re.escape("{" + key + "}") for key in variables)
        )
        return pattern.sub(
            lambda m: str(variables[m.group(0)[1:-1]]), template
        )

    def invalidate_cache(self) -> None:
        """テンプレート編集後にキャッシュを破棄する。"""
        with self._cache_lock:
            self._cache.clear()


# シングルトンインスタンス（オプション）
default_loader = PromptLoader()


if __name__ == "__main__":
    # 簡単な動作テスト
    loader = PromptLoader()
    print("利用可能なバージョン:", loader._available_versions)

    # システムプロンプトをロード
    system_prompt = loader.load("system")
    print("\n--- システムプロンプト (raw) ---")
    print(system_prompt[:200] + "..." if len(system_prompt) > 200 else system_prompt)

    # レンダリングテスト
    rendered = loader.render(
        "system",
        version="v1.0",
        min_chars=1000,
        max_chars=5000,
        genre="ファンタジー",
        keywords=["ドラゴン", "魔法"],
        tone="壮大"
    )
    print("\n--- レンダリング結果 ---")
    print(rendered)
