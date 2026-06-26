from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, abort, session, current_app
)
from flask_login import login_required, current_user
from models import db, Generation, User, TelegramUser, SavedPrompt, Referral, Payment
from sqlalchemy.exc import IntegrityError
from services.claude import refine_prompt, refine_image_prompt, extract_on_screen_text
from services.video import (
    generate_video,
    generate_video_async,
    generate_video_from_image,
    merge_audio_into_video,
    add_text_overlay,
    text_to_video_cost,
    generate_image as generate_ai_image   # aliased to avoid conflict with route name
)
# Premium Kling image-to-video is charged at the higher rate.
IMAGE_TO_VIDEO_COST = 10
from services.credits import (
    video_gate, image_gate, charge_video, charge_image, IMAGE_COST
)
from services.audio import generate_voiceover, generate_video_script
import os
import secrets
from datetime import date
from functools import wraps



def get_country_from_ip(ip):
    try:
        import requests as req
        response = req.get(f'https://ipapi.co/{ip}/json/', timeout=3)
        data = response.json()
        return data.get('country_name', 'Unknown')
    except:
        return 'Unknown'

def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr
def generate_referral_code():
    return secrets.token_urlsafe(8)


main = Blueprint("main", __name__)

# ---------- Admin authorization ----------
ADMIN_EMAILS = [
    email.strip().lower()
    for email in os.environ.get(
        "ADMIN_EMAILS",
        "oadedamola07@gmail.com"
    ).split(",")
]

def admin_required(func):
    @wraps(func)
    @login_required
    def decorated_view(*args, **kwargs):
        # Case‑insensitive admin check
        if current_user.email.lower() not in ADMIN_EMAILS:
            flash('Access denied!', 'danger')
            return redirect(url_for('main.dashboard'))
        return func(*args, **kwargs)
    return decorated_view


# ---------- File validation for image uploads ----------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- Routes ----------

@main.route("/")
def index():
    from models import Generation, User
    total_users = User.query.count()
    total_generations = Generation.query.filter_by(status='completed').count()
    return render_template("main/index.html",
        total_users=total_users,
        total_generations=total_generations
    )


@main.route("/dashboard")
@login_required
def dashboard():
    total_generations = Generation.query.filter_by(user_id=current_user.id).count()
    completed_generations = Generation.query.filter_by(
        user_id=current_user.id, status='completed'
    ).count()
    # Telegram linking status + bot handle for the "Connect Telegram" card.
    telegram_linked = TelegramUser.query.filter_by(user_id=current_user.id).first() is not None
    telegram_bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', '')
    return render_template(
        "main/dashboard.html",
        total_generations=total_generations,
        completed_generations=completed_generations,
        telegram_linked=telegram_linked,
        telegram_bot_username=telegram_bot_username,
    )


@main.route('/telegram/connect-code', methods=['POST'])
@login_required
def telegram_connect_code():
    """Issue a one-time code the user sends to the bot as `/link <code>`."""
    code = secrets.token_hex(3).upper()  # 6 hex chars, e.g. "A3F9C1"
    current_user.telegram_link_code = code
    db.session.commit()
    return jsonify({
        "success": True,
        "code": code,
        "bot_username": os.environ.get('TELEGRAM_BOT_USERNAME', ''),
    })


@main.route('/telegram/link-status')
@login_required
def telegram_link_status():
    """Poll target so the dashboard can confirm a successful bind in real time."""
    tg = TelegramUser.query.filter_by(user_id=current_user.id).first()
    return jsonify({
        "success": True,
        "linked": tg is not None,
        "telegram_username": tg.username if tg else None,
        "telegram_name": (tg.first_name if tg else None),
    })


@main.route('/generate', methods=['POST'])
@login_required
def generate():
    prompt = request.form.get('prompt')
    style = request.form.get('style', 'cinematic')
    action = request.form.get('action', 'generate')
    print("ACTION RECEIVED:", action)
    add_voiceover = request.form.get('add_voiceover')
    aspect_ratio = request.form.get('aspect_ratio', '16:9')

    if not prompt:
        flash('Please enter a video idea!', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        refined = refine_prompt(prompt, style)
    except Exception as e:
        print("REFINE ERROR:", str(e))
        return jsonify({"success": False, "error": "Could not refine your prompt right now. Please try again."})

    if action == 'refine_only':
        return jsonify({"success": True, "type": "refine_only", "refined": refined, "original": prompt})

    # Plan / credit gate (shared with the Telegram bot via services.credits).
    # Pro users get the premium 10s Kling model on supported styles, so we gate
    # against the extended cost.
    ok, error, _ = video_gate(current_user, style, extended=(current_user.plan == 'pro'))
    if not ok:
        return jsonify({"success": False, "error": error})

    try:
        if current_user.plan == 'free':
            style = 'cinematic'

        webhook_url = url_for('main.fal_webhook', _external=True)
        print("WEBHOOK URL:", webhook_url)
        # Pro users get the longer clip on styles that support it (anime/social),
        # and the premium 10s Kling model on cinematic/realistic/african.
        extended = (current_user.plan == 'pro')
        video_cost = text_to_video_cost(style, extended=extended)
        result = generate_video_async(refined, style, aspect_ratio, webhook_url=webhook_url, extended=extended)

        if not result["success"]:
            raise Exception(result["error"])

        # Voiceover is a Pro feature. We only remember the choice here; the
        # audio is generated later in the fal webhook, but only if the video
        # actually succeeds, so we never pay for a voiceover on a failed video.
        wants_voiceover = (add_voiceover == '1' and current_user.plan == 'pro')

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=None,
            wants_voiceover=wants_voiceover,
            status="processing",
            credit_cost=video_cost,
            fal_request_id=result["request_id"]
        )
        db.session.add(generation)

        if current_user.plan == 'free':
            current_user.monthly_videos_used += 1

        db.session.commit()

        return jsonify({
            "success": True,
            "type": "processing",
            "message": "Your video is being generated! You'll receive an email when it's ready.",
            "generation_id": generation.id
        })

    except Exception as e:
        db.session.rollback()
        print("VIDEO GENERATION ERROR:", str(e))
        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=None,
            status="failed"
        )
        db.session.add(generation)
        db.session.commit()
        return jsonify({"success": False, "error": "Video generation failed. Please try again."})

