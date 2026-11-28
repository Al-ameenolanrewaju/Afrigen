import pytest
from werkzeug.security import generate_password_hash
from app import app
from models import db, User, MovieProject, MovieCharacter, MovieScene, MovieShot, Generation
from services.entitlements import can_access_movie_studio, can_access_image_to_video, get_user_entitlements


def setup_function():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.create_all()


def test_entitlements_gating():
    # 1. Anonymous or None
    assert not can_access_movie_studio(None)
    assert not can_access_image_to_video(None)

    # 2. Spark / Free user
    spark_user = User(username="spark_fan", email="spark@test.com", password="x", plan="spark")
    assert not can_access_movie_studio(spark_user)
    assert not can_access_image_to_video(spark_user)

    # 3. Creator user (Tier 1)
    creator_user = User(username="creator_pro", email="creator@test.com", password="x", plan="creator")
    assert not can_access_movie_studio(creator_user)
    assert not can_access_image_to_video(creator_user)

    # 4. Studio user (Tier 2)
    studio_user = User(username="studio_boss", email="studio@test.com", password="x", plan="studio")
    assert not can_access_movie_studio(studio_user)
    assert can_access_image_to_video(studio_user)

    # 5. Director user (Tier 3)
    director_user = User(username="director_elite", email="director@test.com", password="x", plan="director")
    assert can_access_movie_studio(director_user)
    assert can_access_image_to_video(director_user)

    # 6. Admin user
    admin_user = User(username="super_admin", email="oadedamola07@gmail.com", password="x", plan="spark")
    assert can_access_movie_studio(admin_user)
    assert can_access_image_to_video(admin_user)


def test_movie_studio_access_views():
    client = app.test_client()
    with app.app_context():
        # Setup Spark user
        spark_u = User.query.filter_by(email="spark_test@afrigen.com").first()
        if not spark_u:
            spark_u = User(
                username="spark_tester",
                email="spark_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="spark"
            )
            db.session.add(spark_u)
        else:
            spark_u.password = generate_password_hash("pass123")
            spark_u.plan = "spark"

        # Setup Director user
        director_u = User.query.filter_by(email="director_test@afrigen.com").first()
        if not director_u:
            director_u = User(
                username="director_tester",
                email="director_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="director"
            )
            db.session.add(director_u)
        else:
            director_u.password = generate_password_hash("pass123")
            director_u.plan = "director"
        db.session.commit()

        # Anonymous access redirects to login
        res = client.get("/movie-studio/")
        assert res.status_code == 302
        assert "/auth/login" in res.headers.get("Location", "")

        # Spark user login
        login_res = client.post("/auth/login", data={"email": "spark_test@afrigen.com", "password": "pass123"}, follow_redirects=True)
        assert login_res.status_code == 200

        # Spark user sees the locked promotion page
        res = client.get("/movie-studio/")
        assert res.status_code == 200
        assert b"DIRECTOR TIER EXCLUSIVE" in res.data or b"Unlock Afrigen Movie Studio" in res.data

        # Director user login
        client.post("/auth/login", data={"email": "director_test@afrigen.com", "password": "pass123"}, follow_redirects=True)

        # Director user logged in sees the actual Studio Dashboard
        res = client.get("/movie-studio/")
        assert res.status_code == 200
        assert b"Movie Production Studio" in res.data
        assert b"New Movie Project" in res.data


