import sys
from types import SimpleNamespace
from unittest.mock import patch

from app import app
from models import (
    db,
    MovieCharacter,
    MovieProject,
    MovieRenderJob,
    MovieScene,
    MovieShot,
    Notification,
    User,
)
from services.movie_studio import (
    generate_character_portrait_asset,
    generate_shot_video_clip,
    start_movie_render_job,
)


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def _project_with_user():
    user = User(
        username="movie_creator",
        email="movie-creator@example.test",
        password="pw",
        plan="director",
        credits=1000,
    )
    db.session.add(user)
    db.session.flush()
    project = MovieProject(user_id=user.id, title="The Afrigen Story", target_duration=5)
    db.session.add(project)
    db.session.commit()
    return user, project


def test_movie_studio_portrait_and_clip_success_create_notifications():
    with app.app_context():
        user, project = _project_with_user()
        character = MovieCharacter(
            project_id=project.id,
            name="Amara",
            role="Protagonist",
        )
        scene = MovieScene(project_id=project.id, scene_number=1)
        db.session.add_all([character, scene])
        db.session.commit()
        shot = MovieShot(
            scene_id=scene.id,
            project_id=project.id,
            shot_number=2,
            visual_prompt="A sunrise over the city",
        )
        db.session.add(shot)
        db.session.commit()
        user_id = user.id

        with patch("services.movie_studio.generate_image", return_value={
            "success": True,
            "image_url": "https://media.example.test/portrait.png",
        }), patch("services.movie_studio.generate_video", return_value={
            "success": True,
            "video_url": "https://media.example.test/clip.mp4",
        }):
            assert generate_character_portrait_asset(character.id)[0] is True
            assert generate_shot_video_clip(shot.id)[0] is True

        notifications = Notification.query.filter_by(user_id=user_id).all()
        assert [item.title for item in notifications] == [
            "Your character portrait is ready",
            "Your video clip is ready",
        ]
        assert all(item.type == "success" for item in notifications)


def test_movie_studio_completed_render_creates_notification(monkeypatch):
    with app.app_context():
        user, project = _project_with_user()
        scene = MovieScene(project_id=project.id, scene_number=1)
        db.session.add(scene)
        db.session.flush()
        db.session.add(MovieShot(
            scene_id=scene.id,
            project_id=project.id,
            shot_number=1,
            visual_prompt="A sunrise over the city",
            video_url="https://media.example.test/clip.mp4",
            status="completed",
        ))
        db.session.commit()
        project_id = project.id
        user_id = user.id

        class ImmediateThread:
            def __init__(self, target, daemon):
                self.target = target

            def start(self):
                self.target()

        def fake_run(command, **_kwargs):
            with open(command[-1], "wb") as output_file:
                output_file.write(b"rendered video")
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr("services.movie_studio.threading.Thread", ImmediateThread)
        monkeypatch.setattr(
            "services.movie_studio.requests.get",
            lambda *_args, **_kwargs: SimpleNamespace(
                status_code=200,
                content=b"source clip",
            ),
        )
        monkeypatch.setattr("services.movie_studio.subprocess.run", fake_run)
        monkeypatch.setitem(
            sys.modules,
            "imageio_ffmpeg",
            SimpleNamespace(get_ffmpeg_exe=lambda: "ffmpeg"),
        )
        monkeypatch.setitem(
            sys.modules,
            "fal_client",
            SimpleNamespace(upload_file=lambda _path: "https://media.example.test/movie.mp4"),
        )

        ok, _job_id = start_movie_render_job(project_id, user_id, app_instance=app)

        assert ok is True
        notification = Notification.query.filter_by(user_id=user_id).one()
        assert notification.title == "Your movie is ready"
        assert notification.type == "success"
        assert MovieRenderJob.query.one().status == "completed"


def test_movie_master_render_requires_full_target_footage():
    from services.movie_studio import start_movie_render_job

    with app.app_context():
        user, project = _project_with_user()
        project.target_duration = 60
        db.session.commit()
        ok, message = start_movie_render_job(project.id, user.id, app_instance=app)
        assert ok is False
        assert "0 of 60 seconds" in message
        assert MovieRenderJob.query.count() == 0
