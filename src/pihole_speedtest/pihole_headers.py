from __future__ import annotations

from urllib.parse import urlparse


class HeaderPolicyError(ValueError):
    """Raised when Pi-hole's header policy cannot be changed safely."""


def _origin(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HeaderPolicyError(
            "companion URL must be an HTTP(S) origin without a path, "
            "credentials, query, or fragment"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise HeaderPolicyError(f"companion URL has an invalid port: {exc}") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port_text = f":{port}" if port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port_text}"


def allow_companion_frame(headers: list[str], companion_url: str) -> list[str]:
    """Return Pi-hole headers with one exact companion frame source allowed."""
    origin = _origin(companion_url)
    if not isinstance(headers, list) or not all(isinstance(item, str) for item in headers):
        raise HeaderPolicyError("Pi-hole webserver headers must be an array of strings")

    matches = [
        index
        for index, header in enumerate(headers)
        if header.lower().startswith("content-security-policy:")
    ]
    if len(matches) != 1:
        raise HeaderPolicyError(
            "expected exactly one Pi-hole Content-Security-Policy header"
        )

    index = matches[0]
    name, policy = headers[index].split(":", 1)
    directives = [item.strip() for item in policy.split(";") if item.strip()]
    directive_names = [item.split(None, 1)[0].lower() for item in directives]
    if "frame-src" in directive_names:
        raise HeaderPolicyError(
            "Pi-hole Content-Security-Policy already defines frame-src"
        )

    try:
        insert_at = directive_names.index("frame-ancestors")
    except ValueError:
        insert_at = len(directives)
    directives.insert(insert_at, f"frame-src {origin}")

    changed = list(headers)
    changed[index] = f"{name}: {'; '.join(directives)}"
    return changed