def test_movie_studio_project_creation(monkeypatch):
    client = app.test_client()
    with app.app_context():
        director_u = User.query.filter_by(email="director_test@afrigen.com").first()
        if not director_u:
            director_u = User(
                username="director_tester",
                email="director_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="director"
            )
            db.session.add(director_u)
            db.session.commit()

        # Mock the screenplay generation so tests run offline quickly
        def mock_treatment(proj):
            proj.logline = "A brave warrior defends ancient kingdoms."
            proj.synopsis = "A full narrative arc."
            scene = MovieScene(project_id=proj.id, scene_number=1, title="Opening", slugline="EXT. PALACE - SUNSET", description="Warriors gather.")
            db.session.add(scene)
            db.session.commit()
            return True, "Mock treatment created"

        import routes.movie_studio as rms
        monkeypatch.setattr(rms, "generate_screenplay_treatment", mock_treatment)

        client.post("/auth/login", data={"email": "director_test@afrigen.com", "password": "pass123"}, follow_redirects=True)

        res = client.post("/movie-studio/projects/create", data={
            "title": "Chronicles of Oyo",
            "genre": "Historical Epic",
            "cinematic_tone": "Golden Hour Africa",
            "aspect_ratio": "16:9",
            "target_duration": "60",
            "logline": "A tale of royalty and courage."
        }, follow_redirects=True)

        assert res.status_code == 200
        assert b"Chronicles of Oyo" in res.data

        # Verify in DB
        proj = MovieProject.query.filter_by(title="Chronicles of Oyo").first()
        assert proj is not None
        assert proj.user_id == director_u.id
        assert proj.genre == "Historical Epic"
        assert len(proj.scenes) >= 1


def test_standalone_voiceover_route(monkeypatch):
    client = app.test_client()
    with app.app_context():
        director_u = User.query.filter_by(email="director_test@afrigen.com").first()
        if not director_u:
            director_u = User(
                username="director_tester",
                email="director_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="director",
                credits=50
            )
            db.session.add(director_u)
        else:
            director_u.credits = 50
        db.session.commit()

        # Mock voiceover synthesis and script generator
        def mock_generate_vo(script):
            return "https://fal.media/files/mock_voiceover.mp3"

        def mock_generate_script(prompt):
            return "Narrator: Welcome to Afrigen AI 2.0, where Africa creates and AI generates."

        import services.audio as audio_srv
        import routes.main as rmain
        monkeypatch.setattr(audio_srv, "generate_voiceover", mock_generate_vo)
        monkeypatch.setattr(audio_srv, "generate_video_script", mock_generate_script)
        monkeypatch.setattr(rmain, "generate_voiceover", mock_generate_vo)
        monkeypatch.setattr(rmain, "generate_video_script", mock_generate_script)

        client.post("/auth/login", data={"email": "director_test@afrigen.com", "password": "pass123"}, follow_redirects=True)

        res = client.post("/generate-voice", json={
            "prompt": "Welcome to Afrigen AI 2.0. Africa Creates, AI Generates.",
            "voice": "en-NG-AbeoNeural"
        })

        assert res.status_code == 200
        data = res.get_json()
        assert data.get("success") is True
        assert data.get("audio_url") in ("https://fal.media/files/mock_voiceover.mp3", f"/media/generation/{data['generation_id']}/audio")

        # Check Generation record
        gen = Generation.query.filter_by(id=data["generation_id"]).first()
        assert gen is not None
        assert gen.audio_url == "https://fal.media/files/mock_voiceover.mp3"


def test_404_error_page_renders_with_null_endpoint():
    client = app.test_client()
    with app.app_context():
        # Anonymous 404
        res = client.get("/non-existent-endpoint-xyz-123")
        assert res.status_code == 404
        assert b"404" in res.data

        # Authenticated 404 (renders base.html with auth_sidebar.html)
        director_u = User.query.filter_by(email="director_test@afrigen.com").first()
        if not director_u:
            director_u = User(
                username="director_tester",
                email="director_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="director"
            )
            db.session.add(director_u)
            db.session.commit()

        client.post("/auth/login", data={"email": "director_test@afrigen.com", "password": "pass123"}, follow_redirects=True)
        res_auth = client.get("/non-existent-endpoint-authenticated-456")
        assert res_auth.status_code == 404
        assert b"404" in res_auth.data



