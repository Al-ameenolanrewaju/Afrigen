"""Director-only AI Drama Studio series and episode workspace."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import db, DramaSeries, DramaEpisode, DramaEpisodeCharacter, MovieShot
from services.entitlements import can_access_movie_studio, is_admin
from services.drama_studio import (
    create_series, create_episode, add_series_character,
    add_character_to_episode, assign_character_to_shot, monthly_usage_summary,
    generate_series_character_portrait,
    generate_series_character_portrait,
)

drama_studio_bp = Blueprint("drama_studio", __name__, url_prefix="/drama-studio")


def _series_for_user(series_id):
    series = db.session.get(DramaSeries, series_id)
    if not series or (series.user_id != current_user.id and not is_admin(current_user)):
        abort(404)
    return series


@drama_studio_bp.route("/")
@login_required
def index():
    if not can_access_movie_studio(current_user):
        flash("AI Drama Studio is exclusive to the Director plan.", "warning")
        return redirect(url_for("main.upgrade"))
    series = DramaSeries.query.filter_by(user_id=current_user.id).order_by(DramaSeries.updated_at.desc()).all()
    usage = monthly_usage_summary(current_user.id)
    return render_template("main/drama_studio/index.html", series=series, usage=usage)


@drama_studio_bp.route("/series", methods=["POST"])
@login_required
def create_series_view():
    if not can_access_movie_studio(current_user):
        abort(403)
    ok, message, series = create_series(
        current_user,
        request.form.get("title"),
        genre=request.form.get("genre", "Drama"),
        synopsis=request.form.get("synopsis"),
        visual_style=request.form.get("visual_style", "cinematic"),
        dialogue_language=request.form.get("dialogue_language", "nigerian_pidgin"),
        aspect_ratio=request.form.get("aspect_ratio", "9:16"),
        episode_duration_seconds=request.form.get("episode_duration_seconds", 60),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("drama_studio.series_workspace", series_id=series.id) if ok else url_for("drama_studio.index"))


@drama_studio_bp.route("/series/<int:series_id>")
@login_required
def series_workspace(series_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    series = _series_for_user(series_id)
    usage = monthly_usage_summary(current_user.id)
    return render_template("main/drama_studio/series.html", series=series, usage=usage)


@drama_studio_bp.route("/series/<int:series_id>/episodes", methods=["POST"])
@login_required
def create_episode_view(series_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    _series_for_user(series_id)
    ok, message, episode, job = create_episode(
        current_user, series_id,
        title=request.form.get("title"),
        logline=request.form.get("logline"),
    )
    if not ok:
        flash(message, "danger")
        return redirect(url_for("drama_studio.series_workspace", series_id=series_id))
    flash(message + " Open the episode workspace to continue screenplay and shot production.", "success")
    return redirect(url_for("movie_studio.project_workspace", project_id=episode.movie_project_id))


@drama_studio_bp.route("/series/<int:series_id>/characters", methods=["POST"])
@login_required
def add_character_view(series_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    _series_for_user(series_id)
    ok, message, _character = add_series_character(
        current_user, series_id,
        name=request.form.get("name"),
        role=request.form.get("role", "Supporting"),
        description=request.form.get("description"),
        personality=request.form.get("personality"),
        physical_appearance=request.form.get("physical_appearance"),
        signature_clothing=request.form.get("signature_clothing"),
        voice_id=request.form.get("voice_id"),
        notes=request.form.get("notes"),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("drama_studio.series_workspace", series_id=series_id))




@drama_studio_bp.route("/series/<int:series_id>/characters/<int:character_id>/portrait", methods=["POST"])
@login_required
def generate_character_portrait_view(series_id, character_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    _series_for_user(series_id)
    ok, result = generate_series_character_portrait(current_user, series_id, character_id)
    message = "Canonical portrait generated and synced to episode cast copies." if ok else str(result)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("drama_studio.series_workspace", series_id=series_id))


@drama_studio_bp.route("/episodes/<int:episode_id>/characters/<int:character_id>", methods=["POST"])
@login_required
def add_episode_character_view(episode_id, character_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    episode = db.session.get(DramaEpisode, episode_id)
    if not episode or (episode.user_id != current_user.id and not is_admin(current_user)):
        abort(404)
    ok, message, _link = add_character_to_episode(current_user, episode_id, character_id)
    flash(message, "success" if ok else "danger")
    return redirect(url_for("movie_studio.project_workspace", project_id=episode.movie_project_id))


@drama_studio_bp.route("/episodes/<int:episode_id>/shots/<int:shot_id>/characters/<int:episode_character_id>", methods=["POST"])
@login_required
def assign_shot_character_view(episode_id, shot_id, episode_character_id):
    if not can_access_movie_studio(current_user):
        abort(403)
    ok, message = assign_character_to_shot(current_user, episode_id, shot_id, episode_character_id)
    return jsonify({"success": ok, "message": message}), (200 if ok else 400)
