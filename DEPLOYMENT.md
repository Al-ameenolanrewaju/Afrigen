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

The application logs a warning naming any missing full-capability variables at
startup. The following integrations are required for their corresponding
features:

- `GROQ_API_KEY`: assistant and content-generation flows.
- `FAL_KEY`: image/video generation.
- `HF_TOKEN`: Hugging Face image-generation integration.
- `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY`: payments.

### Other Integration Keys
- `ELEVENLABS_API_KEY`: optional voice integration.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET`: Telegram integration.
- Google OAuth client ID/secret and SMTP credentials when those features are enabled.

## Deployment Steps
1. Provide the required production environment variables and a persistent PostgreSQL database.
2. The platform installs dependencies from `requirements.txt`.
3. Run `flask db upgrade` once as the release/pre-deploy step, before routing traffic to the new release. Do not run migrations independently in every web replica.
4. Start the web service with `gunicorn app:app --workers 1 --threads 8 --timeout 180`. The single web process owns the in-process scheduler; keep `ENABLE_SCHEDULER=true` on one process only.
5. Configure the platform readiness probe to use `/healthz`. It returns only a generic database dependency status and does not expose connection details.

The Docker image excludes local environment files, credentials, database files,
logs, test data, and local uploads. For a container deployment, run the image's
`flask db upgrade` command once as a release step, then start the web container.
Media written to `static/uploads` is local to the container by default. Configure
a persistent mounted volume at that path or integrate durable object storage
before relying on locally rendered Movie Studio exports or generated promo
assets in a production deployment.

## Post-Deployment Verification
- Verify the DB connection.
- Verify `support@afrigen.com.ng` is properly displayed in the footer.
- Test generating a small campaign to ensure the background executor works correctly in the production environment.

## Railway Deployment Note
The `railway.json` file defines the pre-deploy migration and web start commands.
Telegram is integrated into the Flask web application; the obsolete standalone
bot process entry has been removed because its target script is not present.
