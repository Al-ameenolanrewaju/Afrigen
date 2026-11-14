from urllib.parse import urljoin, urlparse

import requests
from flask import Response, abort, redirect, request, stream_with_context
from werkzeug.utils import secure_filename


_MEDIA_HOSTS = ("fal.media",)
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class MediaProxyError(RuntimeError):
    pass


def _is_allowed_url(url):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and port in (None, 443)
        and any(hostname == host or hostname.endswith("." + host) for host in _MEDIA_HOSTS)
    )


def _allowed_local_path(url):
    return (
        isinstance(url, str)
        and url.startswith("/static/uploads/")
        and ".." not in url.split("/")
        and "\\" not in url
    )


def proxy_media(url, filename, content_type, as_attachment=False):
    """Stream a stored generated asset through Afrigen without exposing its CDN host."""
    if _allowed_local_path(url):
        return redirect(url)
    if not _is_allowed_url(url):
        abort(404)
    filename = secure_filename(filename) or "afrigen-media"

    upstream = None
    current_url = url
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    try:
        for _ in range(4):
            upstream = requests.get(
                current_url,
                headers=headers,
                stream=True,
                allow_redirects=False,
                timeout=(5, 120),
            )
            if upstream.status_code not in _REDIRECT_STATUSES:
                break

            location = upstream.headers.get("Location")
            upstream.close()
            next_url = urljoin(current_url, location or "")
            if not location or not _is_allowed_url(next_url):
                raise MediaProxyError("Media redirect was not allowed.")
            current_url = next_url
        else:
            raise MediaProxyError("Media redirect limit exceeded.")

        if upstream is None or upstream.status_code not in (200, 206):
            raise MediaProxyError("Media is unavailable.")

        upstream_type = upstream.headers.get("Content-Type", "").split(";", 1)[0].lower()
        expected_type = content_type.split("/", 1)[0]
        if upstream_type and upstream_type != "application/octet-stream":
            if upstream_type.split("/", 1)[0] != expected_type:
                raise MediaProxyError("Media type did not match the requested asset.")
            content_type = upstream_type

        response_headers = {
            "Content-Type": content_type,
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
                if as_attachment else f'inline; filename="{filename}"'
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        }
        for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
            if upstream.headers.get(header):
                response_headers[header] = upstream.headers[header]

        def stream():
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            stream_with_context(stream()),
            status=upstream.status_code,
            headers=response_headers,
        )
    except requests.RequestException as exc:
        if upstream is not None:
            upstream.close()
        raise MediaProxyError("Media service is unavailable.") from exc
    except Exception:
        if upstream is not None:
            upstream.close()
        raise