def test_movie_shot_selects_only_named_character_references():
    from types import SimpleNamespace
    from services.movie_studio import _character_references_for_shot, _build_character_consistency_prompt

    amina = SimpleNamespace(
        name="Amina",
        reference_image_url="https://cdn.example/amina.png",
        physical_appearance="Young woman with braided hair",
        description="A village teacher",
        clothing="Blue Ankara dress",
    )
    baba = SimpleNamespace(
        name="Baba Tunde",
        reference_image_url="https://cdn.example/baba.png",
        physical_appearance="Elderly man with grey beard",
        description="Village elder",
        clothing="Cream agbada",
    )
    project = SimpleNamespace(characters=[amina, baba])
    scene = SimpleNamespace(description="Amina enters the village square.", screenplay_text="AMINA: Good morning.")
    shot = SimpleNamespace(project=project, scene=scene, visual_prompt="Amina walks into the market.")

    selected = _character_references_for_shot(shot)
    assert selected == [amina]

    elements, continuity = _build_character_consistency_prompt(shot, selected)
    assert elements == [{"frontal_image_url": "https://cdn.example/amina.png"}]
    assert "@Element1 is Amina" in continuity
    assert "Blue Ankara dress" in continuity
    assert "Baba Tunde" not in continuity


def test_reference_guided_shot_calls_kling_with_element_bindings(monkeypatch):
    from types import SimpleNamespace
    import services.movie_studio as movie_service

    character = SimpleNamespace(
        name="Amina",
        reference_image_url="https://cdn.example/amina.png",
        physical_appearance="Braided hair",
        description="Village teacher",
        clothing="Blue Ankara dress",
    )
    shot = SimpleNamespace(
        reference_image_url=None,
        duration="5",
    )
    captured = {}

    def fake_subscribe(model, arguments):
        captured["model"] = model
        captured["arguments"] = arguments
        return {"video": {"url": "https://cdn.example/shot.mp4"}}

    monkeypatch.setattr(movie_service.fal_client, "subscribe", fake_subscribe)
    result = movie_service._generate_reference_guided_shot(
        shot, "Amina walks through the village.", [character]
    )

    assert result == "https://cdn.example/shot.mp4"
    assert captured["model"] == "fal-ai/kling-video/v3/pro/image-to-video"
    assert captured["arguments"]["start_image_url"] == character.reference_image_url
    assert captured["arguments"]["elements"][0]["frontal_image_url"] == character.reference_image_url
    assert captured["arguments"]["generate_audio"] is False
    assert "@Element1 is Amina" in captured["arguments"]["prompt"]


def test_movie_studio_movie_style_cost_is_duration_based():
    from services.video import text_to_video_cost

    assert text_to_video_cost("movie", extended=True, duration="5") == 12
    assert text_to_video_cost("movie", extended=True, duration="10") == 23


def test_scene_pidgin_dialogue_creates_character_voice_track(monkeypatch):
    from models import MovieAudioTrack
    import services.movie_studio as movie_service

    with app.app_context():
        user = User(username="pidgin_creator", email="pidgin@test.com", password="x", plan="director", credits=100)
        db.session.add(user)
        db.session.flush()
        project = MovieProject(user_id=user.id, title="Pidgin Film")
        db.session.add(project)
        db.session.flush()
        character = MovieCharacter(
            project_id=project.id, name="Amina", role="Protagonist",
            voice_attributes="en-NG-EzinneNeural",
        )
        scene = MovieScene(
            project_id=project.id, scene_number=1, slugline="INT. HOME - DAY",
            screenplay_text="AMINA: I will not leave my family behind.",
        )
        db.session.add_all([character, scene])
        db.session.flush()
        shot = MovieShot(
            scene_id=scene.id, project_id=project.id, shot_number=1,
            visual_prompt="Amina speaks to her family.", duration="5",
        )
        db.session.add(shot)
        db.session.commit()

        monkeypatch.setattr(
            movie_service.provider_manager, "generate_text",
            lambda **_kwargs: '[{"shot_number": 1, "character": "Amina", "line": "I no go leave my family behind, no matter wetin happen."}]',
        )
        monkeypatch.setattr(
            movie_service, "generate_speech_audio",
            lambda line, voice: "https://media.example.test/amina-dialogue.mp3",
        )

        ok, message, tracks = movie_service.generate_scene_pidgin_dialogue(scene.id)
        assert ok is True
        assert "Nigerian Pidgin" in message
        assert tracks[0]["character"] == "Amina"
        saved = MovieAudioTrack.query.filter_by(project_id=project.id, track_type="dialogue").one()
        assert saved.voice_id == "en-NG-EzinneNeural"
        assert "I no go leave" in saved.script_text


