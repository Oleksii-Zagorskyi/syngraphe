"""The sending-address form and its saving, on either page (DL-0202, DL-0388, DL-0390, DL-0392): the
stored password reaches only the server it was entered for; a replacement is audited, never its
value; names and addresses in any script are carried as the mail needs them; a test reports the
steps it made, freshly, one at a time; the outbox shows its newest 200 emails.

People, addresses and passwords are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import re
import time
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/platform/mail/"
# The password `tests/mail/conftest.py`'s signing sink accepts.
SINK_PASSWORD = "synthetic-sink-password"


@pytest.fixture
def operator(member_of: Any) -> Any:
    client, _, _ = member_of("o.synthetic@example.test", is_platform_admin=True)
    return client


@pytest.fixture
def queued_tests(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    queued: list[Any] = []
    monkeypatch.setattr("mail.tasks.test_sender.delay", lambda *args: queued.append(args))
    return queued


def form(**changed: Any) -> dict[str, Any]:
    values = {
        "action": "save",
        "host": "smtp.example.test",
        "port": "587",
        "address": "platform.sender@example.test",
        "display_name": "Synthetic platform",
        "username": "platform.sender@example.test",
        "password": "",
        "security": "starttls",
    }
    values.update(changed)
    return values


def stored(**fields: Any) -> Any:
    from mail import secrets
    from mail.models import MailSender, Security

    values = {
        "host": "smtp.example.test",
        "port": 587,
        "address": "platform.sender@example.test",
        "display_name": "Synthetic platform",
        "username": "platform.sender@example.test",
        "password_encrypted": secrets.encrypt("stored-synthetic-password"),
        "security": Security.STARTTLS,
    }
    values.update(fields)
    with schema_context(None):
        return MailSender.objects.create(**values)


@pytest.mark.parametrize(
    "changed",
    [{"host": "elsewhere.example.test"}, {"port": "2525"}, {"security": "tls"}, {"username": "x"}],
)
def test_the_stored_password_never_follows_a_new_server(
    operator: Any, queued_tests: list[Any], changed: dict[str, Any]
) -> None:
    """DL-0390: an empty password keeps the stored one only for the server it was entered for."""
    from mail import secrets
    from mail.models import MailSender

    stored()
    for address in (PAGE, f"{PAGE}test/"):
        refused = operator.post(address, form(**changed))
        assert refused.status_code == 200
        assert 'data-error-for="password"' in refused.content.decode()
    assert queued_tests == []
    with schema_context(None):
        row = MailSender.objects.get()
    assert row.host == "smtp.example.test" and row.port == 587
    assert secrets.decrypt(bytes(row.password_encrypted)) == "stored-synthetic-password"

    # Unchanged, the empty field keeps the stored password.
    assert operator.post(PAGE, form(display_name="Another name")).status_code == 302


def test_a_replaced_or_removed_password_is_audited_and_an_unchanged_save_is_not(
    operator: Any,
) -> None:
    from audit.models import AuditEvent

    stored()
    operator.post(PAGE, form(password="new-synthetic-password"))
    operator.post(PAGE, form(display_name="Synthetic platform"))
    operator.post(PAGE, form(username="", password="", security="starttls"))

    events = list(AuditEvent.objects.filter(action="mail.sender_saved").order_by("at"))
    assert [event.after.get("password_change") for event in events] == ["replaced", "removed"]
    for event in events:
        assert "stored-synthetic-password" not in str(event.after)
        assert "new-synthetic-password" not in str(event.after)


def test_a_password_without_a_user_name_is_not_kept(operator: Any) -> None:
    from mail.models import MailSender

    operator.post(PAGE, form(username="", password="autofilled-synthetic-password"))
    with schema_context(None):
        assert bytes(MailSender.objects.get().password_encrypted) == b""
    assert "data-password-stored" not in operator.get(PAGE).content.decode()


@pytest.mark.parametrize(
    ("field", "value", "kept"),
    [
        ("host", "пошта.приклад.укр", "xn--80a1acn3a.xn--80aikifvh.xn--j1amh"),
        ("host", "smtp.example.test.", "smtp.example.test"),
        ("host", "2001:db8::1", "2001:db8::1"),
        ("port", "1", 1),
        ("port", "65535", 65535),
        ("address", "sender@приклад.укр", "sender@xn--80aikifvh.xn--j1amh"),
    ],
)
def test_accepted_values_are_kept_as_the_mail_needs_them(
    operator: Any, field: str, value: str, kept: Any
) -> None:
    from mail.models import MailSender

    response = operator.post(PAGE, form(**{field: value, "password": "synthetic-password"}))
    assert response.status_code == 302, response.content.decode()[-800:]
    with schema_context(None):
        assert getattr(MailSender.objects.get(), field) == kept


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "::1%elsewhere.example.test"),
        ("host", "smtp.example.test:25"),
        ("username", "користувач"),
        ("address", "відправник@example.test"),
        ("display_name", "Name\x07"),
        ("port", "0"),
    ],
)
def test_refused_values_name_their_field(operator: Any, field: str, value: str) -> None:
    response = operator.post(PAGE, form(**{field: value, "password": "synthetic-password"}))
    assert response.status_code == 200
    assert f'data-error-for="{field}"' in response.content.decode()


def test_one_password_error_for_a_password_the_mail_cannot_carry(operator: Any) -> None:
    page = operator.post(PAGE, form(password="ключ")).content.decode()
    assert page.count('data-error-for="password"') == 1


def test_a_test_runs_on_the_values_just_saved_and_reports_them_freshly(
    operator: Any, sender: Any, signing_sink: Any, queued_tests: list[Any]
) -> None:
    import json

    from mail.models import MailSender
    from mail.tasks import test_sender

    old = sender(None, port=1, display_name="Стара назва")
    with schema_context(None):
        MailSender.objects.filter(pk=old.pk).update(
            last_test_result=json.dumps({"done": ["connected", "signed_in", "sent"]})
        )
    values = form(
        host="127.0.0.1",
        port=str(signing_sink.port),
        security="none",
        address=old.address,
        display_name="Нова назва",
        username="platform.sender@example.test",
        password=SINK_PASSWORD,
    )
    redirected = operator.post(f"{PAGE}test/", values)
    assert redirected.status_code == 302
    waiting = operator.get(redirected["Location"]).content.decode()
    assert "data-pending" in waiting and 'data-outcome="done"' not in waiting
    assert 'hx-get="' in waiting

    test_sender(None)
    page = operator.get(redirected["Location"]).content.decode()
    for step in ("connected", "signed_in", "sent"):
        assert f'data-step="{step}" data-outcome="done"' in page, step
    # The result in, the page stops asking for it.
    assert 'hx-get="' not in page
    [received] = signing_sink.messages
    assert "Нова назва" in str(received.message["From"])


def test_without_a_user_name_no_sign_in_is_reported(operator: Any, sender: Any, sink: Any) -> None:
    from mail.tasks import test_sender

    sender(None)
    test_sender(None)
    page = operator.get(PAGE).content.decode()
    assert 'data-step="signed_in" data-outcome="not_needed"' in page
    assert 'data-step="sent" data-outcome="done"' in page


def test_polling_ends_after_thirty_seconds_with_a_word(operator: Any, sender: Any) -> None:
    sender(None)
    page = operator.get(f"{PAGE}?testing={int(time.time()) - 31}").content.decode()
    assert 'hx-get="' not in page
    assert "data-no-result" in page


def test_one_test_at_a_time(operator: Any, sender: Any, queued_tests: list[Any]) -> None:
    """DL-0392: a second request within thirty seconds, while the first has no result, waits."""
    saved = sender(None)
    values = form(
        host=saved.host, port=str(saved.port), security="none", username="", address=saved.address
    )
    assert operator.post(f"{PAGE}test/", values).status_code == 302
    second = operator.post(f"{PAGE}test/", values)
    assert second.status_code == 200
    assert "data-test-running" in second.content.decode()
    assert len(queued_tests) == 1


def test_the_outbox_shows_its_newest_two_hundred(operator: Any) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from mail.models import EmailOutbox

    now = timezone.now()
    with schema_context(None):
        EmailOutbox.objects.bulk_create(
            EmailOutbox(
                sender="platform.sender@example.test",
                recipient=f"r{n}.synthetic@example.test",
                subject="Synthetic subject",
                body="A synthetic letter.",
                created_at=now - timedelta(seconds=n),
            )
            for n in range(201)
        )
    page = operator.get(PAGE).content.decode()
    shown = re.findall(r'data-outbox="[0-9a-f-]+"', page)
    assert len(shown) == 200
    assert "r0.synthetic@example.test" in page and "r200.synthetic@example.test" not in page
    assert "data-outbox-capped" in page


def test_a_missing_key_is_named_on_the_form(operator: Any, monkeypatch: Any) -> None:
    from mail.models import MailSender

    monkeypatch.delenv("MAIL_PASSWORD_KEY")
    response = operator.post(PAGE, form(password="synthetic-password"))
    assert response.status_code == 200
    assert "MAIL_PASSWORD_KEY" in response.content.decode()
    with schema_context(None):
        assert not MailSender.objects.exists()


def test_errors_read_as_sentences_never_as_class_names(operator: Any) -> None:
    import json

    from mail.models import EmailOutbox, MailSender

    saved = stored()
    with schema_context(None):
        MailSender.objects.filter(pk=saved.pk).update(
            last_test_result=json.dumps({"done": [], "failed": "connected", "error": "timeout"})
        )
        EmailOutbox.objects.create(
            sender=saved.address,
            recipient="r.synthetic@example.test",
            subject="Synthetic subject",
            body="A synthetic letter.",
            last_error="name_not_found",
        )
    page = operator.get(PAGE).content.decode()
    assert "TimeoutError" not in page and "gaierror" not in page
    assert 'data-error-code="timeout"' in page
    assert 'data-error-code="name_not_found"' in page


def test_a_result_never_lands_on_a_sender_saved_while_the_test_ran(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A save that changes the server forgets the last result; a test still running for the old
    server must not write its steps onto the new one."""
    from django.utils import timezone

    from mail import services, tasks
    from mail.models import MailSender

    stored()

    def saved_meanwhile(found: Any, now: Any) -> dict[str, Any]:
        MailSender.objects.filter(pk=found.pk).update(
            host="elsewhere.example.test",
            updated_at=timezone.now(),
            last_test_at=None,
            last_test_result="",
        )
        return {"done": ["connected", "signed_in", "sent"], "skipped": [], "failed": None}

    monkeypatch.setattr(services, "try_sender", saved_meanwhile)
    tasks.test_sender(None)
    with schema_context(None):
        row = MailSender.objects.get()
    assert (row.last_test_at, row.last_test_result) == (None, "")


