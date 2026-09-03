import os
import json
import time
import uuid
import datetime
from typing import Any, Dict, List

import services.blog as blog_service
import services.newsletter as newsletter_service
import services.video as video_service
import services.audio as audio_service
import services.claude as claude_service
import content_engine.utils as content_engine_utils
from app import app

# Using a flat file datastore for Sprint 8 to bypass Supabase schema issues locally.
# In production, this would map directly to the Workflow and WorkflowLog SQLAlchemy models.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'automations.json')
ASSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'automation_assets.json')

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

def _ensure_file():
    if not os.path.exists(os.path.dirname(DATA_FILE)):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({"workflows": [], "logs": []}, f)

def get_workflows():
    _ensure_file()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    return data.get("workflows", [])

def get_logs():
    _ensure_file()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    # Return latest logs first
    return sorted(data.get("logs", []), key=lambda x: x.get('started_at', ''), reverse=True)

def save_workflow(workflow_data):
    _ensure_file()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        
    if 'id' not in workflow_data or not workflow_data['id']:
        workflow_data['id'] = "wf_" + str(uuid.uuid4())[:8]
        workflow_data['created_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
    _ensure_campaign_brand_on_workflow(workflow_data)
    workflows = data.get("workflows", [])
    
    # Update if exists
    idx = next((i for i, w in enumerate(workflows) if w['id'] == workflow_data['id']), None)
    if idx is not None:
        workflows[idx] = workflow_data
    else:
        workflows.append(workflow_data)
        
    data["workflows"] = workflows
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    return workflow_data

def delete_workflow(workflow_id):
    _ensure_file()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    
    workflows = data.get("workflows", [])
    data["workflows"] = [w for w in workflows if w.get('id') != workflow_id]
    
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    
    return True


def _ensure_campaign_brand_on_workflow(workflow_data):
    """Ensure workflow has explicit campaign and brand context if available."""
    try:
        from models import db, Campaign, Brand
        if workflow_data.get('campaign_id'):
            campaign = db.session.get(Campaign, workflow_data['campaign_id'])
            if campaign:
                workflow_data.setdefault('campaign', {})
                workflow_data['campaign'].update({
                    'id': campaign.id,
                    'title': campaign.title,
                    'goal': campaign.goal,
                })
        if not workflow_data.get('brand'):
            brand = Brand.query.filter_by(user_id=workflow_data.get('user_id')).first()
            if brand:
                workflow_data['brand'] = {
                    'name': brand.name,
                    'primary_color': brand.primary_color,
                    'secondary_color': brand.secondary_color,
                    'accent_color': brand.accent_color,
                    'typography': brand.typography,
                }
    except Exception:
        # Best-effort only; don't fail save if DB not available
        pass


def save_log(log_data):
    _ensure_file()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    logs = data.get("logs", [])
    logs.append(log_data)
    data["logs"] = logs
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def _ensure_asset_store():
    if not os.path.exists(os.path.dirname(ASSET_FILE)):
        os.makedirs(os.path.dirname(ASSET_FILE), exist_ok=True)
    if not os.path.exists(ASSET_FILE):
        with open(ASSET_FILE, 'w') as f:
            json.dump([], f)


def _load_assets_from_file() -> List[Dict[str, Any]]:
    _ensure_asset_store()
    with open(ASSET_FILE, 'r') as f:
        return json.load(f)


def _write_assets_to_file(assets: List[Dict[str, Any]]):
    _ensure_asset_store()
    with open(ASSET_FILE, 'w') as f:
        json.dump(assets, f, indent=4)


def _persist_user_content(user_id: int, workflow_id: str, run_id: str, node: Dict[str, Any], provider: str, asset_payload: Dict[str, Any], prompt: str, result: Any):
    if not user_id:
        return None

    content_type = _asset_type_for_node(node.get("type"))
    metadata = {
        "workflow_id": workflow_id,
        "run_id": run_id,
        "node_id": node.get("id") or "",
        "node_label": node.get("label", node.get("type")),
        "prompt": prompt,
        "provider": provider,
        "source": "automation",
    }

    if content_type == "blog":
        title = asset_payload.get("title") or node.get("label") or "Generated blog"
        body = asset_payload.get("content") or ""
        summary = body[:500] if body else None
    else:
        title = asset_payload.get("title") or node.get("label") or "Generated asset"
        body = asset_payload.get("content") or asset_payload.get("url") or ""
        summary = body[:500] if body else None

    try:
        from models import db, User, UserContent
        from sqlalchemy import func

        user = db.session.get(User, user_id)
        if not user:
            user = User(username=f"automation_user_{user_id}", email=f"automation_{user_id}@example.com", password="default")
            db.session.add(user)
            db.session.commit()

        next_id = (db.session.query(func.max(UserContent.id)).scalar() or 0) + 1
        item = UserContent(
            id=next_id,
            user_id=user.id,
            content_type=content_type,
            title=title,
            body=body,
            summary=summary,
            file_url=asset_payload.get("url") or None,
            thumbnail_url=asset_payload.get("thumbnail_url") or None,
            status="draft",
            source="automation",
            provider_used=provider,
            content_metadata=json.dumps(metadata, sort_keys=True),
        )
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item
    except Exception as exc:
        if 'db' in locals():
            db.session.rollback()
        print(f"[automation] user content persist failed: {exc}")
        return None


def _persist_asset(workflow_id: str, run_id: str, node_index: int, node: Dict[str, Any], provider: str, duration_seconds: float, asset_payload: Dict[str, Any], prompt: str, result: Any, workflow: Dict[str, Any] | None = None):
    print(f"[automation] _persist_asset entry workflow={workflow_id} run={run_id} node_index={node_index} asset_payload_present={asset_payload is not None} provider={provider}")
    if not asset_payload:
        print(f"[automation] _persist_asset skipped due to empty asset_payload")
        return None

    metadata = {
        "workflow_id": workflow_id,
        "run_id": run_id,
        "node_id": node.get("id") or f"node_{node_index}",
        "node_label": node.get("label", node.get("type")),
        "node_type": node.get("type"),
        "prompt": prompt,
        "provider": provider,
        "duration_seconds": duration_seconds,
    }

    if node.get("type") == "prompt_refinement":
        metadata["original_prompt"] = prompt
        metadata["refined_prompt"] = result if isinstance(result, str) else asset_payload.get("content")
    elif node.get("type") == "ai_assistant":
        metadata["assistant_output"] = result if isinstance(result, str) else asset_payload.get("content")

    asset_record = {
        "id": f"asset_{uuid.uuid4().hex[:8]}",
        "workflow_id": workflow_id,
        "run_id": run_id,
        "node_id": metadata["node_id"],
        "asset_type": _asset_type_for_node(node.get("type")),
        "title": node.get("label", node.get("type")),
        "content": asset_payload.get("content") or "",
        "file_url": asset_payload.get("url") or None,
        "thumbnail_url": asset_payload.get("thumbnail_url") or None,
        "provider_used": provider,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "generation_time": round(duration_seconds, 3),
        "metadata": metadata,
    }

    persisted_to_db = False
    try:
        from models import db, Campaign, CampaignAsset
        if db.session is not None:
            try:
                campaign = None
                campaign_id = None
                if isinstance(workflow, dict):
                    campaign_id = workflow.get('campaign_id') or (workflow.get('campaign') or {}).get('id')

                print(f"[automation] _persist_asset workflow campaign_id={campaign_id} user_id={workflow.get('user_id') if isinstance(workflow, dict) else None}")
                if campaign_id is not None:
                    campaign = db.session.get(Campaign, campaign_id)
                    print(f"[automation] campaign lookup by id returned {campaign}")
                if not campaign and isinstance(workflow, dict):
                    user_id = workflow.get('user_id')
                    if user_id is not None:
                        campaign = db.session.query(Campaign).filter_by(user_id=user_id).order_by(Campaign.id.desc()).first()
                        print(f"[automation] campaign lookup by user_id returned {campaign}")

                if campaign is not None:
                    asset_obj = CampaignAsset(
                        campaign_id=campaign.id,
                        title=asset_record["title"],
                        asset_type=asset_record["asset_type"],
                        content=asset_record["content"] or "",
                        file_url=asset_record["file_url"],
                        thumbnail_url=asset_record["thumbnail_url"],
                        provider_used=asset_record["provider_used"],
                        generation_time=asset_record["generation_time"],
                        meta_data=json.dumps(asset_record["metadata"], sort_keys=True),
                    )
                    db.session.add(asset_obj)
                    db.session.commit()
                    asset_record["database_id"] = asset_obj.id
                    asset_record["campaign_id"] = campaign.id
                    asset_record["storage"] = "database"
                    persisted_to_db = True
                    print(f"[automation] campaign asset persisted id={asset_obj.id} campaign_id={campaign.id}")
                else:
                    print(f"[automation] no matching campaign found for workflow campaign_id={campaign_id} user_id={workflow.get('user_id') if isinstance(workflow, dict) else None}")
            except Exception as exc:
                db.session.rollback()
                print(f"[automation] asset persist failed: {exc}")
    except Exception as exc:
        print(f"[automation] asset persist setup failed: {exc}")

    assets = _load_assets_from_file()
    assets.append(asset_record)
    _write_assets_to_file(assets)

    if not persisted_to_db:
        asset_record["storage"] = "file"

    return asset_record


def get_assets_for_run(run_id: str):
    assets = _load_assets_from_file()
    matching = [asset for asset in assets if asset.get("run_id") == run_id]
    if matching:
        return matching

    try:
        from models import db, CampaignAsset
        rows = db.session.query(CampaignAsset).filter(CampaignAsset.meta_data.contains(f'"run_id": "{run_id}"')).all()
        return [
            {
                "id": row.id,
                "workflow_id": None,
                "run_id": run_id,
                "asset_type": row.asset_type,
                "title": row.title,
                "content": row.content,
                "file_url": row.file_url,
                "thumbnail_url": row.thumbnail_url,
                "provider_used": row.provider_used,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "generation_time": row.generation_time,
                "metadata": json.loads(row.meta_data or "{}"),
                "storage": "database",
            }
            for row in rows
        ]
    except Exception:
        return []


def get_workflow_run(run_id: str):
    logs = get_logs()
    for log in logs:
        if log.get("id") == run_id:
            return log
    return None


def _normalize_node_type(node_type):
    return {
        "generate_content": "generate_blog",
    }.get(node_type, node_type)


def _asset_type_for_node(node_type):
    normalized = _normalize_node_type(node_type)
    return {
        "generate_blog": "blog",
        "generate_newsletter": "newsletter",
        "generate_image": "image",
        "generate_video": "video",
        "generate_voice": "voice",
        "ai_assistant": "assistant",
        "prompt_refinement": "prompt_refinement",
        "publish_social": "publish_result",
    }.get(normalized, normalized)


def _estimate_credits(node_type):
    normalized = _normalize_node_type(node_type)
    return {
        "generate_blog": 2,
        "generate_newsletter": 2,
        "generate_image": 1,
        "generate_video": 5,
        "generate_voice": 2,
        "ai_assistant": 0,
        "prompt_refinement": 0,
    }.get(normalized, 0)


def _provider_for_node(node_type):
    normalized = _normalize_node_type(node_type)
    return {
        "generate_blog": "BlogService",
        "generate_newsletter": "NewsletterService",
        "generate_image": "VideoService/Image",
        "generate_video": "VideoService/Video",
        "generate_voice": "AudioService",
        "ai_assistant": "ContentEngine/ProviderManager",
        "prompt_refinement": "Claude/ProviderManager",
    }.get(normalized, "AutomationEngine")


def _build_asset_payload(node_type, result):
    normalized = _normalize_node_type(node_type)
    if normalized == "publish_social":
        return {
            "type": "publish_result",
            "content": result,
        }
    if normalized == "generate_blog":
        if isinstance(result, dict):
            return {
                "type": "blog",
                "title": result.get("title") or result.get("slug"),
                "content": result.get("body") or result.get("content"),
                "slug": result.get("slug"),
            }
        return {
            "type": "blog",
            "title": getattr(result, "title", None),
            "content": getattr(result, "body", None),
            "slug": getattr(result, "slug", None),
        }

    if normalized == "generate_newsletter":
        if isinstance(result, tuple) and len(result) == 2:
            subject, body = result
            return {"type": "newsletter", "subject": subject, "body": body}
        if isinstance(result, dict):
            return {"type": "newsletter", "subject": result.get("subject"), "body": result.get("body") or result.get("content")}
        return {"type": "newsletter", "content": result}

    if normalized == "generate_image":
        if isinstance(result, dict):
            url = result.get("image_url") or result.get("url")
            return {"type": "image", "url": url}
        return {"type": "image", "url": result}

    if normalized == "generate_video":
        if isinstance(result, dict):
            url = result.get("video_url") or result.get("url")
            return {"type": "video", "url": url}
        return {"type": "video", "url": result}

    if normalized == "generate_voice":
        return {"type": "voice", "url": result}

    if normalized == "ai_assistant":
        return {"type": "assistant", "content": result}

    if normalized == "prompt_refinement":
        return {"type": "prompt_refinement", "content": result}

    return None


def _publish_automation_asset(user_id, provider, action, scheduled_for, asset, title):
    """Publish the most recent generated asset from a workflow node."""
    if not user_id or not provider:
        raise ValueError("Publish node requires a provider and user")
    if not asset or not asset.get("url"):
        raise ValueError("Publish node requires a generated asset from a previous node")

    from models import db, ConnectedAccount, PublishingRetryQueue, UserContent
    account = ConnectedAccount.query.filter_by(
        user_id=user_id, provider=provider, status="connected"
    ).first()
    if not account:
        raise ValueError(f"{provider} is not connected")

    content = UserContent(
        user_id=user_id,
        content_type=asset.get("type", "video"),
        title=title[:300],
        body="",
        file_url=asset["url"],
        status="draft",
        source="automation_publish",
    )
    db.session.add(content)
    db.session.flush()

    if action == "schedule":
        try:
            next_attempt = datetime.datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise ValueError("Scheduled publishing requires a valid scheduled_for value")
        if next_attempt.tzinfo is None:
            next_attempt = next_attempt.replace(tzinfo=datetime.timezone.utc)
        if next_attempt <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("Scheduled publishing time must be in the future")
        db.session.add(PublishingRetryQueue(
            user_id=user_id,
            content_id=content.id,
            provider=provider,
            status="pending",
            next_attempt=next_attempt,
        ))
        db.session.commit()
        return {"ok": True, "scheduled": True, "status": "pending"}

    from services.connected_accounts.provider_registry import get_adapter
    result = get_adapter(provider).publish(user_id, content, {})
    if result.get("ok"):
        content.status = "published"
        content.published_to = provider
        content.published_at = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()
    return result


def _run_node(node, workflow_id: str, run_id: str, node_index: int, user_id: int | None = None, workflow: Dict[str, Any] | None = None, runtime_context: Dict[str, Any] | None = None):
    node_type = _normalize_node_type(node.get('type'))
    prompt = node.get('prompt') or node.get('text') or ''
    runtime_context = runtime_context or {}
    context_parts = []
    if (workflow or {}).get('brand'):
        brand = workflow['brand']
        context_parts.append(f"Brand: {brand.get('name', '')}; colors: {brand.get('primary_color', '')}, {brand.get('secondary_color', '')}.")
    if (workflow or {}).get('campaign'):
        campaign = workflow['campaign']
        context_parts.append(f"Campaign: {campaign.get('title', '')}; goal: {campaign.get('goal', '')}.")
    if context_parts and node_type in {'generate_video', 'generate_image', 'generate_blog', 'generate_newsletter'}:
        prompt = f"{prompt}\n\nContext: {' '.join(context_parts)}"
    provider = _provider_for_node(node_type)
    start_time = time.time()
    last_error = None
    asset = None
    result = None

    print(f"[automation] running node {node_index} type={node_type} label={node.get('label')} workflow={workflow_id} run={run_id} campaign_id={workflow.get('campaign_id') if isinstance(workflow, dict) else None}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with app.app_context():
                if node_type == 'generate_blog':
                    result = blog_service.generate_blog_content()
                elif node_type == 'generate_newsletter':
                    result = newsletter_service.generate_weekly_digest()
                elif node_type == 'generate_image':
                    from models import db, User
                    owner = db.session.get(User, user_id) if user_id else None
                    provider = 'fal' if owner and owner.plan == 'pro' else 'huggingface'
                    result = video_service.generate_image(prompt, style=node.get('style', 'african'), provider=provider)
                elif node_type == 'generate_video':
                    from models import db, User
                    owner = db.session.get(User, user_id) if user_id else None
                    if owner and owner.plan != 'pro':
                        raise ValueError('Video generation is a Pro feature.')
                    result = video_service.generate_video(prompt, style=node.get('style', 'cinematic'))
                elif node_type == 'publish_social':
                    result = _publish_automation_asset(
                        user_id=user_id,
                        provider=node.get('provider'),
                        action=node.get('action', 'publish_now'),
                        scheduled_for=node.get('scheduled_for'),
                        asset=runtime_context.get('last_asset'),
                        title=node.get('label', 'Automation content'),
                    )
                elif node_type == 'generate_voice':
                    result = audio_service.generate_voiceover(prompt)
                elif node_type == 'ai_assistant':
                    result = content_engine_utils.generate_with_llm(
                        system='You are a helpful AI assistant for Afrigen workflows.',
                        user=prompt,
                        max_tokens=300,
                    )
                elif node_type == 'prompt_refinement':
                    result = claude_service.refine_prompt(prompt)
                else:
                    result = f"No handler for node type: {node_type}"

            asset = _build_asset_payload(node_type, result)
            duration_seconds = round(time.time() - start_time, 3)
            print(f"[automation] node {node_index} result={type(result).__name__ if result is not None else 'None'} asset={asset is not None}")
            with app.app_context():
                asset_record = _persist_asset(
                    workflow_id=workflow_id,
                    run_id=run_id,
                    node_index=node_index,
                    node=node,
                    provider=provider,
                    duration_seconds=duration_seconds,
                    asset_payload=asset,
                    prompt=prompt,
                    result=result,
                    workflow=workflow,
                )
                print(f"[automation] _persist_asset returned {asset_record is not None}")
                if asset_record:
                    asset["asset_id"] = asset_record.get("id")
                    asset["storage"] = asset_record.get("storage")

                if asset and asset.get("url"):
                    runtime_context["last_asset"] = asset
    
                user_content = _persist_user_content(user_id, workflow_id, run_id, node, provider, asset, prompt, result)
                if user_content:
                    asset["user_content_id"] = user_content.id
            return {
                "node_type": node_type,
                "label": node.get('label', node_type),
                "success": True,
                "provider": provider,
                "duration_seconds": duration_seconds,
                "credits_consumed": _estimate_credits(node_type),
                "asset": asset,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        except Exception as exc:
            last_error = str(exc)
            print(f"[automation] node {node_index} attempt {attempt} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
                continue

    return {
        "node_type": node_type,
        "label": node.get('label', node_type),
        "success": False,
        "provider": provider,
        "duration_seconds": round(time.time() - start_time, 3),
        "credits_consumed": 0,
        "asset": None,
        "error": last_error,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def execute_workflow_sync(workflow_id, user_id: int | None = None):
    """Executes the workflow nodes sequentially using real generation services."""
    workflows = get_workflows()
    workflow = next((w for w in workflows if w['id'] == workflow_id), None)
    if not workflow:
        return

    nodes = workflow.get('nodes', [])
    log_id = "log_" + str(uuid.uuid4())[:8]

    log = {
        "id": log_id,
        "workflow_id": workflow_id,
        "workflow_name": workflow.get('name', 'Unknown'),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "running",
        "nodes_executed": [],
        "credits_used": 0,
        "assets": [],
    }

    try:
        runtime_context = {}
        for index, node in enumerate(nodes):
            node_record = _run_node(node, workflow_id=workflow_id, run_id=log_id, node_index=index, user_id=user_id, workflow=workflow, runtime_context=runtime_context)
            print(f"[automation] node_record {index} success={node_record.get('success')} asset_present={node_record.get('asset') is not None}")
            log['nodes_executed'].append(node_record)
            log['credits_used'] += node_record.get('credits_consumed', 0)
            if node_record.get('asset'):
                log['assets'].append(node_record['asset'])

        log['status'] = "completed"

    except Exception as e:
        log['status'] = "failed"
        log['error'] = str(e)

    log['completed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_log(log)

def trigger_workflow_async(workflow_id, user_id: int | None = None):
    """Fires a workflow in a background job to prevent UI blocking."""
    from app import scheduler
    scheduler.add_job(
        id=f"execute_automation_{workflow_id}_{int(time.time())}",
        func=execute_workflow_sync,
        args=[workflow_id, user_id]
    )

def apscheduler_tick():
    """
    This function is intended to be called by APScheduler every minute.
    It checks workflow schedules and triggers async executions.
    """
    print("[AutomationEngine] Checking scheduled workflows...")
    # Schedule parsing logic (cron) would go here for production.
