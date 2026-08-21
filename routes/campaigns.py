from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, Campaign, CampaignTask, CampaignAsset, TaskStatus, CampaignStatus, Brand
from services.workflow_planner import workflow_planner
from services.workflow_executor import workflow_executor

campaigns_bp = Blueprint('campaigns', __name__)

@campaigns_bp.route('/', methods=['POST'])
@login_required
def create_campaign():
    data = request.get_json()
    if not data or 'business_goal' not in data:
        return jsonify({"error": "business_goal is required"}), 400


    campaign = Campaign(
        user_id=current_user.id,
        title=data.get('title', 'New Campaign'),
        goal=data['business_goal'],
        business_goal=data['business_goal'],
        target_audience=data.get('target_audience'),
        tone=data.get('tone'),
        industry=data.get('industry')
    )
    db.session.add(campaign)
    db.session.commit()

    # Phase 2: Workflow Planner
    workflow_planner.create_plan(campaign)

    # Phase 3: Start Executor in background
    from app import scheduler
    scheduler.add_job(
        id=f"execute_campaign_{campaign.id}",
        func=workflow_executor.execute_campaign,
        args=[campaign.id]
    )

    return jsonify({
        "message": "Campaign created and execution started",
        "campaign_id": campaign.id,
        "status": campaign.status
    }), 201


@campaigns_bp.route('/', methods=['GET'])
@login_required
def list_campaigns():
    """Returns all campaigns for the logged-in user."""
    campaigns = Campaign.query.filter_by(user_id=current_user.id).order_by(Campaign.created_at.desc()).all()
    result = []
    for c in campaigns:
        result.append({
            "id": c.id,
            "title": c.title,
            "business_goal": c.business_goal,
            "status": c.status,
            "progress": c.progress,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
    # Fetch user's primary brand (optional)
    brand = Brand.query.filter_by(user_id=current_user.id).first()
    brand_data = None
    if brand:
        brand_data = {
            "name": brand.name,
            "primary_color": brand.primary_color,
            "secondary_color": brand.secondary_color,
            "accent_color": brand.accent_color,
            "typography": brand.typography
        }

    return jsonify({"campaigns": result, "brand": brand_data})


@campaigns_bp.route('/<int:campaign_id>', methods=['GET'])
@login_required
def get_campaign(campaign_id):
    """
    Phase 4: Campaign Library endpoint.
    Returns campaign details, tasks, and generated assets.
    """
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    tasks = CampaignTask.query.filter_by(campaign_id=campaign.id).order_by(CampaignTask.priority.asc()).all()
    assets = CampaignAsset.query.filter_by(campaign_id=campaign.id).order_by(CampaignAsset.created_at.desc()).all()

    tasks_data = []
    for t in tasks:
        tasks_data.append({
            "id": t.id,
            "name": t.name,
            "task_type": t.task_type,
            "status": t.status,
            "progress": t.progress,
            "priority": t.priority,
            "error_message": t.error_message,
        })

    assets_data = []
    for a in assets:
        assets_data.append({
            "id": a.id,
            "task_id": a.task_id,
            "asset_type": a.asset_type,
            "title": a.title,
            "content": a.content,
            "file_url": a.file_url,
            "thumbnail_url": a.thumbnail_url,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })

    completed_tasks_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
    failed_tasks_count = sum(1 for t in tasks if t.status == TaskStatus.FAILED.value)
    remaining_tasks_count = len(tasks) - completed_tasks_count - failed_tasks_count
    
    current_task = next((t.name for t in tasks if t.status in [TaskStatus.RUNNING.value, TaskStatus.RETRYING.value]), None)
    
    # Simple estimation: 15 seconds per remaining task
    estimated_completion_seconds = remaining_tasks_count * 15

    return jsonify({
        "campaign": {
            "id": campaign.id,
            "title": campaign.title,
            "business_goal": campaign.business_goal,
            "target_audience": campaign.target_audience,
            "tone": campaign.tone,
            "industry": campaign.industry,
            "status": campaign.status,
            "progress": campaign.progress,
            "completed_tasks": completed_tasks_count,
            "failed_tasks": failed_tasks_count,
            "remaining_tasks": remaining_tasks_count,
            "current_task": current_task,
            "estimated_completion_seconds": estimated_completion_seconds,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None
        },
        "tasks": tasks_data,
        "assets": assets_data
    })


@campaigns_bp.route('/<int:campaign_id>/retry', methods=['POST'])
@login_required
def retry_campaign(campaign_id):
    """Retries all failed tasks for a campaign."""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    failed_tasks = CampaignTask.query.filter_by(campaign_id=campaign.id, status=TaskStatus.FAILED.value).all()
    for t in failed_tasks:
        t.status = TaskStatus.RETRYING.value
    db.session.commit()
    
    # Start executor in background
    from app import scheduler
    scheduler.add_job(
        id=f"execute_campaign_{campaign.id}_retry",
        func=workflow_executor.execute_campaign,
        args=[campaign.id]
    )
    
    return jsonify({"message": "Retrying failed tasks"}), 200


@campaigns_bp.route('/<int:campaign_id>/pause', methods=['POST'])
@login_required
def pause_campaign(campaign_id):
    """Pauses a running campaign."""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    if campaign.status == CampaignStatus.RUNNING.value:
        campaign.status = CampaignStatus.PAUSED.value
        db.session.commit()
        return jsonify({"message": "Campaign paused"}), 200
        
    return jsonify({"message": f"Cannot pause campaign in status {campaign.status}"}), 400


@campaigns_bp.route('/<int:campaign_id>/resume', methods=['POST'])
@login_required
def resume_campaign(campaign_id):
    """Resumes a paused campaign."""
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=current_user.id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
        
    if campaign.status == CampaignStatus.PAUSED.value:
        campaign.status = CampaignStatus.RUNNING.value
        db.session.commit()
        
        # Start executor in background
        from app import scheduler
        scheduler.add_job(
            id=f"execute_campaign_{campaign.id}_resume",
            func=workflow_executor.execute_campaign,
            args=[campaign.id]
        )
        
        return jsonify({"message": "Campaign resumed"}), 200
        
    return jsonify({"message": f"Cannot resume campaign in status {campaign.status}"}), 400

