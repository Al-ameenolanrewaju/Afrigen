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
from services.ai_products import customer_error, redact_secrets
from services.audio import generate_voiceover, generate_speech_audio
from services.credits import video_gate, deduct_credits_atomic, refund_video
from services.entitlements import is_admin
import fal_client

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
        logger.error("Screenplay generation failed: %s", redact_secrets(str(exc)))
        db.session.rollback()
        return False, customer_error("movie")


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
        f"Style: {project.visual_style}, {project.cinematic_tone}. Natural studio lighting, cinematic portrait composition."
    )

    try:
        res = generate_image(prompt, style="realistic", aspect_ratio="1:1", provider="fal", allow_fal=True)
        if res and res.get("success") and res.get("image_url"):
            char.reference_image_url = res["image_url"]
            from services.generation_notifications import create_media_ready_notification
            create_media_ready_notification(
                project.user_id,
                "photo",
                f"/movie-studio/projects/{project.id}#characters",
                title="Your character portrait is ready",
                message=f"The portrait for {char.name} has been generated.",
            )
            db.session.commit()
            return True, res["image_url"]
        return False, res.get("error", "Image generation failed")
    except Exception as e:
        logger.error("Character portrait generation error: %s", redact_secrets(str(e)))
        return False, customer_error("image")


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
        "Breakdown the screenplay scene into 2 to 3 cinematic shots. Mention the exact character names from the cast whenever they appear in a shot. Preserve their established appearance and clothing.\n"
        "Return ONLY JSON matching:\n"
        "[\n"
        '  {"shot_number": 1, "camera_angle": "Wide Shot", "camera_movement": "Slow Tracking", "lighting": "Golden Hour", "visual_prompt": "Detailed description of what is visible on screen."}\n'
        "]"
    )

    cast_notes = "\n".join(
        f"- {char.name}: {char.physical_appearance or char.description or 'appearance not specified'}; clothing: {char.clothing or 'preserve the approved reference outfit'}"
        for char in project.characters
    )
    user_content = (
        f"Slugline: {scene.slugline}\nDescription: {scene.description}\nScript: {scene.screenplay_text}\n"
        f"CAST REFERENCES (use exact names in visual_prompt whenever visible):\n{cast_notes}"
    )

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
        logger.error("Storyboard creation failed: %s", redact_secrets(str(exc)))
        db.session.rollback()
        return False, customer_error("movie")


# ---------------------------------------------------------------------
# 4. Shot Video Generator
# ---------------------------------------------------------------------

def _character_references_for_shot(shot):
    """Return approved character portraits explicitly present in this shot."""
    project = shot.project
    context = " ".join([
        shot.visual_prompt or "",
        getattr(shot.scene, "description", "") or "",
        getattr(shot.scene, "screenplay_text", "") or "",
    ]).casefold()
    matches = [
        character for character in project.characters
        if character.reference_image_url and character.name.casefold() in context
    ]
    return matches[:3]


def _build_character_consistency_prompt(shot, characters):
    """Build Kling element references and continuity instructions for a shot."""
    elements = []
    continuity = []
    for index, character in enumerate(characters, 1):
        elements.append({"frontal_image_url": character.reference_image_url})
        appearance = character.physical_appearance or character.description or "match the approved portrait"
        clothing = character.clothing or "keep the clothing shown in the approved reference"
        continuity.append(
            f"@Element{index} is {character.name}. Preserve this exact person's facial identity, "
            f"skin tone, age appearance, hairstyle and body proportions. Appearance: {appearance}. "
            f"Clothing continuity: {clothing}. Do not redesign or substitute this character."
        )
    return elements, " ".join(continuity)


def _generate_reference_guided_shot(shot, prompt, characters):
    """Generate a shot using Kling V3 image-to-video with character elements."""
    elements, continuity = _build_character_consistency_prompt(shot, characters)
    start_image = shot.reference_image_url or (
        characters[0].reference_image_url if characters else None
    )
    if not start_image:
        return None

    duration = str(shot.duration or "5")
    if duration not in {str(value) for value in range(3, 16)}:
        duration = "5"

    arguments = {
        "start_image_url": start_image,
        "prompt": f"{prompt} {continuity}".strip(),
        "duration": duration,
        "generate_audio": False,
        "negative_prompt": (
            "different person, changed face, changed hairstyle, changed clothing, "
            "inconsistent character, face distortion, extra limbs, blurry, low quality"
        ),
    }
    if elements:
        arguments["elements"] = elements

    result = fal_client.subscribe(
        "fal-ai/kling-video/v3/pro/image-to-video",
        arguments=arguments,
    )
    video = (result or {}).get("video") or {}
    return video.get("url")


