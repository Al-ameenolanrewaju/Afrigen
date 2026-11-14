"""Afrigen 2.0 Movie Studio Routes.

Full AI filmmaking workspace restricted strictly to Director Tier (Tier 3) and Admin.
"""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import csrf, limiter
from models import (
    db, MovieProject, MovieCharacter, MovieScene, MovieShot,
    StoryboardFrame, MovieAudioTrack, MovieTimeline, MovieRenderJob
)
from services.entitlements import can_access_movie_studio, get_user_entitlements
from services.movie_studio import (
    generate_screenplay_treatment, generate_character_portrait_asset,
    create_scene_shots_and_storyboards, generate_shot_video_clip,
    start_movie_render_job
)

movie_studio_bp = Blueprint('movie_studio', __name__, url_prefix='/movie-studio')


@movie_studio_bp.route('/')
@login_required
def index():
    """Movie Studio Home. Unlocked for Director tier; locked upgrade pitch for lower tiers."""
    entitlements = get_user_entitlements(current_user)
    if not can_access_movie_studio(current_user):
        return render_template('main/movie_studio/locked.html', entitlements=entitlements)

    projects = (
        MovieProject.query
        .filter_by(user_id=current_user.id)
        .order_by(MovieProject.updated_at.desc())
        .all()
    )
    recent_jobs = (
        MovieRenderJob.query
        .filter_by(user_id=current_user.id)
        .order_by(MovieRenderJob.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        'main/movie_studio/index.html',
        projects=projects,
        recent_jobs=recent_jobs,
        entitlements=entitlements
    )


@movie_studio_bp.route('/projects/create', methods=['POST'])
@login_required
def create_project():
    if not can_access_movie_studio(current_user):
        flash("Movie Studio is exclusively available on the Director plan.", "warning")
        return redirect(url_for('main.upgrade'))

    title = (request.form.get('title') or "Untitled Masterpiece").strip()[:200]
    genre = request.form.get('genre', 'Afrofuturism')
    cinematic_tone = request.form.get('cinematic_tone', 'Moody & Cinematic')
    aspect_ratio = request.form.get('aspect_ratio', '16:9')
    target_duration = int(request.form.get('target_duration', 60))
    logline = (request.form.get('logline') or '').strip()

    project = MovieProject(
        user_id=current_user.id,
        title=title,
        genre=genre,
        cinematic_tone=cinematic_tone,
        aspect_ratio=aspect_ratio,
        target_duration=target_duration,
        logline=logline,
        status="draft"
    )
    db.session.add(project)
    db.session.commit()

    # Generate initial treatment
    generate_screenplay_treatment(project)

    flash(f"Movie project '{title}' created successfully!", "success")
    return redirect(url_for('movie_studio.project_workspace', project_id=project.id))


@movie_studio_bp.route('/projects/<int:project_id>')
@login_required
def project_workspace(project_id):
    if not can_access_movie_studio(current_user):
        return render_template('main/movie_studio/locked.html', entitlements=get_user_entitlements(current_user))

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        flash("Movie project not found or unauthorized.", "danger")
        return redirect(url_for('movie_studio.index'))

    return render_template(
        'main/movie_studio/project.html',
        project=project,
        entitlements=get_user_entitlements(current_user)
    )


@movie_studio_bp.route('/projects/<int:project_id>/treatment', methods=['POST'])
@login_required
def regenerate_treatment(project_id):
    if not can_access_movie_studio(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Not found"}), 404

    ok, msg = generate_screenplay_treatment(project)
    return jsonify({"success": ok, "message": msg})


@movie_studio_bp.route('/projects/<int:project_id>/characters/<int:char_id>/portrait', methods=['POST'])
@login_required
def generate_character_portrait(project_id, char_id):
    if not can_access_movie_studio(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Not found"}), 404

    ok, url_or_err = generate_character_portrait_asset(char_id)
    return jsonify({"success": ok, "image_url": url_or_err if ok else None, "error": None if ok else url_or_err})


@movie_studio_bp.route('/projects/<int:project_id>/scenes/<int:scene_id>/storyboard', methods=['POST'])
@login_required
def generate_storyboards(project_id, scene_id):
    if not can_access_movie_studio(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Not found"}), 404

    ok, msg = create_scene_shots_and_storyboards(scene_id)
    return jsonify({"success": ok, "message": msg})


@movie_studio_bp.route('/projects/<int:project_id>/shots/<int:shot_id>/generate', methods=['POST'])
@login_required
def generate_shot(project_id, shot_id):
    if not can_access_movie_studio(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Not found"}), 404

    ok, url_or_err = generate_shot_video_clip(shot_id)
    return jsonify({"success": ok, "video_url": url_or_err if ok else None, "error": None if ok else url_or_err})


@movie_studio_bp.route('/projects/<int:project_id>/render', methods=['POST'])
@login_required
def trigger_render(project_id):
    if not can_access_movie_studio(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    project = db.session.get(MovieProject, project_id)
    if not project or project.user_id != current_user.id:
        return jsonify({"success": False, "error": "Not found"}), 404

    ok, job_id_or_err = start_movie_render_job(project.id, current_user.id)
    return jsonify({"success": ok, "job_id": job_id_or_err if ok else None, "error": None if ok else job_id_or_err})


@movie_studio_bp.route('/render-jobs/<int:job_id>/status')
@login_required
def render_job_status(job_id):
    job = db.session.get(MovieRenderJob, job_id)
    if not job or job.user_id != current_user.id:
        return jsonify({"success": False, "error": "Job not found"}), 404

    return jsonify({
        "success": True,
        "status": job.status,
        "progress": job.progress,
        "output_video_url": job.output_video_url,
        "error_message": job.error_message
    })

