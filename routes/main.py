from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Generation, User, TelegramUser, SavedPrompt, Referral
from services.claude import refine_prompt, refine_image_prompt
from services.video import generate_video
from flask import jsonify
from services.audio import generate_voiceover, generate_video_script
import os
from services.video import generate_video_from_image
from services.video import generate_image
import secrets

def generate_referral_code():
    return secrets.token_urlsafe(8)


main = Blueprint("main", __name__)

@main.route("/")
def index():
    return render_template("main/index.html")


@main.route("/dashboard")
@login_required
def dashboard():
    # Get real stats
    total_generations = Generation.query.filter_by(
        user_id=current_user.id
    ).count()

    completed_generations = Generation.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).count()

    return render_template("main/dashboard.html",
                           total_generations=total_generations,
                           completed_generations=completed_generations)

@main.route('/generate', methods=['POST'])
@login_required
def generate():

    prompt = request.form.get('prompt')
    style = request.form.get('style', 'cinematic')
    action = request.form.get('action', 'generate')
    add_voiceover = request.form.get('add_voiceover')
    aspect_ratio = request.form.get('aspect_ratio', '16:9')

    print(f"Prompt: {prompt}")
    print(f"Style: {style}")
    print(f"Action: {action}")

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

    if current_user.credits <= 0:
        flash('No credits remaining! Upgrade to Pro.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:

        # Generate actual video
        result = generate_video(
            refined,
            style,
            aspect_ratio
        )

        print("VIDEO RESULT:", result)

        if not result["success"]:
            raise Exception(result["error"])

        video_url = result["video_url"]

        # Voiceover
        audio_filename = None

        if add_voiceover and current_user.plan == 'pro':
            script = generate_video_script(prompt, style)
            audio_filename = generate_voiceover(script)

        # Save generation
        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            video_url=video_url,
            audio_url=audio_filename,
            status="completed"
        )

        db.session.add(generation)

        current_user.credits -= 1

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
        print("VIDEO GENERATION ERROR:", str(e))

        flash(
            'Video generation is temporarily unavailable. Please try again later. If problem persists, contact support.',
            'warning')

        return render_template(
            'main/result.html',
            original=prompt,
            refined=refined,
            video_url=None,
            audio_filename=None,
            style=style,
            error=None  # ← hide real error from user!
        )




@main.route('/refine-prompt', methods=['POST'])
def refine_prompt_free():
    data = request.get_json()
    prompt = data.get('prompt')

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    try:
        refined = refine_prompt(prompt)
        return jsonify({"refined": refined})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main.route('/history')
@login_required
def history():
    generations = Generation.query.filter_by(
        user_id=current_user.id
    ).order_by(Generation.created_at.desc()).all()

    return render_template('main/history.html',
                           generations=generations)


@main.route('/admin')
@login_required
def admin():
    # Only allow admin users
    if current_user.email != 'oadedamola07@gmail.com':
        flash('Access denied!', 'danger')
        return redirect(url_for('main.dashboard'))

    # Get all users
    users = User.query.order_by(User.created_at.desc()).all()

    # Get all generations
    generations = Generation.query.order_by(
        Generation.created_at.desc()
    ).all()
    telegram_users = TelegramUser.query.order_by(TelegramUser.joined_at.desc()).all()

    # Stats
    total_users = User.query.count()
    total_generations = Generation.query.count()
    pro_users = User.query.filter_by(plan='pro').count()
    free_users = User.query.filter_by(plan='free').count()
    total_telegram = TelegramUser.query.count()

    return render_template('main/admin.html',
                           users=users,
                           generations=generations,
                           telegram_users=telegram_users,
                           total_users=total_users,
                           total_generations=total_generations,
                           pro_users=pro_users,
                           free_users=free_users,
                           total_telegram=total_telegram)

@main.route('/admin/upgrade/<int:user_id>')
@login_required
def upgrade_user(user_id):
    # Only admin can do this
    if current_user.email != 'oadedamola07@gmail.com':
        flash('Access denied!', 'danger')
        return redirect(url_for('main.dashboard'))

    user = User.query.get(user_id)
    if user:
        user.plan = 'pro'
        user.credits = 999999  # Unlimited
        db.session.commit()

        # Send upgrade email
        try:
            from services.email import send_pro_upgrade_email
            send_pro_upgrade_email(user.email, user.username)
        except Exception as e:
            print(f"Email error: {e}")

        flash(f'{user.username} upgraded to Pro!', 'success')

    return redirect(url_for('main.admin'))

@main.route('/admin/downgrade/<int:user_id>')
@login_required
def downgrade_user(user_id):
    # Only admin can do this
    if current_user.email != 'oadedamola07@gmail.com':
        flash('Access denied!', 'danger')
        return redirect(url_for('main.dashboard'))

    user = User.query.get(user_id)
    if user:
        user.plan = 'free'
        user.credits = 5
        db.session.commit()
        flash(f'{user.username} downgraded to Free!', 'warning')

    return redirect(url_for('main.admin'))

