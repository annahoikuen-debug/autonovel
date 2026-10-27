"""media_mix の各種台本生成器の単体テスト."""

from types import SimpleNamespace

from src.easy_mode import EpisodeResult, SeriesResult
from src.easy_mode.phase3.media_mix import (
    AudioCue,
    AudioDramaScriptGenerator,
    MangaScriptGenerator,
    MediaFormat,
    MediaMixExporter,
    MediaScript,
    Panel,
    VideoScriptGenerator,
    VoiceLine,
    VideoShot,
    create_media_mix_exporter,
)


def make_episode(content: str = "テスト本文") -> EpisodeResult:
    return EpisodeResult(
        episode_num=1,
        title="第一話",
        content=content,
        word_count=len(content),
        audit_score=80.0,
        audit_passed=True,
        rewrite_count=0,
        spice_elements=[],
        metadata={},
    )


def make_series() -> SeriesResult:
    return SeriesResult(
        genre="fantasy",
        title="物語",
        concept="concept",
        total_episodes=1,
        episodes=[],
        bible={},
        plot_outline=[],
        metadata={},
    )


PRESET = {
    "style": {"manga_notes": "note"},
    "characters": {
        "archetypes": {
            "hero": {
                "name_pattern": "アリス（勇者）",
                "personality": "brave",
                "speech_patterns": {"first_person": "私", "tone": "cool"},
            }
        }
    },
    "erotic": {},
}


class TestDataclasses:
    def test_panel_to_dict(self):
        p = Panel(number=1, description="d")
        d = p.to_dict()
        assert d["number"] == 1
        assert d["camera_angle"] == "medium"
        assert d["mood"] == "neutral"

    def test_audio_cue_to_dict(self):
        c = AudioCue(type="bgm", name="n", description="d")
        d = c.to_dict()
        assert d["volume"] == 1.0
        assert d["fade_in"] == 0.0

    def test_voice_line_to_dict(self):
        v = VoiceLine(character="c", text="t", audio_cues_before=[AudioCue("sfx", "n", "d")])
        d = v.to_dict()
        assert d["audio_cues_before"][0]["name"] == "n"
        assert d["audio_cues_after"] == []

    def test_video_shot_to_dict(self):
        s = VideoShot(number=1, duration=3.0, visual_description="v")
        d = s.to_dict()
        assert d["transition"] == "cut"
        assert d["lighting"] == "natural"

    def test_media_script_to_dict_and_json(self):
        ms = MediaScript(
            format=MediaFormat.MANGA,
            title="t",
            episode_num=2,
            source_content="c",
            panels=[Panel(number=1, description="d")],
        )
        d = ms.to_dict()
        assert d["format"] == "manga"
        assert d["panels"][0]["number"] == 1
        assert "created_at" in ms.to_json()

    def test_media_formats(self):
        assert MediaFormat.VIDEO.value == "video"
        assert MediaFormat.LIGHT_NOVEL.value == "light_novel"
        assert MediaFormat.WEBTOON.value == "webtoon"