def test_shot_dialogue_lip_sync_uses_saved_audio_and_charges_credits(monkeypatch):
    from models import MovieAudioTrack
    import services.movie_studio as movie_service

    with app.app_context():
        user = User(
            username="lipsync_creator", email="lipsync@test.com",
            password="x", plan="director", credits=50,
        )
        db.session.add(user)
        db.session.flush()
        project = MovieProject(user_id=user.id, title="Lip Sync Film")
        db.session.add(project)
        db.session.flush()
        scene = MovieScene(project_id=project.id, scene_number=2)
        db.session.add(scene)
        db.session.flush()
        shot = MovieShot(
            scene_id=scene.id, project_id=project.id, shot_number=3,
            visual_prompt="Amina speaks.", duration="5",
            video_url="https://media.example.test/shot.mp4", status="completed",
        )
        db.session.add(shot)
        db.session.add(MovieAudioTrack(
            project_id=project.id, track_type="dialogue",
            title="Dialogue · Scene 2 · Shot 3 · Amina",
            audio_url="https://media.example.test/dialogue.mp3",
            script_text="I no go leave my family.",
            voice_id="en-NG-EzinneNeural",
        ))
        db.session.commit()
        captured = {}

        def fake_subscribe(model, arguments):
            captured["model"] = model
            captured["arguments"] = arguments
            return {"video": {"url": "https://media.example.test/synced.mp4"}}

        monkeypatch.setattr(movie_service.fal_client, "subscribe", fake_subscribe)
        ok, result = movie_service.sync_shot_dialogue(shot.id)
        assert ok is True
        assert result == "https://media.example.test/synced.mp4"
        assert captured["model"] == "fal-ai/kling-video/lipsync/audio-to-video"
        assert captured["arguments"]["audio_url"] == "https://media.example.test/dialogue.mp3"
        assert db.session.get(User, user.id).credits == 45
        assert db.session.get(MovieShot, shot.id).video_url == result



def test_movie_studio_project_creation_reports_treatment_failure(monkeypatch):
    client = app.test_client()
    with app.app_context():
        director_u = User.query.filter_by(email="director_test@afrigen.com").first()
        if not director_u:
            director_u = User(
                username="director_tester",
                email="director_test@afrigen.com",
                password=generate_password_hash("pass123"),
                plan="director"
            )
            db.session.add(director_u)
            db.session.commit()

        import routes.movie_studio as rms
        monkeypatch.setattr(
            rms,
            "generate_screenplay_treatment",
            lambda _project: (False, "The screenplay provider is temporarily unavailable."),
        )

        client.post(
            "/auth/login",
            data={"email": "director_test@afrigen.com", "password": "pass123"},
            follow_redirects=True,
        )
        response = client.post(
            "/movie-studio/projects/create",
            data={
                "title": "Treatment Retry Test",
                "genre": "Drama",
                "cinematic_tone": "Cinematic",
                "aspect_ratio": "16:9",
                "target_duration": "60",
                "logline": "A test story.",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"was created, but screenplay generation failed" in response.data
        assert b"The screenplay provider is temporarily unavailable." in response.data

        project = MovieProject.query.filter_by(title="Treatment Retry Test").one()
        assert project.status == "draft"
        assert project.user_id == director_u.id
