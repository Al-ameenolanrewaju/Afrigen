import json
import os
import random
from typing import List, Dict, Any
from datetime import datetime
from .models import ContentCategory

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "content_history.json")

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
        return {"categories": [], "topics": [], "last_run": None}

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
        """
        Select a category avoiding the most recently used ones.
        """
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
        self.history["last_run"] = datetime.utcnow().isoformat()
        self._save_history()
        
        from .utils import get_logger
        logger = get_logger("Planner")
        logger.info(f"Selected Category: {selected.value}")
        return selected

    def record_topic(self, topic: str):
        """
        Record a used topic to avoid repeating it too soon.
        """
        self.history.setdefault("topics", []).append(topic)
        self._save_history()

    def is_topic_recent(self, topic: str, limit: int = 10) -> bool:
        """
        Check if a topic was used recently.
        """
        recent_topics = self.history.get("topics", [])[-limit:]
        for t in recent_topics:
            if topic.lower() in t.lower() or t.lower() in topic.lower():
                return True
        return False
