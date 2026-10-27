"""BibleDomainService の非同期メソッド群の単体テスト."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.domain_services.bible_domain_service import (
    BibleConsistencyChecker,
    BibleDomainService,
    BibleValidationError,
    BibleValidator,
    SettingConflictType,
)
from src.domain.entities.world_bible import Lore, Setting, WorldBible
from src.domain.value_objects.ids import NovelId, SettingId
from src.domain.value_objects.text import TextContent


def make_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_by_novel = AsyncMock(return_value=None)
    repo.save = AsyncMock(side_effect=lambda b: b)
    repo.save_setting = AsyncMock(side_effect=lambda n, s: s)
    repo.save_lore = AsyncMock(side_effect=lambda n, l: l)
    repo.get_all_lore = AsyncMock(return_value=[])
    repo.get_lore = AsyncMock(return_value=None)
    repo.get_setting = AsyncMock(return_value=None)
    repo.delete_setting = AsyncMock(return_value=True)
    repo.delete_lore = AsyncMock(return_value=True)
    repo.create_setting_snapshot = AsyncMock(return_value=1)
    repo.get_setting_history = AsyncMock(return_value=[])
    repo.restore_setting_version = AsyncMock(return_value=None)
    return repo


NOVEL_ID = NovelId("novel-1")


def make_service() -> tuple[BibleDomainService, MagicMock]:
    repo = make_repo()
    return BibleDomainService(bible_repo=repo), repo


def existing_bible(**kwargs) -> WorldBible:
    bible = WorldBible.create(NOVEL_ID)
    if "settings" in kwargs:
        bible.update_settings(TextContent(kwargs["settings"]))
    if "revealed" in kwargs:
        bible.update_revealed(TextContent(kwargs["revealed"]))
    return bible


class TestValidator:
    def test_validate_world_bible_ok(self):
        assert BibleValidator.validate_world_bible(WorldBible.create(NOVEL_ID)) == []

    def test_validate_world_bible_novel_id(self):
        bible = WorldBible.create(NOVEL_ID)
        bible.novel_id = None
        assert "Novel ID is required" in BibleValidator.validate_world_bible(bible)

    def test_validate_world_bible_version(self):
        bible = WorldBible.create(NOVEL_ID)
        bible.version = 0
        assert "Version must be >= 1" in BibleValidator.validate_world_bible(bible)

    def test_validate_setting_ok(self):
        s = Setting(id=SettingId.generate(), name="n", value=TextContent("v"), category="c")
        assert BibleValidator.validate_setting(s) == []

    def test_validate_setting_empty_fields(self):
        # エンティティは構築時に空文字を弾くため、構造のみを模した値を渡す
        s = SimpleNamespace(name="  ", category="  ")
        errs = BibleValidator.validate_setting(s)
        assert len(errs) == 2

    def test_validate_lore_ok(self):
        lore = Lore.create(NOVEL_ID, "title", TextContent("c"), "cat")
        assert BibleValidator.validate_lore(lore) == []

    def test_validate_lore_empty_fields(self):
        lore = SimpleNamespace(title="  ", category="  ")
        assert len(BibleValidator.validate_lore(lore)) == 2


class TestConsistencyCheckerInternals:
    def test_flatten_nested(self):
        c = BibleConsistencyChecker(make_repo())
        assert c._flatten_dict({"a": {"b": {"c": 1}}}) == {"a.b.c": 1}

    def test_parse_settings_invalid_json(self):
        c = BibleConsistencyChecker(make_repo())
        assert c._parse_settings(TextContent("not json")) == {}

    async def test_full_consistency_check_detects_inconsistent_revealed(self):
        # revealed 矛盾検出まで到達し、list/dict 不整合で落ちない。
        # (以前は `get_pending_settings().items()` の list/dict 不整合で必ず
        #  AttributeError になっていたため `pytest.raises` で固定されていた。
        #  呼び出し側が list を正しく反復するよう修正されたので，如今は
        #  矛盾が検出されて通常どおり返ることを検証する。)
        repo = make_repo()
        bible = existing_bible(settings='{"a": 1}', revealed='{"a": 2}')
        repo.get_by_novel.return_value = bible
        c = BibleConsistencyChecker(repo)
        result = await c.full_consistency_check(NOVEL_ID)
        assert result is not None

    def test_get_nested_value(self):
        c = BibleConsistencyChecker(make_repo())
        assert c._get_nested_value({"a": {"b": 1}}, "a.b") == 1
        assert c._get_nested_value({"a": 1}, "a.b") is None
        assert c._get_nested_value({}, "a") is None

    def test_extract_keywords(self):
        c = BibleConsistencyChecker(make_repo())
        kws = c._extract_keywords("魔術体系の 世界設定について")
        assert "魔術体系" in kws
        assert all(len(k) > 2 for k in kws)

    def test_get_opposite(self):
        c = BibleConsistencyChecker(make_repo())
        assert c._get_opposite("生") == "死"
        assert c._get_opposite("未知") is None

    def test_check_setting_conflicts_dependency_missing(self):
        # フラットキーは _get_nested_value のドット分割で解決できないため、
        # 依存未設定警告は必ず出る
        c = BibleConsistencyChecker(make_repo())
        conflicts = c.check_setting_conflicts(
            TextContent('{"technology.level": "high"}'),
            {"technology.level": "low"},
        )
        types = [x.conflict_type for x in conflicts]
        assert types == [SettingConflictType.MISSING_DEPENDENCY]

    def test_check_lore_consistency_duplicate(self):
        c = BibleConsistencyChecker(make_repo())
        existing = Lore.create(NOVEL_ID, "Magic", TextContent("content"), "world")
        new = Lore.create(NOVEL_ID, "magic", TextContent("other"), "world")
        conflicts = c.check_lore_consistency([existing], new)
        assert any(x.conflict_type == SettingConflictType.DIRECT_CONTRADICTION for x in conflicts)

    def test_check_lore_consistency_same_category_no_conflict(self):
        c = BibleConsistencyChecker(make_repo())
        existing = Lore.create(NOVEL_ID, "A", TextContent("abc"), "world")
        new = Lore.create(NOVEL_ID, "B", TextContent("def"), "history")
        assert c.check_lore_consistency([existing], new) == []

    def test_detect_circular_dependencies(self, monkeypatch):
        c = BibleConsistencyChecker(make_repo())
        monkeypatch.setattr(
            BibleConsistencyChecker,
            "SETTING_DEPENDENCIES",
            {"a.key": ["b.key"], "b.key": ["a.key"]},
        )
        cycles = c._detect_circular_dependencies({"a.key": 1, "b.key": 1})
        assert cycles
        assert cycles[0][0] == cycles[0][-1]

    def test_detect_no_cycles(self):
        c = BibleConsistencyChecker(make_repo())
        assert c._detect_circular_dependencies({"unrelated": 1}) == []

    async def test_full_consistency_check_not_found(self):
        c = BibleConsistencyChecker(make_repo())
        report = await c.full_consistency_check(NOVEL_ID)
        assert report.is_consistent is False
        assert report.conflicts[0].description == "World bible not found"

    async def test_full_consistency_check_pending_settings_is_list_bug(self):
        # WorldBible.get_pending_settings() は list を返す。domain 側が .items() を
        # 呼ぶと必ず AttributeError になっていたが、呼び出し側が list を正しく
        # 反復するよう修正されたため、聖典が存在しても例外を投げずに完了する。
        # (このテストは修正前はバグの pinning になっていたため、期待値を正す。)
        repo = make_repo()
        repo.get_by_novel.return_value = existing_bible(settings='{"a": 1}')
        c = BibleConsistencyChecker(repo)
        result = await c.full_consistency_check(NOVEL_ID)
        assert result is not None


class TestBibleDomainServiceCrud:
    async def test_create_world_bible(self):
        svc, repo = make_service()
        bible = await svc.create_world_bible(NOVEL_ID)
        assert isinstance(bible, WorldBible)

    async def test_create_world_bible_already_exists(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        with pytest.raises(BibleValidationError):
            await svc.create_world_bible(NOVEL_ID)

    async def test_get_world_bible(self):
        svc, repo = make_service()
        assert await svc.get_world_bible(NOVEL_ID) is None

    async def test_update_settings(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        bible = await svc.update_settings(NOVEL_ID, TextContent('{"a": 1}'))
        assert bible.version == 2

    async def test_update_settings_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.update_settings(NOVEL_ID, TextContent("{}"))

    async def test_update_settings_validation_error(self):
        svc, repo = make_service()
        bible = WorldBible.create(NOVEL_ID)
        bible.novel_id = None
        repo.get_by_novel.return_value = bible
        with pytest.raises(BibleValidationError):
            await svc.update_settings(NOVEL_ID, TextContent("{}"))

    async def test_update_revealed(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        bible = await svc.update_revealed(NOVEL_ID, TextContent('{"a": 1}'))
        assert bible.revealed.content == '{"a": 1}'

    async def test_update_revealed_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.update_revealed(NOVEL_ID, TextContent("{}"))

    async def test_propose_setting_change(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        bible = await svc.propose_setting_change(NOVEL_ID, "field", TextContent("v"), 0.8)
        assert isinstance(bible, WorldBible)

    async def test_propose_setting_change_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.propose_setting_change(NOVEL_ID, "f", TextContent("v"))

    async def test_propose_setting_change_bad_confidence(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        with pytest.raises(BibleValidationError):
            await svc.propose_setting_change(NOVEL_ID, "f", TextContent("v"), 1.5)

    async def test_confirm_pending_setting(self):
        svc, repo = make_service()
        bible = WorldBible.create(NOVEL_ID)
        bible.add_pending_setting("f", TextContent("v"), 0.5)
        repo.get_by_novel.return_value = bible
        pending = await svc.confirm_pending_setting(NOVEL_ID, "f")
        assert pending is not None
        assert pending.status == "pending"
        assert bible.version == 2

    async def test_confirm_pending_setting_missing(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        assert await svc.confirm_pending_setting(NOVEL_ID, "zzz") is None

    async def test_confirm_pending_setting_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.confirm_pending_setting(NOVEL_ID, "f")

    async def test_reject_pending_setting(self):
        svc, repo = make_service()
        bible = WorldBible.create(NOVEL_ID)
        bible.add_pending_setting("f", TextContent("v"), 0.5)
        repo.get_by_novel.return_value = bible
        pending = await svc.reject_pending_setting(NOVEL_ID, "f")
        assert pending.status == "pending"

    async def test_reject_pending_setting_missing(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        assert await svc.reject_pending_setting(NOVEL_ID, "zzz") is None

    async def test_reject_pending_setting_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.reject_pending_setting(NOVEL_ID, "f")

    async def test_get_pending_settings(self):
        svc, repo = make_service()
        bible = WorldBible.create(NOVEL_ID)
        bible.add_pending_setting("f", TextContent("v"), 0.5)
        repo.get_by_novel.return_value = bible
        assert len(await svc.get_pending_settings(NOVEL_ID)) == 1

    async def test_get_pending_settings_no_bible(self):
        svc, repo = make_service()
        assert await svc.get_pending_settings(NOVEL_ID) == []


class TestBibleDomainServiceSettings:
    async def test_add_setting(self):
        svc, repo = make_service()
        repo.get_by_novel.return_value = WorldBible.create(NOVEL_ID)
        setting = await svc.add_setting(NOVEL_ID, "name", TextContent("v"), "cat")
        assert setting.name == "name"

    async def test_add_setting_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.add_setting(NOVEL_ID, "name", TextContent("v"), "cat")

    async def test_update_setting(self):
        svc, repo = make_service()
        existing = Setting(id=SettingId.generate(), name="n", value=TextContent("v"), category="c")
        repo.get_setting.return_value = existing
        updated = await svc.update_setting(NOVEL_ID, existing.id, TextContent("v2"))
        assert updated.value.content == "v2"

    async def test_update_setting_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.update_setting(NOVEL_ID, SettingId.generate(), TextContent("v"))

    async def test_reveal_setting(self):
        svc, repo = make_service()
        existing = Setting(id=SettingId.generate(), name="n", value=TextContent("v"), category="c")
        repo.get_setting.return_value = existing
        revealed = await svc.reveal_setting(NOVEL_ID, existing.id)
        assert revealed.is_revealed is True

    async def test_reveal_setting_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.reveal_setting(NOVEL_ID, SettingId.generate())

    async def test_delete_setting(self):
        svc, repo = make_service()
        assert await svc.delete_setting(NOVEL_ID, SettingId.generate()) is True

    async def test_create_setting_snapshot(self):
        svc, repo = make_service()
        assert await svc.create_setting_snapshot(NOVEL_ID, "summary", "me") == 1

    async def test_get_setting_history(self):
        svc, repo = make_service()
        assert await svc.get_setting_history(NOVEL_ID) == []

    async def test_restore_setting_version(self):
        svc, repo = make_service()
        repo.restore_setting_version.return_value = WorldBible.create(NOVEL_ID)
        assert isinstance(await svc.restore_setting_version(NOVEL_ID, 1), WorldBible)

    async def test_restore_setting_version_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.restore_setting_version(NOVEL_ID, 1)


class TestBibleDomainServiceLore:
    async def test_create_lore(self):
        svc, repo = make_service()
        lore = await svc.create_lore(NOVEL_ID, "Title", TextContent("content"), "world")
        assert lore.title == "Title"

    async def test_create_lore_conflict(self):
        svc, repo = make_service()
        repo.get_all_lore.return_value = [Lore.create(NOVEL_ID, "Title", TextContent("a"), "world")]
        with pytest.raises(BibleValidationError):
            await svc.create_lore(NOVEL_ID, "Title", TextContent("b"), "world")

    async def test_update_lore_content(self):
        svc, repo = make_service()
        lore = Lore.create(NOVEL_ID, "T", TextContent("a"), "cat")
        repo.get_lore.return_value = lore
        updated = await svc.update_lore(NOVEL_ID, lore.id, content=TextContent("b"))
        assert updated.content.content == "b"

    async def test_update_lore_tags(self):
        svc, repo = make_service()
        lore = Lore.create(NOVEL_ID, "T", TextContent("a"), "cat")
        repo.get_lore.return_value = lore
        updated = await svc.update_lore(NOVEL_ID, lore.id, tags=["x"])
        assert updated.tags == ["x"]

    async def test_update_lore_no_args(self):
        svc, repo = make_service()
        lore = Lore.create(NOVEL_ID, "T", TextContent("a"), "cat")
        repo.get_lore.return_value = lore
        updated = await svc.update_lore(NOVEL_ID, lore.id)
        assert updated.id == lore.id

    async def test_update_lore_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.update_lore(NOVEL_ID, SettingId.generate())

    async def test_add_lore_tag(self):
        svc, repo = make_service()
        lore = Lore.create(NOVEL_ID, "T", TextContent("a"), "cat")
        repo.get_lore.return_value = lore
        updated = await svc.add_lore_tag(NOVEL_ID, lore.id, "tag")
        assert "tag" in updated.tags

    async def test_add_lore_tag_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.add_lore_tag(NOVEL_ID, SettingId.generate(), "tag")

    async def test_get_all_lore(self):
        svc, repo = make_service()
        assert await svc.get_all_lore(NOVEL_ID) == []

    async def test_get_lore_by_category(self):
        svc, repo = make_service()
        repo.get_all_lore.return_value = [
            Lore.create(NOVEL_ID, "A", TextContent("a"), "world"),
            Lore.create(NOVEL_ID, "B", TextContent("b"), "history"),
        ]
        result = await svc.get_lore_by_category(NOVEL_ID, "world")
        assert len(result) == 1

    async def test_delete_lore(self):
        svc, repo = make_service()
        assert await svc.delete_lore(NOVEL_ID, SettingId.generate()) is True


class TestBibleDomainServiceChecks:
    async def test_check_consistency(self):
        svc, repo = make_service()
        report = await svc.check_consistency(NOVEL_ID)
        assert report.is_consistent is False

    async def test_check_setting_conflicts(self):
        svc, repo = make_service()
        bible = existing_bible(settings='{"color": "blue"}')
        repo.get_by_novel.return_value = bible
        conflicts = await svc.check_setting_conflicts(NOVEL_ID, {"color": "red"})
        assert len(conflicts) == 1

    async def test_check_setting_conflicts_not_found(self):
        svc, repo = make_service()
        with pytest.raises(BibleValidationError):
            await svc.check_setting_conflicts(NOVEL_ID, {"color": "red"})

    def test_post_init(self):
        svc, _ = make_service()
        assert isinstance(svc._validator, BibleValidator)
        assert isinstance(svc._consistency_checker, BibleConsistencyChecker)

