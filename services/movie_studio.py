"""Afrigen 2.0 Movie Studio Engine.

Powers:
- AI Screenplay Writer (Story concepts, treatments, scene outlines, dialogue).
- Character Dossier Development & Visual Reference generation.
- Storyboard generation & prompt synthesis.
- Scene & Shot video generation via Kling AI & Kling Pro models.
- Audio Production (Dialogue, narration, Edge-TTS synthesis).
- FFmpeg Multi-Shot Concatenation & Master Movie Rendering.
"""
import os
import json
import logging
import tempfile
import threading
import subprocess
import requests
from datetime import datetime, timezone
from flask import current_app
from models import (
    db, User, MovieProject, MovieCharacter, MovieScene,
    MovieShot, StoryboardFrame, MovieAudioTrack, MovieTimeline, MovieRenderJob
)
from services.provider_manager import provider_manager
from services.video import generate_image, generate_video, generate_video_from_image
from services.audio import generate_voiceover

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# 1. AI Screenplay Writer
# ---------------------------------------------------------------------

def generate_screenplay_treatment(project: MovieProject):
    """Use Groq LLM to generate logline, synopsis, character suggestions, and scene breakdown."""
    system_prompt = (
        "You are an award-winning African film director and master screenwriter. "
        "Create a compelling, professional cinematic treatment for an AI-generated movie. "
        "The story should have rich African cultural resonance, vivid visuals, and high dramatic stakes.\n\n"
        "OUTPUT FORMAT: Return ONLY valid JSON with no markdown wrapping or preamble, matching this schema:\n"
        "{\n"
        '  "logline": "A one-sentence hook.",\n'
        '  "synopsis": "A 2-3 paragraph summary of the narrative arc.",\n'
        '  "characters": [\n'
        '    {"name": "Character Name", "role": "Protagonist/Antagonist/Supporting", "description": "Brief bio & visual look"}\n'
        '  ],\n'
        '  "scenes": [\n'
        '    {"scene_number": 1, "title": "Opening Scene", "slugline": "EXT. LAGOS WATERFRONT - SUNSET", "description": "Visual action", "screenplay_text": "Sample dialogue and action lines."}\n'
        '  ]\n'
        "}"
    )

    user_prompt = (
        f"Title: {project.title}\n"
        f"Genre: {project.genre}\n"
        f"Cinematic Tone: {project.cinematic_tone}\n"
        f"Visual Style: {project.visual_style}\n"
        f"Desired Duration: {project.target_duration} seconds\n"
        f"Story Concept / Idea: {project.logline or project.synopsis or 'An ambitious creative narrative set in modern and futuristic Africa.'}"
    )

    try:
        raw = provider_manager.generate_text(
            task_type="Screenplay Treatment",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2200
        )
        
        # Clean JSON from response
        clean = (raw or "").strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        data = json.loads(clean)
        
        # Persist to project
        if data.get("logline"):
            project.logline = data["logline"]
        if data.get("synopsis"):
            project.synopsis = data["synopsis"]

        # Populate characters
        for char_data in data.get("characters", []):
            char = MovieCharacter(
                project_id=project.id,
                name=char_data.get("name", "Character"),
                role=char_data.get("role", "Protagonist"),
                description=char_data.get("description", ""),
                physical_appearance=char_data.get("description", "")
            )
            db.session.add(char)

        # Populate scenes
        for i, sc in enumerate(data.get("scenes", []), 1):
            scene = MovieScene(
                project_id=project.id,
                scene_number=sc.get("scene_number", i),
                title=sc.get("title", f"Scene {i}"),
                slugline=sc.get("slugline", "EXT. SCENE - DAY"),
                description=sc.get("description", ""),
                screenplay_text=sc.get("screenplay_text", ""),
                order=i
            )
            db.session.add(scene)

        project.status = "storyboarding"
        db.session.commit()
        return True, "Screenplay treatment generated successfully!"

    except Exception as exc:
        logger.exception("Screenplay generation failed: %s", exc)
        db.session.rollback()
        return False, str(exc)


# ---------------------------------------------------------------------
# 2. Character Reference Generator
# ---------------------------------------------------------------------

