from services.email import get_newsletter_email_html, _newsletter_plain_text


def test_newsletter_email_uses_magazine_frame_and_unsubscribe_link():
    markup = get_newsletter_email_html(
        '<h1>Cover story</h1><p>A useful editorial insight.</p>',
        "https://afrigen.com.ng/unsubscribe/test-token",
    )
    assert "The Creator Intelligence Brief" in markup
    assert "max-width:680px" in markup
    assert "Cover story" in markup
    assert "https://afrigen.com.ng/unsubscribe/test-token" in markup


def test_newsletter_plain_text_fallback_is_readable():
    text = _newsletter_plain_text(
        "<h1>Cover story</h1><p>A useful editorial insight.</p>"
    )
    assert "Cover story" in text
    assert "A useful editorial insight." in text
