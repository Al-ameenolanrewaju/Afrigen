# Afrigen V2 - Comprehensive Technical Audit & Upgrade Roadmap

## 1. Overview & Current Architecture
Afrigen V2 is an AI marketing automation platform serving African and global creators. It generates marketing strategies, social media copy, image assets, and videos using multi-model AI routing (Groq, Claude, OpenAI, Fal AI, Hugging Face).

### Core Components
- **Web Layer**: Flask application (`app.py`, `routes/`).
- **Database & State**: PostgreSQL managed via SQLAlchemy and Flask-Migrate (Alembic).
- **Background Tasks**: APScheduler in-app cron jobs + webhook worker threads.
- **Telegram Bot**: Python-telegram-bot worker interface (`bot/bot.py`).
- **Media Engine**: Fal AI (Kling / AnimateDiff / LTX) + local FFmpeg rendering.

---

## 2. Completed Upgrades & Features

### A. Free Video Allowance for Free Users (Admin-Controlled)
- Added `free_video_allowance` column to `User` model with Alembic migration (`s7b8c9d0e1f2`).
- Updated `video_gate`, `charge_video`, and `refund_video` in `services/credits.py` to allow free-tier users with active allowance to generate videos at 0 credits.
- Added one-click **`+ Video`** action button and allowance badges to `/admin` and `/admin/credits`.

### B. Telegram Voice Note Prompting (Groq Whisper)
- Built `transcribe_voice_note(audio_file_path)` in `services/audio.py` powered by Groq's high-speed `whisper-large-v3` API.
- Implemented `handle_voice` in `bot/bot.py` (`filters.VOICE | filters.AUDIO`):
  1. User records a voice note in Telegram.
  2. Bot downloads the `.ogg` clip and transcribes dialect/accent into text prompt.
  3. Displays transcribed prompt back to the user and begins video/photo generation automatically.

### C. Automatic Free Video Watermarking (Viral Engine)
- Built `add_watermark_to_video()` in `services/video.py` using FFmpeg `drawtext`.
- Automatically overlays a subtle `"Made with Afrigen.com.ng"` badge on videos produced by free users across both Web and Telegram Bot.
- Pro users receive clean, watermark-free videos.
- Best-effort execution: returns original URL on any FFmpeg error so watermarking never corrupts user generation.

### D. Test Suite & Developer Tooling Modernization
- Configured `pytest.ini` with `testpaths = tests`.
- Added `pytest-asyncio` and `requirements-dev.txt`.
- Result: **16/16 tests passing green in ~6.4 seconds**.

### E. Database Migrations, Concurrency & CI/CD
- Tracked all migration history in Git (`migrations/versions/`).
- Added atomic credit decrement in `services/credits.py`.
- Added `Dockerfile`, `docker-compose.yml`, and GitHub Actions CI workflow.

---

## 3. Recommended Future Roadmap

1. **Pay-as-You-Go Credit Micro-Bundles via Paystack** (e.g., ₦1,500 for 10 credits).
2. **Automated Referral Rewards** (grant +1 free video allowance when an invited friend signs up).
3. **Modular Blueprint Decomposition** (`routes/admin.py`, `routes/generator.py`, `routes/billing.py`).
