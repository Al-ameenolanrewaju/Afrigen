import json
import os
import random
from typing import List, Dict, Any
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from .models import ContentCategory

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "content_history.json")

NEWSLETTER_EDITORIAL_CALENDAR = {
    0: {"name": "AI Industry Intelligence", "category": ContentCategory.AI_NEWS,
        "angle": "Explain an important AI concept, verified development, or industry shift and its practical implications."},
    1: {"name": "Creator Education", "category": ContentCategory.EDUCATIONAL_CONTENT,
        "angle": "Teach a useful creative skill or repeatable content-production technique."},
    2: {"name": "African Creativity", "category": ContentCategory.CREATOR_STORY,
        "angle": "Explore African visual culture, storytelling, creative businesses, and the opportunities around them without inventing people or case studies."},
    3: {"name": "Tools and Workflows", "category": ContentCategory.AI_TIP,
        "angle": "Explain a practical AI tool, prompting technique, or workflow. Name a third-party tool only when verified source material is supplied."},
    4: {"name": "Creator Business", "category": ContentCategory.CASE_STUDY,
        "angle": "Explore practical creator-business models, content strategy, audience building, and digital opportunities without inventing results."},
    5: {"name": "Creative Experiments", "category": ContentCategory.USER_SHOWCASE,
        "angle": "Give readers a practical experiment, creative exercise, or workflow they can try."},
    6: {"name": "The Weekly Perspective", "category": ContentCategory.AI_NEWS,
        "angle": "Connect useful ideas and developments from the week. Use only supplied, dated sources; otherwise provide an evergreen perspective."},
}


def get_newsletter_editorial_theme(now=None):
    """Return the stable daily editorial theme using Africa/Lagos local time."""
    if now is None:
        now = datetime.now(ZoneInfo("Africa/Lagos"))
    elif isinstance(now, date) and not isinstance(now, datetime):
        now = datetime.combine(now, datetime.min.time(), tzinfo=ZoneInfo("Africa/Lagos"))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("Africa/Lagos"))
    else:
        now = now.astimezone(ZoneInfo("Africa/Lagos"))
    theme = NEWSLETTER_EDITORIAL_CALENDAR[now.weekday()]
    return {
        "day": now.strftime("%A"),
        "date": now.strftime("%B %d, %Y"),
        "name": theme["name"],
        "category": theme["category"],
        "angle": theme["angle"],
    }


class ContentPlanner:
    def __init__(self):
        self.history = self._load_history()

    def _load_history(self) -> Dict[str, Any]:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"categories": [], "topics": [], "last_run": None, "newsletter_topics": []}

    def _save_history(self):
        temp_file = HISTORY_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=4)
            os.replace(temp_file, HISTORY_FILE)
        except Exception as e:
            from .utils import get_logger
            get_logger("Planner").error(f"Failed to save history: {e}")

    def select_category(self) -> ContentCategory:
        """Select a category avoiding the most recently used ones."""
        all_categories = list(ContentCategory)
        recent_categories = []
        for c in self.history.get("categories", [])[-5:]:
            try:
                recent_categories.append(ContentCategory(c))
            except ValueError:
                pass
        available = [c for c in all_categories if c not in recent_categories]
        if not available:
            available = all_categories
        selected = random.choice(available)
        self.history.setdefault("categories", []).append(selected.value)
        self.history["last_run"] = datetime.now(timezone.utc).isoformat()
        self._save_history()
        from .utils import get_logger
        get_logger("Planner").info(f"Selected Category: {selected.value}")
        return selected

    def select_newsletter_theme(self, now=None):
        """Select the fixed daily magazine theme without changing social content planning."""
        return get_newsletter_editorial_theme(now)

    def record_newsletter_topic(self, topic: str):
        topics = self.history.setdefault("newsletter_topics", [])
        topics.append({"topic": topic, "recorded_at": datetime.now(timezone.utc).isoformat()})
        self.history["newsletter_topics"] = topics[-90:]
        self._save_history()

    def is_newsletter_topic_recent(self, topic: str, limit: int = 14) -> bool:
        candidate = (topic or "").strip().lower()
        if not candidate:
            return False
        recent = self.history.get("newsletter_topics", [])[-limit:]
        for item in recent:
            previous = item.get("topic", "") if isinstance(item, dict) else str(item)
            previous = previous.lower()
            if candidate == previous or candidate in previous or previous in candidate:
                return True
        return False

    def record_topic(self, topic: str):
        """Record a used topic to avoid repeating it too soon."""
        self.history.setdefault("topics", []).append(topic)
        self._save_history()

    def is_topic_recent(self, topic: str, limit: int = 10) -> bool:
        recent_topics = self.history.get("topics", [])[-limit:]
        for t in recent_topics:
            if topic.lower() in t.lower() or t.lower() in topic.lower():
                return True
        return False
