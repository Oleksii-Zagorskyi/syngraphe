"""Fixtures for the mail tests: an SMTP server in the test process that records what it accepts and
refuses on command; a `sender` that writes a sending address pointed at it in a given schema; and
the review tests' document, groups, versions and cast, loaded from their own conftest so the
folders build documents alike.

People, groups, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import importlib.util
import socket
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "mail_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

Cast = _review.Cast
new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version
cast = _review.cast

SINK_PASSWORD = "synthetic-sink-password"


@dataclass
class Received:
    """One message as the sink saw it: the envelope and the parsed message."""

    mail_from: str
    rcpt_tos: list[str]
    message: EmailMessage

    @property
    def body(self) -> str:
        part = self.message.get_body(preferencelist=("plain",))
        assert part is not None
        return str(part.get_content())


@dataclass
class Sink:
    """The handler of the in-process SMTP server. `refuse_next = N` refuses the next N messages
    with a `451`; `always_refuse` refuses every one; `delay` holds each message that long before
    answering. `messages` holds what was accepted, `refused` the recipients of each refusal."""

    port: int = 0
    refuse_next: int = 0
    always_refuse: bool = False
    delay: float = 0.0
    messages: list[Received] = field(default_factory=list)
    refused: list[list[str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        if self.delay:
            await asyncio.sleep(self.delay)
        with self.lock:
            if self.always_refuse or self.refuse_next > 0:
                if self.refuse_next > 0:
                    self.refuse_next -= 1
                self.refused.append(list(envelope.rcpt_tos))
                return "451 4.3.0 Synthetic refusal, try again later"
            content = envelope.content
            if isinstance(content, str):
                content = content.encode("utf-8")
            parsed = email.message_from_bytes(content, policy=email.policy.default)
            assert isinstance(parsed, EmailMessage)
            self.messages.append(Received(str(envelope.mail_from), list(envelope.rcpt_tos), parsed))
        return "250 OK"

    def refusals_to(self, recipient: str) -> int:
        return sum(1 for rcpt in self.refused if recipient in rcpt)


def _free_port() -> int:
    # `port=0` cannot be given to the controller: it connects to its own port to see it is up.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def sink() -> Iterator[Sink]:
    """An SMTP server on a free local port, stopped when the test ends."""
    from aiosmtpd.controller import Controller

    handler = Sink(port=_free_port())
    controller = Controller(handler, hostname="127.0.0.1", port=handler.port)
    controller.start()
    try:
        yield handler
    finally:
        controller.stop()


@pytest.fixture
def sender(sink: Sink) -> Callable[..., Any]:
    """`sender(schema, **fields)`: a `MailSender` written in the tenant schema numbered `schema`,
    or in the shared schema for `None`, pointed at the sink with no sign-in and no encryption
    unless `fields` say otherwise; returned."""

    def make(schema: int | None, **fields: Any) -> Any:
        from mail import secrets
        from mail.models import MailSender, Security

        values: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": sink.port,
            "address": (
                "platform.sender@example.test"
                if schema is None
                else f"tenant{schema}.sender@example.test"
            ),
            "display_name": "Synthetic mailing list",
            "username": "",
            "security": Security.NONE,
        }
        values.update(fields)
        if "password_encrypted" not in values:
            values["password_encrypted"] = secrets.encrypt(SINK_PASSWORD)
        with schema_context(schema):
            return MailSender.objects.create(**values)

    return make


@pytest.fixture
def signing_sink() -> Iterator[Sink]:
    """An SMTP server that offers sign-in and accepts only `SINK_PASSWORD`, on a free local
    port; what it accepts and refuses is recorded as `sink`'s is."""
    from aiosmtpd.controller import Controller
    from aiosmtpd.smtp import AuthResult, LoginPassword

    def authenticate(server: Any, session: Any, envelope: Any, mechanism: str, data: Any) -> Any:
        ok = isinstance(data, LoginPassword) and data.password.decode() == SINK_PASSWORD
        return AuthResult(success=ok)

    handler = Sink(port=_free_port())
    controller = Controller(
        handler,
        hostname="127.0.0.1",
        port=handler.port,
        authenticator=authenticate,
        auth_require_tls=False,
    )
    controller.start()
    try:
        yield handler
    finally:
        controller.stop()
