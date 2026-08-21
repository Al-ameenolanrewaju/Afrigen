# Afrigen V2 - Architecture

## High-Level Overview

Afrigen V2 is a monolithic Flask application structured with a Service Layer pattern to decouple core business logic from API routes.

## Core Components

1. **Routes (`routes/`)**: Handles incoming HTTP requests, session management, and rendering templates.
2. **Models (`models.py`)**: Defines the SQLAlchemy ORM mapping for the database (PostgreSQL).
3. **Services (`services/`)**: The core business logic layer.
   - `provider_manager.py`: The single point of entry for text-based AI generation. Routes requests to specific AI models based on task mapping and health checks.
   - `workflow_planner.py`: Generates sequential tasks for a marketing campaign.
   - `workflow_executor.py`: Asynchronously executes campaign tasks and records progress.
   - `video.py`, `audio.py`, `claude.py`: Specific integration layers for Fal AI and Anthropic.
4. **Templates (`templates/`)**: Jinja2 HTML templates.

## The Campaign Engine Flow
1. User requests a campaign in `routes/campaigns.py`.
2. `Campaign` model is created.
3. `workflow_planner` creates `CampaignTask` records.
4. `workflow_executor` starts in a background thread, picking up `pending` or `retrying` tasks.
5. The executor determines the `AssetType` and routes to the appropriate service (e.g. `video.py` for Images/Video, `provider_manager.py` for Text).
6. Successes are saved as `CampaignAsset` and task progress is updated in real-time.
