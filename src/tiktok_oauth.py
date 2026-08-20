"""Local OAuth callback server for TikTok Marketing API authorization."""

from __future__ import annotations

import hmac
import http.server
import json
import time
from collections.abc import Callable, Mapping
from secrets import token_urlsafe
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


AUTHORIZATION_URL = "https://ads.tiktok.com/marketing_api/auth"
TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
DEFAULT_REDIRECT_URI = "http://localhost:3000/api/oauth/tiktok/callback"


class OAuthStateStore:
    """Hold a short-lived, single-use OAuth state value only in memory."""

    def __init__(self, ttl_seconds: int = 300, clock: Callable[[], float] | None = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._states: dict[str, float] = {}

    def put(self, state: str | None = None) -> str:
        value = state or token_urlsafe(32)
        self._states[value] = self._clock() + self._ttl_seconds
        return value

    def consume(self, candidate: str | None) -> bool:
        if not candidate:
            return False
        matched = next((state for state in self._states if hmac.compare_digest(state, candidate)), None)
        if matched is None:
            return False
        expires_at = self._states.pop(matched)
        return self._clock() <= expires_at


def build_authorization_url(
    app_id: str,
    *,
    state: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> str:
    if not app_id or not state or not redirect_uri:
        raise ValueError("app_id, state and redirect_uri are required")
    return f"{AUTHORIZATION_URL}?{urlencode({'app_id': app_id, 'state': state, 'redirect_uri': redirect_uri})}"


def extract_access_token(response: Mapping[str, Any]) -> str | None:
    data = response.get("data")
    if isinstance(data, Mapping):
        value = data.get("access_token")
        if isinstance(value, str) and value:
            return value
    return None


def _query_value(params: Mapping[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values and values[0] else None


def _exchange_access_token(app_id: str, app_secret: str, auth_code: str) -> str:
    request = Request(
        TOKEN_URL,
        data=json.dumps({"app_id": app_id, "secret": app_secret, "auth_code": auth_code}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
    except (HTTPError, URLError, OSError) as error:
        raise RuntimeError("TikTok token exchange failed") from error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("TikTok token exchange returned invalid JSON") from error
    if not isinstance(payload, Mapping):
        raise RuntimeError("TikTok token exchange returned invalid data")
    token = extract_access_token(payload)
    if not token:
        raise RuntimeError("TikTok token exchange returned no access token")
    return token


def create_local_server(
    *,
    app_id: str,
    app_secret: str,
    on_access_token: Callable[[str], None],
    host: str = "127.0.0.1",
    port: int = 3000,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> http.server.ThreadingHTTPServer:
    """Serve one interactive authorization flow; credentials remain process-only."""

    state_store = OAuthStateStore()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/oauth/tiktok/start":
                state = state_store.put()
                self.send_response(302)
                self.send_header("Location", build_authorization_url(app_id, state=state, redirect_uri=redirect_uri))
                self.end_headers()
                return
            if parsed.path != "/api/oauth/tiktok/callback":
                self._send_text(404, "Not found")
                return

            params = parse_qs(parsed.query, keep_blank_values=True)
            state = _query_value(params, "state")
            auth_code = _query_value(params, "auth_code")
            if not state_store.consume(state) or not auth_code or _query_value(params, "error"):
                self._send_text(400, "TikTok 授权回调无效、过期或被拒绝。")
                return
            try:
                on_access_token(_exchange_access_token(app_id, app_secret, auth_code))
            except Exception:
                self._send_text(502, "TikTok 授权完成，但创意明细下载失败；原有报表未覆盖。")
                return
            self._send_text(200, "TikTok 授权与创意明细下载已完成，可以关闭此页面。")

        def _send_text(self, status: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
