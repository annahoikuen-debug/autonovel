"""scripts/check_test_collection.py の感度テスト。

returncode != 0（collection error 発生）でも件数が一致していれば通過してしまう
旧動作を防ぐため、returncode != 0 なら exit 1 にすることを検証する。
"""

from scripts import check_test_collection


def test_collect_count_nonzero_returncode_fails(monkeypatch):
    """pytest --collect-only が returncode != 0 で終わると exit 1 になること。

    件数がベースラインと一致していても、collection error があれば赤にする。
    """

    def fake_collect_count():
        raise RuntimeError("終了コード 2 で pytest --collect-only が失敗しました")

    monkeypatch.setattr(check_test_collection, "_collect_count", fake_collect_count)
    monkeypatch.setattr("sys.argv", ["check_test_collection.py"])

    rc = check_test_collection.main()
    assert rc == 1


def test_main_runtimeerror_returns_1(monkeypatch):
    """_collect_count() が RuntimeError を投げたら main() は 1 を返すこと。"""

    def fake_collect_count():
        raise RuntimeError("pytest --collect-only の出力から収集件数を取得できませんでした")

    monkeypatch.setattr(check_test_collection, "_collect_count", fake_collect_count)
    monkeypatch.setattr("sys.argv", ["check_test_collection.py"])

    rc = check_test_collection.main()
    assert rc == 1


def test_collect_count_zero_returncode_passes(monkeypatch):
    """pytest --collect-only が returncode 0 で終われば件数を返すこと。"""

    def fake_collect_count():
        return 9763

    monkeypatch.setattr(check_test_collection, "_collect_count", fake_collect_count)

    count = check_test_collection._collect_count()
    assert count == 9763