def generate_scene_pidgin_dialogue(scene_id: int):
    """Create a Nigerian Pidgin dialogue read for each storyboard shot."""
    scene = db.session.get(MovieScene, scene_id)
    if not scene:
        return False, "Scene not found", []
    project = scene.project
    if not scene.screenplay_text or not scene.screenplay_text.strip():
        return False, "This scene has no screenplay dialogue yet.", []
    cast = list(project.characters)
    if not cast:
        return False, "Add characters before generating dialogue.", []

    cast_text = "\n".join(
        f"- {character.name}: role={character.role}; voice={character.voice_attributes or 'en-NG-AbeoNeural'}"
        for character in cast
    )
    shot_text = "\n".join(
        f"- Shot {shot.shot_number}: {shot.visual_prompt}" for shot in scene.shots
    )
    try:
        raw = provider_manager.generate_text(
            task_type="Movie Studio Pidgin Dialogue",
            messages=[
                {"role": "system", "content": (
                    "You are a Nigerian screenwriter fluent in natural Nigerian Pidgin. "
                    "Adapt screenplay dialogue into expressive conversational Nigerian Pidgin, preserving intent. "
                    "Return only a JSON array of objects: shot_number (integer), character (exact cast name), "
                    "line (8 to 24 spoken words). One speaker per shot. Only include shots with spoken dialogue. "
                    "Do not invent characters, narration or stage directions."
                )},
                {"role": "user", "content": (
                    f"Scene {scene.scene_number}: {scene.slugline}\nScreenplay:\n{scene.screenplay_text}\n"
                    f"Cast:\n{cast_text}\nStoryboard:\n{shot_text}"
                )},
            ],
            max_tokens=1200,
        )
        dialogue_rows = json.loads((raw or "").strip())
        if not isinstance(dialogue_rows, list):
            raise ValueError("Dialogue response must be a JSON array")

        character_by_name = {character.name.casefold(): character for character in cast}
        shot_by_number = {shot.shot_number: shot for shot in scene.shots}
        created = []
        for row in dialogue_rows:
            character = character_by_name.get(str(row.get("character", "")).strip().casefold())
            shot = shot_by_number.get(int(row.get("shot_number", 0)))
            line = str(row.get("line", "")).strip()
            if not character or not shot or not line:
                continue
            voice = character.voice_attributes or "en-NG-AbeoNeural"
            audio_url = generate_speech_audio(line, voice=voice)
            if not audio_url:
                raise RuntimeError(f"Could not synthesize dialogue for {character.name}")
            title = f"Dialogue · Scene {scene.scene_number} · Shot {shot.shot_number} · {character.name}"
            track = MovieAudioTrack.query.filter_by(
                project_id=project.id, track_type="dialogue", title=title
            ).first()
            if track is None:
                track = MovieAudioTrack(
                    project_id=project.id, track_type="dialogue", title=title,
                    audio_url=audio_url, script_text=line, voice_id=voice,
                    start_time=0.0, duration=0.0,
                )
                db.session.add(track)
            else:
                track.audio_url = audio_url
                track.script_text = line
                track.voice_id = voice
            created.append({"shot_id": shot.id, "shot_number": shot.shot_number,
                            "character": character.name, "line": line})
        db.session.commit()
        if not created:
            return False, "No valid dialogue lines were returned for this scene.", []
        return True, f"Generated {len(created)} Nigerian Pidgin dialogue track(s).", created
    except Exception as exc:
        db.session.rollback()
        logger.error("Pidgin dialogue generation failed: %s", redact_secrets(str(exc)))
        return False, customer_error("audio"), []


