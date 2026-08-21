import threading
import time
from datetime import datetime, timezone
from models import db, PublishingRetryQueue, PublishingLog
from services.connected_accounts.provider_registry import get_adapter
from services.connected_accounts.health import ProviderHealthService
import uuid

def process_queue():
    """
    Background worker that processes the PublishingRetryQueue.
    Designed to be called periodically by APScheduler.
    """
    from flask import current_app
    # Find pending or processing items whose next_attempt is passed or None
    now = datetime.now(timezone.utc)
    items = PublishingRetryQueue.query.filter(
        PublishingRetryQueue.status.in_(["pending", "failed"]),
        (PublishingRetryQueue.next_attempt == None) | (PublishingRetryQueue.next_attempt <= now),
        PublishingRetryQueue.retry_count < 5
    ).all()
    
    if not items:
        return
        
    for item in items:
        # Skip if provider is down
        if not ProviderHealthService.is_provider_healthy(item.provider):
            continue
            
        item.status = "processing"
        db.session.commit()
        
        try:
            adapter = get_adapter(item.provider)
            start_time = time.time()
            
            # Generate request ID
            req_id = str(uuid.uuid4())
            
            # Attempt publish
            result = adapter.publish(item.user_id, item.content)
            
            exec_time_ms = int((time.time() - start_time) * 1000)
            
            # Log it
            log = PublishingLog(
                user_id=item.user_id,
                content_id=item.content_id,
                provider=item.provider,
                status="success" if result.get("ok") else "failed",
                message=result.get("error", "Published successfully"),
                request_id=req_id,
                response_id=str(result.get("post_id", "")),
                published_url=result.get("url"),
                execution_time_ms=exec_time_ms,
                error_details=str(result) if not result.get("ok") else None
            )
            db.session.add(log)
            
            if result.get("ok"):
                item.status = "success"
                ProviderHealthService.record_success(item.provider, exec_time_ms)
            else:
                item.status = "failed"
                item.retry_count += 1
                item.next_attempt = datetime.now(timezone.utc) # Add delay logic here
                ProviderHealthService.record_failure(item.provider, result.get("error", "Unknown error"))
                
            db.session.commit()
        except Exception as e:
            item.status = "failed"
            item.retry_count += 1
            ProviderHealthService.record_failure(item.provider, str(e))
            db.session.commit()