@main.route('/refine-prompt', methods=['POST'])
def refine_prompt_free():
    data = request.get_json() or {}
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    try:
        refined = refine_prompt(prompt, 'cinematic')
        return jsonify({"refined": refined})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route('/refine-image-prompt', methods=['POST'])
def refine_image_prompt_free():
    data = request.get_json() or {}
    prompt = data.get('prompt')
    style = data.get('style', 'realistic')
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    try:
        refined = refine_image_prompt(prompt, style)
        return jsonify({"refined": refined})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route('/generate-from-image', methods=['POST'])
@login_required
def generate_from_image():
    if current_user.plan != 'pro':
        flash('Image to Video is a Pro feature!', 'danger')
        return redirect(url_for('main.dashboard'))

    if current_user.credits < IMAGE_TO_VIDEO_COST:
        flash(f'You need at least {IMAGE_TO_VIDEO_COST} credits for image-to-video!', 'danger')
        return redirect(url_for('main.dashboard'))

    prompt = request.form.get('prompt')
    image_file = request.files.get('image')
    if not prompt or not image_file:
        flash('Please provide both image and prompt!', 'danger')
        return redirect(url_for('main.dashboard'))

    # Pro users choose clip length via the dashboard dropdown (5s or 10s).
    duration = request.form.get('duration', '5')
    if duration not in ('5', '10'):
        duration = '5'

    # Honour the form's aspect-ratio dropdown instead of forcing 16:9.
    aspect_ratio = request.form.get('aspect_ratio', '16:9')
    if aspect_ratio not in ('16:9', '9:16', '1:1'):
        aspect_ratio = '16:9'

    # Validate file extension
    if not allowed_file(image_file.filename):
        flash('Invalid image format. Allowed: png, jpg, jpeg, webp.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        # Preserve original extension
        ext = image_file.filename.rsplit('.', 1)[1].lower()
        filename = f"temp_{os.urandom(8).hex()}.{ext}"
        filepath = os.path.join("static", "uploads", filename)
        os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
        image_file.save(filepath)

        image_url = url_for('static', filename=f'uploads/{filename}', _external=True)
        refined = refine_image_prompt(prompt, "cinematic")
        video_url = generate_video_from_image(image_url, refined, duration=duration, aspect_ratio=aspect_ratio)

        # Video models render text badly, so burn any words the user asked to
        # show on screen onto the finished clip (best-effort; falls back to the
        # raw video on failure).
        if video_url:
            video_url = add_text_overlay(video_url, extract_on_screen_text(prompt))

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=video_url,
            image_url=image_url,
            generation_type="image",
            status="completed" if video_url else "failed",
            credit_cost=IMAGE_TO_VIDEO_COST,
        )
        db.session.add(generation)

        # Only deduct credits if video generation succeeded
        if video_url:
            current_user.credits -= IMAGE_TO_VIDEO_COST

        db.session.commit()

        return jsonify(
            {"success": True, "type": "video", "video_url": video_url, "refined": refined, "original": prompt,
             "style": "cinematic", "generation_id": generation.id, "share_url": share_url_for(generation.id)})

    except Exception as e:
        db.session.rollback()
        print("IMAGE-TO-VIDEO ERROR:", str(e))
        return jsonify({"success": False, "error": "Image-to-video failed. Please try again."})
    finally:
        # Clean up temp file
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)


@main.route('/generate-image', methods=['POST'])
@login_required
def generate_image():
    prompt = request.form.get('prompt')
    style = request.form.get('style', 'realistic')
    aspect_ratio = request.form.get('aspect_ratio', '1:1')
    if aspect_ratio not in ('1:1', '16:9', '9:16'):
        aspect_ratio = '1:1'

    if not prompt:
        flash('Please enter an image idea!', 'danger')
        return redirect(url_for('main.dashboard'))

    # Plan / credit gate (shared with the Telegram bot via services.credits).
    ok, error = image_gate(current_user)
    if not ok:
        return jsonify({"success": False, "error": error})

    try:
        refined = refine_image_prompt(prompt, style)
        result = generate_ai_image(refined, style, aspect_ratio)

        if not result["success"]:
            raise Exception(result["error"])

        image = result["image_url"]

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            image_url=image,
            generation_type="image",
            status="completed" if image else "failed"
        )
        db.session.add(generation)

        if image:
            charge_image(current_user)

        db.session.commit()

        return jsonify({"success": True, "type": "image", "image_url": image, "refined": refined, "original": prompt,
                        "generation_id": generation.id, "share_url": share_url_for(generation.id)})

    except Exception as e:
        db.session.rollback()
        print("IMAGE GENERATION ERROR:", str(e))
        return jsonify({"success": False, "error": "Image generation failed. Please try again."})


@main.app_template_global('share_url_for')
def share_url_for(gen_id):
    """Build the public, signed share URL for a generation (used in templates)."""
    from services.share import make_share_token
    return url_for('main.public_share', token=make_share_token(gen_id), _external=True)


@main.route('/v/<token>')
def public_share(token):
    """Public, no-login page for a single completed generation: shows the clip/
    image with a 'make your own free' signup CTA, so every shared link converts
    instead of dead-ending on a raw media file. Token is signed (services.share)
    so generation IDs can't be enumerated."""
    from services.share import load_share_token
    gen_id = load_share_token(token)
    if gen_id is None:
        abort(404)
    gen = Generation.query.get(gen_id)
    if not gen or gen.status != 'completed' or not (gen.video_url or gen.image_url):
        abort(404)
    return render_template('main/share.html', gen=gen)


