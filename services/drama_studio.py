"""Series and episode orchestration for Afrigen AI Drama Studio."""
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import (
    db, User, MovieProject, MovieCharacter, MovieShot,
    DramaSeries, DramaCharacter, DramaEpisode, DramaEpisodeCharacter,
    DramaShotCharacter, DramaMonthlyUsage, DramaProductionJob, DramaUsageLedger,
)
from services.entitlements import can_access_movie_studio, is_admin

DIRECTOR_MONTHLY_EPISODE_LIMIT = 30
ALLOWED_VOICES = {"en-NG-AbeoNeural", "en-NG-EzinneNeural"}


def current_period_start(today=None):
    today = today or datetime.now(timezone.utc).date()
    return today.replace(day=1)


def _can_access(user):
    return bool(user and can_access_movie_studio(user))


def _owns_series(user, series):
    return bool(series and (series.user_id == user.id or is_admin(user)))


def create_series(user, title, genre="Drama", synopsis=None, visual_style="cinematic",
                  dialogue_language="nigerian_pidgin", aspect_ratio="9:16",
                  episode_duration_seconds=60):
    if not _can_access(user):
        return False, "AI Drama Studio is available on the Director plan.", None
    title = (title or "").strip()[:255]
    if not title:
        return False, "Enter a series title.", None
    if aspect_ratio not in {"9:16", "16:9", "1:1"}:
        aspect_ratio = "9:16"
    try:
        duration = int(episode_duration_seconds)
    except (TypeError, ValueError):
        duration = 60
    if duration not in {60, 180, 300}:
        duration = 60
    series = DramaSeries(
        user_id=user.id, title=title, genre=(genre or "Drama").strip()[:100],
        synopsis=(synopsis or "").strip() or None,
        visual_style=(visual_style or "cinematic").strip()[:100],
        dialogue_language=dialogue_language if dialogue_language in {"nigerian_pidgin", "nigerian_english", "english"} else "nigerian_pidgin",
        aspect_ratio=aspect_ratio, episode_duration_seconds=duration,
    )
    db.session.add(series)
    db.session.commit()
    return True, "Drama series created.", series


def add_series_character(user, series_id, name, role="Supporting", description=None,
                         personality=None, physical_appearance=None,
                         signature_clothing=None, voice_id=None, notes=None):
    series = db.session.get(DramaSeries, series_id)
    if not _owns_series(user, series):
        return False, "Series not found.", None
    name = (name or "").strip()[:120]
    if not name:
        return False, "Character name is required.", None
    if voice_id not in ALLOWED_VOICES:
        voice_id = None
    character = DramaCharacter(
        series_id=series.id, name=name, role=(role or "Supporting").strip()[:100],
        description=(description or "").strip() or None,
        personality=(personality or "").strip() or None,
        physical_appearance=(physical_appearance or "").strip() or None,
        signature_clothing=(signature_clothing or "").strip() or None,
        voice_id=voice_id, notes=(notes or "").strip() or None,
    )
    db.session.add(character)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "A character with that name already exists in this series.", None
    return True, "Series character added.", character


def _copy_character_to_episode(character, episode):
    movie_character = MovieCharacter(
        project_id=episode.movie_project_id, name=character.name, role=character.role,
        description=character.description, personality=character.personality,
        physical_appearance=character.physical_appearance,
        clothing=character.signature_clothing, voice_attributes=character.voice_id,
        reference_image_url=character.reference_image_url, notes=character.notes,
    )
    db.session.add(movie_character)
    db.session.flush()
    link = DramaEpisodeCharacter(
        episode_id=episode.id, character_id=character.id,
        movie_character_id=movie_character.id,
    )
    db.session.add(link)
    return link


