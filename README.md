# Afrigen V2

Afrigen V2 is an AI-powered marketing and campaign generation platform designed to automate the creation of high-quality marketing assets including strategies, blogs, newsletters, social media posts, images, videos, and voiceovers.

## Features

- **Campaign Engine**: Automatically sequence and generate entire marketing campaigns using AI.
- **AI Orchestration**: Server-side task routing, provider adapters, and fallbacks; infrastructure choices remain private to Afrigen.
- **Workflow Executor**: Background processing of AI generation tasks with automated retry mechanisms.
- **Asset Library**: Centralized storage for all generated text, images, video, and audio assets.

## Core Technologies

- **Backend**: Python 3.13, Flask, SQLAlchemy (PostgreSQL).
- **Frontend**: HTML5, Bootstrap 5, Vanilla JavaScript.
- **Background Jobs**: Threading / APScheduler.
- **AI Integrations**: Backend-only generation services configured through private deployment settings.

## Environment Variables

Set application secrets in your private deployment environment. Never place
provider credentials in templates, JavaScript, or other browser-delivered files.

The application requires:
- `SECRET_KEY`: Flask secret key.
- `DATABASE_URL`: PostgreSQL connection string (Supabase).
- AI service credentials as defined by the private operations configuration.

## Local Development

1. Create a virtual environment: `python -m venv venv`
2. Activate it: `.\venv\Scripts\Activate.ps1`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up the database: `flask db upgrade`
5. Run the server: `flask run`
