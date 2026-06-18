# Afrigen — Code Analysis

## What it is
Afrigen is an **AI content-generation platform** ("Africa Creates, AI Generates") built in
**Python with Flask**. Users sign up on a website, type a prompt, and the app generates
**videos and images** with AI — plus there's a **Telegram bot** that does prompt refinement
and generation from chat.

## Tech stack
- **Backend:** Python + Flask
- **Database:** SQLAlchemy ORM with Alembic migrations (SQLite locally, Postgres in production)
- **Auth:** Flask-Login + Google OAuth (Authlib)
- **Frontend:** Jinja2 HTML templates + CSS/JS (no separate framework)
- **Background jobs:** APScheduler (monthly credit resets, weekly newsletters)
- **External AI/services:** Groq (LLaMA 3.3 for prompt refinement), fal.ai (video/image
  generation), ElevenLabs (AI voiceover), Paystack (payments), Gmail SMTP (email),
  Telegram Bot API

## How the code is organized
The project follows a clean, layered structure — each part has one job:

```
app.py            -> app setup, scheduler, Telegram webhook
config.py         -> all settings/secrets from environment variables
models.py         -> database tables (9 models)
routes/           -> web endpoints (URLs)
  |- main.py      -> core app: generate, dashboard, admin, payments
  |- auth.py      -> register, login, Google OAuth, password reset
  |- api.py       -> API status
services/         -> business logic, separated from routes
  |- claude.py    -> prompt refinement
  |- video.py     -> video generation
  |- audio.py     -> voiceover
  |- credits.py   -> credit/billing rules
  |- email.py     -> emails
  |- newsletter.py-> weekly newsletter
bot/bot.py        -> the standalone Telegram bot
templates/        -> all the HTML pages
migrations/       -> database version history
```

This separation (**routes -> services -> models**) is good practice: the URLs stay thin,
and the real logic lives in `services/`.

## The data model (9 tables)
- **User** — accounts, plan (free/pro), credits, usage limits, ban status, Telegram link code
- **Generation** — every video/image job, its status, cost, and result URL
- **Payment** — Paystack transactions (with replay protection)
- **TelegramUser** — Telegram accounts linked to website accounts so they **share one credit balance**
- **SavedPrompt, Subscriber, NewsletterIssue, EmailOptOut, Referral** — supporting features

## Key features (the app is fairly complete — ~60 endpoints)
1. **AI generation** — video, image, image-to-video, with style choices
2. **Credits & plans** — free tier with daily/monthly limits, Pro plan, "watch an ad to unlock download"
3. **Payments** — Paystack monthly + annual, with webhook verification
4. **Telegram bot** — refines prompts and generates content, sharing the user's website credits
5. **Admin panel** — upgrade/ban/delete users, view analytics
6. **Marketing** — pre-launch waitlist, referrals, automated weekly newsletter
   (auto-generated Saturday, sent Monday)
7. **Email** — password reset, contact, newsletters with unsubscribe

## Strengths
- Clean separation of concerns (routes vs. services vs. models)
- Secrets kept out of code, loaded from environment variables
- Database migrations are tracked properly
- Thoughtful billing safeguards (unique payment references prevent double-crediting;
  credit cost recorded per job)
- Production-ready touches: logging with rotation, error pages (403/404/500), scheduled jobs

## Next improvements (honest weak points)
- `app.py` contains a **second, duplicate Telegram bot** — the real one lives in `bot/bot.py`,
  so this is dead/confusing code worth removing
- `routes/main.py` is **~1,400 lines** — it could be split into smaller files
  (payments, admin, newsletter)
- `SECRET_KEY` has a hardcoded fallback — fine for dev, should be required in production
- No real tests yet (`test_afrigen.py` is empty)

## How to present this
1. **What it does** (the platform + bot)
2. **The stack** (Flask, SQLAlchemy, the AI services)
3. **How it's organized** (the routes -> services -> models layering)
4. **The main features**
5. **What you'd improve next** — this shows maturity and that you understand your own
   code's tradeoffs.
