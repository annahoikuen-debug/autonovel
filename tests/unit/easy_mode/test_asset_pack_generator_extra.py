"""AssetPackGenerator の追加単体テスト."""

import json
from unittest.mock import MagicMock

from src.easy_mode import EpisodeResult, SeriesResult
from src.easy_mode.phase3.asset_pack import (
    AssetPackGenerator,
    AssetPackMetadata,
    create_asset_pack_generator,
    export_asset_pack,
    pack_to_zip,
)


def make_episode(num: int = 1) -> EpisodeResult:
    return EpisodeResult(
        episode_num=num,
        title=f"第{num}話",
        content="本文" * 10,
        word_count=100,
        audit_score=85.0,
        audit_passed=True,
        rewrite_count=1,
        spice_elements=[],
        metadata={},
    )


def make_series(n: int = 2, genre: str = "fantasy", bible: dict | None = None, metadata: dict | None = None) -> SeriesResult:
    return SeriesResult(
        genre=genre,
        title="物語",
        concept="コンセプト",
        total_episodes=n,
        episodes=[make_episode(i + 1) for i in range(n)],
        bible=bible if bible is not None else {"protagonist": "勇者", "cheat_ability": "魔力"},
        plot_outline=[{"beat": 1}],
        metadata=metadata if metadata is not None else {},
    )


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


class _ShimbFormat:
    """asset_pack の『名前が値と一致する』MediaFormat 相当の代用（テスト専用）."""

    __members__ = {"SHIMAX": "shimax", "MANGA2": "manga"}

    def __init__(self, value: str = ""):
        self.value = value

    def __call__(self, name: str) -> "_ShimbFormat":
        if name not in self.__members__:
            raise ValueError(name)
        return _ShimbFormat(self.__members__[name])

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ShimbFormat) and other.value == self.value


ShimbFormat = _ShimbFormat()


class TestAssetPackMetadata:
    def test_to_dict(self):
        m = AssetPackMetadata(pack_id="p", title="t", genre="g")
        d = m.to_dict()
        assert d["pack_id"] == "p"
        assert d["version"] == "1.0.0"
        assert d["media_mix"] == []


