import logging
from typing import List
from models import db, Campaign, CampaignTask, AssetType, TaskStatus, CampaignStatus

logger = logging.getLogger(__name__)

class WorkflowPlanner:
    """
    Decides the task order, assigns priorities, creates CampaignTask records,
    and sets status='pending'. Does NOT execute or generate content.
    """
    
    # Default ordered execution sequence
    TASK_SEQUENCE = [
        (AssetType.STRATEGY, "Campaign Strategy"),
        (AssetType.BLOG, "Blog Article"),
        (AssetType.FACEBOOK, "Facebook Post"),
        (AssetType.LINKEDIN, "LinkedIn Post"),
        (AssetType.X, "X (Twitter) Post"),
        (AssetType.NEWSLETTER, "Email Newsletter"),
        (AssetType.IMAGE, "Promotional Images"),
        (AssetType.VIDEO, "Promotional Video"),
        (AssetType.LANDING_PAGE, "Landing Page Copy")
    ]

    def create_plan(self, campaign: Campaign) -> List[CampaignTask]:
        """
        Creates the ordered tasks for the given campaign.
        """
        if campaign.status != CampaignStatus.PLANNING.value and campaign.status != CampaignStatus.DRAFT.value:
            logger.warning(f"Campaign {campaign.id} is already in status {campaign.status}. Skipping planning.")
            return []

        logger.info(f"Creating workflow plan for Campaign {campaign.id}")
        
        # Determine sequence (could be dynamic based on campaign.business_goal later)
        sequence = self.TASK_SEQUENCE

        tasks = []
        for index, (asset_type, name) in enumerate(sequence, start=1):
            task = CampaignTask(
                campaign_id=campaign.id,
                name=name,
                task_type=asset_type.value,
                status=TaskStatus.PENDING.value,
                priority=index, # 1 is highest priority in sequence
                progress=0
            )
            db.session.add(task)
            tasks.append(task)
            
        # Update Campaign status
        campaign.status = CampaignStatus.RUNNING.value
        db.session.commit()
        
        logger.info(f"Created {len(tasks)} tasks for Campaign {campaign.id}")
        return tasks

workflow_planner = WorkflowPlanner()
