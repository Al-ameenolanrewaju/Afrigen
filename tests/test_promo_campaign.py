from services.promo_campaign import publish_prepared_campaign


def test_instagram_is_reported_as_prepared_not_published():
    result = publish_prepared_campaign(
        "Launch announcement",
        {"instagram": "Our reviewed launch caption."},
        ["instagram"],
        "https://example.com/flyer.png",
    )

    instagram = result["platforms"]["instagram"]
    assert instagram["ok"] is False
    assert instagram["status"] == "prepared"
    assert "Not published" in instagram["note"]
    assert instagram["caption"] == "Our reviewed launch caption."


def test_missing_reviewed_copy_is_reported_as_failure():
    result = publish_prepared_campaign("Launch", {}, ["facebook"])

    facebook = result["platforms"]["facebook"]
    assert facebook["ok"] is False
    assert "No reviewed copy" in facebook["error"]


def test_facebook_publisher_result_is_returned_unchanged():
    expected = {"ok": True, "post_id": "page-post-123"}
    from unittest.mock import patch

    with patch("platforms.facebook.post_to_page", return_value=expected):
        result = publish_prepared_campaign(
            "Launch",
            {"facebook": "Reviewed Facebook post."},
            ["facebook"],
        )

    assert result["platforms"]["facebook"] == expected
