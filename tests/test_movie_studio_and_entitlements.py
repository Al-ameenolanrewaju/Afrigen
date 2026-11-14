import pytest
from werkzeug.security import generate_password_hash
from app import app
from models import db, User, MovieProject, MovieScene, MovieShot, Generation
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
        assert data.get("audio_url") == "https://fal.media/files/mock_voiceover.mp3"

        # Check Generation record
        gen = Generation.query.filter_by(id=data["generation_id"]).first()
        assert gen is not None
