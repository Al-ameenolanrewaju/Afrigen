# Afrigen V2

Afrigen V2 is an AI-powered marketing and campaign generation platform designed to automate the creation of high-quality marketing assets including strategies, blogs, newsletters, social media posts, images, videos, and voiceovers.

## Features

- **Campaign Engine**: Automatically sequence and generate entire marketing campaigns using AI.
- **Provider Manager**: Robust integration with multiple AI providers (OpenAI, Anthropic, Fal AI, Gemini) with built-in fallbacks.
- **Workflow Executor**: Background processing of AI generation tasks with automated retry mechanisms.
- **Asset Library**: Centralized storage for all generated text, images, video, and audio assets.

## Core Technologies

- **Backend**: Python 3.13, Flask, SQLAlchemy (PostgreSQL).
- **Frontend**: HTML5, Bootstrap 5, Vanilla JavaScript.
- **Background Jobs**: Threading / APScheduler.
- **AI Integrations**: ProviderManager routing, Fal AI (Video/Image).

## Environment Variables

Ensure the following are set in your `.env`:
- `SECRET_KEY`: Flask secret key.
- `DATABASE_URL`: PostgreSQL connection string (Supabase).
- `FAL_KEY_ID` / `FAL_KEY_SECRET`: Credentials for Fal AI (Image/Video).
- `GROQ_API_KEY`: Credentials for Groq (Llama).
- `ANTHROPIC_API_KEY`: Credentials for Claude (Prompt Refinement).
- `OPENAI_API_KEY` (Optional)

## Local Development

1. Create a virtual environment: `python -m venv venv`
2. Activate it: `.\venv\Scripts\Activate.ps1`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up the database: `flask db upgrade`
5. Run the server: `flask run`
