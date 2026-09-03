from flask import Blueprint, render_template, request, redirect, url_for,flash, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Referral
from services.email import generate_reset_token, verify_reset_token, send_reset_password_email
from services.email import send_welcome_email
import logging
import os
from routes.main import get_country_from_ip, get_real_ip

auth = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


def verify_user_password(stored_password, provided_password):
    """Accept both modern werkzeug hashes and legacy plaintext passwords.

    Old records created before the password hashing change can still contain a
    raw string, which would otherwise cause check_password_hash() to raise a
    ValueError and 500 the login route.
    """
    if not stored_password:
        return False

    if stored_password == provided_password:
        return True

    try:
        return check_password_hash(stored_password, provided_password)
    except (TypeError, ValueError):
        return False


@auth.route('/register', methods=['GET', 'POST'])
def register():
    # Capture UTM source from GET params and store in session
    if request.method == 'GET':
        utm_source = request.args.get('utm_source', '')
        ref_code = request.args.get('ref', '')
        if utm_source:
            session['signup_source'] = utm_source
        if ref_code:
            session['ref_code'] = ref_code

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        ref_code = session.get('ref_code') or request.args.get('ref')
        signup_source = session.get('signup_source', 'direct')

        # Detect source from referrer header if no UTM
        if signup_source == 'direct' and request.referrer:
            referrer = request.referrer.lower()
            if 'facebook' in referrer:
                signup_source = 'facebook'
            elif 'twitter' in referrer or 'x.com' in referrer:
                signup_source = 'twitter'
            elif 'instagram' in referrer:
                signup_source = 'instagram'
            elif 'linkedin' in referrer:
                signup_source = 'linkedin'
            elif 'google' in referrer:
                signup_source = 'google'
            elif 'telegram' in referrer:
                signup_source = 'telegram'

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            logger.warning(f"Registration failed - email exists: {email}")
            flash('Email already registered!', 'danger')
            return redirect(url_for('auth.register'))

        # username is also unique in the DB; check it too, otherwise the commit
        # below raises an IntegrityError and 500s instead of a friendly message.
        if User.query.filter_by(username=username).first():
            logger.warning(f"Registration failed - username taken: {username}")
            flash('Username already taken!', 'danger')
            return redirect(url_for('auth.register'))

        # Get country from IP

        ip = get_real_ip()
        country = get_country_from_ip(ip)

        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            email=email,
            password=hashed_password,
            credits=5,
            country=country,
            signup_source=signup_source
        )
        db.session.add(new_user)
        db.session.flush()

        # Handle referral
        if ref_code:
            referral = Referral.query.filter_by(
                referral_code=ref_code,
                is_used=False
            ).first()

            if referral:
                referrer = User.query.get(referral.referrer_id)
                if referrer:
                    if referrer.plan == 'pro':
                        referrer.credits += 10  # Equivalent value for pro users, or whatever is appropriate
                
                referral.referred_id = new_user.id
                referral.is_used = True
                flash('Referral recorded successfully!', 'success')

        db.session.commit()

        # Clear session
        session.pop('signup_source', None)
        session.pop('ref_code', None)

        logger.info(f"New user registered: {username} ({email}) from {country} via {signup_source}")

        try:
            send_welcome_email(email, username)
        except Exception as e:
            logger.error(f"Welcome email failed for {email}: {e}")

        flash('Account created! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and verify_user_password(user.password, password):
            if user.plan == 'banned':
                logger.warning(f"Banned user login attempt: {email}")
                flash('Your account has been banned!', 'danger')
                return redirect(url_for('auth.login'))

            if user.password == password:
                user.password = generate_password_hash(password)
                db.session.commit()

            login_user(user)
            logger.info(f"User logged in: {email}")
            flash('Welcome back!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            logger.warning(f"Failed login attempt: {email}")
            flash('Invalid email or password!', 'danger')

    return render_template('auth/login.html')
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('main.index'))




@auth.route('/google')
def google_login():
    from app import google
    # Only force HTTPS in production. Locally, it should remain HTTP to match standard Flask behavior.
    if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER'):
        redirect_uri = url_for('auth.google_callback', _external=True, _scheme='https')
    else:
        redirect_uri = url_for('auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@auth.route('/google/callback')
def google_callback():
    from app import google
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
    except Exception as e:
        flash('Google login failed or was cancelled.', 'danger')
        return redirect(url_for('auth.login'))

    if user_info:
        email = user_info['email']
        username = user_info['name']

        # Check if user exists
        user = User.query.filter_by(email=email).first()

        if not user:
            # username comes from the Google profile name, which is not unique;
            # disambiguate so the unique constraint doesn't 500 the callback.
            if User.query.filter_by(username=username).first():
                username = f"{username}_{os.urandom(3).hex()}"

            ip = get_real_ip()
            country = get_country_from_ip(ip)

            # Create new user (match email signup: 5 starting credits)
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(os.urandom(24).hex()),
                credits=5,
                country=country,
                signup_source=session.get('signup_source', 'google')
            )
            db.session.add(user)
            db.session.flush()

            # Honor a referral code if the user arrived via a referral link
            ref_code = session.get('ref_code')
            if ref_code:
                referral = Referral.query.filter_by(
                    referral_code=ref_code, is_used=False
                ).first()
                if referral:
                    referrer = User.query.get(referral.referrer_id)
                    if referrer:
                        if referrer.plan == 'pro':
                            referrer.credits += 10
                            
                    referral.referred_id = user.id
                    referral.is_used = True

            db.session.commit()

            session.pop('signup_source', None)
            session.pop('ref_code', None)

            # Send welcome email
            try:
                from services.email import send_welcome_email
                send_welcome_email(email, username)
            except Exception as e:
                print(f"Email error: {e}")

        login_user(user)
        flash('Logged in with Google! 🎉', 'success')
        return redirect(url_for('main.dashboard'))

    flash('Google login failed!', 'danger')
    return redirect(url_for('auth.login'))



@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()

        if user:
            # Generate reset token
            token = generate_reset_token(email)
            reset_url = url_for('auth.reset_password',
                                token=token, _external=True)

            # Send reset email
            try:
                send_reset_password_email(email, user.username, reset_url)
            except Exception as e:
                print(f"Email error: {e}")
                # Don't flash an error here to prevent enumeration by observing email failures
        
        flash('If that email exists, a reset link has been sent!', 'success')

        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Verify token
    email = verify_reset_token(token)

    if not email:
        flash('Invalid or expired reset link!', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('auth.reset_password', token=token))

        # Update password
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Password reset successfully! Please login.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)



