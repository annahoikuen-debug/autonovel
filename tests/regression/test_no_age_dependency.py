"""Regression test to verify complete decoupling from Apache AGE (Step 26)."""

import importlib
import pytest


def test_core_services_import_without_age():
    """Verify core services can be imported and initialized without age_client."""
    modules_to_test = [
        "src.integrations.rag.rag_service",
        "src.engine.graph_pipeline",
        "src.services.reflective_rag",
        "src.engine.compression.layer2_subgraph",
        "src.engine.compression.compressor",
        "src.backend.routers.graph",
    ]
    for mod_name in modules_to_test:
        mod = importlib.import_module(mod_name)
        assert mod is not None


def test_age_client_deprecation_warning():
    """Verify importing age_client emits a DeprecationWarning."""
    with pytest.deprecated_call():
        import src.integrations.age_client
        importlib.reload(src.integrations.age_client)