@main.route('/result/video')
@login_required
def video_result():
    return render_template('main/result.html',
        video_url=request.args.get('video_url', ''),
        original=request.args.get('original', ''),
        refined=request.args.get('refined', ''),
        style=request.args.get('style', ''),
        audio_url=request.args.get('audio_url')
    )

@main.route('/result/image')
@login_required
def image_result():
    return render_template('main/image_result.html',
        image_url=request.args.get('image_url', ''),
        original=request.args.get('original', ''),
        refined=request.args.get('refined', ''),
        share_url=request.args.get('share_url', '')
    )

@main.route('/history')
@login_required
def history():
    generations = Generation.query.filter_by(
        user_id=current_user.id
    ).order_by(Generation.created_at.desc()).all()
    return render_template('main/history.html', generations=generations)


@main.route('/admin')
@admin_required
def admin():
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from collections import Counter

    users = User.query.order_by(User.created_at.desc()).all()
    generations = Generation.query.order_by(Generation.created_at.desc()).all()
    telegram_users = TelegramUser.query.order_by(TelegramUser.joined_at.desc()).all()

    total_users = User.query.count()
    total_generations = Generation.query.count()
    pro_users = User.query.filter_by(plan='pro').count()
    free_users = User.query.filter_by(plan='free').count()
    banned_users = User.query.filter_by(plan='banned').count()
    total_telegram = TelegramUser.query.count()

    # Generation stats
    completed_generations = Generation.query.filter_by(status='completed').count()
    failed_generations = Generation.query.filter_by(status='failed').count()
    video_generations = Generation.query.filter(
        Generation.status == 'completed',
        Generation.image_url == None
    ).count()
    image_generations = Generation.query.filter(
        Generation.generation_type == 'image',
        Generation.status == 'completed'
    ).count()
    success_rate = round((completed_generations / total_generations * 100) if total_generations > 0 else 0)

    # Last 7 days signups
    signups_7days = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        count = User.query.filter(
            func.date(User.created_at) == day
        ).count()
        signups_7days.append({"day": day.strftime('%a'), "count": count})

    # Last 7 days generations
    generations_7days = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        count = Generation.query.filter(
            func.date(Generation.created_at) == day
        ).count()
        generations_7days.append({"day": day.strftime('%a'), "count": count})

    # Top 5 most active users
    top_users = db.session.query(
        User, func.count(Generation.id).label('gen_count')
    ).join(Generation).group_by(User.id).order_by(
        func.count(Generation.id).desc()
    ).limit(5).all()

    # Country breakdown
    country_counts = Counter(
        u.country for u in users if u.country and u.country != 'Unknown'
    )
    top_countries = country_counts.most_common(5)

    # Source breakdown
    source_counts = Counter(
        u.signup_source for u in users if u.signup_source
    )
    source_breakdown = dict(source_counts)

    return render_template(
        'main/admin.html',
        users=users,
        generations=generations,
        telegram_users=telegram_users,
        total_users=total_users,
        total_generations=total_generations,
        pro_users=pro_users,
        free_users=free_users,
        banned_users=banned_users,
        total_telegram=total_telegram,
        completed_generations=completed_generations,
        failed_generations=failed_generations,
        video_generations=video_generations,
        image_generations=image_generations,
        success_rate=success_rate,
        signups_7days=signups_7days,
        generations_7days=generations_7days,
        top_users=top_users,
        top_countries=top_countries,
        source_breakdown=source_breakdown
    )


@main.route('/admin/upgrade/<int:user_id>')
@admin_required
def upgrade_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.plan = 'pro'
        user.credits = 100
        db.session.commit()
        try:
            from services.email import send_pro_upgrade_email
            send_pro_upgrade_email(user.email, user.username)
        except Exception as e:
            print(f"Email error: {e}")
        flash(f'{user.username} upgraded to Pro!', 'success')
    return redirect(url_for('main.admin'))


@main.route('/admin/downgrade/<int:user_id>')
@admin_required
def downgrade_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.plan = 'free'
        user.credits = 10
        db.session.commit()
        flash(f'{user.username} downgraded to Free!', 'warning')
    return redirect(url_for('main.admin'))


@main.route('/admin/ban/<int:user_id>')
@admin_required
def ban_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.plan = 'banned'
        user.credits = 0
        db.session.commit()
        flash(f'{user.username} has been banned!', 'warning')
    return redirect(url_for('main.admin'))


@main.route('/admin/delete/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        Generation.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User deleted successfully!', 'danger')
    return redirect(url_for('main.admin'))


# ---------- Payments ----------
import requests as http_requests

@main.route('/upgrade')
def upgrade():
    # Public so logged-out visitors can see pricing (transparency). The actual
    # payment forms are still gated — anonymous users get a sign-up CTA instead.
    return render_template('main/upgrade.html',
                           paystack_public_key=os.environ.get('PAYSTACK_PUBLIC_KEY'))


@main.route('/payment/initialize', methods=['POST'])
@login_required
def initialize_payment():
    amount = 500000
    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }
    data = {
        "email": current_user.email,
        "amount": amount,
        "callback_url": url_for('main.payment_callback', _external=True),
        "metadata": {"user_id": current_user.id, "username": current_user.username}
    }
    response = http_requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers, json=data
    )
    result = response.json()
    if result['status']:
        return redirect(result['data']['authorization_url'])
    else:
        flash('Payment initialization failed!', 'danger')
        return redirect(url_for('main.upgrade'))


