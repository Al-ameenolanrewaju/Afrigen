from datetime import datetime, timezone

from content_engine.models import ContentCategory
from content_engine.planner import get_newsletter_editorial_theme


def test_newsletter_editorial_calendar_covers_all_weekdays():
    expected = [
        ("AI Industry Intelligence", ContentCategory.AI_NEWS),
        ("Creator Education", ContentCategory.EDUCATIONAL_CONTENT),
        ("African Creativity", ContentCategory.CREATOR_STORY),
        ("Tools and Workflows", ContentCategory.AI_TIP),
        ("Creator Business", ContentCategory.CASE_STUDY),
        ("Creative Experiments", ContentCategory.USER_SHOWCASE),
        ("The Weekly Perspective", ContentCategory.AI_NEWS),
    ]
    for weekday, (name, category) in enumerate(expected):
        result = get_newsletter_editorial_theme(
            datetime(2026, 11, 16 + weekday, 12, 0, tzinfo=timezone.utc)
        )
        assert result["name"] == name
        assert result["category"] == category


def test_newsletter_editorial_calendar_uses_lagos_local_date():
    # 23:30 UTC on Monday is already 00:30 Tuesday in Lagos.
    result = get_newsletter_editorial_theme(
        datetime(2026, 11, 16, 23, 30, tzinfo=timezone.utc)
    )
    assert result["day"] == "Tuesday"
    assert result["name"] == "Creator Education"
