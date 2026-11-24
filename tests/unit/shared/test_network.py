"""src/shared/network.py (NetworkUtils) の単体テスト."""

from __future__ import annotations

from src.shared.network import NetworkUtils


class TestNetworkUtils:
    """NetworkUtils のテスト."""

    def test_generate_connection_id_returns_str(self):
        cid = NetworkUtils.generate_connection_id()
        assert isinstance(cid, str)

    def test_generate_connection_id_is_uuid_format(self):
        cid = NetworkUtils.generate_connection_id()
        # UUID 形式 (8-4-4-4-12 の 36 文字)
        assert len(cid) == 36
        assert cid.count("-") == 4

    def test_generate_connection_ids_are_unique(self):
        ids = {NetworkUtils.generate_connection_id() for _ in range(100)}
        assert len(ids) == 100