def test_a_change_is_never_kept_without_its_audit(
    operator: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sender's row and its audit are one act: an audit that fails leaves the row as it was,
    on saving and on removing alike."""
    from mail.models import MailSender
    from mail.views import common

    def failing(**kwargs: Any) -> None:
        raise RuntimeError("the audit could not be written")

    monkeypatch.setattr(common, "record", failing)
    with pytest.raises(RuntimeError):
        operator.post(PAGE, form(password="new-synthetic-password"))
    with schema_context(None):
        assert not MailSender.objects.exists()
    monkeypatch.undo()
    stored()
    monkeypatch.setattr(common, "record", failing)
    with pytest.raises(RuntimeError):
        operator.post(PAGE, {"action": "remove"})
    with schema_context(None):
        assert MailSender.objects.exists()


def test_a_change_is_audited_with_the_values_it_replaced(operator: Any) -> None:
    from audit.models import AuditEvent

    stored()
    operator.post(
        PAGE,
        form(host="elsewhere.example.test", security="tls", password="new-synthetic-password"),
    )
    event = AuditEvent.objects.filter(action="mail.sender_saved").latest("at")
    assert event.before["host"] == "smtp.example.test" and event.before["security"] == "starttls"
    assert event.after["host"] == "elsewhere.example.test" and event.after["security"] == "tls"


def test_a_test_is_claimed_once_whoever_asks_at_the_same_moment(operator: Any) -> None:
    """Two requests that both found no test running: one claim succeeds, the other is refused,
    so one job is queued (DL-0392)."""
    from mail.views import common

    with schema_context(None):
        sender = stored()
        stale = type(sender).objects.get(pk=sender.pk)
        assert common.claim_test(sender) is True
        assert common.claim_test(stale) is False
