"""In-app notifications for successfully generated user media."""
from models import db, Notification


def create_media_ready_notification(user_id, media_type, link, title=None, message=None):
    """Add a success notification for a generated photo or video."""
    if media_type not in ("photo", "video"):
        raise ValueError("media_type must be 'photo' or 'video'.")

    media_label = "photo" if media_type == "photo" else "video"
    notification = Notification(
        user_id=user_id,
        title=title or f"Your {media_label} is ready",
        message=message or f"Your {media_label} has been generated successfully.",
        link=link,
        type="success",
    )
    db.session.add(notification)
    return notification


def notify_generation_ready(generation):
    """Queue one in-app notification when a generation has produced media."""
    if generation.status != "completed":
        return None

    if generation.id is None:
        db.session.flush()

    if generation.video_url:
        title = "Your video is ready"
        message = "Your video has been generated successfully."
        link = f"/result/video?generation_id={generation.id}"
    elif generation.image_url:
        title = "Your photo is ready"
        message = "Your photo has been generated successfully."
        link = f"/result/image?generation_id={generation.id}"
    else:
        return None

    existing = Notification.query.filter_by(
        user_id=generation.user_id,
        link=link,
        type="success",
    ).first()
    if existing:
        return existing

    media_type = "video" if generation.video_url else "photo"
    return create_media_ready_notification(
        generation.user_id, media_type, link, title=title, message=message
    )