def generate_character_portrait_asset(character_id: int):
    """Generate a photorealistic 35mm portrait for character reference consistency."""
    char = db.session.get(MovieCharacter, character_id)
    if not char:
        return False, "Character not found"

    project = char.project
    prompt = (
        f"Cinematic close-up portrait of {char.name}, an African {char.role.lower()}. "
        f"{char.physical_appearance or char.description or 'Authentic rich melanin skin, dignified features'}. "
        f"Style: {project.visual_style}, {project.cinematic_tone}. Natural studio lighting, 35mm film still, photorealistic, 8K."
    )

    try:
        res = generate_image(prompt, style="realistic", aspect_ratio="1:1", provider="fal", allow_fal=True)
        if res and res.get("success") and res.get("image_url"):
            char.reference_image_url = res["image_url"]
            db.session.commit()
            return True, res["image_url"]
        return False, res.get("error", "Image generation failed")
    except Exception as e:
        logger.error("Character portrait generation error: %s", e)
        return False, str(e)


# ---------------------------------------------------------------------
# 3. Storyboard & Shot Creator
# ---------------------------------------------------------------------

def create_scene_shots_and_storyboards(scene_id: int):
    """Breakdown a scene into shots and create visual storyboard frames."""
    scene = db.session.get(MovieScene, scene_id)
    if not scene:
        return False, "Scene not found"

    project = scene.project
    system_prompt = (
        "You are an expert storyboard artist and cinematographer. "
        "Breakdown the screenplay scene into 2 to 3 cinematic shots.\n"
        "Return ONLY JSON matching:\n"
        "[\n"
        '  {"shot_number": 1, "camera_angle": "Wide Shot", "camera_movement": "Slow Tracking", "lighting": "Golden Hour", "visual_prompt": "Detailed description of what is visible on screen."}\n'
        "]"
    )

    user_content = f"Slugline: {scene.slugline}\nDescription: {scene.description}\nScript: {scene.screenplay_text}"

    try:
        raw = provider_manager.generate_text(
            task_type="Storyboard Breakdown",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=1000
        )
        clean = (raw or "").strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        shot_list = json.loads(clean)
        for i, s in enumerate(shot_list, 1):
            shot = MovieShot(
                scene_id=scene.id,
                project_id=project.id,
                shot_number=s.get("shot_number", i),
                visual_prompt=s.get("visual_prompt", scene.description),
                camera_angle=s.get("camera_angle", "Wide Shot"),
                camera_movement=s.get("camera_movement", "Slow Push-In"),
                lighting=s.get("lighting", "Volumetric Golden"),
                duration="5",
                order=i
            )
            db.session.add(shot)
            db.session.flush()

            # Create storyboard frame
            frame = StoryboardFrame(
                shot_id=shot.id,
                scene_id=scene.id,
                project_id=project.id,
                image_url="",
                visual_description=shot.visual_prompt,
                caption=f"Scene {scene.scene_number} · Shot {shot.shot_number}: {shot.camera_angle}",
                order=i
            )
            db.session.add(frame)

        db.session.commit()
        return True, f"Created {len(shot_list)} shots for Scene {scene.scene_number}"
    except Exception as exc:
        logger.exception("Storyboard creation failed: %s", exc)
        db.session.rollback()
        return False, str(exc)


# ---------------------------------------------------------------------
# 4. Shot Video Generator
# ---------------------------------------------------------------------

def generate_shot_video_clip(shot_id: int):
    """Render the cinematic video clip for a specific shot using Kling Pro."""
    shot = db.session.get(MovieShot, shot_id)
    if not shot:
        return False, "Shot not found"

    project = shot.project
    full_prompt = (
        f"{shot.visual_prompt}. Camera: {shot.camera_angle}, {shot.camera_movement}. "
        f"Lighting: {shot.lighting}. Style: {project.visual_style}, cinematic masterwork, ARRI Alexa 65 4k."
    )

    shot.status = "generating"
    db.session.commit()

    try:
        # Use movie style which routes to Kling Pro in services/video.py
        res = generate_video(
            full_prompt,
            style="movie",
            aspect_ratio=project.aspect_ratio or "16:9",
            extended=True,
            duration=str(shot.duration or "5"),
            allow_fal=True
        )

        if res and res.get("success") and res.get("video_url"):
            shot.video_url = res["video_url"]
            shot.status = "completed"
            db.session.commit()
            return True, shot.video_url
        else:
            shot.status = "failed"
            shot.error_message = res.get("error", "Video generation failed")
            db.session.commit()
            return False, shot.error_message
    except Exception as exc:
        shot.status = "failed"
        shot.error_message = str(exc)
        db.session.commit()
        return False, str(exc)


