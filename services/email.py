import resend
import os
import json

resend.api_key = os.environ.get("RESEND_API_KEY")

BASE_URL = os.environ.get("BASE_URL", "https://afrigen.com.ng")
FROM_EMAIL = "Afrigen <hello@afrigen.com.ng>"


def get_base_email_html(content):
    social_links_text_html = ""
    try:
        from models import Brand
        afrigen_brand = Brand.query.filter(Brand.name.ilike('%afrigen%')).first()
        if not afrigen_brand:
            afrigen_brand = Brand.query.first()
            
        if afrigen_brand and afrigen_brand.social_links:
            if isinstance(afrigen_brand.social_links, str):
                social_links = json.loads(afrigen_brand.social_links)
            else:
                social_links = afrigen_brand.social_links
                
            if social_links and isinstance(social_links, dict):
                for platform, url in social_links.items():
                    platform_name = platform.capitalize()
                    social_links_text_html += f'<a href="{url}" target="_blank" style="color: #666666; font-size: 12px; text-decoration: none; margin-right: 16px;">{platform_name}</a>\n'
    except Exception as e:
        print(f"Error fetching social links for email template: {e}")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Afrigen</title>
</head>
<body style="margin: 0; padding: 0; background-color: #000000; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #000000;">
        <tr>
            <td align="center" style="padding: 60px 20px;">
                <!-- Main Container -->
                <table width="480" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; width: 100%; background-color: #0A0A0A; border: 1px solid #1A1A1A; border-radius: 12px; overflow: hidden;">
                    
                    <!-- Accent Line -->
                    <tr>
                        <td style="height: 2px; background-color: #F5A623;"></td>
                    </tr>
                    
                    <tr>
                        <td align="left" style="padding: 40px;">
                            <!-- Header -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 40px;">
                                <tr>
                                    <td align="left">
                                        <h1 style="color: #FFFFFF; margin: 0; font-size: 16px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;">Afrigen</h1>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Content -->
                            {content}
                            
                            <!-- Footer -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 60px;">
                                <tr>
                                    <td style="border-top: 1px solid #222222; padding-top: 24px;" align="left">
                                        <div style="margin-bottom: 16px;">
                                            <a href="{BASE_URL}" target="_blank" style="color: #666666; font-size: 12px; text-decoration: none; margin-right: 16px;">Website</a>
                                            <a href="{BASE_URL}/blog" target="_blank" style="color: #666666; font-size: 12px; text-decoration: none; margin-right: 16px;">Blog</a>
                                            {social_links_text_html}
                                        </div>
                                        <p style="color: #444444; font-size: 12px; margin: 0;">Africa Creates, AI Generates 🌍</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
                <p style="color: #333333; font-size: 11px; margin: 24px 0 0 0; text-align: center;">© 2026 Afrigen. All rights reserved.</p>
            </td>
        </tr>
    </table>