@main.route('/admin/ban/<int:user_id>')
@login_required
def ban_user(user_id):
    if current_user.email != 'oadedamola07@gmail.com':
        flash('Access denied!', 'danger')
        return redirect(url_for('main.dashboard'))

    user = User.query.get(user_id)
    if user:
        user.plan = 'banned'
        user.credits = 0
        db.session.commit()
        flash(f'{user.username} has been banned!', 'warning')

    return redirect(url_for('main.admin'))

@main.route('/admin/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.email != 'oadedamola07@gmail.com':
        flash('Access denied!', 'danger')
        return redirect(url_for('main.dashboard'))

    user = User.query.get(user_id)
    if user:
        # Delete user's generations first
        Generation.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User deleted successfully!', 'danger')

    return redirect(url_for('main.admin'))


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
        "metadata": {
            "user_id": current_user.id,
            "username": current_user.username
        }
    }

    print(f"Paystack Secret Key: {os.environ.get('PAYSTACK_SECRET_KEY')[:10]}...")
    print(f"Email: {current_user.email}")
    print(f"Amount: {amount}")

    response = http_requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers,
        json=data
    )

    result = response.json()
    print(f"Paystack response: {result}")

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

    # Verify payment
    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"
    }

    response = http_requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )

    result = response.json()

    if result['status'] and result['data']['status'] == 'success':
        # Upgrade user to Pro!
        current_user.plan = 'pro'
        current_user.credits = 999999
        db.session.commit()

        # Send upgrade email
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



@main.route('/refine-image-prompt', methods=['POST'])
def refine_image_prompt_free():
    data = request.get_json()
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
    print("generate_from_image called")
    # Pro only!
    if current_user.plan != 'pro':
        flash('Image to Video is a Pro feature!', 'danger')
        return redirect(url_for('main.dashboard'))

    if current_user.credits <= 0:
        flash('No credits remaining!', 'danger')
        return redirect(url_for('main.dashboard'))

    prompt = request.form.get('prompt')
    image_file = request.files.get('image')

    if not prompt or not image_file:
        flash('Please provide both image and prompt!', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        # Save image temporarily
        import os
        filename = f"temp_{os.urandom(8).hex()}.jpg"
        filepath = os.path.join("static", "uploads", filename)
        os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
        image_file.save(filepath)

        # Get image URL
        image_url = url_for('static',
                           filename=f'uploads/{filename}',
                           _external=True)

        # Refine prompt
        refined = refine_prompt(prompt, "cinematic")

        # Generate video from image
        video_url = generate_video_from_image(image_url, refined)

        # Save to database
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
        current_user.credits -= 1
        db.session.commit()

        return render_template('main/result.html',
                             original=prompt,
                             refined=refined,
                             video_url=video_url,
                             audio_filename=None,
                             style="cinematic")

    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('main.dashboard'))

@main.route('/generate-image', methods=['POST'])
@login_required
def generate_image():
    prompt = request.form.get('prompt')
    style = request.form.get('style', 'realistic')

    if not prompt:
        flash('Please enter an image idea!', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        # Refine prompt for image
        refined = refine_image_prompt(prompt, style)

        # Generate image
        from services.video import generate_image as gen_image
        image = gen_image(refined)

        # Save to database
        generation = Generation(
            user_id=current_user.id,
            original_prompt=prompt,
            refined_prompt=refined,
            image_url=image,
            generation_type="image",
            status="completed" if image else "failed"
        )
        db.session.add(generation)
        db.session.commit()

        return render_template('main/image_result.html',
                               original=prompt,
                               refined=refined,
                               image_url=image)

    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('main.dashboard'))


@main.route('/save-prompt', methods=['POST'])
@login_required
def save_prompt():
    data = request.get_json()

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
    # Get or create referral code
    referral = Referral.query.filter_by(
        referrer_id=current_user.id,
        is_used=False
    ).first()

    if not referral:
        referral = Referral(
            referrer_id=current_user.id,
            referral_code=generate_referral_code()
        )
        db.session.add(referral)
        db.session.commit()

    referral_link = url_for('auth.register',
                            ref=referral.referral_code,
                            _external=True)

    return render_template('main/referral.html',
                           referral_link=referral_link,
                           referral_code=referral.referral_code)

@main.route('/payment/initialize/annual', methods=['POST'])
@login_required
def initialize_payment_annual():
    amount = 5000000  # ₦50,000 in kobo

    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }

    data = {
        "email": current_user.email,
        "amount": amount,
        "callback_url": url_for('main.payment_callback', _external=True),
        "metadata": {
            "user_id": current_user.id,
            "plan": "annual"
        }
    }

    response = http_requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers=headers,
        json=data
    )

    result = response.json()

    if result['status']:
        return redirect(result['data']['authorization_url'])
    else:
        flash('Payment initialization failed!', 'danger')
        return redirect(url_for('main.upgrade'))
