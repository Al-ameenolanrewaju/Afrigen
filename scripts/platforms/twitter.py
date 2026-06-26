"""
Post a thread to Twitter/X via the Twitter API v2.

X free-tier API v2 only allows posting tweets — no media uploads, no thread
endpoint. So we post each tweet as a reply to the previous one to build the
thread manually.

Secrets required:
  TWITTER_API_KEY        — from Twitter Developer Portal > Project & Apps > Keys and tokens > API Key
  TWITTER_API_SECRET     — from same page > API Key Secret
  TWITTER_ACCESS_TOKEN   — from same page > Access Token
  TWITTER_ACCESS_SECRET  — from same page > Access Token Secret

Get them at: https://developer.twitter.com/en/portal/dashboard
"""

import os
import requests


def post_thread(tweets: list[str]) -> dict:
    """Post a thread of tweets. Each tweet replies to the previous one so they
    appear as a connected thread on X.

    Args:
        tweets: list of tweet texts, each <= 280 chars.

    Returns:
        {ok: bool, tweet_ids: [str, ...], error: str|None}
    """
    if not tweets:
        return {"ok": False, "error": "No tweets provided", "tweet_ids": []}

    # OAuth 1.0a is required for posting. Use requests_oauthlib if available,
    # otherwise do a direct OAuth 1.0a signing.
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        return {
            "ok": False,
            "error": "requests_oauthlib not installed. Run: pip install requests_oauthlib",
            "tweet_ids": [],
        }

    api_key = os.environ.get("TWITTER_API_KEY", "")
    api_secret = os.environ.get("TWITTER_API_SECRET", "")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

    if not all([api_key, api_secret, access_token, access_secret]):
        return {
            "ok": False,
            "error": "Missing Twitter credentials (TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)",
            "tweet_ids": [],
        }

    auth = OAuth1(
        api_key, api_secret, access_token, access_secret,
        signature_type="auth_header",
    )

    tweet_ids = []
    previous_id = None

    for i, text in enumerate(tweets):
        payload = {"text": text}
        if previous_id:
            payload["reply"] = {"in_reply_to_tweet_id": previous_id}

        try:
            resp = requests.post(
                "https://api.twitter.com/2/tweets",
                json=payload,
                auth=auth,
                timeout=15,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                tid = data["data"]["id"]
                tweet_ids.append(tid)
                previous_id = tid
                print(f"[twitter] tweet {i+1}/{len(tweets)} posted (id={tid})")
            else:
                error_detail = data.get("detail", data.get("errors", str(data)))
                return {
                    "ok": False,
                    "error": f"Tweet {i+1} failed: {error_detail}",
                    "tweet_ids": tweet_ids,
                }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Tweet {i+1} exception: {e}",
                "tweet_ids": tweet_ids,
            }

    return {"ok": True, "tweet_ids": tweet_ids, "error": None}


# ---------------------------------------------------------------------------
# Build tweet URLs for reporting
# ---------------------------------------------------------------------------

def tweet_url(tweet_id: str) -> str:
    username = "Alameenwaju"  # The account handle (without @)
    return f"https://x.com/{username}/status/{tweet_id}"