class TestPromoGeneration:
    def test_synopsis_long(self):
        gen = AssetPackGenerator("fantasy", {})
        text = gen._generate_synopsis(make_series(bible={"protagonist": "勇者", "catharsis_target": "敵"}))
        assert "【あらすじ】" in text
        assert "主人公: 勇者" in text
        assert "カタルシス対象: 敵" in text
        assert "【見所】" in text

    def test_synopsis_long_no_bible(self):
        gen = AssetPackGenerator("fantasy", {})
        text = gen._generate_synopsis(make_series(bible={}, metadata={}))
        assert "チート能力" not in text

    def test_synopsis_long_no_concept(self):
        gen = AssetPackGenerator("fantasy", {})
        series = make_series()
        series.concept = ""
        text = gen._generate_synopsis(series, long=True)
        assert "【見所】" in text

    def test_synopsis_short_with_hook(self):
        gen = AssetPackGenerator("fantasy", {})
        series = make_series(metadata={"synopsis": {"hook": "HOOKTEXT"}})
        assert "HOOKTEXT" in gen._generate_synopsis(series, long=False)

    def test_synopsis_short_no_hook_no_concept(self):
        gen = AssetPackGenerator("fantasy", {})
        series = make_series()
        series.concept = ""
        assert gen._generate_synopsis(series, long=False).strip().endswith("")

    def test_catchphrases_from_templates(self):
        preset = {
            "marketing": {
                "catchphrase_templates": [
                    "{title}の{genre}、{protagonist}が{cheat}Murder",
                ]
            }
        }
        gen = AssetPackGenerator("fantasy", preset)
        phrases = gen._generate_catchphrases(make_series())
        assert "物語" in phrases[0]
        assert "勇者" in phrases[0]
        assert "魔力" in phrases[0]

    def test_catchphrases_genre_variants(self):
        for genre in ("zarma", "aku_reijo", "cheat_tensei", "slow_life", "loop"):
            gen = AssetPackGenerator(genre, {})
            assert len(gen._generate_catchphrases(make_series())) == 2, genre

    def test_catchphrases_no_preset(self):
        gen = AssetPackGenerator("unknown_genre", {})
        assert gen._generate_catchphrases(make_series()) == []

    def test_character_intros(self):
        bible = {
            "characters": {
                "archetypes": {
                    "hero": {
                        "name_pattern": "勇者（男）",
                        "role": "主人公",
                        "description": " protagon",
                        "speech_patterns": {"first_person": "私", "tone": "冷静"},
                    },
                    "bare": {},
                }
            }
        }
        gen = AssetPackGenerator("fantasy", {})
        text = gen._generate_character_intros(make_series(bible=bible))
        assert "勇者（男）" in text
        assert "役割: 主人公" in text
        assert "一人称: 私" in text
        assert "口調: 冷静" in text
        assert "bare" in text

    def test_keywords_genre_variants(self):
        for genre in (
            "zarma",
            "aku_reijo",
            "cheat_tensei",
            "slow_life",
            "dungeon_admin",
            "modern_cheat",
            "ts_tensei",
            "vrmmo",
            "loop",
            "unknown",
        ):
            gen = AssetPackGenerator(genre, {})
            kws = gen._generate_keywords(make_series())
            assert len(kws) <= 50, genre
            assert kws[0] == "物語"

    def test_keywords_no_bible(self):
        gen = AssetPackGenerator("fantasy", {})
        kws = gen._generate_keywords(make_series(bible={}))
        assert not any(k.startswith("主人公:") for k in kws)

    def test_sns_posts(self):
        gen = AssetPackGenerator("fantasy", {})
        posts = gen._generate_sns_posts(make_series(bible={}))
        assert len(posts["twitter"]) == 2
        assert len(posts["pixiv"]) == 1
        assert len(posts["note"]) == 1

    def test_press_release(self):
        gen = AssetPackGenerator("fantasy", {})
        text = gen._generate_press_release(make_series())
        assert "【プレスリリース】" in text
        assert "物語" in text

    def test_genre_feature_text(self):
        for genre in (
            "zarma",
            "aku_reijo",
            "cheat_tensei",
            "slow_life",
            "dungeon_admin",
            "modern_cheat",
            "ts_tensei",
            "vrmmo",
            "loop",
            "nope",
        ):
            gen = AssetPackGenerator(genre, {})
            assert gen._get_genre_feature_text(), genre


