from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer
import os



def send_welcome_email(user_email, username):
    try:
        from app import mail
        msg = Message(
            subject="Welcome to Afrigen! 🎬",
            recipients=[user_email],
            html=f"""
            <div style="font-family: Arial; background: #0D1117; 
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">🎬 Welcome to Afrigen!</h1>
                <p>Hi {username}! 👋</p>
                <p>You're now part of the African AI revolution!</p>
                <p style="color: #C9D1D9;">
                    You have <strong style="color: #F5A623;">5 free credits</strong> 
                    to generate AI videos!
                </p>
                <a href="http://127.0.0.1:5000/dashboard" 
                   style="background: #F5A623; color: #0D1117; 
                          padding: 12px 24px; border-radius: 8px; 
                          text-decoration: none; font-weight: bold;">
                    Start Generating! 🚀
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
        print("Welcome email sent!")
    except Exception as e:
        print(f"Email error: {e}")

def send_video_ready_email(user_email, username, original_prompt, video_url):
    try:
        from app import mail
        msg = Message(
            subject="Your Afrigen video is ready! 🎬",
            recipients=[user_email],
            html=f"""
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
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email error: {e}")

def send_credits_low_email(user_email, username, credits_left):
    try:
        from app import mail
        msg = Message(
            subject=f"You have {credits_left} credit left! ⚠️",
            recipients=[user_email],
            html=f"""
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
                <a href="http://127.0.0.1:5000/upgrade" 
                   style="background: #F5A623; color: #0D1117; 
                          padding: 12px 24px; border-radius: 8px; 
                          text-decoration: none; font-weight: bold;">
                    Upgrade to Pro ⭐
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email error: {e}")

def send_credits_exhausted_email(user_email, username):
    try:
        from app import mail
        msg = Message(
            subject="You've used all your credits! 😔",
            recipients=[user_email],
            html=f"""
            <div style="font-family: Arial; background: #0D1117; 
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #E74C3C;">😔 No Credits Left!</h1>
                <p>Hi {username}! 👋</p>
                <p style="color: #C9D1D9;">
                    You've used all your free credits this month.
                </p>
                <p>Upgrade to Pro for unlimited video generation!</p>
                <a href="http://127.0.0.1:5000/upgrade" 
                   style="background: #F5A623; color: #0D1117; 
                          padding: 12px 24px; border-radius: 8px; 
                          text-decoration: none; font-weight: bold;">
                    Upgrade to Pro ⭐
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email error: {e}")


def send_pro_upgrade_email(user_email, username):
    try:
        from app import mail
        msg = Message(
            subject="You've been upgraded to Afrigen Pro! ⭐",
            recipients=[user_email],
            html=f"""
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
                    <li>✅ HD quality videos</li>
                    <li>✅ Priority generation</li>
                    <li>✅ All premium features!</li>
                </ul>
                <a href="http://127.0.0.1:5000/dashboard" 
                   style="background: #F5A623; color: #0D1117; 
                          padding: 12px 24px; border-radius: 8px; 
                          text-decoration: none; font-weight: bold;">
                    Start Generating! 🚀
                </a>
                <hr style="border-color: #21262D; margin: 30px 0;">
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Email error: {e}")

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    return serializer.dumps(email, salt='password-reset')

def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY"))
    try:
        email = serializer.loads(
            token,
            salt='password-reset',
            max_age=expiration
        )
        return email
    except:
        return None

def send_reset_password_email(user_email, username, reset_url):
    try:
        from app import mail
        msg = Message(
            subject="Reset Your Afrigen Password 🔑",
            recipients=[user_email],
            html=f"""
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
                <p style="color: #888;">
                    Africa Creates, AI Generates 🌍
                </p>
            </div>
            """
        )
        mail.send(msg)
        print("Reset email sent!")
    except Exception as e:
        print(f"Email error: {e}")



def send_contact_email(name, email, message):
    try:
        from app import mail
        msg = Message(
            subject=f"New Contact from {name} - Afrigen",
            recipients=["afrigenng@gmail.com"],
            html=f"""
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
        )
        mail.send(msg)
    except Exception as e:
        print(f"Contact email error: {e}")


def send_feedback_email(user_email, rating, feedback_text, feature):
    try:
        from app import mail
        msg = Message(
            subject=f"New Feedback - {rating}/5 Stars - Afrigen",
            recipients=["afrigenng@gmail.com"],
            html=f"""
            <div style="font-family: Arial; background: #0D1117; 
                        color: #F0F6FC; padding: 40px; max-width: 600px;">
                <h1 style="color: #F5A623;">⭐ New Feedback</h1>
                <p><strong>From:</strong> {user_email}</p>
                <p><strong>Rating:</strong> {'⭐' * int(rating)}</p>
                <p><strong>Feature:</strong> {feature}</p>
                <p><strong>Feedback:</strong></p>
                <p style="background: #161B22; padding: 15px; border-radius: 8px;">
                    {feedback_text}
                </p>
                <hr style="border-color: #21262D;">
                <p style="color: #888;">Africa Creates, AI Generates 🌍</p>
            </div>
            """
        )
        mail.send(msg)
    except Exception as e:
        print(f"Feedback email error: {e}")