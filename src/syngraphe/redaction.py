"""Credentials that travel in a text the platform keeps or prints: a link that sets a password
carries its token in the path, a credential while it is valid (DL-0406). One pattern serves the
outbox, the application's log and Gunicorn's access log; the front's configuration, which
Python does not reach, keeps its own copy of the alternation, held to this one by a test."""

from __future__ import annotations

import re

CREDENTIAL_LINK = re.compile(r"(/(?:invitation|reset)/)[^/\s?\"']+")
SPENT = r"\1…"


def without_credentials(text: str) -> str:
    """`text` with every credential link's token replaced; the rest kept."""
    return CREDENTIAL_LINK.sub(SPENT, text)
