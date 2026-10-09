# Deployment Guide (Afrigen V2)

## Prerequisites
- PostgreSQL database (e.g., Supabase, RDS).
- Redis (optional, if migrating background tasks from Threading to Celery in V3).
- Platform: Render, Heroku, or Railway.

## Environment Variables Required in Production
- `FLASK_APP=app.py`
- `FLASK_ENV=production`
- `SECRET_KEY`: A strong secret key.
- `DATABASE_URL`: Start with `postgresql://` (ensure the provider uses IPv4 or proper DNS resolution if applicable).

### AI Provider Keys
- `FAL_KEY_ID` / `FAL_KEY_SECRET`
- `GROQ_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`

## Deployment Steps
1. Push code to the production branch.
2. The platform will install dependencies via `requirements.txt`.
3. Pre-deploy command: `flask db upgrade` (Ensures all Sprint 12 and Sprint 13 migrations are applied).
4. Run command: `gunicorn -w 4 -b 0.0.0.0:8000 app:app` (or similar WSGI server).

## Post-Deployment Verification
- Verify the DB connection.
- Verify `support@afrigen.com.ng` is properly displayed in the footer.
- Test generating a small campaign to ensure the background executor works correctly in the production environment.

## Railway Deployment Note (Telegram Bot)
The `railway.json` file only defines the web start command. To run the full-featured Telegram bot on Railway, you must deploy a **second service** from the same repository with the start command `python bot/bot.py`. 
Ensure this second service has the same environment variables configured: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `FAL_KEY`, `GROQ_API_KEY`, and `SITE_URL`.
