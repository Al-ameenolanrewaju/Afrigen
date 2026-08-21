import resend
import os

resend.api_key = os.environ.get("RESEND_API_KEY")

BASE_URL = os.environ.get("BASE_URL", "https://afrigen.com.ng")
FROM_EMAIL = "Afrigen <hello@afrigen.com.ng>"


def send_welcome_email(user_email, username):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Welcome to Afrigen! 🎬",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">🎬 Welcome to Afrigen!</h1>
                <p>Hi {username}! 👋</p>
                <p>You're now part of the African AI revolution!</p>
                <p style="color: #C9D1D9;">
                    You have <strong style="color: #F5A623;">5 free credits</strong>
                    to generate AI videos!
                </p>
                <a href="{BASE_URL}/dashboard"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Start Generating! 🚀
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Welcome email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_video_ready_email(user_email, username, original_prompt, video_url):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Your Afrigen video is ready! 🎬",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">🎬 Your Video Is Ready!</h1>
                <p>Hi {username}! 👋</p>
                <p>Your AI video has been generated!</p>
                <p style="color: #C9D1D9;">
                    Original idea: <em>"{original_prompt}"</em>
                </p>
                <a href="{video_url}"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Watch Your Video 🎬
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Video ready email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_credits_low_email(user_email, username, credits_left):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": f"You have {credits_left} credit left! ⚠️",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">⚠️ Credits Running Low!</h1>
                <p>Hi {username}! 👋</p>
                <p style="color: #C9D1D9;">
                    You only have
                    <strong style="color: #F5A623;">{credits_left} credit</strong>
                    remaining!
                </p>
                <p>Upgrade to Pro for unlimited video generation!</p>
                <a href="{BASE_URL}/upgrade"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Upgrade to Pro ⭐
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Credits low email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_credits_exhausted_email(user_email, username):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "You've used all your credits! 😔",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #E74C3C;">😔 No Credits Left!</h1>
                <p>Hi {username}! 👋</p>
                <p style="color: #C9D1D9;">
                    You've used all your free credits this month.
                </p>
                <p>Upgrade to Pro for unlimited video generation!</p>
                <a href="{BASE_URL}/upgrade"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Upgrade to Pro ⭐
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Credits exhausted email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_pro_upgrade_email(user_email, username):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "You've been upgraded to Afrigen Pro! ⭐",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">⭐ Welcome to Afrigen Pro!</h1>
                <p>Hi {username}! 👋</p>
                <p style="color: #C9D1D9;">
                    Great news! You've been upgraded to
                    <strong style="color: #F5A623;">Afrigen Pro!</strong>
                </p>
                <p>You now have:</p>
                <ul style="color: #C9D1D9;">
                    <li>✅ Unlimited video generation</li>
                    <li>✅ 100 credits per month</li>
                    <li>✅ Image generation</li>
                    <li>✅ Image to video</li>
                    <li>✅ AI voiceover</li>
                    <li>✅ Direct download (no ads)</li>
                </ul>
                <a href="{BASE_URL}/dashboard"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Start Generating! 🚀
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Pro upgrade email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def generate_reset_token(email):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    return serializer.dumps(email, salt='password-reset')


def verify_reset_token(token, expiration=3600):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    try:
        email = serializer.loads(token, salt='password-reset', max_age=expiration)
        return email
    except:
        return None


def generate_unsub_token(email):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    return serializer.dumps(email, salt='newsletter-unsub')


def verify_unsub_token(token):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    try:
        # No expiry: an unsubscribe link should work indefinitely.
        return serializer.loads(token, salt='newsletter-unsub')
    except Exception:
        return None


def send_reset_password_email(user_email, username, reset_url):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Reset Your Afrigen Password 🔑",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">🔑 Reset Your Password</h1>
                <p>Hi {username}! 👋</p>
                <p style="color: #C9D1D9;">
                    You requested to reset your password.
                    Click the button below to reset it!
                </p>
                <a href="{reset_url}"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    Reset Password 🔑
                </a>
                <p style="color: #888; margin-top: 20px;">
                    This link expires in 1 hour!
                    If you didn't request this, ignore this email.
                </p>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Reset email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_contact_email(name, email, message):
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": "contact@afrigen.com.ng",
            "subject": f"New Contact from {name} - Afrigen",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">📬 New Contact Message</h1>
                <p><strong>Name:</strong> {name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Message:</strong></p>
                <p style="background: #161B22; padding: 15px; border-radius: 8px;">
                    {message}
                </p>
                <hr style="border-color: #21262D;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Contact email sent!")
    except Exception as e:
        print(f"Contact email error: {e}")


