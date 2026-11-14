"""Afrigen 2.0 Movie Studio Routes.

Full AI filmmaking workspace restricted strictly to Director Tier (Tier 3) and Admin.
"""
import json
import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
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
logger = logging.getLogger(__name__)


def _movie_media_response(url, asset_type, asset_id):
    from services.ai_products import customer_error
    from services.media_proxy import MediaProxyError, proxy_media

    content_type = {
        'character': 'image/jpeg',
        'shot-image': 'image/jpeg',
        'shot-video': 'video/mp4',
        'project-cover': 'image/jpeg',
        'project-video': 'video/mp4',
        'job': 'video/mp4',
        'audio': 'audio/mpeg',
    }[asset_type]
    try:
        return proxy_media(url, f'afrigen-movie-{asset_type}-{asset_id}', content_type)
    except MediaProxyError:
        logger.exception('Movie Studio media proxy failed')
        product = 'video' if content_type.startswith('video/') else 'image'
        return customer_error(product), 502, {'Content-Type': 'text/plain; charset=utf-8'}


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
    return jsonify({
        "success": ok,
        "image_url": url_for(
            'movie_studio.movie_media',
            asset_type='character',
            asset_id=char_id,
        ) if ok else None,
        "error": None if ok else url_or_err,
    })


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
    return jsonify({
        "success": ok,
        "video_url": url_for(
            'movie_studio.movie_media',
            asset_type='shot-video',
            asset_id=shot_id,
        ) if ok else None,
        "error": None if ok else url_or_err,
    })


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
        "output_video_url": url_for(
            'movie_studio.movie_media',
            asset_type='job',
            asset_id=job.id,
        ) if job.output_video_url else None,
        "error_message": (
            "Afrigen Movie Engine couldn't complete this render. Please try again."
            if job.error_message else None
        )
    })


@movie_studio_bp.route('/media/<asset_type>/<int:asset_id>')
@login_required
def movie_media(asset_type, asset_id):
    if not can_access_movie_studio(current_user):
        abort(404)

    url = None
    if asset_type == 'character':
        asset = db.session.get(MovieCharacter, asset_id)
        if asset and asset.project.user_id == current_user.id:
            url = asset.reference_image_url
    elif asset_type in ('shot-image', 'shot-video'):
        asset = db.session.get(MovieShot, asset_id)
        if asset and asset.project.user_id == current_user.id:
            url = asset.reference_image_url if asset_type == 'shot-image' else asset.video_url
    elif asset_type in ('project-cover', 'project-video'):
        asset = db.session.get(MovieProject, asset_id)
        if asset and asset.user_id == current_user.id:
            url = asset.cover_image_url if asset_type == 'project-cover' else asset.final_video_url
    elif asset_type == 'job':
        asset = db.session.get(MovieRenderJob, asset_id)
        if asset and asset.user_id == current_user.id:
            url = asset.output_video_url
    elif asset_type == 'audio':
        asset = db.session.get(MovieAudioTrack, asset_id)
        if asset and asset.project.user_id == current_user.id:
            url = asset.audio_url

    if not url:
        abort(404)
    return _movie_media_response(url, asset_type, asset_id)