# ---------------------------------------------------------------------
# 5. Master Movie Timeline Renderer (FFmpeg Background Pipeline)
# ---------------------------------------------------------------------

def start_movie_render_job(project_id: int, user_id: int, app_instance=None):
    """Queue and execute the background FFmpeg concatenation and mastering job."""
    app = app_instance or current_app._get_current_object()

    render_job = MovieRenderJob(
        project_id=project_id,
        user_id=user_id,
        status="processing",
        progress=10
    )
    db.session.add(render_job)
    db.session.commit()
    job_id = render_job.id

    def _render_worker():
        with app.app_context():
            job = db.session.get(MovieRenderJob, job_id)
            project = db.session.get(MovieProject, project_id)
            if not job or not project:
                return

            temp_dir = tempfile.mkdtemp(prefix="afrigen_movie_")
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

                # 1. Collect all completed shots in sequence
                shots = (
                    MovieShot.query
                    .filter_by(project_id=project.id, status="completed")
                    .order_by(MovieShot.scene_id.asc(), MovieShot.order.asc())
                    .all()
                )

                if not shots:
                    job.status = "failed"
                    job.error_message = "No completed video shots found in project to render."
                    db.session.commit()
                    return

                # 2. Download clip files
                clip_paths = []
                for idx, s in enumerate(shots):
                    if not s.video_url:
                        continue
                    clip_file = os.path.join(temp_dir, f"clip_{idx:03d}.mp4")
                    r = requests.get(s.video_url, timeout=120)
                    if r.status_code == 200:
                        with open(clip_file, "wb") as f:
                            f.write(r.content)
                        clip_paths.append(clip_file)

                if not clip_paths:
                    job.status = "failed"
                    job.error_message = "Failed to download clip source files."
                    db.session.commit()
                    return

                job.progress = 40
                db.session.commit()

                # 3. Build concat file list for FFmpeg
                concat_list_file = os.path.join(temp_dir, "concat_list.txt")
                with open(concat_list_file, "w", encoding="utf-8") as f:
                    for cp in clip_paths:
                        # Forward slashes for FFmpeg compatibility
                        safe_cp = cp.replace("\\", "/")
                        f.write(f"file '{safe_cp}'\n")

                output_file = os.path.join(temp_dir, f"master_movie_{project.id}.mp4")

                job.progress = 65
                db.session.commit()

                # 4. Execute FFmpeg concatenation
                cmd = [
                    ffmpeg_exe, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_file,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "fast",
                    "-crf", "20",
                    output_file
                ]

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if proc.returncode != 0 or not os.path.exists(output_file):
                    logger.error("FFmpeg concat failed: %s", proc.stderr)
                    job.status = "failed"
                    job.error_message = f"Movie rendering failed: {proc.stderr[:300]}"
                    db.session.commit()
                    return

                job.progress = 85
                db.session.commit()

                # 5. Upload master movie to Fal Storage CDN
                import fal_client
                uploaded_url = fal_client.upload_file(output_file)

                if not uploaded_url:
                    # Fallback to local uploads
                    from werkzeug.utils import secure_filename
                    local_filename = f"movie_{project.id}_{int(datetime.now().timestamp())}.mp4"
                    local_dir = os.path.join(app.root_path, "static", "uploads")
                    os.makedirs(local_dir, exist_ok=True)
                    local_target = os.path.join(local_dir, local_filename)
                    import shutil
                    shutil.copyfile(output_file, local_target)
                    uploaded_url = f"/static/uploads/{local_filename}"

                # 6. Complete Job & update Project
                project.final_video_url = uploaded_url
                project.status = "completed"
                job.status = "completed"
                job.progress = 100
                job.output_video_url = uploaded_url
                job.completed_at = datetime.now(timezone.utc)
                db.session.commit()

            except Exception as exc:
                logger.exception("Movie render error: %s", exc)
                job.status = "failed"
                job.error_message = str(exc)
                db.session.commit()
            finally:
                # Cleanup temp dir
                try:
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    threading.Thread(target=_render_worker, daemon=True).start()
    return True, job_id

