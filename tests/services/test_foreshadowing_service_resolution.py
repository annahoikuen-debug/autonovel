"""伏線解決の**本番経路**に対する回帰テスト。

なぜこのファイルが存在するか
---------------------------
2026-10-04 の公開前調査で `tests/services/test_foreshadowing_resolution_step.py`
（452行・6件失敗）を削除した。削除の理由は次の通り:

1. テストは `ForeshadowingResolutionStep` を検証していたが、
   `git log --all -S "class ForeshadowingResolutionStep"` は**空**であり、
   全履歴で**一度も実装されたことがない**（未実装の赤テスト）
2. テストは 1 行目で
   `ForeshadowingRegistrationStep as ForeshadowingResolutionStep` と alias しており、
   import は通るが**別物**（伏線「登録」ステップ）を叩いていた。
   そのため「この Step の失敗」ではなく「登録ステップの失敗」に見えてしまっていた
3. テストが主張していた仕様
   （「`hang_volume == current_volume` かつ `hang_episode == current_episode` の
   伏線を解決済みにする」）は**張った章と回収した章が同一**の伏線が許される
   意味論として成立しない
4. 解決判定は**既に別経路で実装済み**であり、
   新規 Step を足すと同一伏線に 2 系統の回収判定が競合して片方が誤判定を食う

欠落していたカバレッジを、正しい場所（本番経路）で取り直すのが本ファイルの目的。

本番経路:
    `src/agents/writing/episode_writer.py:374`
    `src/backend/workflows/writing_langgraph.py:779`
      → `ForeshadowingService.check_and_resolve()`
        → `repo.get_unresolved()` / `repo.resolve()`
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _StubRepo:
    """`ForeshadowingService` が使う repository の最小スタブ。"""

    def __init__(self, items, resolve_ok: bool = True):
        self._items = items
        self._resolve_ok = resolve_ok
        self.resolved: list[tuple[int, int]] = []

    async def get_unresolved(self, book_id: int):
        return list(self._items)

    async def resolve(self, foreshadowing_id: int, episode_num: int) -> bool:
        self.resolved.append((foreshadowing_id, episode_num))
        return self._resolve_ok

    # KPI 系が触るメソッド（契約上は未使用だが、存在しないと AttributeError になる）
    async def update_status(self, *args, **kwargs):
        return True

    async def defer(self, *args, **kwargs):
        return True

    async def get_by_id(self, foreshadowing_id: int):
        for it in self._items:
            if getattr(it, "id", None) == foreshadowing_id:
                return it
        return None


def _make_service(repo, resolved_status="RESOLVED"):
    """`check_and_resolve` のみを検証するためのサービス实例を作る。"""
    from src.services.foreshadowing_service import ForeshadowingService

    service = ForeshadowingService.__new__(ForeshadowingService)
    service.repo = repo
    service.predicate_analyzer = SimpleNamespace(
        analyze_foreshadowing=lambda **kw: SimpleNamespace(
            probability=0.9, confidence=0.9, evidence=[]
        )
    )
    return service


def _foreshadowing(fid: int, title: str, target_episode=None, status="planted"):
    return SimpleNamespace(
        id=fid,
        title=title,
        target_episode=target_episode,
        status=status,
        keywords=[],
    )


def _stub_kpi(monkeypatch) -> None:
    """KPI 報告をスタブ化する。

    `check_and_resolve` 内部で `ForeshadowingKpiService(self.repo)` が
    構築され、`report_transition()` が伏線オブジェクトの各種状態
    （`should_reschedule` 等）に触る。本ファイルが検証したいのは
    「回収判定 → `repo.resolve()` → 返却」という契約であり、
    KPI の内部状態は対象外の責務なので分離する。
    """
    import src.services.foreshadowing_service as mod

    class _StubKpi:
        def __init__(self, repo):
            self.repo = repo
            self.transitions: list[tuple[str, str]] = []

        async def report_transition(self, before: str, after: str) -> None:
            self.transitions.append((before, after))

    monkeypatch.setattr(mod, "ForeshadowingKpiService", _StubKpi)


class TestCheckAndResolveHappyPath:
    """回収判定された伏線が repository 経由で更新される。"""

    @pytest.mark.asyncio
    async def test_resolved_foreshadowing_is_marked(self, monkeypatch) -> None:
        """EnsembleJudge が RESOLVED と判定した場合、`repo.resolve()` が呼ばれる。"""
        from src.services.foreshadowing import ensemble_judge

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge,
            "evaluate",
            staticmethod(
                lambda **kw: SimpleNamespace(status="RESOLVED", rationale="本文で回収", should_reschedule=False)
            ),
        )

        _stub_kpi(monkeypatch)
        repo = _StubRepo([_foreshadowing(1, "欠けた鍵")])
        service = _make_service(repo)

        titles = await service.check_and_resolve(
            book_id=1, episode_num=3, draft_text="彼は欠けた鍵を手にした。"
        )

        assert titles == ["欠けた鍵"]
        assert repo.resolved == [(1, 3)], "repo.resolve() が呼ばれていない"

    @pytest.mark.asyncio
    async def test_no_unresolved_returns_empty(self) -> None:
        """未回収の伏線が 0 件なら空リストを返す（LLM 呼び出しなし）。"""
        repo = _StubRepo([])
        service = _make_service(repo)

        result = await service.check_and_resolve(
            book_id=1, episode_num=1, draft_text="何もない"
        )

        assert result == []
        assert repo.resolved == []


class TestPerItemFailureIsolation:
    """1件の失敗で当該話全体の判定が全滅しないこと（Step 33 の意図）。"""

    @pytest.mark.asyncio
    async def test_single_failure_does_not_stop_others(self, monkeypatch) -> None:
        """1本目の評価が例外を投げても、2本目以降は処理されること。

        長編では 1 話に数十本の伏線が並ぶ。1 件の DB エラーで
        残りの回収判定が失われると伏線管理が破綻するため、
        per-item の例外隔離が必須。
        """
        from src.services.foreshadowing import ensemble_judge

        items = [
            _foreshadowing(1, "一つ目"),
            _foreshadowing(2, "二つ目"),
        ]

        calls: list[int] = []

        def _evaluate(**kw):
            fid = kw.get("foreshadowing_id")
            calls.append(fid)
            if fid == 1:
                raise RuntimeError("DB error")
            return SimpleNamespace(status="RESOLVED", rationale="ok", should_reschedule=False)

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge, "evaluate", staticmethod(_evaluate)
        )

        _stub_kpi(monkeypatch)
        repo = _StubRepo(items)
        service = _make_service(repo)

        titles = await service.check_and_resolve(
            book_id=1, episode_num=2, draft_text="本文"
        )

        assert calls == [1, 2], "1件目の失敗で 2件目が処理されていない"
        assert titles == ["二つ目"], "1件目の失敗で 2件目の回収が失われている"
        assert repo.resolved == [(2, 2)]

    @pytest.mark.asyncio
    async def test_items_without_id_are_skipped(self) -> None:
        """`id` が None の伏線は判定対象にしない。"""
        repo = _StubRepo([SimpleNamespace(id=None, title="不正データ", target_episode=None)])
        service = _make_service(repo)

        result = await service.check_and_resolve(
            book_id=1, episode_num=1, draft_text="本文"
        )

        assert result == []


class TestContractedVsUncontracted:
    """`target_episode is None` を「契約済み」扱いしないこと。

    旧挙動は `target_ep is None` のときに契約済みとみなしていたため、
    契約情報を持たない全伏線を無条件に「本話回収必須」扱いしていた。
    現在の仕様（`foreshadowing_service.py:123-126`）は、
    `contract_ids` に含まれるか `target_episode == episode_num` の場合のみ
    契約済みとみなす。
    """

    @pytest.mark.asyncio
    async def test_target_episode_none_is_not_contracted(self, monkeypatch) -> None:
        """`target_episode=None` は「契約済み」ではない。"""
        from src.services.foreshadowing import ensemble_judge

        seen: dict[str, object] = {}

        def _evaluate(**kw):
            seen["is_contracted"] = kw.get("is_contracted")
            return SimpleNamespace(status="PLANTED", rationale="未回収", should_reschedule=False)

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge, "evaluate", staticmethod(_evaluate)
        )

        repo = _StubRepo([_foreshadowing(1, "無期限", target_episode=None)])
        service = _make_service(repo)

        await service.check_and_resolve(
            book_id=1, episode_num=5, draft_text="本文"
        )

        assert seen["is_contracted"] is False, (
            "target_episode=None の伏線が契約済みと判定されている"
        )

    @pytest.mark.asyncio
    async def test_target_episode_equal_to_current_is_contracted(
        self, monkeypatch
    ) -> None:
        """`target_episode == episode_num` は契約済み。"""
        from src.services.foreshadowing import ensemble_judge

        seen: dict[str, object] = {}

        def _evaluate(**kw):
            seen["is_contracted"] = kw.get("is_contracted")
            return SimpleNamespace(status="PLANTED", rationale="未回収", should_reschedule=False)

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge, "evaluate", staticmethod(_evaluate)
        )

        repo = _StubRepo([_foreshadowing(1, "今話回収", target_episode=5)])
        service = _make_service(repo)

        await service.check_and_resolve(book_id=1, episode_num=5, draft_text="本文")

        assert seen["is_contracted"] is True

    @pytest.mark.asyncio
    async def test_contract_ids_none_differs_from_empty_list(
        self, monkeypatch
    ) -> None:
        """`contract_ids=None` と `[]` は意味が異なる（前者は情報なし、後者は契約0件）。"""
        from src.services.foreshadowing import ensemble_judge

        seen: list[object] = []

        def _evaluate(**kw):
            seen.append(kw.get("is_contracted"))
            return SimpleNamespace(status="PLANTED", rationale="", should_reschedule=False)

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge, "evaluate", staticmethod(_evaluate)
        )

        repo = _StubRepo([_foreshadowing(1, "対象", target_episode=99)])
        service = _make_service(repo)

        await service.check_and_resolve(
            book_id=1, episode_num=1, draft_text="本文", contract_ids=None
        )
        await service.check_and_resolve(
            book_id=1, episode_num=1, draft_text="本文", contract_ids=[]
        )

        assert len(seen) == 2
        # None でも [] でも、target_episode != episode_num なら契約済みではない
        assert all(v is False for v in seen), f"contract_ids の扱いが不統一: {seen}"


class TestResolveFailureDoesNotReportAsResolved:
    """`repo.resolve()` が False を返した場合、回収済みとして報告しないこと。"""

    @pytest.mark.asyncio
    async def test_resolve_false_is_not_counted_as_resolved(self, monkeypatch) -> None:
        """DB 側で更新に失敗した伏線を「回収した」と返さないこと。

        報告すると KPI が過大計上され、伏線管理が壊れる。
        """
        from src.services.foreshadowing import ensemble_judge

        monkeypatch.setattr(
            ensemble_judge.EnsembleJudge,
            "evaluate",
            staticmethod(lambda **kw: SimpleNamespace(status="RESOLVED", rationale="判定", should_reschedule=False)),
        )

        _stub_kpi(monkeypatch)
        repo = _StubRepo([_foreshadowing(1, "更新失敗")], resolve_ok=False)
        service = _make_service(repo)

        titles = await service.check_and_resolve(
            book_id=1, episode_num=2, draft_text="本文"
        )

        assert titles == [], "更新に失敗した伏線が回収済みとして報告された"
        assert repo.resolved == [(1, 2)], "resolve は呼ばれている（DB が拒否した）"
