from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, abort, session
)
from flask_login import login_required, current_user
from models import db, Generation, User, TelegramUser, SavedPrompt, Referral
from services.claude import refine_prompt, refine_image_prompt
from services.video import (
    generate_video,
    generate_video_from_image,
    generate_image as generate_ai_image   # aliased to avoid conflict with route name
)
from services.audio import generate_voiceover, generate_video_script
import os
import secrets
from datetime import date
from functools import wraps

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
    return render_template("main/index.html")


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
    add_voiceover = request.form.get('add_voiceover')
    aspect_ratio = request.form.get('aspect_ratio', '16:9')

    if not prompt:
        flash('Please enter a video idea!', 'danger')
        return redirect(url_for('main.dashboard'))

    refined = refine_prompt(prompt, style)

    if action == 'refine_only':
        return render_template(
            'main/result.html',
            original=prompt,
            refined=refined,
            video_url=None,
            audio_filename=None,
            style=style
        )

    # Daily limit for free users
    if current_user.plan == 'free':
        today = date.today()
        if current_user.last_credit_reset != today:
            current_user.daily_credits_used = 0
            current_user.last_credit_reset = today
            db.session.commit()
        if current_user.daily_credits_used >= 2:
            flash('You’ve used your 2 free videos today. Upgrade to Pro for unlimited!', 'warning')
            return redirect(url_for('main.dashboard'))
    elif current_user.plan == 'pro':
        pass
    else:
        flash('Your account is restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        result = generate_video(refined, style, aspect_ratio)
        if not result["success"]:
            raise Exception(result["error"])
        video_url = result["video_url"]
        if not video_url:
            raise Exception("No video URL returned")

        audio_filename = None
        if add_voiceover and current_user.plan == 'pro':
            script = generate_video_script(prompt, style)
            audio_filename = generate_voiceover(script)

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=video_url,
            audio_url=audio_filename,
            status="completed"
        )
        db.session.add(generation)

        if current_user.plan == 'free':
            current_user.daily_credits_used += 1

        db.session.commit()

        return render_template(
            'main/result.html',
            original=prompt,
            refined=refined,
            video_url=video_url,
            audio_filename=audio_filename,
            style=style
        )

    except Exception as e:
        db.session.rollback()
        print("VIDEO GENERATION ERROR:", str(e))
        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=None,
            audio_url=None,
            status="failed"
        )
        db.session.add(generation)
        db.session.commit()

        flash('Video generation is temporarily unavailable. Please try again later.', 'warning')
        return render_template(
            'main/result.html',
            original=prompt,
            refined=refined,
            video_url=None,
            audio_filename=None,
            style=style,
            error=None
        )


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

    if current_user.credits < 10:
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
            current_user.credits -= 10

        db.session.commit()

        return render_template(
            'main/result.html',
            original=prompt,
            refined=refined,
            video_url=video_url,
            audio_filename=None,
            style="cinematic"
        )

    except Exception as e:
        db.session.rollback()
        print("IMAGE-TO-VIDEO ERROR:", str(e))
        flash('Image-to-video generation failed. Please try again later.', 'danger')
        return redirect(url_for('main.dashboard'))
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

    if current_user.credits < 2:
        flash('Not enough credits! You need 2 credits to generate an image.', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        refined = refine_image_prompt(prompt, style)
        image = generate_ai_image(refined)

        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            image_url=image,
            generation_type="image",
            status="completed" if image else "failed"
        )
        db.session.add(generation)

        # Only deduct credits if image was generated
        if image:
            current_user.credits -= 2

        db.session.commit()

        return render_template(
            'main/image_result.html',
            original=prompt,
            refined=refined,
            image_url=image
        )

    except Exception as e:
        db.session.rollback()
        print("IMAGE GENERATION ERROR:", str(e))
        flash('Image generation failed. Please try again later.', 'danger')
        return redirect(url_for('main.dashboard'))


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
    users = User.query.order_by(User.created_at.desc()).all()
    generations = Generation.query.order_by(Generation.created_at.desc()).all()
    telegram_users = TelegramUser.query.order_by(TelegramUser.joined_at.desc()).all()

    total_users = User.query.count()
    total_generations = Generation.query.count()
    pro_users = User.query.filter_by(plan='pro').count()
    free_users = User.query.filter_by(plan='free').count()
    total_telegram = TelegramUser.query.count()

    return render_template(
        'main/admin.html',
        users=users,
        generations=generations,
        telegram_users=telegram_users,
        total_users=total_users,
        total_generations=total_generations,
        pro_users=pro_users,
        free_users=free_users,
        total_telegram=total_telegram
    )


@main.route('/admin/upgrade/<int:user_id>')
@admin_required
def upgrade_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.plan = 'pro'
        user.credits = 50
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
        current_user.credits = 50
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
    return render_template('main/referral.html',
                           referral_link=referral_link,
                           referral_code=referral.referral_code)


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