@main.route('/payment/initialize/annual', methods=['POST'])
@login_required
def initialize_payment_annual():
    amount = 5000000
    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }
    data = {
        "email": current_user.email,
        "amount": amount,
        "callback_url": url_for('main.payment_callback', _external=True),
        "metadata": {"user_id": current_user.id, "plan": "annual"}
    }
    response = http_requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers, json=data
    )
    result = response.json()
    if result['status']:
        return redirect(result['data']['authorization_url'])
    else:
        flash('Payment initialization failed!', 'danger')
        return redirect(url_for('main.upgrade'))


@main.route('/payment/callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        flash('Payment reference not found!', 'danger')
        return redirect(url_for('main.upgrade'))

    headers = {"Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"}
    response = http_requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )
    result = response.json()
    data = result.get('data', {}) if result.get('status') else {}
    amount = data.get('amount')

    # Verify payment status, payer email, metadata user_id, AND that the amount
    # is one we actually charge (so the tier can't be downgraded by paying less).
    verified = (
        result.get('status')
        and data.get('status') == 'success'
        and data.get('customer', {}).get('email') == current_user.email
        and str((data.get('metadata') or {}).get('user_id')) == str(current_user.id)
        and amount in (500000, 5000000)
    )

    if not verified:
        flash('Payment verification failed!', 'danger')
        return redirect(url_for('main.upgrade'))

    # Idempotency: each Paystack reference may grant credits exactly once.
    # Without this, revisiting an old successful callback URL would refill
    # credits for free (Paystack keeps returning "success" for the reference).
    if Payment.query.filter_by(reference=reference).first():
        flash('This payment has already been applied. ⭐', 'info')
        return redirect(url_for('main.dashboard'))

    # Tier is derived from the verified amount, not the (spoofable) metadata.
    is_annual = amount == 5000000
    current_user.plan = 'pro'
    current_user.credits = 1200 if is_annual else 100
    db.session.add(Payment(
        user_id=current_user.id,
        reference=reference,
        amount=amount,
        plan='annual' if is_annual else 'monthly'
    ))

    try:
        db.session.commit()
    except IntegrityError:
        # Reference was recorded concurrently (e.g. the webhook beat us to it).
        db.session.rollback()
        flash('This payment has already been applied. ⭐', 'info')
        return redirect(url_for('main.dashboard'))

    try:
        from services.email import send_pro_upgrade_email
        send_pro_upgrade_email(current_user.email, current_user.username)
    except Exception as e:
        print(f"Email error: {e}")
    flash('Payment successful! Welcome to Pro! ⭐', 'success')
    return redirect(url_for('main.dashboard'))


# ---------- Downloads with ad gate ----------
@main.route('/download/<int:generation_id>')
@login_required
def download_video(generation_id):
    generation = Generation.query.get_or_404(generation_id)
    if generation.user_id != current_user.id:
        abort(403)

    if not generation.video_url:
        flash('Video not available.', 'danger')
        return redirect(url_for('main.history'))

    if current_user.plan == 'pro':
        return redirect(generation.video_url)

    if not generation.ad_watched:
        return redirect(url_for('main.watch_ad', generation_id=generation.id))

    return redirect(generation.video_url)


@main.route('/watch-ad/<int:generation_id>')
@login_required
def watch_ad(generation_id):
    generation = Generation.query.get_or_404(generation_id)
    if generation.user_id != current_user.id:
        abort(403)

    # Set a session token to prove the user actually visited the ad page
    session[f'ad_started_{generation.id}'] = True
    return render_template('main/watch_ad.html', generation=generation)


@main.route('/unlock-download/<int:generation_id>', methods=['POST'])
@login_required
def unlock_download(generation_id):
    generation = Generation.query.get_or_404(generation_id)
    if generation.user_id != current_user.id:
        abort(403)

    # Pro users should not be here; redirect them directly to download
    if current_user.plan == 'pro':
        return redirect(url_for('main.download_video', generation_id=generation.id))

    # Verify the user came from the ad page
    if not session.pop(f'ad_started_{generation.id}', None):
        abort(403)

    generation.ad_watched = True
    db.session.commit()
    return redirect(url_for('main.download_video_file', generation_id=generation.id))


# ---------- Saved prompts, referrals, contact, docs ----------
@main.route('/save-prompt', methods=['POST'])
@login_required
def save_prompt():
    data = request.get_json() or {}
    saved = SavedPrompt(
        user_id=current_user.id,
        original_prompt=data.get('original'),
        refined_prompt=data.get('refined'),
        prompt_type=data.get('type', 'video'),
        style=data.get('style', 'cinematic')
    )
    db.session.add(saved)
    db.session.commit()
    return jsonify({"success": True, "message": "Prompt saved!"})


@main.route('/saved-prompts')
@login_required
def saved_prompts():
    prompts = SavedPrompt.query.filter_by(
        user_id=current_user.id
    ).order_by(SavedPrompt.created_at.desc()).all()
    return render_template('main/saved_prompts.html', prompts=prompts)


@main.route('/referral')
@login_required
def referral():
    referral = Referral.query.filter_by(
        referrer_id=current_user.id, is_used=False
    ).first()
    if not referral:
        referral = Referral(
            referrer_id=current_user.id,
            referral_code=generate_referral_code()
        )
        db.session.add(referral)
        db.session.commit()

    referral_link = url_for('auth.register', ref=referral.referral_code, _external=True)

    # Get all successful referrals
    used_referrals = Referral.query.filter_by(
        referrer_id=current_user.id,
        is_used=True
    ).all()

    # Get referred users
    referred_users = []
    for r in used_referrals:
        if r.referred_id:
            from models import User
            user = User.query.get(r.referred_id)
            if user:
                referred_users.append({
                    "username": user.username,
                    "joined": user.created_at.strftime('%b %d, %Y'),
                    "plan": user.plan
                })

    total_referrals = len(used_referrals)
    credits_earned = total_referrals * 2

    return render_template('main/referral.html',
        referral_link=referral_link,
        referral_code=referral.referral_code,
        referred_users=referred_users,
        total_referrals=total_referrals,
        credits_earned=credits_earned
    )