def sync_shot_dialogue(shot_id: int):
    """Lip-sync a completed shot to its saved character dialogue and charge by duration."""
    shot = db.session.get(MovieShot, shot_id)
    if not shot:
        return False, "Shot not found"
    if not shot.video_url or shot.status != "completed":
        return False, "Generate the shot video before applying lip-sync."
    duration = int(float(shot.duration or 5))
    if duration < 2 or duration > 10:
        return False, "Kling LipSync supports clips between 2 and 10 seconds."
    scene = shot.scene
    project = shot.project
    title_prefix = f"Dialogue · Scene {scene.scene_number} · Shot {shot.shot_number} · "
    track = MovieAudioTrack.query.filter(
        MovieAudioTrack.project_id == project.id,
        MovieAudioTrack.track_type == "dialogue",
        MovieAudioTrack.title.like(f"{title_prefix}%"),
    ).first()
    if not track or not track.audio_url:
        return False, "Generate this scene's Pidgin dialogue first."

    cost = max(5, ((duration + 4) // 5) * 5)
    user = project.user
    charged = False
    if not is_admin(user):
        charged, error = deduct_credits_atomic(
            user.id, cost, f"Movie Studio lip-sync · Scene {scene.scene_number}, Shot {shot.shot_number}"
        )
        if not charged:
            return False, f"Lip-sync costs {cost} credits for this {duration}-second shot. {error or 'Add credits and try again.'}"
        db.session.commit()
    try:
        result = fal_client.subscribe(
            "fal-ai/kling-video/lipsync/audio-to-video",
            arguments={"video_url": shot.video_url, "audio_url": track.audio_url},
        )
        synced_url = ((result or {}).get("video") or {}).get("url")
        if not synced_url:
            raise RuntimeError("Lip-sync provider returned no video URL")
        shot.video_url = synced_url
        db.session.commit()
        return True, synced_url
    except Exception as exc:
        if charged:
            refund_video(user, cost, f"Refund Movie Studio lip-sync · Shot {shot.shot_number}")
        db.session.commit()
        logger.error("Movie shot lip-sync failed: %s", redact_secrets(str(exc)))
        return False, customer_error("video")


def generate_shot_video_clip(shot_id: int):
    """Generate a Movie Studio shot, using approved character references when available."""
    shot = db.session.get(MovieShot, shot_id)
    if not shot:
        return False, "Shot not found"

    project = shot.project
    user = project.user
    duration = str(shot.duration or "5")
    full_prompt = (
        f"{shot.visual_prompt}. Camera: {shot.camera_angle}, {shot.camera_movement}. "
        f"Lighting: {shot.lighting}. Style: {project.visual_style}, cinematic composition."
    )
    characters = _character_references_for_shot(shot)
    cost = 0
    charged = False
    admin_bypass = is_admin(user)

    if not admin_bypass:
        allowed, error, cost = video_gate(
            user, "movie", extended=True, duration=duration
        )
        if not allowed:
            return False, error
        if cost > 0:
            charged, charge_error = deduct_credits_atomic(
                user.id, cost, f"Movie Studio shot {shot.id} generation"
            )
            if not charged:
                return False, charge_error or "Not enough credits."
            db.session.commit()

    shot.status = "generating"
    shot.error_message = None
    db.session.commit()

    try:
        video_url = None
        if characters or shot.reference_image_url:
            video_url = _generate_reference_guided_shot(
                shot, full_prompt, characters
            )

        # Environment-only shots keep the established text-to-video path.
        if not video_url:
            res = generate_video(
                full_prompt,
                style="movie",
                aspect_ratio=project.aspect_ratio or "16:9",
                extended=True,
                duration=duration,
                allow_fal=True,
            )
            if res and res.get("success"):
                video_url = res.get("video_url")

        if not video_url:
            raise RuntimeError("Video provider returned no output URL")

        shot.video_url = video_url
        shot.status = "completed"
        from services.generation_notifications import create_media_ready_notification
        create_media_ready_notification(
            project.user_id,
            "video",
            f"/movie-studio/projects/{project.id}#shots",
            title="Your video clip is ready",
            message=f"Shot {shot.shot_number} has been generated.",
        )
        db.session.commit()
        return True, shot.video_url
    except Exception as exc:
        shot.status = "failed"
        shot.error_message = customer_error("video")
        if charged:
            refund_video(user, cost, f"Refund failed Movie Studio shot {shot.id}")
        db.session.commit()
        logger.error("Movie shot generation failed: %s", redact_secrets(str(exc)))
        return False, customer_error("video")

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
                    job.error_message = customer_error("movie")
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
                from services.generation_notifications import create_media_ready_notification
                create_media_ready_notification(
                    user_id,
                    "video",
                    f"/movie-studio/projects/{project.id}",
                    title="Your movie is ready",
                    message=f"{project.title} has finished rendering.",
                )
                db.session.commit()

            except Exception as exc:
                logger.error("Movie render failed: %s", redact_secrets(str(exc)))
                job.status = "failed"
                job.error_message = customer_error("movie")
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

