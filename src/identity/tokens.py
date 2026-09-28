"""One-time tokens: printed or sent once, stored only as a hash (DL-0231)."""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> str:
    """A fresh token, 43 URL-safe characters; the caller shows it once and keeps only its hash."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The stored form of a token: SHA-256 in hex."""
    return hashlib.sha256(token.encode()).hexdigest()