@main.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        try:
            from services.email import send_contact_email
            send_contact_email(name, email, message)
            flash('Message sent successfully!', 'success')
        except Exception as e:
            print(f"Contact email error: {e}")
            flash('Message received! We will get back to you soon.', 'success')
        return redirect(url_for('main.contact'))
    return render_template('main/contact.html')


@main.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        rating = request.form.get('rating')
        feedback_text = request.form.get('feedback')
        feature = request.form.get('feature')
        try:
            from services.email import send_feedback_email
            send_feedback_email(
                current_user.email if current_user.is_authenticated else 'Anonymous',
                rating, feedback_text, feature
            )
            flash('Thank you for your feedback! 🙏', 'success')
        except Exception as e:
            print(f"Feedback email error: {e}")
            flash('Thank you for your feedback! 🙏', 'success')
        return redirect(url_for('main.feedback'))
    return render_template('main/feedback.html')


@main.route('/docs')
def docs():
    return render_template('main/docs.html')


@main.route('/blog')
def blog():
    from services.blog import get_all_posts
    return render_template('main/blog.html', posts=get_all_posts())


@main.route('/blog/<slug>')
def blog_post(slug):
    from services.blog import get_post
    post = get_post(slug)
    if not post:
        abort(404)
    return render_template('main/blog_post.html', post=post)


# ---------- Blog draft review (admin only) ----------

@main.route('/admin/blog')
@admin_required
def admin_blog():
    from services.blog import get_drafts, get_all_posts
    return render_template(
        'main/blog_admin.html',
        drafts=get_drafts(),
        published=get_all_posts(),
    )


@main.route('/admin/blog/generate', methods=['POST'])
@admin_required
def admin_blog_generate():
    """Generate ONE blog draft on demand (same code path as the daily 7am
    scheduler). Mirrors /admin/newsletter/generate so the admin never has to wait
    for the cron job — they can produce a draft to review whenever they want."""
    from services.blog import run_daily_draft_generation
    try:
        draft = run_daily_draft_generation()
    except Exception as e:
        current_app.logger.exception("Blog draft generation failed")
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'id': draft.id, 'title': draft.title, 'slug': draft.slug})


@main.route('/admin/blog/publish/<int:post_id>', methods=['POST'])
@admin_required
def admin_blog_publish(post_id):
    from services.blog import get_post_by_id, publish_post
    post = get_post_by_id(post_id)
    if not post:
        abort(404)
    publish_post(post)
    flash(f'Published "{post.title}" — it is now live on the blog.', 'success')

    # Fire the content distribution GitHub Action asynchronously so the admin
    # doesn't wait. One failure here (e.g. no token configured) is non-fatal —
    # the manual workflow_dispatch is always available as a fallback.
    _trigger_distribution_async(f"https://afrigen.com.ng/blog/{post.slug}")

    return redirect(url_for('main.admin_blog'))


