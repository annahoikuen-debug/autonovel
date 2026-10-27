"""Character dictionary loader."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Optional

import yaml


def _normalize_characters(values) -> set:
    """辞書要素から有効なキャラ名のみを取り出す。

    空文字や非文字列 (数値・null 等) は除外する。空文字が残ると
    ``text.find("", 0)`` が常に 0 を返し、抽出ループが無限に回る。
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        return set()
    return {v for v in values if isinstance(v, str) and v.strip()}


@functools.lru_cache(maxsize=1)
def _load_character_dict_frozen(path: Optional[str] = None) -> frozenset:
    """キャラクタ辞書を読み込み (frozen でキャッシュする内部実装)。"""
    if path is None:
        # デフォルト検索パス
        candidates = [
            Path(__file__).parent.parent.parent / "config" / "characters.yaml",
            Path(__file__).parent.parent.parent / "config" / "characters.yml",
            Path.cwd() / "config" / "characters.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                break
        else:
            # 見つからない場合は空セット返却
            return frozenset()

    path_obj = Path(path)
    if not path_obj.exists():
        return frozenset()

    with open(path, "r", encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            data = yaml.safe_load(f)
        elif path.endswith(".json"):
            import json
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported format: {path}")

    # リスト形式を想定
    if isinstance(data, list):
        return frozenset(_normalize_characters(data))
    elif isinstance(data, dict) and "characters" in data:
        return frozenset(_normalize_characters(data["characters"]))
    else:
        return frozenset()


def load_character_dict(path: Optional[str] = None) -> set[str]:
    """キャラクタ辞書を読み込み（キャッシュ付き・呼び出しごとに複製を返す）

    Args:
        path: YAML/JSONファイルパス。Noneの場合はデフォルト場所を探索

    Returns:
        キャラクター名のセット
    """
    # キャッシュ本体は frozen だが、呼び出し側が set を変更しても
    # 他のリクエストへ影響しないようコピーを返す
    return set(_load_character_dict_frozen(path))


def save_character_dict(characters: set[str], path: str) -> None:
    """キャラクタ辞書を保存"""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    data = {"characters": sorted(characters)}

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


__all__ = ["load_character_dict", "save_character_dict"]
