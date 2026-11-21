"""Signature verification for the Crew_Webhook (``POST /api/apps/stupid-code/crew``).

``verify_crew_signature`` is a pure function: it reads no environment variable, does no
I/O, and logs nothing. It returns ``None`` for a valid request and raises
``InvalidSignature`` otherwise. The exception carries a fixed message and never holds the
secret, a header value, a computed value, or the signed string.

Two schemes are accepted. Rules, in order; the first rule that applies decides:

1. ``now`` must be a timezone-aware ``datetime`` with a zero UTC offset.
2. ``X-Kiro-Signature`` (header names match case-insensitively). More than one value
   rejects. Exactly one value decides alone: it must be ``sha256=<64 lower-case hex>``,
   the HMAC-SHA256 of the raw body keyed with the secret. ``X-Crew-Proxy`` is then never
   read, so it cannot rescue an invalid ``X-Kiro-Signature``.
3. Otherwise ``X-Crew-Proxy``: zero values (neither header present) or more than one value
   rejects.
4. The value must be ``<timestamp>:<64 lower-case hex>`` with a 10 to 12 digit decimal
   Unix-seconds timestamp.
5. The timestamp must be at most ``CREW_SKEW_SECONDS`` (60) from ``now``.
6. The HMAC must equal HMAC-SHA256 of
   ``f"{timestamp}:{METHOD}:{path_with_query}:{sha256hex(raw_body)}"`` keyed with the secret.

Every comparison uses ``hmac.compare_digest`` on ASCII strings.

``headers`` is a sequence of raw ``(name, value)`` string pairs (for example
``request.headers.raw`` decoded as Latin-1), so a repeated header stays visible.
``path_with_query`` is the request path as received, followed by ``?`` and the raw query
string when the query string is non-empty.
"""

import hashlib
import hmac
import re
from collections.abc import Sequence
from datetime import datetime, timedelta

__all__ = ["CREW_SKEW_SECONDS", "InvalidSignature", "verify_crew_signature"]

CREW_SKEW_SECONDS = 60

_KIRO_HEADER = "x-kiro-signature"
_PROXY_HEADER = "x-crew-proxy"
_KIRO_PATTERN = re.compile(r"sha256=([0-9a-f]{64})")
_PROXY_PATTERN = re.compile(r"([0-9]{10,12}):([0-9a-f]{64})")


class InvalidSignature(Exception):
    """Raised for every rejection. Carries no header value, signature, or signed string."""

    def __init__(self) -> None:
        super().__init__("invalid signature")


def _values(headers: Sequence[tuple[str, str]], name: str) -> list[str]:
    return [value for key, value in headers if key.lower() == name]


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_crew_signature(
    secret: str,
    headers: Sequence[tuple[str, str]],
    method: str,
    path_with_query: str,
    raw_body: bytes,
    now: datetime,
) -> None:
    """Return ``None`` when the request is authentic, else raise ``InvalidSignature``."""
    if not isinstance(secret, str) or not secret:
        raise InvalidSignature()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise InvalidSignature()

    kiro_values = _values(headers, _KIRO_HEADER)
    if len(kiro_values) > 1:
        raise InvalidSignature()
    if len(kiro_values) == 1:
        match = _KIRO_PATTERN.fullmatch(kiro_values[0])
        if match is None:
            raise InvalidSignature()
        if not hmac.compare_digest(match.group(1), _hmac_hex(secret, raw_body)):
            raise InvalidSignature()
        return None

    proxy_values = _values(headers, _PROXY_HEADER)
    if len(proxy_values) != 1:
        raise InvalidSignature()
    match = _PROXY_PATTERN.fullmatch(proxy_values[0])
    if match is None:
        raise InvalidSignature()
    timestamp, received = match.group(1), match.group(2)
    if abs(int(timestamp) - int(now.timestamp())) > CREW_SKEW_SECONDS:
        raise InvalidSignature()
    body_hash = hashlib.sha256(raw_body).hexdigest()
    signed = f"{timestamp}:{method.upper()}:{path_with_query}:{body_hash}"
    if not hmac.compare_digest(received, _hmac_hex(secret, signed.encode("utf-8"))):
        raise InvalidSignature()
    return None
