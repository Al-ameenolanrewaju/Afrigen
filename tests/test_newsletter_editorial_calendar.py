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



def test_newsletter_prompt_never_includes_unverified_community_metrics():
    from types import SimpleNamespace
    from content_engine.prompts.newsletter_prompt import get_newsletter_user_prompt

    brief = SimpleNamespace(
        topic="AI workflows",
        goal="Teach a practical workflow",
        key_message="Start with a clear brief",
        key_insight="Specific inputs improve outputs",
        suggested_tone="Practical",
        call_to_action="Try the workflow",
    )
    prompt = get_newsletter_user_prompt(
        brief=brief,
        features_block="",
        posts_block="",
        users=0,
        generations=0,
        date_str="November 17, 2026",
    )
    assert "Registered users: 0" not in prompt
    assert "Total generations: 0" not in prompt
    assert "Do not include creator counts" in prompt
