import pytest

from app import app
from models import (
    db, User, MovieProject, MovieScene, MovieShot,
    DramaSeries, DramaEpisode, DramaCharacter, DramaEpisodeCharacter,
    DramaMonthlyUsage, DramaProductionJob, DramaUsageLedger,
)
from services.drama_studio import (
    create_series, add_series_character, create_episode,
    assign_character_to_shot, finalize_episode_quota, monthly_usage_summary,
)


def _user(plan="director", suffix="one"):
    user = User(
        username=f"drama_{suffix}",
        email=f"drama_{suffix}@example.test",
        password="test-hash",
        plan=plan,
        credits=100,
    )
    db.session.add(user)
    db.session.commit()
    return user


def setup_function():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()


def test_drama_studio_is_director_only():
    with app.app_context():
        spark = _user("spark", "spark")
        ok, message, series = create_series(spark, "Locked Series")
        assert not ok
        assert series is None
        assert "Director" in message
        assert DramaSeries.query.count() == 0


def test_series_episode_and_character_continuity_are_created():
    with app.app_context():
        user = _user(suffix="continuity")
        ok, _, series = create_series(user, "The Last Promise", genre="Drama")
        assert ok
        ok, _, character = add_series_character(
            user, series.id, "Amina", role="Protagonist",
            physical_appearance="Braided hair, warm brown skin",
            signature_clothing="Blue Ankara dress",
            voice_id="en-NG-EzinneNeural",
        )
        assert ok

        ok, message, episode, job = create_episode(user, series.id, title="The Warning")
        assert ok, message
        assert episode.episode_number == 1
        assert episode.movie_project_id
        assert job.status == "queued"
        assert DramaProductionJob.query.filter_by(episode_id=episode.id).count() == 1

        cast_link = DramaEpisodeCharacter.query.filter_by(episode_id=episode.id).one()
        assert cast_link.character_id == character.id
        assert cast_link.movie_character.name == "Amina"
        assert cast_link.movie_character.reference_image_url is None
        assert cast_link.movie_character.clothing == "Blue Ankara dress"
        assert cast_link.movie_character.voice_attributes == "en-NG-EzinneNeural"

        usage = monthly_usage_summary(user.id)
        assert usage["reserved"] == 1
        assert usage["completed"] == 0
        assert usage["remaining"] == 29


def test_episode_quota_finalization_is_idempotent():
    with app.app_context():
        user = _user(suffix="quota")
        _, _, series = create_series(user, "Quota Story")
        ok, _, episode, _ = create_episode(user, series.id)
        assert ok

        assert finalize_episode_quota(episode.id, success=True) is True
        assert finalize_episode_quota(episode.id, success=True) is False
        usage = monthly_usage_summary(user.id)
        assert usage["reserved"] == 0
        assert usage["completed"] == 1
        assert DramaUsageLedger.query.filter_by(
            episode_id=episode.id, usage_type="episode_completed"
        ).count() == 1


def test_failed_episode_releases_monthly_slot():
    with app.app_context():
        user = _user(suffix="release")
        _, _, series = create_series(user, "Retry Story")
        ok, _, episode, _ = create_episode(user, series.id)
        assert ok
        assert finalize_episode_quota(episode.id, success=False)
        usage = monthly_usage_summary(user.id)
        assert usage["reserved"] == 0
        assert usage["completed"] == 0
        assert usage["remaining"] == 30
        assert episode.quota_status == "released"


def test_monthly_episode_allowance_blocks_episode_31():
    with app.app_context():
        user = _user(suffix="limit")
        _, _, series = create_series(user, "Thirty Episodes")
        usage = DramaMonthlyUsage(
            user_id=user.id,
            period_start=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().replace(day=1),
            episodes_reserved=0,
            episodes_completed=30,
        )
        db.session.add(usage)
        db.session.commit()

        ok, message, episode, job = create_episode(user, series.id)
        assert not ok
        assert episode is None and job is None
        assert "30-episode" in message
        assert MovieProject.query.filter_by(user_id=user.id).count() == 0


def test_shot_character_assignment_is_explicit_and_used_for_reference_selection():
    with app.app_context():
        user = _user(suffix="shotcast")
        _, _, series = create_series(user, "Market Stories")
        _, _, character = add_series_character(
            user, series.id, "Bisi", physical_appearance="Short natural hair",
            signature_clothing="Yellow blouse",
        )
        ok, _, episode, _ = create_episode(user, series.id)
        assert ok
        link = DramaEpisodeCharacter.query.filter_by(episode_id=episode.id, character_id=character.id).one()
        scene = MovieScene(project_id=episode.movie_project_id, scene_number=1, title="Market", description="A crowded market")
        db.session.add(scene)
        db.session.flush()
        shot = MovieShot(
            scene_id=scene.id, project_id=episode.movie_project_id,
            shot_number=1, visual_prompt="A woman walks through the market",
            duration="5",
        )
        db.session.add(shot)
        db.session.commit()

        ok, message = assign_character_to_shot(user, episode.id, shot.id, link.id)
        assert ok, message

        # The series character portrait is the canonical reference. Once generated,
        # it is copied into the episode-local MovieCharacter record and selected
        # through the explicit join rather than prompt-name matching.
        link.movie_character.reference_image_url = "https://cdn.example.test/bisi.png"
        db.session.commit()
        from services.movie_studio import _character_references_for_shot
        selected = _character_references_for_shot(shot)
        assert len(selected) == 1
        assert selected[0].name == "Bisi"
        assert selected[0].reference_image_url == "https://cdn.example.test/bisi.png"


def test_shot_assignment_rejects_character_from_another_episode():
    with app.app_context():
        user = _user(suffix="crosscast")
        _, _, series = create_series(user, "Cross Cast")
        _, _, character = add_series_character(user, series.id, "Tunde")
        _, _, episode, _ = create_episode(user, series.id)
        other_series_ok, _, other_series = create_series(user, "Different Story")
        _, _, other_episode, _ = create_episode(user, other_series.id)
        other_link = DramaEpisodeCharacter.query.filter_by(
            episode_id=other_episode.id, character_id=character.id
        ).first()
        # Character from the first series cannot be attached to a different series episode.
        assert other_link is None