@main.route('/admin/blog/edit/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def admin_blog_edit(post_id):
    from services.blog import get_post_by_id, update_post
    post = get_post_by_id(post_id)
    if not post:
        abort(404)
    if request.method == 'POST':
        update_post(
            post,
            title=request.form.get('title', ''),
            description=request.form.get('description', ''),
            body=request.form.get('body', ''),
            tag=request.form.get('tag', ''),
            read_time=request.form.get('read_time', ''),
        )
        flash(f'Saved changes to "{post.title}".', 'success')
        return redirect(url_for('main.admin_blog'))
    return render_template('main/blog_edit.html', post=post)


@main.route('/admin/blog/discard/<int:post_id>', methods=['POST'])
@admin_required
def admin_blog_discard(post_id):
    from services.blog import get_post_by_id, discard_post
    post = get_post_by_id(post_id)
    if not post:
        abort(404)
    title = post.title
    discard_post(post)
    flash(f'Discarded draft "{title}".', 'warning')
    return redirect(url_for('main.admin_blog'))


# ---------- Content Distribution (admin only) ----------

@main.route('/admin/facebook/trigger', methods=['POST'])
@admin_required
def admin_facebook_trigger():
    """Manually trigger the daily Facebook automation engine."""
    from services.facebook_engine import run_daily_facebook_engine
    try:
        result = run_daily_facebook_engine()
        if result.get('ok'):
            flash('Facebook daily post triggered successfully!', 'success')
        else:
            flash(f"Facebook trigger failed: {result.get('error')}", 'danger')
    except Exception as e:
        current_app.logger.exception("Facebook engine trigger failed")
        flash(f"Facebook engine error: {str(e)}", 'danger')
    return redirect(url_for('main.admin'))


@main.route('/admin/distribution')
@admin_required
def admin_distribution():
    """Distribution dashboard — all runs + per-post status."""
    from services.distribution import get_all_runs
    from services.blog import get_all_posts
    runs = get_all_runs(limit=30)
    published = get_all_posts()
    return render_template(
        'main/distribution.html',
        runs=runs,
        published=published,
    )


@main.route('/admin/distribution/trigger/<int:post_id>', methods=['POST'])
@admin_required
def admin_distribution_trigger(post_id):
    """Trigger distribution for a published blog post. Returns JSON for the
    async frontend flow (button → spinner → results)."""
    from services.distribution import trigger_distribution
    try:
        run_id = trigger_distribution(post_id)
        return jsonify({"ok": True, "run_id": run_id})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        current_app.logger.exception("Distribution trigger failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@main.route('/admin/distribution/run/<int:run_id>')
@admin_required
def admin_distribution_run(run_id):
    """AJAX endpoint: return a single run's status as JSON (polled by the UI)."""
    from services.distribution import get_run
    run = get_run(run_id)
    if not run:
        abort(404)
    post = run.blog_post
    results = []
    for r in run.results:
        results.append({
            "platform": r.platform,
            "ok": r.ok,
            "error": r.error,
            "post_url": r.post_url,
        })
    return jsonify({
        "ok": True,
        "run": {
            "id": run.id,
            "status": run.status,
            "total_platforms": run.total_platforms,
            "success_count": run.success_count,
            "fail_count": run.fail_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "post": {
                "id": post.id,
                "title": post.title,
                "slug": post.slug,
                "url": f"https://afrigen.com.ng/blog/{post.slug}",
            } if post else None,
            "results": results,
        },
    })


@main.route('/admin/distribution/retry/<int:run_id>/<platform>', methods=['POST'])
@admin_required
def admin_distribution_retry(run_id, platform):
    """Retry a single failed platform within a run."""
    from services.distribution import retry_platform
    try:
        ok = retry_platform(run_id, platform)
        return jsonify({"ok": ok})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        current_app.logger.exception("Distribution retry failed")
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------- Analytics ----------
@main.route('/analytics')
@login_required
def analytics():
    from sqlalchemy import func
    from datetime import datetime, timedelta

    total = Generation.query.filter(
        Generation.user_id == current_user.id,
        Generation.status.in_(['completed', 'failed'])
    ).count()

    completed = Generation.query.filter_by(
        user_id=current_user.id, status='completed'
    ).count()

    failed = Generation.query.filter_by(
        user_id=current_user.id, status='failed'
    ).count()

    videos = Generation.query.filter(
        Generation.user_id == current_user.id,
        Generation.status == 'completed',
        Generation.image_url == None
    ).count()

    images = Generation.query.filter(
        Generation.user_id == current_user.id,
        Generation.status == 'completed',
        Generation.generation_type == 'image',
        Generation.image_url != None,
        Generation.video_url == None
    ).count()

    # Last 7 days activity
    seven_days = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        count = Generation.query.filter(
            Generation.user_id == current_user.id,
            Generation.status.in_(['completed', 'failed']),
            func.date(Generation.created_at) == day
        ).count()
        seven_days.append({"day": day.strftime('%a'), "count": count})

    return render_template('main/analytics.html',
        total=total,
        completed=completed,
        failed=failed,
        videos=videos,
        images=images,
        success_rate=round((completed / total * 100) if total > 0 else 0),
        seven_days=seven_days,
        style_map={}
    )


@main.route('/terms')
def terms():
    return render_template('main/terms.html')

@main.route('/privacy')
def privacy():
    return render_template('main/privacy.html')

@main.route('/founder')
def founder():
    return render_template('main/founder.html')


# ---------- Pre-launch waitlist (/launch) ----------

@main.route('/launch')
def launch():
    # Retired after launch via LAUNCH_ACTIVE=false — send visitors to the live site.
    if not current_app.config.get('LAUNCH_ACTIVE', True):
        return redirect(url_for('main.index'))
    from models import Subscriber
    count = Subscriber.query.count()
    # Where the "Join Launch Event" button sends people once they subscribe.
    launch_link = os.environ.get('LAUNCH_LINK') or url_for('auth.register')
    return render_template('main/launch.html', count=count, launch_link=launch_link)


@main.route('/launch/subscribe', methods=['POST'])
def launch_subscribe():
    if not current_app.config.get('LAUNCH_ACTIVE', True):
        abort(404)
    from models import Subscriber
    from services.email import send_launch_confirmation

    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    newsletter = bool(data.get('newsletter'))

    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email are required.'}), 400

    launch_link = os.environ.get('LAUNCH_LINK') or url_for('auth.register')

    existing = Subscriber.query.filter_by(email=email).first()
    if existing:
        # Idempotent: re-subscribing just confirms they're already on the list.
        return jsonify({'success': True, 'link': launch_link, 'already': True})

    subscriber = Subscriber(name=name, email=email, newsletter=newsletter)
    db.session.add(subscriber)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': True, 'link': launch_link, 'already': True})

    send_launch_confirmation(email, name)
    return jsonify({'success': True, 'link': launch_link})


@main.route('/launch/count')
def launch_count():
    if not current_app.config.get('LAUNCH_ACTIVE', True):
        abort(404)
    from models import Subscriber
    return jsonify({'count': Subscriber.query.count()})


@main.route('/launch/admin')
@admin_required
def launch_admin():
    return render_template('main/launch_admin.html')


@main.route('/launch/admin/data')
@admin_required
def launch_admin_data():
    from models import Subscriber
    subscribers = Subscriber.query.order_by(Subscriber.created_at.asc()).all()
    return jsonify([
        {
            'name': s.name,
            'email': s.email,
            'newsletter': s.newsletter,
            'date': s.created_at.isoformat() if s.created_at else None,
        }
        for s in subscribers
    ])


@main.route('/launch/admin/export')
@admin_required
def launch_admin_export():
    import csv
    import io
    from models import Subscriber
    from flask import Response

    subscribers = Subscriber.query.order_by(Subscriber.created_at.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'email', 'newsletter', 'date'])
    for s in subscribers:
        writer.writerow([
            s.name,
            s.email,
            'yes' if s.newsletter else 'no',
            s.created_at.isoformat() if s.created_at else '',
        ])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=subscribers.csv'},
    )


@main.route('/launch/admin/newsletter', methods=['POST'])
@admin_required
def launch_admin_newsletter():
    from models import Subscriber
    from services.email import send_newsletter

    data = request.get_json(silent=True) or request.form
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()

    if not body:
        return jsonify({'sent': 0, 'error': 'Newsletter body is required.'}), 400

    recipients = [
        (s.email, s.name)
        for s in Subscriber.query.filter_by(newsletter=True).all()
        if s.email
    ]
    if not recipients:
        return jsonify({'sent': 0, 'message': 'No newsletter subscribers to send to.'})

    sent = send_newsletter(recipients, subject, body)
    return jsonify({'sent': sent})


# ---------- Weekly auto-generated newsletter ----------