def create_episode(user, series_id, title=None, logline=None):
    if not _can_access(user):
        return False, "AI Drama Studio is available on the Director plan.", None, None
    series = db.session.get(DramaSeries, series_id)
    if not _owns_series(user, series):
        return False, "Series not found.", None, None
    period_start = current_period_start()
    try:
        db.session.query(User).filter_by(id=user.id).with_for_update().one()
        usage = DramaMonthlyUsage.query.filter_by(
            user_id=user.id, period_start=period_start
        ).with_for_update().first()
        if usage is None:
            usage = DramaMonthlyUsage(user_id=user.id, period_start=period_start)
            db.session.add(usage)
            db.session.flush()
        if usage.episodes_reserved + usage.episodes_completed >= DIRECTOR_MONTHLY_EPISODE_LIMIT:
            db.session.rollback()
            return False, "You have reached the 30-episode Director allowance for this month.", None, None

        next_number = (db.session.query(func.max(DramaEpisode.episode_number))
                       .filter_by(series_id=series.id).scalar() or 0) + 1
        episode_title = (title or f"Episode {next_number}").strip()[:255]
        project = MovieProject(
            user_id=user.id, title=f"{series.title} — {episode_title}"[:255],
            genre=series.genre, cinematic_tone="Moody & Cinematic",
            aspect_ratio=series.aspect_ratio, target_duration=series.episode_duration_seconds,
            visual_style=series.visual_style, status="draft",
        )
        db.session.add(project)
        db.session.flush()
        episode = DramaEpisode(
            series_id=series.id, user_id=user.id, movie_project_id=project.id,
            episode_number=next_number, title=episode_title,
            logline=(logline or "").strip() or None,
            target_duration_seconds=series.episode_duration_seconds,
            status="queued", quota_period_start=period_start, quota_status="reserved",
        )
        db.session.add(episode)
        db.session.flush()
        usage.episodes_reserved += 1
        for character in series.characters:
            if character.is_active:
                _copy_character_to_episode(character, episode)
        job = DramaProductionJob(
            episode_id=episode.id, user_id=user.id,
            idempotency_key=f"drama-episode:{episode.id}:production:v1",
            status="queued", current_step="screenplay",
        )
        db.session.add(job)
        db.session.add(DramaUsageLedger(
            user_id=user.id, episode_id=episode.id,
            usage_type="episode_reservation", status="reserved",
            idempotency_key=f"drama-episode:{episode.id}:quota-reserve",
        ))
        db.session.commit()
        return True, "Episode queued for production.", episode, job
    except IntegrityError:
        db.session.rollback()
        return False, "The episode could not be reserved. Please retry.", None, None
    except Exception:
        db.session.rollback()
        raise


def add_character_to_episode(user, episode_id, character_id):
    episode = db.session.get(DramaEpisode, episode_id)
    if not episode or (episode.user_id != user.id and not is_admin(user)):
        return False, "Episode not found.", None
    character = db.session.get(DramaCharacter, character_id)
    if not character or character.series_id != episode.series_id:
        return False, "Character does not belong to this series.", None
    existing = DramaEpisodeCharacter.query.filter_by(
        episode_id=episode.id, character_id=character.id
    ).first()
    if existing:
        return True, "Character is already in this episode.", existing
    link = _copy_character_to_episode(character, episode)
    db.session.commit()
    return True, "Character added to episode.", link


def assign_character_to_shot(user, episode_id, shot_id, episode_character_id):
    episode = db.session.get(DramaEpisode, episode_id)
    if not episode or (episode.user_id != user.id and not is_admin(user)):
        return False, "Episode not found."
    shot = db.session.get(MovieShot, shot_id)
    if not shot or shot.project_id != episode.movie_project_id:
        return False, "Shot does not belong to this episode."
    link = db.session.get(DramaEpisodeCharacter, episode_character_id)
    if not link or link.episode_id != episode.id or not link.movie_character_id:
        return False, "Character is not assigned to this episode."
    existing = DramaShotCharacter.query.filter_by(
        movie_shot_id=shot.id, episode_character_id=link.id
    ).first()
    if existing:
        return True, "Character already assigned to this shot."
    db.session.add(DramaShotCharacter(movie_shot_id=shot.id, episode_character_id=link.id))
    db.session.commit()
    return True, "Character assigned to shot."


def finalize_episode_quota(episode_id, success):
    """Finalize a reserved slot once; duplicate worker callbacks are harmless."""
    episode = db.session.get(DramaEpisode, episode_id)
    if not episode or episode.quota_status != "reserved" or not episode.quota_period_start:
        return False
    usage = DramaMonthlyUsage.query.filter_by(
        user_id=episode.user_id, period_start=episode.quota_period_start
    ).with_for_update().first()
    if not usage:
        return False
    usage.episodes_reserved = max(0, usage.episodes_reserved - 1)
    if success:
        usage.episodes_completed += 1
        episode.quota_status = "completed"
        episode.status = "completed"
        ledger_type = "episode_completed"
    else:
        episode.quota_status = "released"
        episode.status = "failed"
        ledger_type = "episode_reservation_released"
    key = f"drama-episode:{episode.id}:quota-finalize"
    if not DramaUsageLedger.query.filter_by(idempotency_key=key).first():
        db.session.add(DramaUsageLedger(
            user_id=episode.user_id, episode_id=episode.id,
            usage_type=ledger_type, status="recorded", idempotency_key=key,
        ))
    db.session.commit()
    return True


def monthly_usage_summary(user_id, period_start=None):
    period_start = period_start or current_period_start()
    usage = DramaMonthlyUsage.query.filter_by(user_id=user_id, period_start=period_start).first()
    reserved = usage.episodes_reserved if usage else 0
    completed = usage.episodes_completed if usage else 0
    return {
        "period_start": period_start.isoformat(),
        "limit": DIRECTOR_MONTHLY_EPISODE_LIMIT,
        "reserved": reserved,
        "completed": completed,
        "remaining": max(0, DIRECTOR_MONTHLY_EPISODE_LIMIT - reserved - completed),
    }
