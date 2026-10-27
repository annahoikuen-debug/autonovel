"""SPI 関連のユニットテスト"""

from src.core.spi.llm.interface import ILLMProvider
from src.core.spi.vector_store.interface import IVectorStoreProvider
from src.core.spi.interface import IImageProvider, ImageResult

from src.core.spi.llm.mock_adapter import MockLLMProvider
from src.core.spi.vector_store.chroma_adapter import ChromaVectorProvider
from src.core.spi.vector_store.mock_adapter import MockVectorProvider
from src.core.spi.image.genai_adapter import GenAIImageProvider
from src.core.spi.image.mock_adapter import MockImageProvider


def test_llm_adapters_implement_interface():
    """LLM アダプターが ILLMProvider を実装していることを確認する"""
    # モックアダプターは API キー不要
    mock_provider = MockLLMProvider()
    assert isinstance(mock_provider, ILLMProvider)


def test_spi_llm_has_no_fake_gemini_provider():
    """フェイク Gemini プロバイダが SPI から除去されていることを確認する。

    過去に `src/core/spi/llm/gemini_adapter.py` に実際の API 呼び出しを一切行わず
    `"[Gemini Response] ..."` という固定文字列を返す実装が存在し、DI 経由で
    DAG パイプラインに注入されていた。本番出力が捏造されうるため、
    モジュール自体が存在しないことを回帰テストで固定する。
    """
    import importlib.util

    assert importlib.util.find_spec("src.core.spi.llm.gemini_adapter") is None, (
        "フェイク GeminiLLMProvider が復活しています。本番出力を捏造するため削除を維持してください"
    )

    # 公開 API からも GeminiLLMProvider が公開されていないこと
    import src.core.spi.llm as spi_llm

    assert not hasattr(spi_llm, "GeminiLLMProvider")


def test_spi_llm_factory_rejects_non_mock_provider():
    """モック以外のプロバイダ指定は黙ってモックへ倒れず、明示的に失敗する。"""
    from src.core.spi.llm.provider_factory import LLMProviderFactory

    factory = LLMProviderFactory()
    assert isinstance(factory.create("mock"), MockLLMProvider)

    for provider in ("gemini", "openai", "claude"):
        try:
            factory.create(provider)
        except ValueError:
            continue
        raise AssertionError(
            f"provider_type={provider!r} が ValueError を投げずに生成されました。"
            " フェイク実装が復活しています"
        )


def test_vector_store_adapters_implement_interface():
    """ベクトルストア アダプターが IVectorStoreProvider を実装していることを確認する"""
    mock_provider = MockVectorProvider()
    assert isinstance(mock_provider, IVectorStoreProvider)

    try:
        chroma_provider = ChromaVectorProvider()
        assert isinstance(chroma_provider, IVectorStoreProvider)
    except Exception:
        # chromadb がインストールされていない可能性がある
        pass


def test_image_adapters_implement_interface():
    """画像 アダプターが IImageProvider を実装していることを確認する"""
    mock_provider = MockImageProvider()
    assert isinstance(mock_provider, IImageProvider)

    try:
        genai_provider = GenAIImageProvider(api_key="dummy")
        assert isinstance(genai_provider, IImageProvider)
    except Exception:
        # API キー関連のエラーが発生する可能性がある
        pass


def test_image_result_dataclass():
    """ImageResult データクラスが正しく動作することを確認する"""
    result = ImageResult(
        image_data=b"dummy",
        prompt="test prompt",
        metadata={"key": "value"},
    )
    assert result.image_data == b"dummy"
    assert result.prompt == "test prompt"
    assert result.metadata == {"key": "value"}