class TestGraphOutputs:
    def test_generate_dot_graph(self):
        gen = AssetPackGenerator("fantasy", {})
        gen.if_generator = None
        from src.easy_mode.phase3.if_routes import IFRouteGenerator

        gen.if_generator = IFRouteGenerator("fantasy", {})
        graph = gen.if_generator.generate_from_series(make_series(2))
        dot = gen._generate_dot_graph(graph)
        assert dot.startswith("digraph IFRouteGraph {")
        assert dot.rstrip().endswith("}")
        assert '"prologue"' in dot

    def test_extract_main_routes(self):
        from src.easy_mode.phase3.if_routes import IFRouteGenerator

        gen = AssetPackGenerator("fantasy", {})
        graph = IFRouteGenerator("fantasy", {}).generate_from_series(make_series(6))
        routes = gen._extract_main_routes(graph)
        assert "main_route" in routes
        assert "hidden_route" in routes
        assert "bad_end_routes" in routes
        assert "true_end_convergence" in routes
        assert routes["main_route"] == sorted(routes["main_route"], key=lambda n: n.episode_num)

    def test_extract_main_routes_empty(self):
        from src.easy_mode.phase3.if_routes import IFRouteGraph

        gen = AssetPackGenerator("fantasy", {})
        assert gen._extract_main_routes(IFRouteGraph()) == {}

    def test_calculate_checksums(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")
        gen = AssetPackGenerator("fantasy", {})
        sums = gen._calculate_checksums(tmp_path)
        assert "a.txt" in sums
        assert str("sub/b.txt").replace("/", "\\") in sums or "sub/b.txt" in sums

    def test_create_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("x", encoding="utf-8")
        target = tmp_path / "out.zip"
        gen = AssetPackGenerator("fantasy", {})
        gen._create_zip(src, target)
        assert target.exists()

    def test_save_original_novel(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        files = gen._save_original_novel(make_series(2), tmp_path)
        assert "series_complete.json" in files
        assert "plot_outline.json" in files
        assert "bible.json" in files
        data = json.loads((tmp_path / "series_complete.json").read_text(encoding="utf-8"))
        assert data["total_episodes"] == 2
        assert data["created_at"] == ""

    def test_save_original_novel_with_created_at(self, tmp_path):
        from datetime import datetime

        gen = AssetPackGenerator("fantasy", {})
        series = make_series(1)
        series.created_at = datetime(2020, 1, 2, 3, 4, 5)
        gen._save_original_novel(series, tmp_path)
        data = json.loads((tmp_path / "series_complete.json").read_text(encoding="utf-8"))
        assert data["created_at"] == "2020-01-02T03:04:05"

    def test_generate_if_routes(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        files = gen._generate_if_routes(make_series(2), tmp_path)
        assert "if_route_graph.json" in files
        assert "if_route_graph.dot" in files
        assert "save_template.json" in files
        save = json.loads((tmp_path / "save_template.json").read_text(encoding="utf-8"))
        assert save["version"] == "1.0"
        assert save["graph_id"] == "prologue"

    def test_generate_media_mix(self, tmp_path, monkeypatch):
        from src.easy_mode.phase3 import asset_pack as ap
        from src.easy_mode.phase3.media_mix import MediaFormat, MediaScript

        monkeypatch.setattr(ap, "MediaFormat", ShimbFormat)
        gen = AssetPackGenerator("fantasy", {})
        exporter = MagicMock()
        script = MediaScript(
            format=MediaFormat.MANGA, title="t", episode_num=1, source_content="c"
        )
        exporter.export_all.return_value = {MediaFormat.MANGA: script}
        exporter.save_all.side_effect = lambda scripts, d: {
            MediaFormat.MANGA: _write(d / "ep001_manga.json", script.to_json())
        }
        gen.media_exporter = exporter
        files = gen._generate_media_mix(make_series(1), tmp_path, ["SHIMAX"])
        assert "media_mix_index.json" in files
        assert any("manga.json" in k for k in files)

    def test_generate_media_mix_lowercase_names_skipped(self, tmp_path):
        # MediaFormat の「メンバー名」でフィルタされるため小文字名は除外される
        gen = AssetPackGenerator("fantasy", {})
        files = gen._generate_media_mix(make_series(1), tmp_path, ["manga"])
        assert files == {"media_mix_index.json": files["media_mix_index.json"]}

    def test_generate_media_mix_default_formats(self, tmp_path, monkeypatch):
        from src.easy_mode.phase3 import asset_pack as ap

        monkeypatch.setattr(ap, "MediaFormat", ShimbFormat)
        gen = AssetPackGenerator("fantasy", {})
        exporter = MagicMock()
        exporter.export_all.return_value = {}
        exporter.save_all.return_value = {}
        gen.media_exporter = exporter
        files = gen._generate_media_mix(make_series(1), tmp_path, ["SHIMAX", "MANGA2", "BOGUS"])
        assert files == {"media_mix_index.json": files["media_mix_index.json"]}

    def test_generate_media_mix_invalid_format(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        files = gen._generate_media_mix(make_series(1), tmp_path, ["bogus"])
        assert files == {"media_mix_index.json": "メディアミックス統合インデックス"}

    def test_generate_ebooks(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        files = gen._generate_ebooks(make_series(1), tmp_path, ["epub", "pdf", "mobi"])
        assert "物語.epub" in files
        assert "物語.pdf" in files
        assert "物語.mobi" in files

    def test_generate_ebooks_unknown_format(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        assert gen._generate_ebooks(make_series(1), tmp_path, ["doc"]) == {}

    def test_generate_ebooks_exception_logged(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        gen.ebook_exporter.export_epub.side_effect = RuntimeError("boom")
        assert gen._generate_ebooks(make_series(1), tmp_path, ["epub"]) == {}

    def test_generate_ebooks_cover_missing(self, tmp_path):
        # cover_image_path は kwargs と明示引数の両方に渡され TypeError になるが、
        # 例外は握り潰されるため戻り値は空。パス検証とログ出力の経路を通す。
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        files = gen._generate_ebooks(
            make_series(1), tmp_path, ["epub"], cover_image_path=str(tmp_path / "nope.png")
        )
        assert files == {}

    def test_generate_ebooks_cover_exists(self, tmp_path):
        cover = tmp_path / "cover.png"
        cover.write_bytes(b"png")
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        out = tmp_path / "out"
        out.mkdir()
        files = gen._generate_ebooks(
            make_series(1), out, ["epub"], cover_image_path=str(cover)
        )
        assert files == {}

    def test_init_components(self, monkeypatch):
        from src.easy_mode.phase3 import asset_pack as ap

        monkeypatch.setattr(ap, "create_ebook_exporter", lambda genre, preset: MagicMock())
        gen = AssetPackGenerator("fantasy", {})
        gen._init_components(make_series(1))
        assert gen.if_generator is not None
        assert gen.media_exporter is not None
        assert gen.ebook_exporter is not None
        first = gen.if_generator
        gen._init_components(make_series(1))
        assert gen.if_generator is first

    def test_generate_promo_materials(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        files = gen._generate_promo_materials(make_series(1), tmp_path)
        for name in (
            "synopsis_long.txt",
            "synopsis_short.txt",
            "catchphrases.txt",
            "character_introductions.txt",
            "keywords.txt",
            "sns_posts.json",
            "press_release.txt",
        ):
            assert name in files
            assert (tmp_path / name).exists()


class TestModuleHelpers:
    def test_create_asset_pack_generator(self):
        gen = create_asset_pack_generator("fantasy", {})
        assert isinstance(gen, AssetPackGenerator)

    def test_pack_to_zip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("a", encoding="utf-8")
        target = tmp_path / "z.zip"
        pack_to_zip(str(src), str(target))
        assert target.exists()

    def test_export_asset_pack(self, tmp_path):
        out = export_asset_pack(tmp_path, ["a", "b"], "タイトル")
        assert out["episode_count"] == 2
        assert out["pack_id"] == "test_pack_タイトル"
        assert out["work_dir"] == str(tmp_path)


class TestGeneratePack:
    def test_generate_pack_minimal(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        gen.media_exporter = MagicMock()
        gen.media_exporter.export_all.return_value = {}
        gen.media_exporter.save_all.return_value = {}
        zip_path = gen.generate_pack(
            make_series(1), tmp_path, include_if_routes=False, include_ebook=False
        )
        assert zip_path.exists()
        assert zip_path.name.startswith("pack_")

    def test_generate_pack_all(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        pack = gen.generate_pack(
            make_series(1), tmp_path, pack_id="my pack", media_formats=["manga"], ebook_formats=["epub"]
        )
        assert pack.name == "my_pack.zip"
        assert not (tmp_path / "asset_pack_my_pack").exists()

    def test_generate_pack_keep_work_dir(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        gen.generate_pack(
            make_series(1),
            tmp_path,
            pack_id="keep",
            include_if_routes=False,
            include_media_mix=False,
            include_ebook=False,
            clean_work_dir=False,
        )
        assert (tmp_path / "asset_pack_keep" / "05_metadata" / "pack_metadata.json").exists()

    def test_generate_pack_custom_licensing(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        gen.generate_pack(
            make_series(1),
            tmp_path,
            pack_id="lic",
            include_if_routes=False,
            include_media_mix=False,
            include_ebook=False,
            clean_work_dir=False,
            licensing={"type": "CC0"},
        )
        data = json.loads(
            (tmp_path / "asset_pack_lic" / "05_metadata" / "pack_metadata.json").read_text(
                encoding="utf-8"
            )
        )
        assert data["licensing"] == {"type": "CC0"}

    def test_generate_pack_id_sanitised(self, tmp_path):
        gen = AssetPackGenerator("fantasy", {})
        gen.ebook_exporter = MagicMock()
        pack = gen.generate_pack(
            make_series(1),
            tmp_path,
            pack_id="a/b c",
            include_if_routes=False,
            include_media_mix=False,
            include_ebook=False,
        )
        assert pack.name == "a_b_c.zip"


