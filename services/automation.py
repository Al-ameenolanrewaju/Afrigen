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

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

def _decode_json(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _workflow_to_dict(workflow):
    nodes = []
    for task in sorted(workflow.tasks, key=lambda item: item.node_index):
        node = _decode_json(task.node_config, {})
        if not node:
            node = {"type": task.task_type}
        node.setdefault("type", task.task_type)
        node.setdefault("id", task.internal_id)
        node.setdefault("status", task.status)
        nodes.append(node)

    result = {
        "id": workflow.legacy_id,
        "name": workflow.name,
        "trigger": workflow.trigger,
        "nodes": nodes,
        "user_id": workflow.user_id,
        "brand_id": workflow.brand_id,
        "campaign_id": workflow.campaign_id,
        "status": workflow.status,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
    }
    _ensure_campaign_brand_on_workflow(result)
    return result


def _asset_to_dict(asset):
    return {
        "id": asset.legacy_id,
        "workflow_id": asset.workflow.legacy_id if asset.workflow else None,
        "run_id": asset.run.legacy_id if asset.run else None,
        "node_id": asset.node_id,
        "asset_type": asset.asset_type,
        "type": asset.asset_type,
        "title": asset.title,
        "content": asset.content,
        "file_url": asset.file_url,
        "url": asset.file_url,
        "thumbnail_url": asset.thumbnail_url,
        "provider_used": asset.provider_used,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "generation_time": asset.generation_time,
        "metadata": _decode_json(asset.meta_data, {}),
        "storage": "database",
    }


def _run_to_dict(run):
    return {
        "id": run.legacy_id,
        "workflow_id": run.workflow.legacy_id if run.workflow else None,
        "workflow_name": run.workflow_name,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "status": run.status,
        "nodes_executed": _decode_json(run.nodes_executed, []),
        "credits_used": run.credits_used or 0,
        "assets": [_asset_to_dict(asset) for asset in run.assets],
        "error": run.error,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def get_workflows(user_id=None):
    from models import Workflow
    query = Workflow.query
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return [_workflow_to_dict(row) for row in query.order_by(Workflow.created_at.asc()).all()]


def get_logs(user_id=None):
    from models import Workflow, WorkflowRun
    query = WorkflowRun.query.join(Workflow)
    if user_id is not None:
        query = query.filter(Workflow.user_id == user_id)
    runs = query.order_by(WorkflowRun.started_at.desc()).all()
    return [_run_to_dict(row) for row in runs]


def save_workflow(workflow_data, user_id=None):
    from models import db, Workflow, WorkflowTask

    workflow_id = workflow_data.get('id') or f"wf_{uuid.uuid4().hex[:8]}"
    workflow = Workflow.query.filter_by(legacy_id=workflow_id).first()
    owner_id = user_id if user_id is not None else workflow_data.get('user_id')
    if workflow and workflow.user_id != owner_id:
        raise PermissionError("Workflow does not belong to this user.")
    if workflow is None:
        workflow = Workflow(legacy_id=workflow_id)
        db.session.add(workflow)

    _ensure_campaign_brand_on_workflow(workflow_data)
    workflow.user_id = owner_id
    workflow.brand_id = workflow_data.get('brand_id') or None
    workflow.campaign_id = workflow_data.get('campaign_id') or None
    workflow.name = workflow_data.get('name') or "Untitled workflow"
    workflow.trigger = workflow_data.get('trigger') or "manual"
    workflow.status = workflow_data.get('status') or "pending"
    if workflow_data.get('created_at'):
        try:
            workflow.created_at = datetime.datetime.fromisoformat(workflow_data['created_at'].replace('Z', '+00:00'))
        except (AttributeError, ValueError):
            pass
    db.session.flush()

    WorkflowTask.query.filter_by(workflow_id=workflow.id).delete()
    for index, node in enumerate(workflow_data.get('nodes', [])):
        db.session.add(WorkflowTask(
            workflow_id=workflow.id,
            task_type=_normalize_node_type(node.get('type')),
            status=node.get('status') or 'pending',
            node_index=index,
            node_config=json.dumps(node),
            dependencies=json.dumps(node.get('dependencies', [])),
            internal_id=node.get('id') or f"node_{index}",
        ))
    db.session.commit()
    return _workflow_to_dict(workflow)


def delete_workflow(workflow_id, user_id=None):
    from models import db, Workflow
    query = Workflow.query.filter_by(legacy_id=workflow_id)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    workflow = query.first()
    if workflow:
        db.session.delete(workflow)
        db.session.commit()
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
            brand_query = Brand.query.filter_by(user_id=workflow_data.get('user_id'))
            if workflow_data.get('brand_id'):
                brand_query = brand_query.filter_by(id=workflow_data['brand_id'])
            brand = brand_query.first()
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
    from models import db, Workflow, WorkflowRun
    workflow = Workflow.query.filter_by(legacy_id=log_data['workflow_id']).first()
    if not workflow:
        raise ValueError(f"Workflow {log_data['workflow_id']} not found")
    run = WorkflowRun.query.filter_by(legacy_id=log_data['id']).first()
    if run is None:
        run = WorkflowRun(legacy_id=log_data['id'], workflow_id=workflow.id)
        db.session.add(run)
    run.workflow_id = workflow.id
    run.workflow_name = log_data.get('workflow_name')
    run.status = log_data.get('status') or 'failed'
    run.started_at = datetime.datetime.fromisoformat(log_data['started_at'].replace('Z', '+00:00'))
    run.completed_at = datetime.datetime.fromisoformat(log_data['completed_at'].replace('Z', '+00:00')) if log_data.get('completed_at') else None
    run.credits_used = log_data.get('credits_used') or 0
    run.nodes_executed = json.dumps(log_data.get('nodes_executed', []))
    run.error = log_data.get('error')
    db.session.commit()
    return run


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
                    print(f"[automation] campaign asset persisted id={asset_obj.id} campaign_id={campaign.id}")
                else:
                    print(f"[automation] no matching campaign found for workflow campaign_id={campaign_id}")
            except Exception as exc:
                db.session.rollback()
                print(f"[automation] asset persist failed: {exc}")
    except Exception as exc:
        print(f"[automation] asset persist setup failed: {exc}")

    try:
        from models import db, Workflow, WorkflowRun, WorkflowAsset
        workflow_row = Workflow.query.filter_by(legacy_id=workflow_id).first()
        run_row = WorkflowRun.query.filter_by(legacy_id=run_id).first()
        if not workflow_row or not run_row:
            raise ValueError("Workflow and run must be persisted before assets")
        asset_row = WorkflowAsset(
            legacy_id=asset_record["id"],
            workflow_id=workflow_row.id,
            run_id=run_row.id,
            node_id=asset_record["node_id"],
            asset_type=asset_record["asset_type"],
            title=asset_record["title"],
            content=asset_record["content"],
            file_url=asset_record["file_url"],
            thumbnail_url=asset_record["thumbnail_url"],
            provider_used=asset_record["provider_used"],
            generation_time=asset_record["generation_time"],
            meta_data=json.dumps(asset_record["metadata"], sort_keys=True),
            created_at=datetime.datetime.fromisoformat(asset_record["created_at"].replace("Z", "+00:00")),
        )
        db.session.add(asset_row)
        db.session.commit()
        asset_record["storage"] = "database"
    except Exception as exc:
        db.session.rollback()
        print(f"[automation] workflow asset persist failed: {exc}")
        return None

    return asset_record


def get_assets_for_run(run_id: str):
    from models import WorkflowAsset, WorkflowRun
    run = WorkflowRun.query.filter_by(legacy_id=run_id).first()
    if not run:
        return []
    return [_asset_to_dict(asset) for asset in run.assets]


def get_workflow_run(run_id: str):
    from models import WorkflowRun
    run = WorkflowRun.query.filter_by(legacy_id=run_id).first()
    return _run_to_dict(run) if run else None


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
                    owner = db.session.get(User, user_id, with_for_update=True) if user_id else None
                    if not owner:
                        raise ValueError('Image generation requires a valid user.')
                    from services.credits import image_gate, charge_image
                    ok, error = image_gate(owner)
                    if not ok:
                        raise ValueError(error)
                    provider = 'fal' if owner and owner.plan == 'pro' else 'huggingface'
                    result = video_service.generate_image(
                        prompt, style=node.get('style', 'african'), provider=provider,
                        allow_fal=bool(owner and owner.plan == 'pro'),
                    )
                    if isinstance(result, dict) and result.get('success') is False:
                        raise ValueError(result.get('error') or 'Image generation failed.')
                    charge_image(owner, reason='Automation image generation')
                elif node_type == 'generate_video':
                    from models import db, User
                    owner = db.session.get(User, user_id, with_for_update=True) if user_id else None
                    if not owner:
                        raise ValueError('Video generation requires a valid user.')
                    from services.credits import video_gate, charge_video
                    style = node.get('style', 'cinematic')
                    ok, error, video_cost = video_gate(owner, style, duration='5')
                    if not ok:
                        raise ValueError(error)
                    result = video_service.generate_video(
                        prompt, style=style, allow_fal=owner.plan == 'pro',
                    )
                    if isinstance(result, dict) and result.get('success') is False:
                        raise ValueError(result.get('error') or 'Video generation failed.')
                    charge_video(owner, video_cost, reason='Automation video generation')
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
    started_at = datetime.datetime.now(datetime.timezone.utc)

    log = {
        "id": log_id,
        "workflow_id": workflow_id,
        "workflow_name": workflow.get('name', 'Unknown'),
        "started_at": started_at.isoformat(),
        "status": "running",
        "nodes_executed": [],
        "credits_used": 0,
        "assets": [],
    }

    try:
        from models import db, Workflow, WorkflowRun, WorkflowTask
        workflow_row = Workflow.query.filter_by(legacy_id=workflow_id).first()
        if not workflow_row:
            raise ValueError(f"Workflow {workflow_id} not found")
        db.session.add(WorkflowRun(
            legacy_id=log_id,
            workflow_id=workflow_row.id,
            workflow_name=log["workflow_name"],
            status="running",
            started_at=started_at,
            credits_used=0,
            nodes_executed="[]",
        ))
        db.session.commit()

        runtime_context = {}
        for index, node in enumerate(nodes):
            node_record = _run_node(node, workflow_id=workflow_id, run_id=log_id, node_index=index, user_id=user_id, workflow=workflow, runtime_context=runtime_context)
            print(f"[automation] node_record {index} success={node_record.get('success')} asset_present={node_record.get('asset') is not None}")
            log['nodes_executed'].append(node_record)
            log['credits_used'] += node_record.get('credits_consumed', 0)
            if node_record.get('asset'):
                log['assets'].append(node_record['asset'])
            task = WorkflowTask.query.filter_by(
                workflow_id=workflow_row.id, node_index=index
            ).first()
            if task:
                task.status = 'completed' if node_record.get('success') else 'failed'
                task.result_data = json.dumps(node_record)
            db.session.commit()

        log['status'] = "failed" if any(
            not node_record.get('success') for node_record in log['nodes_executed']
        ) else "completed"
        workflow_row.status = log['status']
        db.session.commit()

    except Exception as e:
        log['status'] = "failed"
        log['error'] = str(e)
        workflow_row.status = "failed"
        db.session.commit()

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