@main.route('/admin/newsletter')
@admin_required
def admin_newsletter():
    from services.newsletter import get_current_draft, audience_size
    from models import NewsletterIssue

    draft = get_current_draft()
    last_sent = (
        NewsletterIssue.query.filter_by(status='sent')
        .order_by(NewsletterIssue.sent_at.desc())
        .first()
    )
    return render_template(
        'main/newsletter_admin.html',
        draft=draft,
        last_sent=last_sent,
        audience=audience_size(),
    )


@main.route('/admin/newsletter/generate', methods=['POST'])
@admin_required
def admin_newsletter_generate():
    from services.newsletter import run_weekly_generation
    try:
        issue = run_weekly_generation()
    except Exception as e:
        current_app.logger.exception("Newsletter generation failed")
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'subject': issue.subject, 'body': issue.body})


@main.route('/admin/newsletter/save', methods=['POST'])
@admin_required
def admin_newsletter_save():
    from services.newsletter import get_current_draft, create_draft, save_draft

    data = request.get_json(silent=True) or request.form
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()

    draft = get_current_draft()
    if draft is None:
        draft = create_draft(subject, body, auto_generated=False)
    else:
        save_draft(draft, subject, body)
    return jsonify({'ok': True, 'id': draft.id, 'status': draft.status})


@main.route('/admin/newsletter/approve', methods=['POST'])
@admin_required
def admin_newsletter_approve():
    from services.newsletter import get_current_draft, create_draft, approve_draft

    data = request.get_json(silent=True) or request.form
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()

    draft = get_current_draft()
    if draft is None:
        draft = create_draft(subject, body, auto_generated=False)
    if not (body or draft.body):
        return jsonify({'ok': False, 'error': 'Nothing to approve — the draft is empty.'}), 400

    approve_draft(draft, subject=subject, body=body)
    return jsonify({'ok': True, 'id': draft.id, 'status': draft.status})


@main.route('/admin/newsletter/send', methods=['POST'])
@admin_required
def admin_newsletter_send():
    from services.newsletter import get_current_draft, create_draft, save_draft, send_issue

    data = request.get_json(silent=True) or request.form
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()

    # Persist whatever is currently in the editor before sending.
    draft = get_current_draft()
    if draft is None:
        draft = create_draft(subject, body, auto_generated=False)
    elif subject or body:
        save_draft(draft, subject, body)

    if not draft.body:
        return jsonify({'ok': False, 'error': 'Newsletter body is empty.'}), 400

    try:
        sent = send_issue(draft)
    except Exception as e:
        current_app.logger.exception("Newsletter send failed")
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'sent': sent})


@main.route('/unsubscribe/<token>')
def unsubscribe(token):
    from services.email import verify_unsub_token
    from models import EmailOptOut

    email = verify_unsub_token(token)
    if not email:
        return render_template('main/unsubscribe.html', ok=False, email=None), 400

    email = email.lower()
    if not EmailOptOut.query.filter_by(email=email).first():
        db.session.add(EmailOptOut(email=email))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return render_template('main/unsubscribe.html', ok=True, email=email)


def _cron_authorized():
    secret = current_app.config.get('CRON_SECRET')
    return bool(secret) and request.args.get('key') == secret


