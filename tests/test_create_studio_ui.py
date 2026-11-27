import pytest
from bs4 import BeautifulSoup
from app import app
from models import db, User, Generation


@pytest.fixture(autouse=True)
def setup_test_db():
    with app.app_context():
        db.create_all()
        yield
        db.session.rollback()


def _get_test_client():
    client = app.test_client()
    with app.app_context():
        user = User.query.filter_by(email="create_studio_tester@afrigen.com").first()
        if not user:
            user = User(
                username="create_tester",
                email="create_studio_tester@afrigen.com",
                password="testpassword",
                plan="creator",
                credits=100
            )
            db.session.add(user)
            db.session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
    return client


def test_create_studio_loads_default_mode():
    client = _get_test_client()
    res = client.get("/create")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Header and shortcuts
    assert soup.find("h1", string=lambda s: s and "Unified AI Creation Studio" in s)
    assert soup.find("a", href="/saved-prompts")

    # 4 distinct mode buttons
    assert soup.find("button", id="tab_video")
    assert soup.find("button", id="tab_image")
    assert soup.find("button", id="tab_animate")
    assert soup.find("button", id="tab_voice")

    # Default mode should be video
    assert "active" in soup.find("button", id="tab_video")["class"]

    # Prompt textarea exists once and is not duplicated
    textareas = soup.find_all("textarea", id="master_prompt")
    assert len(textareas) == 1

    # Enhancement toolbar exists without button overlap
    assert soup.find("button", id="btnEnhancePrompt")
    assert soup.find("span", id="refine_indicator")


def test_create_studio_url_parameter_determines_initial_mode():
    client = _get_test_client()

    # 1. Mode = image
    res_img = client.get("/create?mode=image")
    assert res_img.status_code == 200
    soup_img = BeautifulSoup(res_img.data.decode("utf-8"), "html.parser")
    assert "active" in soup_img.find("button", id="tab_image")["class"]
    assert "active" not in soup_img.find("button", id="tab_video")["class"]

    # 2. Mode = animate
    res_anim = client.get("/create?mode=animate")
    assert res_anim.status_code == 200
    soup_anim = BeautifulSoup(res_anim.data.decode("utf-8"), "html.parser")
    assert "active" in soup_anim.find("button", id="tab_animate")["class"]

    # 3. Mode = voice
    res_voice = client.get("/create?mode=voice")
    assert res_voice.status_code == 200
    soup_voice = BeautifulSoup(res_voice.data.decode("utf-8"), "html.parser")
    assert "active" in soup_voice.find("button", id="tab_voice")["class"]

    # 4. Mode alias: photo -> image
    res_photo = client.get("/create?mode=photo")
    assert res_photo.status_code == 200
    soup_photo = BeautifulSoup(res_photo.data.decode("utf-8"), "html.parser")
    assert "active" in soup_photo.find("button", id="tab_image")["class"]


def test_create_studio_has_independent_non_nested_forms():
    client = _get_test_client()
    res = client.get("/create")
    html = res.data.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Check each mode form
    video_form = soup.find("form", id="form_video")
    image_form = soup.find("form", id="form_image")
    animate_form = soup.find("form", id="form_animate")
    voice_form = soup.find("form", id="form_voice")

    assert video_form is not None
    assert image_form is not None
    assert animate_form is not None
    assert voice_form is not None

    # Verify NO nested forms
    for f in [video_form, image_form, animate_form, voice_form]:
        assert len(f.find_all("form")) == 0
        # Every POST form must carry its CSRF token, including forms submitted
        # with the native form.submit() API (which skips submit event handlers).
        csrf_field = f.find("input", {"name": "csrf_token"})
        assert csrf_field is not None
        assert csrf_field.get("value")

    # Verify form targets
    assert "/generate" in video_form["action"]
    assert "/generate-image" in image_form["action"]
    assert "/generate-from-image" in animate_form["action"]
    assert "/generate-voice" in voice_form["action"]
    assert animate_form.get("enctype") == "multipart/form-data"


def test_prompt_enhancement_endpoints():
    client = _get_test_client()

    # Test /refine-prompt for video/creative
    res1 = client.post(
        "/refine-prompt",
        json={"prompt": "African warrior in golden armor", "style": "cinematic"}
    )
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert "refined" in data1 or "refined_prompt" in data1

    # Test /refine-image-prompt for photo
    res2 = client.post(
        "/refine-image-prompt",
        json={"prompt": "Lagos sunset market portrait", "style": "realistic"}
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert "refined" in data2


def test_free_user_with_video_credits_can_see_video_button():
    client = _get_test_client()
    with app.app_context():
        user = User.query.filter_by(email="create_studio_tester@afrigen.com").first()
        user.plan = "free"
        user.credits = 100
        user.free_video_allowance = 0
        db.session.commit()

    res = client.get("/create")
    assert res.status_code == 200
    soup = BeautifulSoup(res.data.decode("utf-8"), "html.parser")
    button = soup.find("button", id="btnSubmitGeneration")
    warning = soup.find("div", id="videoAccessWarning")
    assert button is not None and not button.has_attr("hidden")
    assert warning is not None
    assert "Video generation unavailable" in warning.get_text()
