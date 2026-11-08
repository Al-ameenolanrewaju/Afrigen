from datetime import datetime, timezone

from app import app
from models import db, WebsiteVisit
from models import User


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_visit_tracks_utm_source_once_per_session():
    client = app.test_client()

    response = client.get('/?utm_source=Facebook%20Ads')
    assert response.status_code == 200
    client.get('/')

    with client.session_transaction() as browser_session:
        browser_session['_website_visit_at'] = datetime.now(timezone.utc).timestamp() - 31 * 60
    client.get('/')

    with app.app_context():
        visits = WebsiteVisit.query.all()
        assert len(visits) == 2
        assert visits[0].source == 'facebook-ads'
        assert visits[0].landing_page == '/'


def test_visit_tracks_external_referrer_host():
    response = app.test_client().get('/', headers={'Referer': 'https://news.example/story'})

    assert response.status_code == 200
    with app.app_context():
        visit = WebsiteVisit.query.one()
        assert visit.source == 'news.example'


def test_visit_uses_direct_source_without_campaign_or_external_referrer():
    response = app.test_client().get('/')

    assert response.status_code == 200
    with app.app_context():
        visit = WebsiteVisit.query.one()
        assert visit.source == 'direct'


def test_admin_page_survives_missing_website_visits_table(monkeypatch):
    from routes import main as main_routes

    monkeypatch.setattr(main_routes, 'is_admin_user', lambda user: True)
    with app.app_context():
        admin = User(username='admin', email='admin@example.com', password='hash')
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        WebsiteVisit.__table__.drop(db.engine)

    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session['_user_id'] = str(admin_id)
        browser_session['_fresh'] = True

    response = client.get('/admin')

    assert response.status_code == 200
    assert b'Website Visits' in response.data
    assert any(
        rule.endpoint == 'main.admin_provider_status'
        for rule in app.url_map.iter_rules()
    )