def _trigger_distribution_async(blog_url: str):
    """Fire the GitHub Actions content distribution workflow via repository_dispatch.

    This runs in a background thread so the admin's publish flow returns
    immediately.  If the token isn't configured or GitHub is unreachable, the
    failure is logged but never surfaced to the admin — the manual
    workflow_dispatch is always available as a fallback.
    """
    import threading
    import requests as req

    token = os.environ.get("GITHUB_DISPATCH_TOKEN", "")
    if not token:
        print("[distribute] GITHUB_DISPATCH_TOKEN not set — skipping automatic trigger.")
        return

    def _fire():
        try:
            resp = req.post(
                "https://api.github.com/repos/Al-ameenolanrewaju/Afrigen/dispatches",
                json={
                    "event_type": "distribute_blog",
                    "client_payload": {"blog_url": blog_url},
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
            if resp.status_code == 204:
                print(f"[distribute] ✅ workflow triggered for {blog_url}")
            else:
                print(f"[distribute] ⚠️ GitHub dispatch returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[distribute] ⚠️ GitHub dispatch failed (non-fatal): {e}")

    threading.Thread(target=_fire, daemon=True).start()


# ---------- Cron endpoints (key-protected) ----------


@main.route('/cron/newsletter/generate', methods=['POST', 'GET'])
def cron_newsletter_generate():
    if not _cron_authorized():
        abort(403)
    from services.newsletter import run_weekly_generation
    issue = run_weekly_generation()
    return jsonify({'ok': True, 'issue_id': issue.id})


@main.route('/cron/newsletter/weekly', methods=['POST', 'GET'])
def cron_newsletter_weekly():
    if not _cron_authorized():
        abort(403)
    from services.newsletter import run_weekly_send
    sent = run_weekly_send()
    return jsonify({'ok': True, 'sent': sent})


@main.route('/f3dd6d35491e4a168ba565d6e14ccffc.txt')
def indexnow_key():
    return 'f3dd6d35491e4a168ba565d6e14ccffc', 200, {'Content-Type': 'text/plain'}


def submit_to_indexnow(urls):
    payload = {
        "host": "afrigen.com.ng",
        "key": "f3dd6d35491e4a168ba565d6e14ccffc",
        "keyLocation": "https://afrigen.com.ng/f3dd6d35491e4a168ba565d6e14ccffc.txt",
        "urlList": urls
    }
    http_requests.post(
        "https://api.indexnow.org/indexnow",
        json=payload
    )

@main.route('/payment/webhook', methods=['POST'])
def payment_webhook():
    import hmac
    import hashlib

    paystack_secret = os.environ.get('PAYSTACK_SECRET_KEY')
    signature = request.headers.get('x-paystack-signature')
    body = request.get_data()

    expected = hmac.new(
        paystack_secret.encode('utf-8'),
        body,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        return '', 400

    data = request.get_json()

    if data.get('event') == 'charge.success':
        charge = data.get('data', {})
        reference = charge.get('reference')
        user_id = (charge.get('metadata') or {}).get('user_id')
        amount = charge.get('amount')
        user = User.query.get(user_id) if user_id else None

        # Grant exactly once per reference (shared with payment_callback), and
        # derive the tier from the amount Paystack actually charged.
        if (
            user
            and reference
            and amount in (500000, 5000000)
            and not Payment.query.filter_by(reference=reference).first()
        ):
            is_annual = amount == 5000000
            user.plan = 'pro'
            user.credits = 1200 if is_annual else 100
            db.session.add(Payment(
                user_id=user.id,
                reference=reference,
                amount=amount,
                plan='annual' if is_annual else 'monthly'
            ))
            try:
                db.session.commit()
            except IntegrityError:
                # payment_callback recorded it first; nothing more to do.
                db.session.rollback()
                return '', 200
            try:
                from services.email import send_pro_upgrade_email
                send_pro_upgrade_email(user.email, user.username)
            except Exception as e:
                print(f"Email error: {e}")

    return '', 200

@main.route('/fal/webhook', methods=['POST'])
def fal_webhook():
    data = request.get_json()
    print("FAL WEBHOOK RECEIVED:", data)

    request_id = data.get('request_id')
    if not request_id:
        return '', 400

    generation = Generation.query.filter_by(fal_request_id=request_id).first()
    if not generation:
        return '', 404

    if data.get('status') == 'ERROR':
        generation.status = 'failed'
        db.session.commit()
        return '', 200

    video_url = None
    if data.get('payload') and data['payload'].get('video'):
        video_url = data['payload']['video'].get('url')

    if video_url:
        # Idempotency: fal retries the webhook if it thinks the first call
        # failed (e.g. a slow response). Don't re-charge credits or resend the
        # email if we've already processed this completion.
        if generation.status == 'completed':
            return '', 200

        generation.video_url = video_url
        generation.status = 'completed'

        # Deduct credits only on success
        user = User.query.get(generation.user_id)
        if user:
            charge_video(user, generation.credit_cost)
            if user.plan == 'pro' and user.credits <= 5:
                try:
                    from services.email import send_credits_low_email
                    send_credits_low_email(user.email, user.username, user.credits)
                except Exception as e:
                    print(f"Email error: {e}")

        # Persist completion + credit charge BEFORE the slow voiceover/merge
        # step, so a webhook retry hits the idempotency guard above instead of
        # double-charging. The video is marked ready against the raw URL first.
        db.session.commit()

        # Voiceover + merge: best-effort and slower (script + TTS + ffmpeg), and
        # only run after the video actually succeeded, so we never pay for it on
        # a failed generation. When it works, the narration is baked into the
        # video and generation.video_url is upgraded to the merged clip; on any
        # failure we keep the raw (silent) video as a valid fallback.
        if generation.wants_voiceover and not generation.audio_url:
            try:
                vo_script = generate_video_script(generation.original_prompt)
                audio_url = generate_voiceover(vo_script)
                generation.audio_url = audio_url
                if audio_url:
                    merged = merge_audio_into_video(video_url, audio_url)
                    if merged:
                        generation.video_url = merged
                db.session.commit()
            except Exception as e:
                print("VOICEOVER ERROR:", str(e))

        # Burn any requested on-screen words onto the final clip (after voiceover
        # merge, so the caption sits on top of the delivered video). Best-effort:
        # add_text_overlay returns the unchanged URL on any failure.
        try:
            on_screen = extract_on_screen_text(generation.original_prompt)
            if on_screen:
                captioned = add_text_overlay(generation.video_url, on_screen)
                if captioned and captioned != generation.video_url:
                    generation.video_url = captioned
                    db.session.commit()
        except Exception as e:
            print("TEXT OVERLAY ERROR:", str(e))

        # Email last, linking the final (merged, when available) video. Videos
        # without voiceover skip the block above, so their email still goes
        # out promptly.
        try:
            from services.email import send_video_ready_email
            send_video_ready_email(user.email, user.username,
                                   generation.original_prompt, generation.video_url)
        except Exception as e:
            print(f"Email error: {e}")
    else:
        generation.status = 'failed'
        db.session.commit()

    return '', 200

@main.route('/download/video/<int:generation_id>')
@login_required
def download_video_file(generation_id):
    generation = Generation.query.get_or_404(generation_id)
    if generation.user_id != current_user.id:
        abort(403)
    if not generation.video_url:
        flash('Video not available.', 'danger')
        return redirect(url_for('main.history'))

    # Free users must watch an ad before downloading. Pro users skip the gate.
    if current_user.plan == 'free' and not generation.ad_watched:
        return redirect(url_for('main.watch_ad', generation_id=generation.id))

    # Stream the video file from FAL
    response = http_requests.get(generation.video_url, stream=True)
    from flask import Response
    return Response(
        response.iter_content(chunk_size=8192),
        content_type='video/mp4',
        headers={'Content-Disposition': f'attachment; filename="afrigen-video-{generation_id}.mp4"'}
    )


@main.route('/download/image/<int:generation_id>')
@login_required
def download_image_file(generation_id):
    generation = Generation.query.get_or_404(generation_id)
    if generation.user_id != current_user.id:
        abort(403)
    if not generation.image_url:
        flash('Image not available.', 'danger')
        return redirect(url_for('main.history'))

    response = http_requests.get(generation.image_url, stream=True)
    from flask import Response
    return Response(
        response.iter_content(chunk_size=8192),
        content_type='image/jpeg',
        headers={'Content-Disposition': f'attachment; filename="afrigen-image-{generation_id}.jpg"'}
    )