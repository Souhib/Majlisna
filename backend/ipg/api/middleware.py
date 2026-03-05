import re
import time
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

from loguru import logger
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_URL_PATH_LENGTH = 2048

# Patterns for query parameter sanitization
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_DANGEROUS_PROTOCOL_RE = re.compile(r"(javascript|vbscript|data)\s*:", re.IGNORECASE)
_PATH_TRAVERSAL_RE = re.compile(r"\.\./|\.\.\\")


def _sanitize_parameter_value(value: str) -> str:
    """Sanitize a single query parameter value against XSS/injection."""
    value = _SCRIPT_TAG_RE.sub("", value)
    value = _EVENT_HANDLER_RE.sub("", value)
    value = _DANGEROUS_PROTOCOL_RE.sub("", value)
    value = _PATH_TRAVERSAL_RE.sub("", value)
    return value


def _sanitize_query_string(query_string: str) -> str:
    """Sanitize all query parameters in a query string."""
    if not query_string:
        return query_string
    params = parse_qs(query_string, keep_blank_values=True)
    sanitized: dict[str, list[str]] = {}
    for key, values in params.items():
        sanitized_key = _sanitize_parameter_value(key)
        sanitized[sanitized_key] = [_sanitize_parameter_value(v) for v in values]
    return urlencode(sanitized, doseq=True)


class SecurityMiddleware:
    """Pure ASGI middleware that adds security headers, sanitizes input, and prevents common attacks.

    Adds the following headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security (production only)

    Rejects requests with:
    - Null bytes in URL
    - Excessively long URL paths

    Sanitizes:
    - Query parameters (removes script tags, event handlers, dangerous protocols, path traversal)
    """

    def __init__(self, app: ASGIApp, is_production: bool = False) -> None:
        self.app = app
        self.is_production = is_production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Only apply security logic to HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Input sanitization: reject null bytes in URL
        if "\x00" in path:
            logger.warning(f"Rejected request with null bytes in URL: {path[:100]}")
            response = JSONResponse(status_code=400, content={"error": "Invalid request"})
            await response(scope, receive, send)
            return

        # Input sanitization: reject overlong URL paths
        if len(path) > MAX_URL_PATH_LENGTH:
            logger.warning(f"Rejected request with overlong URL path: {len(path)} chars")
            response = JSONResponse(status_code=414, content={"error": "URI too long"})
            await response(scope, receive, send)
            return

        # Sanitize query parameters
        query_string = scope.get("query_string", b"").decode("utf-8", errors="replace")
        if query_string:
            sanitized = _sanitize_query_string(query_string)
            if sanitized != query_string:
                scope["query_string"] = sanitized.encode("utf-8")

        # Inject security headers into the response
        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-xss-protection", b"1; mode=block"))
                if self.is_production:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestIDMiddleware:
    """Pure ASGI middleware that generates a unique request ID for each request.

    Adds an X-Request-ID header to the response and stores it in scope state.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        # Store in scope state for downstream middleware/routes
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class LoggingMiddleware:
    """Pure ASGI middleware that logs request start, completion, slow requests, and errors.

    Uses loguru for structured logging of each HTTP request.
    Binds request_id and user_id to loguru context for correlation.
    """

    SLOW_REQUEST_THRESHOLD_MS = 1000

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = scope.get("state", {}).get("request_id", "N/A")
        path = scope.get("path", "")
        method = scope.get("method", "")

        # Extract user_id hint from headers
        headers_dict = dict(scope.get("headers", []))
        auth_header = headers_dict.get(b"authorization", b"").decode("utf-8", errors="replace")
        user_id = "[user] " if auth_header.startswith("Bearer ") and len(auth_header) > 10 else ""

        # Extract client IP
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        with logger.contextualize(request_id=f"[{request_id[:8]}] ", user_id=user_id):
            logger.info(
                "Request started: {method} {path}",
                method=method,
                path=path,
                client_ip=client_ip,
            )

            start_time = time.perf_counter()
            status_code = 500  # Default in case of error

            async def send_with_logging(message: dict) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                await send(message)

            try:
                await self.app(scope, receive, send_with_logging)
            except Exception:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "Request failed: {method} {path} {duration:.2f}ms",
                    method=method,
                    path=path,
                    duration=duration_ms,
                    exc_info=True,
                )
                raise

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "Request completed: {method} {path} {status_code} {duration:.2f}ms",
                method=method,
                path=path,
                status_code=status_code,
                duration=duration_ms,
            )

            if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
                logger.warning(
                    "Slow request: {method} {path} took {duration:.2f}ms",
                    method=method,
                    path=path,
                    duration=duration_ms,
                )
