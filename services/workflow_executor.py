import logging
import time
from datetime import datetime, timezone
from models import db, Campaign, CampaignTask, CampaignAsset, TaskStatus, CampaignStatus, AssetType
from services.provider_manager import provider_manager
from services.claude import refine_prompt, refine_image_prompt
from services.video import generate_image, generate_video, generate_video_from_image
from services.audio import generate_voiceover

logger = logging.getLogger(__name__)

class WorkflowExecutor:
    """
    Reads CampaignTask records, executes pending tasks sequentially,
    updates progress, saves generated assets, records provider used,
    and continues after recoverable failures.
    """
    
    MAX_RETRIES = 3

    def execute_campaign(self, campaign_id: int):
        """
        Executes pending or retrying tasks for a given campaign sequentially.
        """
        from app import app
        with app.app_context():
            campaign = db.session.get(Campaign, campaign_id)
            if not campaign:
                logger.error(f"Campaign {campaign_id} not found.")
                return
                
            logger.info(f"Starting execution for Campaign {campaign_id}")

            # Fetch tasks sorted by priority (1 is highest)
            # Skip COMPLETED or CANCELED tasks.
            tasks = CampaignTask.query.filter(
                CampaignTask.campaign_id == campaign_id,
                CampaignTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RETRYING.value, TaskStatus.FAILED.value])
            ).order_by(CampaignTask.priority.asc()).all()

            for task in tasks:
                task.status = TaskStatus.QUEUED.value
            db.session.commit()

            for task in tasks:
                if task.status == TaskStatus.QUEUED.value:
                    self._execute_task(campaign, task)
                
            self._update_campaign_progress(campaign)
            
            logger.info(f"Execution run finished for Campaign {campaign_id}")

    def _execute_task(self, campaign: Campaign, task: CampaignTask):
        """
        Executes a single task.
        """
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Executing task: {task.name} (Type: {task.task_type}) for Campaign {campaign.id}")
        
        prompt = self._build_prompt(campaign, task)
        messages = [
            {"role": "system", "content": "You are an expert marketing and campaign strategist. Output high-quality, professional content as requested."},
            {"role": "user", "content": prompt}
        ]
        
        success = False
        error_msg = None
        result_text = ""
        file_url = None
        thumbnail_url = None
        provider_used = "ProviderManager"
        start_time = time.time()
        
        retry_count = 0
        while retry_count < self.MAX_RETRIES and not success:
            try:
                if task.task_type == AssetType.IMAGE.value:
                    refined = refine_image_prompt(prompt)
                    res = generate_image(refined)
                    if isinstance(res, dict) and res.get("success") is False:
                        raise Exception(res.get("error"))
                    file_url = res.get("url") if isinstance(res, dict) else res
                    result_text = refined
                    provider_used = "Fal (Image)"
                elif task.task_type == AssetType.VIDEO.value:
                    refined = refine_prompt(prompt)
                    res = generate_video(refined)
                    if isinstance(res, dict) and res.get("success") is False:
                        raise Exception(res.get("error"))
                    file_url = res.get("url") if isinstance(res, dict) else res
                    result_text = refined
                    provider_used = "Fal (Video)"
                elif task.task_type == AssetType.VOICE.value:
                    res = generate_voiceover(prompt)
                    file_url = res
                    result_text = prompt
                    provider_used = "AudioService"
                else:
                    # Text based generation via ProviderManager
                    result_text = provider_manager.generate_text("Campaign", messages)
                    
                success = True
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                logger.warning(f"Task {task.name} failed (Attempt {retry_count}/{self.MAX_RETRIES}): {error_msg}")
                time.sleep(2)
        
        generation_time = time.time() - start_time
        
        if success:
            task.provider = provider_used
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.now(timezone.utc)
            task.progress = 100
            task.error_message = None
            
            asset = CampaignAsset(
                campaign_id=campaign.id,
                task_id=task.id,
                asset_type=task.task_type,
                title=f"{campaign.title or 'Campaign'} - {task.name}",
                content=result_text,
                file_url=file_url,
                thumbnail_url=thumbnail_url,
                provider_used=provider_used,
                generation_time=generation_time
            )
            db.session.add(asset)
            logger.info(f"Task {task.name} completed successfully.")
        else:
            task.status = TaskStatus.FAILED.value
            task.error_message = error_msg
            logger.error(f"Task {task.name} failed permanently.")
            
        db.session.commit()
        
        if success:
            platform_map = {
                AssetType.FACEBOOK.value: "facebook",
                AssetType.LINKEDIN.value: "linkedin",
                AssetType.X.value: "x",
            }
            target_provider = platform_map.get(task.task_type)
            if target_provider:
                from models import ConnectedAccount, UserContent, PublishingRetryQueue
                account = ConnectedAccount.query.filter_by(user_id=campaign.user_id, provider=target_provider).first()
                if account:
                    logger.info(f"Auto-publishing {task.name} to {target_provider} for Campaign {campaign.id}")
                    user_content = UserContent(
                        user_id=campaign.user_id,
                        content_type=task.task_type,
                        title=f"{campaign.title or 'Campaign'} - {task.name}",
                        body=result_text,
                        file_url=file_url,
                        thumbnail_url=thumbnail_url,
                        status="draft",
                        source="campaign"
                    )
                    db.session.add(user_content)
                    db.session.commit()
                    
                    queue_item = PublishingRetryQueue(
                        user_id=campaign.user_id,
                        content_id=user_content.id,
                        provider=target_provider,
                        status="pending"
                    )
                    db.session.add(queue_item)
                    db.session.commit()
        
        # Flush progress after each task
        self._update_campaign_progress(campaign)

    def _build_prompt(self, campaign: Campaign, task: CampaignTask) -> str:
        """
        Builds a task-specific prompt using campaign metadata.
        """
        base_context = (
            f"Campaign Goal: {campaign.business_goal}\n"
            f"Target Audience: {campaign.target_audience}\n"
            f"Tone: {campaign.tone}\n"
            f"Industry: {campaign.industry}\n\n"
        )
        
        instruction = f"Please generate content for: {task.name}."
        
        if task.task_type == AssetType.STRATEGY.value:
            instruction = "Draft a comprehensive marketing strategy addressing the campaign goal, identifying key messaging pillars, and proposing a high-level timeline."
        elif task.task_type == AssetType.BLOG.value:
            instruction = "Write a highly engaging, SEO-optimized blog article related to the campaign goal. Include an eye-catching title, introduction, body paragraphs, and conclusion."
        elif task.task_type == AssetType.FACEBOOK.value:
            instruction = "Write a Facebook post designed to maximize engagement (likes/comments/shares). Include relevant emojis and a clear Call To Action."
        elif task.task_type == AssetType.LINKEDIN.value:
            instruction = "Write a professional, insightful LinkedIn post. Focus on thought leadership, industry value, and professional networking."
        elif task.task_type == AssetType.X.value:
            instruction = "Write a concise, punchy post for X (Twitter). Include a hook, main point, and relevant hashtags. Keep it under 280 characters."
        elif task.task_type == AssetType.NEWSLETTER.value:
            instruction = "Draft an email newsletter. Include a compelling subject line, a personalized greeting placeholder, engaging body copy, and a clear call to action."
        elif task.task_type == AssetType.IMAGE.value:
            instruction = "Write 3 detailed image generation prompts that visually represent the campaign goal and tone."
        elif task.task_type == AssetType.VIDEO.value:
            instruction = "Write a short promotional video script, including visual descriptions (b-roll) and voiceover text."
        elif task.task_type == AssetType.LANDING_PAGE.value:
            instruction = "Write compelling landing page copy. Include a Hero Headline, Subheadline, 3 Key Benefits, and a Primary Call To Action."

        return f"{base_context}{instruction}"

    def _update_campaign_progress(self, campaign: Campaign):
        """
        Phase 5: Progress Tracking
        Updates the campaign's overall progress percentage and status.
        """
        tasks = CampaignTask.query.filter_by(campaign_id=campaign.id).all()
        if not tasks:
            return
            
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
        failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED.value)
        
        # Calculate overall percentage based purely on completed tasks vs total
        percentage = int((completed_tasks / total_tasks) * 100)
        campaign.progress = percentage
        
        if completed_tasks == total_tasks:
            campaign.status = CampaignStatus.COMPLETED.value
        elif failed_tasks > 0 and (completed_tasks + failed_tasks) == total_tasks:
            campaign.status = CampaignStatus.FAILED.value
            
        db.session.commit()

workflow_executor = WorkflowExecutor()