class TestMangaScriptGenerator:
    def test_generate_rule_based(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        script = gen.generate(make_episode("静かな夜。"), make_series())
        assert script.format == MediaFormat.MANGA
        assert script.metadata["generated_by"] == "rule_based"
        assert script.metadata["estimated_pages"] >= 1

    def test_generate_with_llm(self):
        page = SimpleNamespace(
            scene_mood="tense",
            panels=[
                SimpleNamespace(
                    panel_number=1,
                    visual_description="desc",
                    dialogues=[{"speaker": "A", "text": "hello"}, {"speaker": "", "text": "solo"}],
                    narration="nar",
                    sfx=["bang"],
                    camera_angle="wide",
                )
            ],
        )
        agent = SimpleNamespace(generate_manga_script=lambda c, chars: [page])
        gen = MangaScriptGenerator("fantasy", PRESET, agent)
        script = gen.generate(make_episode(), make_series())
        assert script.metadata["generated_by"] == "llm"
        assert script.panels[0].dialogue == ["A：「hello」", "solo"]
        assert script.panels[0].characters == ["A"]
        assert script.panels[0].mood == "tense"

    def test_generate_llm_failure_fallback(self):
        def boom(content, chars):
            raise RuntimeError("nope")

        gen = MangaScriptGenerator("fantasy", PRESET, SimpleNamespace(generate_manga_script=boom))
        script = gen.generate(make_episode("本文。"), make_series())
        assert script.metadata["generated_by"] == "rule_based"

    def test_build_character_list(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        chars = gen._build_character_list()
        assert chars[0]["name"] == "アリス"
        assert chars[0]["first_person"] == "私"

    def test_classify_scene_types(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._classify_scene("「あ」「い」「う」") == "dialogue"
        assert gen._classify_scene("彼は走った") == "action"
        assert gen._classify_scene("彼の心は揺れた") == "emotion"
        assert gen._classify_scene("あ" * 600) == "exposition"
        assert gen._classify_scene("普通の文章") == "normal"

    def test_extract_scenes_skips_blank(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        scenes = gen._extract_scenes("a。\n\n\n\nb。")
        assert len(scenes) == 2
        assert scenes[0]["word_count"] == 2

    def test_extract_characters(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        chars = gen._extract_characters("アリスが走った。「やあ」")
        assert any("アリス" in c for c in chars)

    def test_split_text_for_panels_single(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._split_text_for_panels("abc", 1) == ["abc"]

    def test_split_text_for_panels_pads(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        chunks = gen._split_text_for_panels("一文。二文。", 3)
        assert len(chunks) == 3
        assert chunks[-1] == ""

    def test_split_text_for_panels_even(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        chunks = gen._split_text_for_panels("一。二。三。四。", 2)
        assert len(chunks) == 2

    def test_scene_to_panels_all_types(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        for stype in ("dialogue", "action", "emotion", "normal"):
            scene = {"text": "アリスが走った。「あ」", "type": stype, "characters": ["アリス"]}
            panels = gen._scene_to_panels(scene, 1, make_episode())
            assert panels
            assert panels[0].number == 1

    def test_generate_panel_description(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert "会話シーン" in gen._generate_panel_description("x", "dialogue", ["A"])
        assert "アクション" in gen._generate_panel_description("x", "action", ["A"])
        assert "心理描写" in gen._generate_panel_description("x", "emotion", [])
        assert "主人公" in gen._generate_panel_description("x", "emotion", [])
        assert "説明/展開" in gen._generate_panel_description("x", "normal", [])
        assert "キーワード" in gen._generate_panel_description("物語の进展", "normal", [])

    def test_extract_dialogue_and_narration(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._extract_dialogue("「a」『b』\"c\"")
        assert gen._extract_narration("前に「a」 後ろ") == "前に 後ろ"

    def test_generate_sfx_action(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        sfx = gen._generate_sfx("action", "剣で斬り、魔法を発動、爆発し、走った。「」")
        assert "SE: 剣の閃光音" in sfx
        assert len(sfx) <= 3

    def test_generate_sfx_emotion(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        sfx = gen._generate_sfx("emotion", "涙と心臓の鼓動")
        assert "SE: 涙の音・すすり泣き" in sfx
        assert "SE: 心拍音" in sfx

    def test_generate_sfx_action_running(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert "SE: 足音・疾走音" in gen._generate_sfx("action", "駆けた")

    def test_determine_camera_angle(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._determine_camera_angle("action", 0, 3) == "wide"
        assert gen._determine_camera_angle("action", 2, 3) == "close_up"
        assert gen._determine_camera_angle("action", 1, 3) == "dynamic"
        assert gen._determine_camera_angle("emotion", 0, 3) == "close_up"
        assert gen._determine_camera_angle("dialogue", 0, 3) == "medium"
        assert gen._determine_camera_angle("dialogue", 1, 3) == "over_shoulder"
        assert gen._determine_camera_angle("normal", 0, 3) == "medium"

    def test_determine_background(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._determine_background("action", "王宮の中") == "城"
        assert gen._determine_background("action", "木立") == "森"
        assert gen._determine_background("action", "路地") == "街"
        assert gen._determine_background("action", "寝室") == "部屋"
        assert gen._determine_background("action", "迷宮") == "ダンジョン"
        assert gen._determine_background("action", "校庭") == "学校"
        assert gen._determine_background("action", "コンビニ") == "現代"
        assert gen._determine_background("action", "何もない") == "汎用背景"

    def test_determine_mood(self):
        gen = MangaScriptGenerator("fantasy", PRESET)
        assert gen._determine_mood("action", "") == "tense"
        assert gen._determine_mood("emotion", "涙") == "sad"
        assert gen._determine_mood("emotion", "笑った") == "happy"
        assert gen._determine_mood("emotion", "憤怒") == "angry"
        assert gen._determine_mood("emotion", "generic") == "emotional"
        assert gen._determine_mood("dialogue", "") == "conversational"
        assert gen._determine_mood("normal", "") == "neutral"


class TestAudioDramaScriptGenerator:
    def test_generate_rule_based(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        script = gen.generate(make_episode("「やあ」今日は。"), make_series())
        assert script.format == MediaFormat.AUDIO_DRAMA
        assert script.metadata["generated_by"] == "rule_based"
        assert script.metadata["bgm_plan"]
        assert script.metadata["sfx_plan"]
        assert "narrator_needed" in script.metadata["cast_requirements"]

    def test_generate_with_llm(self):
        audio_out = SimpleNamespace(
            lines=[
                SimpleNamespace(
                    character="A",
                    text="hi",
                    emotion="happy",
                    direction="d",
                    audio_cues_before=[{"type": "sfx", "name": "pre"}],
                    audio_cues_after=[],
                )
            ],
            bgm_plan=[{"a": 1}],
            sfx_plan=[{"b": 2}],
            cast_requirements=["A"],
        )
        agent = SimpleNamespace(generate_audio_script=lambda c, chars: audio_out)
        gen = AudioDramaScriptGenerator("fantasy", PRESET, agent)
        script = gen.generate(make_episode(), make_series())
        assert script.metadata["generated_by"] == "llm"
        assert script.voice_lines[0].character == "A"
        assert script.voice_lines[0].audio_cues_before[0].name == "pre"

    def test_generate_llm_failure_fallback(self):
        def boom(c, ch):
            raise RuntimeError("x")

        gen = AudioDramaScriptGenerator("fantasy", PRESET, SimpleNamespace(generate_audio_script=boom))
        script = gen.generate(make_episode("本文。"), make_series())
        assert script.metadata["generated_by"] == "rule_based"

    def test_convert_to_voice_lines_defaults(self):
        audio_out = SimpleNamespace(
            lines=[
                SimpleNamespace(
                    character="A",
                    text="t",
                    emotion="neutral",
                    direction="",
                    audio_cues_before=[{"name": "n"}],
                    audio_cues_after=[{"name": "m"}],
                )
            ]
        )
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        lines = gen._convert_to_voice_lines(audio_out)
        assert lines[0].audio_cues_before[0].type == "sfx"
        assert lines[0].audio_cues_after[0].volume == 1.0

    def test_build_character_list(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert gen._build_character_list()[0]["name"] == "アリス"

    def test_convert_to_voice_lines_legacy_empty(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert gen._convert_to_voice_lines_legacy("  \n\n ", make_episode()) == []

    def test_scene_to_voice_lines_narration_tail(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        lines = gen._scene_to_voice_lines("導入の文。「セリフ」")
        assert lines[0].character == "ナレーション"
        assert any(l.text == "セリフ" for l in lines)

    def test_guess_speaker_variants(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert gen._guess_speaker("私は行く", "") == "アリス"
        assert gen._guess_speaker("わたし", "") == "主人公"
        assert gen._guess_speaker("俺", "") == "主人公(男性口調)"
        assert gen._guess_speaker("僕", "") == "主人公(少年口調)"
        assert gen._guess_speaker("はぁ…", "") == "キャラクター"

    def test_guess_speaker_forbidden_word(self):
        preset = {
            "characters": {
                "archetypes": {
                    "a": {"speech_patterns": {"forbidden_words": ["禁句"]}},
                }
            }
        }
        gen = AudioDramaScriptGenerator("fantasy", preset)
        assert gen._guess_speaker("禁句", "") == "キャラクター"

    def test_guess_emotion(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert gen._guess_emotion("死ね！") == "anger"
        assert gen._guess_emotion("ッ！") == "excited"
        assert gen._guess_emotion("本当に？") == "questioning"
        assert gen._guess_emotion("はぁ…") == "sad"
        assert gen._guess_emotion("くくく笑") == "amused"
        assert gen._guess_emotion("普通") == "neutral"

    def test_generate_direction(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        for e in ("anger", "excited", "questioning", "sad", "amused", "neutral"):
            assert gen._generate_direction("t", e) != "[自然体]"
        assert gen._generate_direction("t", "unknown") == "[自然体]"

    def test_pre_and_post_audio_cues(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert gen._get_pre_audio_cues("…")[0].name == "pause"
        assert gen._get_pre_audio_cues("普通") == []
        assert gen._get_post_audio_cues("！")[0].name == "impact"
        assert gen._get_post_audio_cues("ッ")[0].duration == 0.3
        assert gen._get_post_audio_cues("普通") == []

    def test_bgm_and_sfx_plan(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        assert len(gen._generate_bgm_plan(make_episode(), make_series())) == 5
        assert len(gen._generate_sfx_plan(make_episode())) == 5

    def test_get_cast_requirements(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        req = gen._get_cast_requirements([VoiceLine(character="ナレーション", text="")])
        assert req["narrator_needed"] is True
        assert req["total_voice_actors"] == 1

    def test_get_cast_requirements_no_narrator(self):
        gen = AudioDramaScriptGenerator("fantasy", PRESET)
        req = gen._get_cast_requirements([VoiceLine(character="A", text="t", emotion="happy")])
        assert req["narrator_needed"] is False
        assert req["required_emotions"] == ["happy"]
        assert req["total_voice_actors"] == 1


class TestVideoScriptGenerator:
    def test_generate(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        script = gen.generate(make_episode("彼は走った。「やあ」"), make_series())
        assert script.format == MediaFormat.VIDEO
        assert script.metadata["total_shots"] >= 1
        assert script.metadata["aspect_ratio"] == "16:9"
        assert "Genre: fantasy" in script.metadata["style_notes"]

    def test_classify_shot_type(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._classify_shot_type("「a」") == "dialogue"
        assert gen._classify_shot_type("『a』") == "dialogue"
        assert gen._classify_shot_type("走る") == "action"
        assert gen._classify_shot_type("心") == "emotion"
        assert gen._classify_shot_type("あ" * 150) == "exposition"
        assert gen._classify_shot_type("普通") == "normal"

    def test_estimate_duration(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._estimate_duration("", "dialogue") == 4.0
        assert gen._estimate_duration("あ" * 200, "action") == 5.0
        assert gen._estimate_duration("x", "unknown") == 4.02

    def test_generate_visual_description(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        desc = gen._generate_visual_description("アリスが走る。城", "action")
        assert "[ACTION]" in desc
        assert "場所:城" in desc

    def test_generate_visual_description_plain(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._generate_visual_description("です。", "normal") == "[NORMAL]"

    def test_shot_helpers(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._get_camera_movement("action", 0, 2) == "tracking"
        assert gen._get_camera_movement("action", 1, 2) == "static"
        assert gen._get_camera_movement("emotion", 0, 2) == "slow_zoom_in"
        assert gen._get_camera_movement("exposition", 0, 2) == "pan"
        assert gen._get_camera_movement("normal", 0, 2) == "static"
        assert gen._get_camera_movement("zzz", 0, 2) == "static"
        assert gen._get_camera_angle("dialogue") == "over_shoulder"
        assert gen._get_camera_angle("zzz") == "eye_level"
        assert gen._get_lighting("emotion", "夜の影") == "low_key"
        assert gen._get_lighting("action", "") == "high_contrast"
        assert gen._get_lighting("exposition", "") == "natural"
        assert gen._get_lighting("normal", "") == "three_point"
        assert gen._get_bgm_for_shot("dialogue") == "bgm_dialogue"
        assert gen._get_bgm_for_shot("zzz") == "bgm_ambient"
        assert gen._get_transition(0, 2) == "cut"
        assert gen._get_transition(1, 2) == "fade_out"

    def test_sfx_for_shot(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert "sfx_sword" in gen._get_sfx_for_shot("action", "ドアを開けた")
        assert len(gen._get_sfx_for_shot("action", "ドア")) == 2
        assert gen._get_sfx_for_shot("emotion", "") == ["sfx_heartbeat"]
        assert gen._get_sfx_for_shot("normal", "扉") == ["sfx_door"]

    def test_generate_subtitle(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._generate_subtitle("「x」短い") == "短い"
        assert gen._generate_subtitle("あ" * 60).endswith("...")

    def test_convert_to_shots_empty(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._convert_to_shots("   \n\n  ", make_episode()) == []

    def test_shot_dialogue_and_narration(self):
        gen = VideoScriptGenerator("fantasy", PRESET)
        assert gen._extract_dialogue_for_shot("「a」『b』\"c\"") == ["a", "b", "c"]
        assert gen._extract_narration_for_shot("前「a」後") == "前後"


class TestMediaMixExporter:
    def test_create_factory(self):
        exporter = create_media_mix_exporter("fantasy", PRESET)
        assert isinstance(exporter, MediaMixExporter)
        assert isinstance(exporter.manga_gen, MangaScriptGenerator)

    def test_export_all_default(self):
        exporter = MediaMixExporter("fantasy", PRESET)
        res = exporter.export_all(make_episode("本文。"), make_series())
        assert set(res) == {MediaFormat.MANGA, MediaFormat.AUDIO_DRAMA, MediaFormat.VIDEO}

    def test_export_all_unsupported(self):
        exporter = MediaMixExporter("fantasy", PRESET)
        res = exporter.export_all(make_episode(), make_series(), formats=[MediaFormat.LIGHT_NOVEL])
        assert res == {}

    def test_save_all(self, tmp_path):
        exporter = MediaMixExporter("fantasy", PRESET)
        scripts = exporter.export_all(make_episode(), make_series(), formats=[MediaFormat.MANGA])
        out = tmp_path / "out"
        saved = exporter.save_all(scripts, out)
        assert saved[MediaFormat.MANGA].exists()
        assert "ep001_manga.json" in saved[MediaFormat.MANGA].name

    def test_convert_to_manga_empty(self):
        exporter = MediaMixExporter("fantasy", PRESET)
        script = exporter.convert_to_manga("")
        assert script.panels[0].dialogue == [""]

    def test_convert_to_audio_drama_with_speaker(self):
        exporter = MediaMixExporter("fantasy", PRESET)
        script = exporter.convert_to_audio_drama("アリス「こんにちは」")
        assert script.voice_lines[0].character == "アリス"
        assert script.metadata["voice_line_count"] == 1

    def test_convert_to_audio_drama_no_pattern(self):
        exporter = MediaMixExporter("fantasy", PRESET)
        script = exporter.convert_to_audio_drama("ただの文章")
        assert script.voice_lines[0].character == "ナレーター"
        assert script.format == MediaFormat.AUDIO_DRAMA
