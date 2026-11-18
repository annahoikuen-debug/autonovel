"""scripts/check_test_collection.py の感度テスト。

returncode != 0（collection error 発生）でも件数が一致していれば通過してしまう
旧動作を防ぐため、returncode != 0 なら exit 1 にすることを検証する。

Plan Q6 Step11 の計画どおり、``subprocess.run`` を monkeypatch し
``returncode=2`` + 件数行ありの情境を再現して検証する（returncode 分岐を
実際に通過させる）。
"""

from scripts import check_test_collection


class _FakeCompletedProcess:
    returncode: int
    stdout: str
    stderr: str

    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_collect_count_nonzero_returncode_fails(monkeypatch):
    """pytest --collect-only が returncode != 0 で終わると exit 1 になること。

    件数行（"collected 9761 items"）が出力されていても、
    collection error があれば赤にする。
    """

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=2, stdout="collected 9761 items")

    monkeypatch.setattr(check_test_collection, "_run", fake_run)

    try:
        check_test_collection._collect_count()
        assert False, "RuntimeError が発生するはず"
    except RuntimeError as e:
        assert "終了コード 2" in str(e)


def test_collect_count_zero_returncode_passes(monkeypatch):
    """pytest --collect-only が returncode 0 で終われば件数を返すこと。"""

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=0, stdout="collected 9763 items")

    monkeypatch.setattr(check_test_collection, "_run", fake_run)

    count = check_test_collection._collect_count()
    assert count == 9763


def test_main_nonzero_returncode_returns_1(monkeypatch):
    """_collect_count() が returncode != 0 で RuntimeError を投げたら
    main() は 1 を返すこと（件数行が出力されていても）。"""

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=2, stdout="collected 9761 items")

    monkeypatch.setattr(check_test_collection, "_run", fake_run)
    monkeypatch.setattr("sys.argv", ["check_test_collection.py"])

    rc = check_test_collection.main()
    assert rc == 1
