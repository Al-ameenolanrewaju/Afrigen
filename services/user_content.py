import json
from datetime import datetime, timezone

from models import db, UserContent


def serialize_user_content(item):
    return {
        "id": item.id,
        "user_id": item.user_id,
        "content_type": item.content_type,
        "title": item.title,
        "body": item.body,
        "summary": item.summary,
        "file_url": item.file_url,
        "thumbnail_url": item.thumbnail_url,
        "status": item.status,
        "source": item.source,
        "provider_used": item.provider_used,
        "metadata": json.loads(item.content_metadata or "{}"),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "published_at": item.published_at.isoformat() if getattr(item, "published_at", None) else None,
        "published_to": item.published_to,
    }


def list_user_content(user_id, content_type=None, status=None):
    query = UserContent.query.filter_by(user_id=user_id)
    if content_type:
        query = query.filter_by(content_type=content_type)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(UserContent.created_at.desc()).all()


def create_user_content(user_id, content_type, title, body=None, summary=None, file_url=None, thumbnail_url=None, status="draft", source="manual", provider_used=None, metadata=None):
    item = UserContent(
        user_id=user_id,
        content_type=content_type,
        title=title,
        body=body,
        summary=summary,
        file_url=file_url,
        thumbnail_url=thumbnail_url,
        status=status,
        source=source,
        provider_used=provider_used,
        content_metadata=json.dumps(metadata or {}, sort_keys=True),
    )
    db.session.add(item)
    db.session.commit()
    return item


def publish_user_content(content_id, user_id, destination="website"):
    from models import ConnectedAccount, PublishingPreference, PublishingRetryQueue, PublishingLog
    
    item = UserContent.query.filter_by(id=content_id, user_id=user_id).first()
    if not item:
        return None
        
    if destination == "website":
        item.status = "published"
        item.published_at = datetime.now(timezone.utc)
        item.published_to = destination
        metadata = json.loads(item.content_metadata or "{}")
        metadata["published_to"] = destination
        item.content_metadata = json.dumps(metadata, sort_keys=True)
        db.session.commit()
        return item
        
    # 1. Check Connected Account
    account = ConnectedAccount.query.filter_by(user_id=user_id, provider=destination, status="connected").first()
    if not account:
        return {"ok": False, "error": f"No connected account found for {destination}"}
        
    # 2. Check Preferences
    pref = PublishingPreference.query.filter_by(user_id=user_id, provider=destination, content_type=item.content_type).first()
    if pref and not pref.enabled:
        return {"ok": False, "error": f"Publishing {item.content_type} to {destination} is disabled in preferences."}

    # 3. Add to Queue
    queue_item = PublishingRetryQueue(
        user_id=user_id,
        content_id=content_id,
        provider=destination,
        status="pending"
    )
    db.session.add(queue_item)
    
    # 4. Mark item as queued
    item.status = "queued"
    metadata = json.loads(item.content_metadata or "{}")
    metadata["published_to"] = destination
    item.content_metadata = json.dumps(metadata, sort_keys=True)
    db.session.commit()
    
    return {"ok": True, "message": "Content queued for publishing"}
