"""Step 5 (H4): Huey ペイロードの JSON シリアライザ移行と API キー除外。

H4: Huey のデフォルトシリアライザが pickle であり、Redis/SQLite への
書き込み権限があればワーカーで RCE が可能。また llm_config.api_key や
生オブジェクト (FourLayerCompressor) がキューに平文永続化される。
"""
from __future__ import annotations

import inspect

from src.backend.tasks.huey import huey
from src.backend.routers import easy_mode


def test_huey_uses_json_serializer_not_pickle():
    """Huey のシリアライザが JSONSerializer である（H4）。"""
    ser = huey.serializer
    ser_name = type(ser).__name__
    assert ser_name == "HueyJSONSerializer", f"Huey シリアライザが HueyJSONSerializer ではない: {ser_name}"
    # pickle ではないことを明示
    assert "Pickle" not in ser_name


def test_easy_mode_task_params_excludes_api_key_and_compressor():
    """easy_mode.py のタスクパラメータに api_key と compressor 生オブジェクトを含まない（H4）。"""
    src = inspect.getsource(easy_mode)
    # params 構築ブロックに api_key の除外フィルタが含まれること
    assert 'if k != "api_key"' in src, "easy_mode.py で llm_config から api_key が除外されていない (H4)"
    # FourLayerCompressor のインスタンス生成が params から削除されていること
    assert 'FourLayerCompressor(config=CompressionConfig())' not in src, (
        "easy_mode.py の params に FourLayerCompressor 生オブジェクトが残っている (H4)"
    )