def send_launch_confirmation(user_email, name):
    """Confirm a pre-launch waitlist signup from the /launch page."""
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "You're on the AFRIGEN launch list! 🎬",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">🎬 You're on the list!</h1>
                <p>Hi {name}! 👋</p>
                <p>Thanks for joining the AFRIGEN launch list.
                   We'll email you the moment we go live.</p>
                <a href="{BASE_URL}/launch"
                   style="background: #F5A623; color: #0D1117;
                          padding: 12px 24px; border-radius: 8px;
                          text-decoration: none; font-weight: bold;">
                    View Launch Page 🚀
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Launch confirmation email sent!")
    except Exception as e:
        print(f"Launch confirmation email error: {e}")


def send_newsletter(recipients, subject, body, base_url=BASE_URL, is_html=False):
    """Send a newsletter to the given recipients.

    recipients: iterable of (email, name) tuples.
    is_html:    True if `body` is already HTML (e.g. the auto-generated digest);
                False treats `body` as plain text and converts newlines to <br>.
    Each email gets a per-recipient unsubscribe link.
    Returns the number of emails successfully sent.
    """
    html_body = body if is_html else (body or "").replace("\n", "<br>")
    sent = 0
    for email, name in recipients:
        try:
            unsub_url = f"{base_url}/unsubscribe/{generate_unsub_token(email)}"
            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": subject or "AFRIGEN Newsletter",
                "html": f"""
                <div style="font-family: Arial; background: #0D1117;
                            color: #F0F6FC; padding: 40px; max-width: 600px;">
                    <h1 style="color: #F5A623;">AFRIGEN</h1>
                    <p>Hi {name or 'there'}! 👋</p>
                    <div style="color: #C9D1D9; line-height: 1.6;">{html_body}</div>
                    <hr style="border-color: #21262D; margin: 30px 0;">
                    <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
                    <p style="color: #555; font-size: 12px;">
                        You're receiving this because you joined Afrigen.
                        <a href="{unsub_url}" style="color: #888;">Unsubscribe</a>
                    </p>
                </div>
                """
            })
            sent += 1
        except Exception as e:
            print(f"Newsletter send error for {email}: {e}")
    return sent


def send_admin_notice(to_email, heading, message, button_url=None, button_text=None):
    """Small branded internal notice to an admin (e.g. newsletter reminders)."""
    button_html = ""
    if button_url and button_text:
        button_html = f"""
            <a href="{button_url}"
               style="background: #F5A623; color: #0D1117; padding: 12px 24px;
                      border-radius: 8px; text-decoration: none; font-weight: bold;
                      display: inline-block; margin-top: 12px;">{button_text}</a>"""
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": heading,
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">{heading}</h1>
                <p style="color: #C9D1D9; line-height: 1.6;">{message}</p>
                {button_html}
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Admin notice sent!")
    except Exception as e:
        print(f"Admin notice email error: {e}")


def send_feedback_email(user_email, rating, feedback_text, feature):
    try:
        try:
            stars = '⭐' * int(rating)
        except (TypeError, ValueError):
            stars = str(rating or 'N/A')
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": "contact@afrigen.com.ng",
            "subject": f"New Feedback - {rating}/5 Stars - Afrigen",
            "html": f"""
            <div style="font-family: Arial; background: #0D1117;
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">⭐ New Feedback</h1>
                <p><strong>From:</strong> {user_email}</p>
                <p><strong>Rating:</strong> {stars}</p>
                <p><strong>Feature:</strong> {feature}</p>
                <p><strong>Feedback:</strong></p>
                <p style="background: #161B22; padding: 15px; border-radius: 8px;">
                    {feedback_text}
                </p>
                <hr style="border-color: #21262D;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        })
        print("Feedback email sent!")
    except Exception as e:
        print(f"Feedback email error: {e}")