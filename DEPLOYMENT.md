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
- `NEWSLETTER_TEST_RECIPIENT` (optional): Redirect newsletter batches to your email provider's approved testing address. Leave unset to send to subscribers.

### AI Provider Keys
- `FAL_KEY_ID` / `FAL_KEY_SECRET`
- `GROQ_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`

## Deployment Steps
1. Push code to the production branch.
2. The platform will install dependencies via `requirements.txt`.
3. Pre-deploy command: `flask db upgrade` (Applies all pending database migrations).
4. Run command: `gunicorn -w 4 -b 0.0.0.0:8000 app:app` (or similar WSGI server).

## Post-Deployment Verification
- Verify the DB connection.
- Verify `support@afrigen.com.ng` is properly displayed in the footer.
- Test generating a small campaign to ensure the background executor works correctly in the production environment.

## Railway Deployment Note
The `railway.json` file defines the web start command for the app service. Keep the deployment environment aligned with the app's required variables, and avoid adding a second bot worker unless you intentionally reintroduce a separate Telegram integration.