</body>
</html>
"""


def send_welcome_email(user_email, username):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Welcome to Afrigen.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">Hi <strong style="color: #FFFFFF;">{username}</strong>,</p>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 32px 0;">
            You're officially part of the African AI revolution. We've credited your account with 5 free credits so you can start creating immediately.
        </p>
        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{BASE_URL}/dashboard" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">Start Generating</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Welcome to Afrigen",
            "html": get_base_email_html(content)
        })
        print("Welcome email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_video_ready_email(user_email, username, original_prompt, video_url):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Generation complete.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">Hi <strong style="color: #FFFFFF;">{username}</strong>, your AI generation has finished successfully based on your prompt:</p>
        
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 32px;">
            <tr>
                <td style="border-left: 2px solid #333333; padding-left: 16px;">
                    <p style="color: #E4E4E7; font-size: 15px; margin: 0; line-height: 1.6;">{original_prompt}</p>
                </td>
            </tr>
        </table>

        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{video_url}" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">View Result</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Your generation is ready",
            "html": get_base_email_html(content)
        })
        print("Video ready email sent!")
        return True
    except Exception as e:
        print(
            f"EMAIL type=video_ready status=failed recipient={user_email!r} "
            f"resend_api_key_configured={bool(os.environ.get('RESEND_API_KEY'))} error={e}"
        )
        return False


def send_credits_low_email(user_email, username, credits_left):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Action required.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">Hi <strong style="color: #FFFFFF;">{username}</strong>,</p>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 32px 0;">
            You only have {credits_left} credits remaining in your account. To ensure uninterrupted access to generations, please upgrade to a Pro plan.
        </p>
        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{BASE_URL}/upgrade" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">View Plans</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": f"Action required: {credits_left} credits remaining",
            "html": get_base_email_html(content)
        })
        print("Credits low email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_credits_exhausted_email(user_email, username):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Usage limit reached.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">Hi {username},</p>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 32px 0;">
            You've used all your free credits for this billing cycle. To continue creating, please select a Pro plan.
        </p>
        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{BASE_URL}/upgrade" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">Upgrade to Pro</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Usage limit reached",
            "html": get_base_email_html(content)
        })
        print("Credits exhausted email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_pro_upgrade_email(user_email, username):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Welcome to Pro.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">Hi <strong style="color: #FFFFFF;">{username}</strong>, your account has been successfully upgraded to the Pro plan. You now have access to:</p>
        
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 32px;">
            <tr><td style="padding-bottom: 8px; color: #E4E4E7; font-size: 15px;">— Unlimited video generation</td></tr>
            <tr><td style="padding-bottom: 8px; color: #E4E4E7; font-size: 15px;">— 100 credits per month</td></tr>
            <tr><td style="padding-bottom: 8px; color: #E4E4E7; font-size: 15px;">— Image to video capabilities</td></tr>
            <tr><td style="padding-bottom: 8px; color: #E4E4E7; font-size: 15px;">— AI voiceovers</td></tr>
            <tr><td style="color: #E4E4E7; font-size: 15px;">— Direct downloads without ads</td></tr>
        </table>

        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{BASE_URL}/dashboard" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">Go to Dashboard</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Your account has been upgraded",
            "html": get_base_email_html(content)
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
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">Password Reset</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            A request was made to reset the password for your account. Click the button below to proceed.
        </p>
        <table border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{reset_url}" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">Reset Password</a>
                </td>
            </tr>
        </table>
        <p style="color: #52525B; font-size: 13px; margin: 0; line-height: 1.6;">
            This link expires in 1 hour. If you did not make this request, you can safely ignore this email.
        </p>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "Reset your password",
            "html": get_base_email_html(content)
        })
        print("Reset email sent!")
    except Exception as e:
        print(f"Email error: {e}")


def send_contact_email(name, email, message):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 20px; font-weight: 600; margin: 0 0 32px 0;">New Contact Message</h2>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 1px;">From</p>
        <p style="color: #E4E4E7; font-size: 15px; margin: 0 0 24px 0;">{name} &lt;{email}&gt;</p>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 1px;">Message</p>
        <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td style="border-left: 2px solid #333333; padding-left: 16px;">
                    <p style="color: #E4E4E7; font-size: 15px; line-height: 1.6; margin: 0; white-space: pre-wrap;">{message}</p>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": "contact@afrigen.com.ng",
            "subject": f"Contact: {name}",
            "html": get_base_email_html(content)
        })
        print("Contact email sent!")
    except Exception as e:
        print(f"Contact email error: {e}")


def send_launch_confirmation(user_email, name):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 24px; font-weight: 600; margin: 0 0 24px 0; letter-spacing: -0.5px;">You're on the list.</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">Hi <strong style="color: #FFFFFF;">{name}</strong>,</p>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0 0 32px 0;">
            Thank you for joining the Afrigen launch list. We'll notify you the exact moment we go live so you can secure your spot.
        </p>
        <table border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{BASE_URL}/launch" target="_blank" style="display: inline-block; padding: 10px 24px; font-weight: 500; font-size: 14px; color: #000000; text-decoration: none; border-radius: 6px;">Return to Launch Page</a>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": user_email,
            "subject": "You're on the list",
            "html": get_base_email_html(content)
        })
        print("Launch confirmation email sent!")
    except Exception as e:
        print(f"Launch confirmation email error: {e}")


def send_newsletter(recipients, subject, body, base_url=BASE_URL, is_html=False):
    html_body = body if is_html else (body or "").replace("\n", "<br>")
    sent = 0
    for email, name in recipients:
        try:
            unsub_url = f"{base_url}/unsubscribe/{generate_unsub_token(email)}"
            content = f"""
            <p style="color: #E4E4E7; font-size: 15px; margin: 0 0 24px 0;">Hi <strong style="color: #FFFFFF;">{name or 'there'}</strong>,</p>
            <div style="color: #A1A1AA; font-size: 15px; line-height: 1.7; margin-bottom: 40px;">
                {html_body}
            </div>
            
            <p style="color: #52525B; font-size: 13px; margin: 0; line-height: 1.5; padding-top: 32px; border-top: 1px solid #222222;">
                You're receiving this because you subscribed to updates.<br>
                <a href="{unsub_url}" style="color: #A1A1AA; text-decoration: underline;">Unsubscribe from this list</a>.
            </p>
            """
            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": subject or "Afrigen Update",
                "html": get_base_email_html(content)
            })
            sent += 1
        except Exception as e:
            print(f"Newsletter send error for {email}: {e}")
    return sent


def send_admin_notice(to_email, heading, message, button_url=None, button_text=None):
    button_html = ""
    if button_url and button_text:
        button_html = f"""
        <table border="0" cellspacing="0" cellpadding="0" style="margin-top: 24px;">
            <tr>
                <td align="center" style="background-color: #EDEDED; border-radius: 6px;">
                    <a href="{button_url}" target="_blank" style="display: inline-block; padding: 8px 20px; font-weight: 500; font-size: 13px; color: #000000; text-decoration: none; border-radius: 6px;">{button_text}</a>
                </td>
            </tr>
        </table>
        """
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 20px; font-weight: 600; margin: 0 0 16px 0;">{heading}</h2>
        <p style="color: #A1A1AA; font-size: 15px; line-height: 1.6; margin: 0;">{message}</p>
        {button_html}
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": f"Notice: {heading}",
            "html": get_base_email_html(content)
        })
        print("Admin notice sent!")
    except Exception as e:
        print(f"Admin notice email error: {e}")


def send_feedback_email(user_email, rating, feedback_text, feature):
    try:
        content = f"""
        <h2 style="color: #FFFFFF; font-size: 20px; font-weight: 600; margin: 0 0 32px 0;">User Feedback</h2>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 1px;">From</p>
        <p style="color: #E4E4E7; font-size: 15px; margin: 0 0 20px 0;">{user_email}</p>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 1px;">Rating</p>
        <p style="color: #E4E4E7; font-size: 15px; margin: 0 0 20px 0;">{rating} / 5</p>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 1px;">Feature</p>
        <p style="color: #E4E4E7; font-size: 15px; margin: 0 0 24px 0;">{feature}</p>
        
        <p style="color: #A1A1AA; font-size: 13px; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 1px;">Feedback</p>
        <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td style="border-left: 2px solid #333333; padding-left: 16px;">
                    <p style="color: #E4E4E7; font-size: 15px; line-height: 1.6; margin: 0; white-space: pre-wrap;">{feedback_text}</p>
                </td>
            </tr>
        </table>
        """
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": "contact@afrigen.com.ng",
            "subject": f"Feedback ({rating}/5): {feature}",
            "html": get_base_email_html(content)
        })
        print("Feedback email sent!")
    except Exception as e:
        print(f"Feedback email error: {e}")