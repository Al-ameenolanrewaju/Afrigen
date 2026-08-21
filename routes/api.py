from flask import Blueprint, jsonify, abort, request

api = Blueprint('api', __name__)


@api.route('/status')
def status():
    return jsonify({
        "status": "online",
        "platform": "Afrigen",
        "tagline": "African Creates, AI Generates"
    })


@api.route('/blog/<slug>')
def blog_json(slug):
    """Public JSON endpoint for a single PUBLISHED blog post.

    Used by the GitHub Actions content distribution script to fetch blog content
    without scraping HTML. Only returns published posts — drafts 404.
    """
    from services.blog import get_post
    post = get_post(slug)
    if not post:
        abort(404)

    return jsonify({
        "ok": True,
        "post": {
            "id": post.id,
            "slug": post.slug,
            "title": post.title,
            "description": post.description,
            "body": post.body,
            "tag": post.tag,
            "read_time": post.read_time,
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "url": f"https://afrigen.com.ng/blog/{post.slug}",
        },
    })
