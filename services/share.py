"""
Signed share tokens for public generation pages (/v/<token>).

Generations have sequential integer IDs, so exposing them directly at a public
URL would let anyone enumerate /v/1, /v/2, ... and view every user's clips. We
instead sign the ID with the app SECRET_KEY (itsdangerous), so a share link is
only valid if it was minted by us. No database column is needed.
"""
from itsdangerous import URLSafeSerializer, BadData
from flask import current_app

_SALT = "afrigen-gen-share"


def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def make_share_token(gen_id):
    """Sign a generation ID into an opaque, URL-safe token."""
    return _serializer().dumps(int(gen_id))


def load_share_token(token):
    """Return the generation ID for a valid token, or None if it's bad/forged."""
    try:
        return int(_serializer().loads(token))
    except (BadData, ValueError, TypeError):
        return None
