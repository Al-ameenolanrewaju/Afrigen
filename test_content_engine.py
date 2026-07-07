import os
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock

from content_engine import (
    ContentPlanner,
    generate_content_brief,
    ContentCategory,
    write_facebook_post,
    write_linkedin_post,
    write_telegram_post,
    write_newsletter,
    write_devto_article
)
from content_engine.models import ContentBrief
from content_engine.validators import (
    validate_facebook, validate_linkedin, validate_telegram, validate_newsletter, validate_devto
)
from content_engine.utils import generate_with_validation

# --- History and Planner Tests ---

def test_planner_selects_category():
    # Use an isolated history object
    planner = ContentPlanner()
    planner.history = {"categories": [], "topics": [], "last_run": None}
    
    cat = planner.select_category()
    assert isinstance(cat, ContentCategory)
    assert len(planner.history["categories"]) == 1

def test_planner_topic_recent():
    planner = ContentPlanner()
    planner.history = {"topics": ["AI video generation tips"], "categories": [], "last_run": None}
    
    assert planner.is_topic_recent("AI video generation") is True
    assert planner.is_topic_recent("Something completely different") is False

# --- Validators Tests ---

@patch('content_engine.validators.ContentPlanner')
def test_facebook_validator(mock_planner_class):
    mock_planner = MagicMock()
    mock_planner.is_topic_recent.return_value = False
    mock_planner_class.return_value = mock_planner

    # Length test
    long_text = "a" * 3001
    assert validate_facebook(long_text)[0] is False
    
    # Link count test
    text_no_links = "Hello world"
    assert validate_facebook(text_no_links, "http://afrigen.com")[0] is False
    
    text_one_link = "Hello http://afrigen.com"
    assert validate_facebook(text_one_link, "http://afrigen.com")[0] is True

def test_linkedin_validator():
    # Emoji count
    many_emojis = "😀 😀 😀 😀 😀 😀 😀 😀 😀 😀 😀"
    assert validate_linkedin(many_emojis)[0] is False
    
    # Missing required CTA
    text = "Professional content."
    assert validate_linkedin(text, "http://afrigen.com")[0] is False
    
    # Valid CTA
    text_valid = "Professional content. http://afrigen.com"
    assert validate_linkedin(text_valid, "http://afrigen.com")[0] is True

def test_telegram_validator():
    short_text = "Hello " * 10
    long_text = "Hello " * 300
    assert validate_telegram(short_text)[0] is True
    assert validate_telegram(long_text)[0] is False

def test_newsletter_validator():
    valid = '<div><h3>Welcome</h3><p>Text</p><a href="http://link.com">Link</a></div>'
    invalid = "Just plain text"
    assert validate_newsletter(valid)[0] is True
    assert validate_newsletter(invalid)[0] is False

def test_devto_validator():
    valid = '{"title": "Test Title", "body": "Some article content"}'
    invalid = "   "
    assert validate_devto(valid)[0] is True
    assert validate_devto(invalid)[0] is False

# --- Brief Generator and Writers Mock Tests ---

@patch('content_engine.brief_generator.generate_with_llm')
def test_generate_content_brief(mock_llm):
    mock_llm.return_value = '{"topic": "AI", "audience": "Creators", "goal": "Awareness", "key_message": "Use AI", "key_insight": "AI is good", "call_to_action": "Try Afrigen", "suggested_tone": "Helpful", "supporting_facts": []}'
    
    brief = generate_content_brief(ContentCategory.BLOG_POST, "Some blog text")
    assert brief.topic == "AI"
    assert brief.key_message == "Use AI"

@patch('content_engine.utils.generate_with_llm')
def test_generate_with_validation_success(mock_llm):
    mock_llm.return_value = "Valid text"
    def dummy_validator(text, *args):
        return True, ""
        
    result = generate_with_validation("sys", "usr", dummy_validator)
    assert result == "Valid text"
    assert mock_llm.call_count == 1

@patch('content_engine.utils.generate_with_llm')
def test_generate_with_validation_retry(mock_llm):
    # Fails first time, succeeds second time
    mock_llm.side_effect = ["Invalid text", "Valid text"]
    
    def dummy_validator(text, *args):
        return (text == "Valid text", "Reason")
        
    result = generate_with_validation("sys", "usr", dummy_validator)
    assert result == "Valid text"
    assert mock_llm.call_count == 2
