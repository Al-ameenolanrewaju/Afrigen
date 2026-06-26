"""
Publish an article to Hashnode via the Hashnode GraphQL API (gql.hashnode.com).

The canonical URL MUST point back to afrigen.com.ng/blog/{slug} to protect SEO —
Hashnode's `originalArticleURL` marks the Afrigen post as the original source.

Secrets required:
  HASHNODE_API_TOKEN       — From https://hashnode.com/settings/developer ("Personal Access Tokens")
  HASHNODE_PUBLICATION_ID  — Your publication's ID. Find it in your blog dashboard URL
                             (hashnode.com/<publication-id>/dashboard) or via the
                             `me { publications { edges { node { id } } } }` query.

API docs: https://apidocs.hashnode.com/  (mutation: publishPost)
"""

import os
import re
import requests


HASHNODE_API = "https://gql.hashnode.com/"

_PUBLISH_MUTATION = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post {
      id
      slug
      url
    }
  }
}
"""


def _slugify(tag: str) -> str:
    """Hashnode tag slugs must be lowercase alphanumeric with dashes."""
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def publish_article(title: str, content: str, tags: list[str],
                    canonical_url: str, subtitle: str = "") -> dict:
    """Publish a Markdown article on Hashnode with a canonical URL back to Afrigen.

    Args:
        title: Article title.
        content: Article body in Markdown.
        tags: Up to 5 topic tags.
        canonical_url: The original blog URL on afrigen.com.ng (SEO canonical).
        subtitle: Optional subtitle.

    Returns:
        {ok: bool, post_id, post_url, error}
    """
    api_token = os.environ.get("HASHNODE_API_TOKEN", "")
    publication_id = os.environ.get("HASHNODE_PUBLICATION_ID", "")

    # Verify credentials are present and log (masked) what we resolved so a
    # misconfigured environment is obvious in the logs without leaking secrets.
    if not api_token or not publication_id:
        missing = []
        if not api_token:
            missing.append("HASHNODE_API_TOKEN")
        if not publication_id:
            missing.append("HASHNODE_PUBLICATION_ID")
        print(f"[hashnode] ❌ missing credentials: {', '.join(missing)}")
        # Graceful skip — missing credentials must not crash the pipeline.
        return {
            "ok": False,
            "error": f"Missing {' and '.join(missing)}",
            "post_id": None,
            "post_url": None,
        }

    masked_token = f"{api_token[:4]}...{api_token[-4:]}" if len(api_token) > 8 else "set"
    print(f"[hashnode] credentials OK (token={masked_token}, publicationId={publication_id})")

    # Hashnode wants tags as {slug, name} objects, max 5.
    tag_objs = []
    for t in (tags or [])[:5]:
        slug = _slugify(t)
        if slug:
            tag_objs.append({"slug": slug, "name": t})

    article_input = {
        "title": title,
        "publicationId": publication_id,
        "contentMarkdown": content,
        "tags": tag_objs,
        "originalArticleURL": canonical_url,
    }
    if subtitle:
        article_input["subtitle"] = subtitle[:250]

    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }

    # Log the GraphQL payload (without the full markdown body, which is noisy)
    # so we can confirm the mutation variables are well-formed.
    print(
        f"[hashnode] publishing '{title}' "
        f"(content={len(content)} chars, tags={[t['slug'] for t in tag_objs]}, "
        f"canonical={canonical_url})"
    )

    try:
        resp = requests.post(
            HASHNODE_API,
            headers=headers,
            json={"query": _PUBLISH_MUTATION, "variables": {"input": article_input}},
            timeout=20,
        )

        # Log HTTP status + raw body BEFORE parsing — a non-2xx or non-JSON body
        # (HTML error page, empty response, gateway error) is what produces the
        # "Expecting value: line 1 column 1 (char 0)" JSON decode error.
        raw_body = resp.text or ""
        print(f"[hashnode] HTTP {resp.status_code} ({len(raw_body)} bytes)")
        print(f"[hashnode] response body: {raw_body[:1000]}")

        # GraphQL normally returns 200 with a JSON body. Guard the parse so a
        # non-JSON response surfaces the status + a concise reason instead of a
        # cryptic JSONDecodeError. When the body is HTML (e.g. Hashnode's
        # "GraphQL API is moving to a paid offering" notice page), extract the
        # <title> so the admin report stays readable instead of dumping markup.
        try:
            data = resp.json()
        except ValueError:
            title_match = re.search(r"<title>(.*?)</title>", raw_body, re.IGNORECASE | re.DOTALL)
            if title_match:
                reason = f"HTML page: \"{title_match.group(1).strip()}\""
            else:
                reason = raw_body[:300] or "<empty body>"
            print(f"[hashnode] non-JSON response - {reason}")
            return {
                "ok": False,
                "error": f"Hashnode returned non-JSON response (HTTP {resp.status_code}): {reason}",
                "post_id": None,
                "post_url": None,
            }

        # GraphQL returns 200 even on errors — check the `errors` array.
        if data.get("errors"):
            errors = data["errors"]
            error_msg = "; ".join(
                e.get("message", str(e)) for e in errors
            ) or str(errors)
            print(f"[hashnode] GraphQL errors: {error_msg}")
            return {
                "ok": False,
                "error": f"Hashnode API error: {error_msg}",
                "post_id": None,
                "post_url": None,
            }

        post = (data.get("data") or {}).get("publishPost", {}).get("post")
        if post:
            post_id = post.get("id", "")
            post_url = post.get("url", "")
            print(f"[hashnode] published (id={post_id}) url={post_url}")
            return {"ok": True, "post_id": post_id, "post_url": post_url, "error": None}

        return {
            "ok": False,
            "error": f"Hashnode unexpected response ({resp.status_code}): {data}",
            "post_id": None,
            "post_url": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Hashnode exception: {e}",
            "post_id": None,
            "post_url": None,
        }
