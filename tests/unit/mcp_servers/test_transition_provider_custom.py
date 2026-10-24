"""SceneTransitionValidator 汎用ルール（ユーザー定義設定）のテスト。"""

from __future__ import annotations

from src.mcp_servers.transition_schemas import SceneState
from src.mcp_servers.providers.transition_provider import SceneTransitionValidator


def _state(**kwargs) -> SceneState:
    defaults = dict(character_name="Hero", location="Town")
    defaults.update(kwargs)
    return SceneState(**defaults)


# ---------------------------------------------------------------------------
# 1. ユーザー定義ルール（forbidden_instant_moves / allowed_transitions）
# ---------------------------------------------------------------------------


def test_custom_forbidden_instant_moves_detects_conflict():
    validator = SceneTransitionValidator(forbidden_instant_moves=[("Village", "Mountain Peak")])
    res = validator.validate_transition(_state(location="Village"), _state(location="Mountain Peak"))
    assert res.is_valid is False
    assert any(c.conflict_type == "location" for c in res.conflicts)
    assert any("Village" in p for p in res.patch_suggestions)


def test_custom_forbidden_pair_allows_travel_method():
    validator = SceneTransitionValidator(forbidden_instant_moves=[("Village", "Mountain Peak")])
    res = validator.validate_transition(
        _state(location="Village"),
        _state(location="Mountain Peak", metadata={"travel_method": "horse"}),
    )
    assert res.is_valid is True


def test_default_rules_still_apply():
    """デフォルトルール（Dungeon -> Royal Castle）が包括されていること。"""
    validator = SceneTransitionValidator()
    assert ("Dungeon", "Royal Castle") in validator.forbidden_instant_moves
    res = validator.validate_transition(_state(location="Dungeon"), _state(location="Royal Castle"))
    assert res.is_valid is False


def test_default_rules_can_be_disabled():
    """空リスト指定でデフォルトルールを無効化できること。"""
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    res = validator.validate_transition(_state(location="Dungeon"), _state(location="Royal Castle"))
    assert res.is_valid is True


def test_allowed_transitions_rejects_unlisted_pair():
    validator = SceneTransitionValidator(
        allowed_transitions={"Town": ["Forest", "River"], "Forest": ["Town"]},
        forbidden_instant_moves=[],
    )
    res = validator.validate_transition(_state(location="Town"), _state(location="Volcano"))
    assert res.is_valid is False
    assert any("allowed_transitions" in c.message for c in res.conflicts)


def test_allowed_transitions_allows_listed_pair():
    validator = SceneTransitionValidator(
        allowed_transitions={"Town": ["Forest"]},
        forbidden_instant_moves=[],
    )
    res = validator.validate_transition(_state(location="Town"), _state(location="Forest"))
    assert res.is_valid is True


def test_allowed_transitions_accepts_teleport_tag():
    validator = SceneTransitionValidator(
        allowed_transitions={"Town": []},
        forbidden_instant_moves=[],
    )
    res = validator.validate_transition(
        _state(location="Town"),
        _state(location="Volcano", metadata={"tags": ["Teleport"]}),
    )
    assert res.is_valid is True


# ---------------------------------------------------------------------------
# 2. 汎用メタデータルール（distance_category == "remote"）
# ---------------------------------------------------------------------------


def test_remote_metadata_without_travel_method_warns():
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    res = validator.validate_transition(
        _state(location="Town"),
        _state(location="Far Away Land", metadata={"distance_category": "remote"}),
    )
    # warning は is_valid を落とさないがコンフリクトは検出される
    assert any(c.conflict_type == "location" and c.severity == "warning" for c in res.conflicts)


def test_remote_metadata_with_travel_method_is_clean():
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    res = validator.validate_transition(
        _state(location="Town"),
        _state(
            location="Far Away Land",
            metadata={"distance_category": "remote", "travel_method": "airship"},
        ),
    )
    assert res.is_valid is True
    assert res.conflicts == []


def test_remote_rule_can_be_disabled():
    validator = SceneTransitionValidator(forbidden_instant_moves=[], enforce_remote_metadata_rule=False)
    res = validator.validate_transition(
        _state(location="Town"),
        _state(location="Far Away Land", metadata={"distance_category": "remote"}),
    )
    assert res.conflicts == []


# ---------------------------------------------------------------------------
# 3. インベントリ / ステータス整合性（汎用ルールとの組み合わせ）
# ---------------------------------------------------------------------------


def test_item_acquisition_metadata_resolves_inventory_conflict():
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    res = validator.validate_transition(
        _state(inventory=[]),
        _state(inventory=["Magic Orb"], metadata={"item_acquired": True}),
    )
    assert not any(c.conflict_type == "inventory" for c in res.conflicts)


def test_injury_healing_flow_normal():
    """critical_injured -> healed -> normal の正常系。"""
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    injured = _state(location="Camp", status="critical_injured")
    healed = _state(location="Camp", status="injured", metadata={"healed": True})
    res1 = validator.validate_transition(injured, healed)
    assert res1.is_valid is True

    normal = _state(location="Camp", status="normal", metadata={"healed": True})
    res2 = validator.validate_transition(healed, normal)
    assert res2.is_valid is True


def test_injury_recovery_anomaly_still_detected():
    """回復描写なしで normal へ復帰する異常系は検出されること。"""
    validator = SceneTransitionValidator(forbidden_instant_moves=[])
    res = validator.validate_transition(
        _state(location="Camp", status="critical_injured"),
        _state(location="Camp", status="normal"),
    )
    assert res.is_valid is False
    assert any(c.conflict_type == "status" for c in res.conflicts)
