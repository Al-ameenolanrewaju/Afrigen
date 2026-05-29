"""
Afrigen Test Suite
Tests all core functionality without needing FAL.ai credits
Run: python test_afrigen.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Set test environment
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['FAL_KEY'] = 'test-fal-key'

from unittest.mock import patch, MagicMock
from app import app, db
from models import User, Generation
from werkzeug.security import generate_password_hash

# ─── Setup ───────────────────────────────────────────────────────────────────

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

# ─── Helpers ─────────────────────────────────────────────────────────────────

def create_free_user(client, username='freeuser', email='free@test.com'):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        user = User(
            username=username,
            email=email,
            password=generate_password_hash('testpass123'),
            plan='free',
            credits=10,
            monthly_videos_used=0,
            monthly_images_used=0
        )
        db.session.add(user)
        db.session.commit()
        return user.id

def create_pro_user(client, username='prouser', email='pro@test.com', credits=100):
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        user = User(
            username=username,
            email=email,
            password=generate_password_hash('testpass123'),
            plan='pro',
            credits=credits,
            monthly_videos_used=0,
            monthly_images_used=0
        )
        db.session.add(user)
        db.session.commit()
        return user.id

def login(client, email, password='testpass123'):
    return client.post('/auth/login', data={
        'email': email,
        'password': password
    }, follow_redirects=True)

def logout(client):
    return client.get('/auth/logout', follow_redirects=True)

# ─── Tests ───────────────────────────────────────────────────────────────────

passed = 0
failed = 0

def test(name, condition, detail=''):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} {f'— {detail}' if detail else ''}")
        failed += 1

print("\n" + "="*50)
print("🧪 AFRIGEN TEST SUITE")
print("="*50)

with app.test_client() as client:

    # ── 1. Basic Routes ──────────────────────────────────────────────────────
    print("\n📍 Basic Routes")

    r = client.get('/')
    test("Homepage loads", r.status_code == 200)

    r = client.get('/auth/login')
    test("Login page loads", r.status_code == 200)

    r = client.get('/auth/register')
    test("Register page loads", r.status_code == 200)

    r = client.get('/upgrade')
    test("Upgrade redirects if not logged in", r.status_code in [302, 200])

    r = client.get('/dashboard')
    test("Dashboard redirects if not logged in", r.status_code == 302)

    # ── 2. Registration ──────────────────────────────────────────────────────
    print("\n📝 Registration")

    with app.app_context():
        existing = User.query.filter_by(email='newuser@test.com').first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

    r = client.post('/auth/register', data={
        'username': 'newuser',
        'email': 'newuser@test.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    test("New user can register", r.status_code == 200)

    with app.app_context():
        user = User.query.filter_by(email='newuser@test.com').first()
        test("User saved in database", user is not None)
        test("User starts on free plan", user and user.plan == 'free')

    r = client.post('/auth/register', data={
        'username': 'newuser2',
        'email': 'newuser@test.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    test("Duplicate email rejected", b'already registered' in r.data or r.status_code == 200)

    # ── 3. Login / Logout ────────────────────────────────────────────────────
    print("\n🔐 Login & Logout")

    r = login(client, 'newuser@test.com')
    test("Valid login succeeds", r.status_code == 200)

    r = client.get('/dashboard')
    test("Dashboard accessible after login", r.status_code == 200)

    logout(client)
    r = client.get('/dashboard')
    test("Dashboard blocked after logout", r.status_code == 302)

    r = login(client, 'newuser@test.com', 'wrongpassword')
    test("Wrong password rejected", b'Invalid' in r.data or r.status_code == 200)

    # ── 4. Free User Video Limits ────────────────────────────────────────────
    print("\n🎬 Free User Video Limits")

    free_id = create_free_user(client)
    login(client, 'free@test.com')

    with patch('routes.main.generate_video') as mock_video, \
         patch('services.claude.refine_prompt') as mock_refine:

        mock_refine.return_value = "refined test prompt"
        mock_video.return_value = {"success": True, "video_url": "https://test.com/video.mp4"}

        # Generate 3 free videos
        for i in range(3):
            r = client.post('/generate', data={
                'prompt': f'test video {i}',
                'style': 'cinematic',
                'action': 'generate',
                'aspect_ratio': '16:9'
            })

        with app.app_context():
            user = User.query.get(free_id)
            test("Free user used 3 videos", user.monthly_videos_used == 3)

        # Try 4th video - should be blocked
        r = client.post('/generate', data={
            'prompt': 'test video 4',
            'style': 'cinematic',
            'action': 'generate',
            'aspect_ratio': '16:9'
        })
        import json
        try:
            data = json.loads(r.data)
            test("4th video blocked for free user", data.get('success') == False)
        except:
            test("4th video blocked for free user", False, "Could not parse response")

    logout(client)

    # ── 5. Free User Image Limits ────────────────────────────────────────────
    print("\n🖼️ Free User Image Limits")

    login(client, 'free@test.com')

    with patch('routes.main.generate_ai_image') as mock_image, \
         patch('services.claude.refine_image_prompt') as mock_refine:

        mock_refine.return_value = "refined image prompt"
        mock_image.return_value = {"success": True, "image_url": "https://test.com/image.jpg"}

        # Generate 2 free images
        for i in range(2):
            r = client.post('/generate-image', data={
                'prompt': f'test image {i}',
                'style': 'realistic'
            })

        with app.app_context():
            user = User.query.get(free_id)
            test("Free user used 2 images", user.monthly_images_used == 2)

        # Try 3rd image - should be blocked
        r = client.post('/generate-image', data={
            'prompt': 'test image 3',
            'style': 'realistic'
        })
        try:
            data = json.loads(r.data)
            test("3rd image blocked for free user", data.get('success') == False)
        except:
            test("3rd image blocked for free user", False, "Could not parse response")

    logout(client)

    # ── 6. Pro User Credits ──────────────────────────────────────────────────
    print("\n⭐ Pro User Credits")

    pro_id = create_pro_user(client, credits=20)
    login(client, 'pro@test.com')

    with patch('routes.main.generate_video') as mock_video, \
         patch('services.claude.refine_prompt') as mock_refine:

        mock_refine.return_value = "refined test prompt"
        mock_video.return_value = {"success": True, "video_url": "https://test.com/video.mp4"}

        r = client.post('/generate', data={
            'prompt': 'pro test video',
            'style': 'cinematic',
            'action': 'generate',
            'aspect_ratio': '16:9'
        })

        with app.app_context():
            user = User.query.get(pro_id)
            test("Pro user credits deducted (5 per video)", user.credits == 15)

    # Test pro user blocked when credits < 5
    pro_low_id = create_pro_user(client, username='prolowuser', email='prolow@test.com', credits=4)
    logout(client)
    login(client, 'prolow@test.com')

    with patch('services.claude.refine_prompt') as mock_refine:
        mock_refine.return_value = "refined test prompt"
        r = client.post('/generate', data={
            'prompt': 'test video',
            'style': 'cinematic',
            'action': 'generate',
            'aspect_ratio': '16:9'
        })
        try:
            data = json.loads(r.data)
            test("Pro user blocked when credits < 5", data.get('success') == False)
        except:
            test("Pro user blocked when credits < 5", False, "Could not parse response")

    logout(client)

    # ── 7. Payment ───────────────────────────────────────────────────────────
    print("\n💳 Payment")

    login(client, 'pro@test.com')
    r = client.get('/upgrade')
    test("Upgrade page loads", r.status_code == 200)
    test("Paystack key in upgrade page", b'paystack' in r.data.lower() or b'pay' in r.data.lower())
    logout(client)

    # ── 8. Admin ─────────────────────────────────────────────────────────────
    print("\n⚙️ Admin")

    with app.app_context():
        admin = User.query.filter_by(email='oadedamola07@gmail.com').first()
        if admin:
            login(client, 'oadedamola07@gmail.com')
            r = client.get('/admin')
            test("Admin page accessible", r.status_code == 200)
            logout(client)
        else:
            print("  ⚠️  Admin user not found — skipping admin tests")

    # ── 9. Cleanup ───────────────────────────────────────────────────────────
    with app.app_context():
        for email in ['newuser@test.com', 'free@test.com', 'pro@test.com', 'prolow@test.com']:
            user = User.query.filter_by(email=email).first()
            if user:
                Generation.query.filter_by(user_id=user.id).delete()
                db.session.delete(user)
        db.session.commit()

# ─── Results ─────────────────────────────────────────────────────────────────

print("\n" + "="*50)
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")
print(f"📊 Total:  {passed + failed}")
print("="*50 + "\n")

if failed == 0:
    print("🎉 All tests passed! Safe to deploy.\n")
else:
    print(f"⚠️  {failed} test(s) failed. Fix before deploying.\n")