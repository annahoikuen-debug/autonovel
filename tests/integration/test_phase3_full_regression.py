import asyncio

from src.engine.graph.networkx_store import NetworkXGraphStore
from src.integrations.cost_guard.budget_guard import CostBudgetGuard
from src.agents.specialists.model_router import AuditorModelRouter


def test_networkx_graph_store_regression():
    store = NetworkXGraphStore()
    store.add_entity("Character", "アリス", {"role": "protagonist"})
    store.add_entity("Character", "ボブ", {"role": "ally"})
    store.add_relation("Character", "アリス", "Character", "ボブ", "FRIEND")

    neighbors = store.find_neighbors("アリス", hops=1)
    assert len(neighbors.nodes) >= 1
    assert any(n.name == "ボブ" for n in neighbors.nodes)


def test_cost_budget_guard_regression():
    from src.integrations.cost_guard.analytics import CostCalculator
    calc = CostCalculator()
    guard = CostBudgetGuard(calculator=calc, budget_limit=10.0)
    # NOTE: check_budget_status は async 化 (check_budget_status_async) された。
    # total_cost_usd を明示指定すれば db_session は参照されないため None を渡す。
    status = asyncio.run(guard.check_budget_status_async(None, book_id=1, total_cost_usd=5.0))
    assert status.value in ("normal", "warning", "exceeded")


def test_auditor_model_router_regression():
    router = AuditorModelRouter()
    provider = router._resolve_primary_provider_for_auditor("consistency")
    assert provider in ("gemini", "openai", "claude")
