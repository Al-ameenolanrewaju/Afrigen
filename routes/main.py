from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, abort, session
)
from flask_login import login_required, current_user
from models import db, Generation, User, TelegramUser, SavedPrompt, Referral
from services.claude import refine_prompt, refine_image_prompt
from services.video import (
    generate_video,
    generate_video_async,
    generate_video_from_image,
    generate_image as generate_ai_image   # aliased to avoid conflict with route name
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
    return render_template(
        "main/dashboard.html",
        total_generations=total_generations,
        completed_generations=completed_generations
    )


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

    refined = refine_prompt(prompt, style)

    if action == 'refine_only':
        return jsonify({"success": True, "type": "refine_only", "refined": refined, "original": prompt})

    # Plan checks
    if current_user.plan == 'free':
        from datetime import date
        today = date.today()
        if current_user.last_video_reset is None or current_user.last_video_reset.month != today.month:
            current_user.monthly_videos_used = 0
            current_user.last_video_reset = today
            db.session.commit()
        if current_user.monthly_videos_used >= 3:
            return jsonify({"success": False,
                            "error": "You have used your 3 free videos this month. Upgrade to Pro for unlimited!"})
    elif current_user.plan == 'pro':
        if current_user.credits < 5:
            return jsonify({"success": False,
                            "error": "Not enough credits! Please renew your Pro plan at afrigen.com.ng/upgrade"})
    else:
        flash('Your account is restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        if current_user.plan == 'free':
            style = 'cinematic'

        webhook_url = url_for('main.fal_webhook', _external=True)
        result = generate_video_async(refined, style, aspect_ratio, webhook_url=webhook_url)

        if not result["success"]:
            raise Exception(result["error"])

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=None,
            status="processing",
            fal_request_id=result["request_id"]
        )
        db.session.add(generation)

        if current_user.plan == 'free':
            current_user.monthly_videos_used += 1
        elif current_user.plan == 'pro':
            current_user.credits -= 5
            if current_user.credits <= 5:
                try:
                    from services.email import send_credits_low_email
                    send_credits_low_email(current_user.email, current_user.username, current_user.credits)
                except Exception as e:
                    print(f"Email error: {e}")
            if current_user.credits < 0:
                current_user.credits = 0

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

    if current_user.credits < 5:
        flash('You need at least 10 credits for image-to-video!', 'danger')
        return redirect(url_for('main.dashboard'))

    prompt = request.form.get('prompt')
    image_file = request.files.get('image')
    if not prompt or not image_file:
        flash('Please provide both image and prompt!', 'danger')
        return redirect(url_for('main.dashboard'))

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
        video_url = generate_video_from_image(image_url, refined)

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=video_url,
            image_url=image_url,
            generation_type="image",
            status="completed" if video_url else "failed",
        )
        db.session.add(generation)

        # Only deduct credits if video generation succeeded
        if video_url:
            current_user.credits -= 5

        db.session.commit()

        return jsonify(
            {"success": True, "type": "video", "video_url": video_url, "refined": refined, "original": prompt,
             "style": "cinematic"})

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

    if not prompt:
        flash('Please enter an image idea!', 'danger')
        return redirect(url_for('main.dashboard'))

    # Free user limit
    if current_user.plan == 'free':
        from datetime import date
        today = date.today()
        if current_user.last_image_reset is None or current_user.last_image_reset.month != today.month:
            current_user.monthly_images_used = 0
            current_user.last_image_reset = today
            db.session.commit()
        if current_user.monthly_images_used >= 2:
            return jsonify({"success": False,
                            "error": "You have used your 2 free images this month. Upgrade to Pro!"})

    # Pro user credit check
    if current_user.plan == 'pro':
        if current_user.credits < 2:
            return jsonify({"success": False,
                            "error": "Not enough credits! Please renew your Pro plan."})

    try:
        refined = refine_image_prompt(prompt, style)
        result = generate_ai_image(refined, style)

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
            if current_user.plan == 'free':
                current_user.monthly_images_used += 1
            elif current_user.plan == 'pro':
                current_user.credits -= 2

        db.session.commit()

        return jsonify({"success": True, "type": "image", "image_url": image, "refined": refined, "original": prompt})

    except Exception as e:
        db.session.rollback()
        print("IMAGE GENERATION ERROR:", str(e))
        return jsonify({"success": False, "error": "Image generation failed. Please try again."})


@main.route('/result/video')
@login_required
def video_result():
    return render_template('main/result.html',
        video_url=request.args.get('video_url', ''),
        original=request.args.get('original', ''),
        refined=request.args.get('refined', ''),
        style=request.args.get('style', ''),
        audio_filename=None
    )

@main.route('/result/image')
@login_required
def image_result():
    return render_template('main/image_result.html',
        image_url=request.args.get('image_url', ''),
        original=request.args.get('original', ''),
        refined=request.args.get('refined', '')
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
@login_required
def upgrade():
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

    # Verify payment status, payer email, AND metadata user_id
    if (
        result['status']
        and result['data']['status'] == 'success'
        and result['data']['customer']['email'] == current_user.email
        and str(result['data']['metadata']['user_id']) == str(current_user.id)
    ):
        current_user.plan = 'pro'
        current_user.credits = 100
        db.session.commit()
        try:
            from services.email import send_pro_upgrade_email
            send_pro_upgrade_email(current_user.email, current_user.username)
        except Exception as e:
            print(f"Email error: {e}")
        flash('Payment successful! Welcome to Pro! ⭐', 'success')
        return redirect(url_for('main.dashboard'))
    else:
        flash('Payment verification failed!', 'danger')
        return redirect(url_for('main.upgrade'))


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
    return redirect(url_for('main.download_video', generation_id=generation.id))


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

@main.route('/generate-image', methods=['POST'])
@login_required
def generate_image_route():
    prompt = request.form.get('prompt')
    style = request.form.get('style', 'realistic')
    aspect_ratio = request.form.get('aspect_ratio', '1:1')

    if not prompt:
        flash('Please enter an image prompt!', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        result = generate_image(
            prompt,
            style,
            aspect_ratio
        )

        if not result["success"]:
            raise Exception(result["error"])

        image_url = result["image_url"]

        return render_template(
            'main/image_result.html',
            prompt=prompt,
            image_url=image_url,
            style=style
        )

    except Exception as e:
        print("IMAGE GENERATION ERROR:", e)

        flash(
            'Image generation failed. Try again later.',
            'warning'
        )

        return redirect(url_for('main.dashboard'))


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

    if data['event'] == 'charge.success':
        user_id = data['data']['metadata'].get('user_id')
        user = User.query.get(user_id)
        if user and user.plan != 'pro':
            user.plan = 'pro'
            user.credits = 100
            db.session.commit()
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

    # Find generation by request_id
    generation = Generation.query.filter_by(fal_request_id=request_id).first()
    if not generation:
        return '', 404

    # Get video URL from webhook payload
    video_url = None
    if data.get('payload') and data['payload'].get('video'):
        video_url = data['payload']['video'].get('url')

    if video_url:
        generation.video_url = video_url
        generation.status = 'completed'
        db.session.commit()

        # Send email notification
        try:
            user = User.query.get(generation.user_id)
            from services.email import send_video_ready_email
            send_video_ready_email(
                user.email,
                user.username,
                generation.original_prompt,
                video_url
            )
        except Exception as e:
            print(f"Email error: {e}")
    else:
        generation.status = 'failed'
        db.session.commit()

    return '', 200