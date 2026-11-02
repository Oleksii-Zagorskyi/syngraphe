"""Resetting a password by address (ST-0055, ASR-17): every request draws the same page, whatever
the address, the throttle or the sender; a known person's email is queued in the organisation the
request and their memberships place it in, or in the shared outbox; a single-use link sets the
new password, signs the person in and ends their other sessions; requests are throttled per
client on their own row, which the sweep removes.

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from tenancy.schemas import current_tenant, schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

RESET = "/reset/"
PLATFORM = "127.0.0.1"
PASSWORD = "Tr4vel-Plan-Ok"
NEW_PASSWORD = "Sp4rrow-Field-Ok"
SENTENCE = (
    "Request received. If the address is registered, an email with a link to set a new password is "
    "sent to it; if none arrives, ask an administrator."
)
# The addresses compared are of one length, so the masked bodies keep one Content-Length.
UNKNOWN = "nobody.one@example.test"
P1 = "person.one@example.test"
P2 = "person.two@example.test"
WAITING = "waiting.on@example.test"
RESET_LINK = r"https?://([^/\s]+)/reset/[A-Za-z0-9_-]{43}/"


def ask(host: str, email: str, peer: str) -> Any:
    """`POST /reset/` from a client of its own address, so no request delays another."""
    return Client(headers={"host": host}, REMOTE_ADDR=peer).post(RESET, {"email": email})


def a_domain(tenant: Any, host: str) -> None:
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(tenant=tenant, host=host, is_default=True, actor_kind="system")
    invalidate_host_cache()


def to(rows: list[Any], email: str) -> list[Any]:
    return [row for row in rows if row.recipient == email]


def a_reset(user: Any, *, expires_in: timedelta = timedelta(hours=1)) -> str:
    from identity.models import PasswordReset
    from identity.tokens import hash_token, new_token

    token = new_token()
    PasswordReset.objects.create(
        user=user, token_hash=hash_token(token), expires_at=timezone.now() + expires_in
    )
    return token


def test_request_indistinguishable_by_address_and_placed_by_host_and_membership(
    make_tenant_schema: Any, person: Any, sending_address: Any, masked: Any, outbox: Any
) -> None:
    from identity.models import PasswordReset

    a = make_tenant_schema("Synthetic Org A")
    b = make_tenant_schema("Synthetic Org B")
    a_domain(a, "a.example.test")
    sending_address(a.number, "a.sender@example.test")
    sending_address(b.number, "b.sender@example.test")
    sending_address(None, "platform.sender@example.test")
    p1 = person(P1, "Synthetic Org A")
    p2 = person(P2, "Synthetic Org A", "Synthetic Org B")

    on_domain = [
        ask("a.example.test", UNKNOWN, "192.0.2.31"),
        ask("a.example.test", P1, "192.0.2.32"),
    ]
    on_platform = [
        ask(PLATFORM, UNKNOWN, "192.0.2.33"),
        ask(PLATFORM, P1, "192.0.2.34"),
        ask(PLATFORM, P2, "192.0.2.35"),
    ]

    for response in on_domain + on_platform:
        assert response.status_code == 200
        assert SENTENCE in response.content.decode()
    assert masked(on_domain[0], UNKNOWN) == masked(on_domain[1], P1)
    assert masked(on_platform[0], UNKNOWN) == masked(on_platform[1], P1)
    assert masked(on_platform[0], UNKNOWN) == masked(on_platform[2], P2)

    assert PasswordReset.objects.filter(user=p1).count() == 2
    assert PasswordReset.objects.filter(user=p2).count() == 1
    assert PasswordReset.objects.count() == 3

    in_a, in_b, shared = outbox(a.number), outbox(b.number), outbox(None)
    assert len(to(in_a, P1)) == 2 and to(in_b, P1) == [] and to(shared, P1) == []
    assert to(in_a, P2) == [] and to(in_b, P2) == [] and len(to(shared, P2)) == 1
    assert [r for r in in_a + in_b + shared if r.recipient == UNKNOWN] == []
    for row in to(in_a, P1):
        assert row.sender == "a.sender@example.test"
        assert re.findall(RESET_LINK, row.body) == ["a.example.test"]
    [row] = to(shared, P2)
    assert row.sender == "platform.sender@example.test" and row.tenant_id is None
    assert re.findall(RESET_LINK, row.body) == [PLATFORM]


def test_reset_signs_in_and_ends_other_sessions(person: Any) -> None:
    from identity.models import PasswordReset

    user = person(P1)
    token = a_reset(user)
    other = Client(headers={"host": PLATFORM}, REMOTE_ADDR="192.0.2.41")
    signed_in = other.post("/signin/", {"email": P1, "password": PASSWORD})
    assert signed_in.status_code == 302 and other.session["_auth_user_id"] == str(user.id)
    first = Client(headers={"host": PLATFORM}, REMOTE_ADDR="192.0.2.42")

    done = first.post(
        f"/reset/{token}/", {"password": NEW_PASSWORD, "password_again": NEW_PASSWORD}
    )

    assert done.status_code == 302 and done["Location"] == "/"
    assert first.session["_auth_user_id"] == str(user.id)
    assert first.get("/administration/").status_code != 302
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    after = other.get("/administration/")
    anonymous = Client(headers={"host": PLATFORM}).get("/administration/")
    assert after.status_code == anonymous.status_code == 302
    assert after["Location"] == anonymous["Location"]
    assert after["Location"].startswith("/signin/")
    assert PasswordReset.objects.get().used_at is not None
    assert first.get(f"/reset/{token}/").status_code == 404


def test_expired_token_is_unknown(person: Any, masked: Any) -> None:
    token = a_reset(person(P1), expires_in=-timedelta(seconds=1))
    client = Client(headers={"host": PLATFORM})

    missing = masked(client.get("/no-such-page/"))
    expired = masked(client.get(f"/reset/{token}/"))

    assert missing[0] == 404
    assert expired == missing


def test_requests_are_throttled_per_client_on_their_own_row(
    migrated_tenant: Any, person: Any, sending_address: Any, masked: Any, outbox: Any
) -> None:
    from identity.models import PasswordReset, SignInAttempt
    from identity.throttle import reset_key

    person(P1, migrated_tenant.name)
    sending_address(migrated_tenant.number)
    client = Client(headers={"host": PLATFORM}, REMOTE_ADDR="192.0.2.50")
    # The client has signed in wrongly once: its sign-in rows exist, and must stay as they are.
    client.post("/signin/", {"email": P1, "password": "not-the-password"})
    signing_in = list(
        SignInAttempt.objects.exclude(key_kind="reset")
        .order_by("key")
        .values_list("key", "consecutive_failures", "next_allowed_at")
    )
    assert signing_in

    def sent() -> tuple[int, int]:
        mails = to(outbox(migrated_tenant.number) + outbox(None), P1)
        return PasswordReset.objects.count(), len(mails)

    first = client.post(RESET, {"email": P1})
    after_first = sent()
    # Well inside the delay, however slowly the run goes.
    SignInAttempt.objects.filter(key_kind="reset").update(
        next_allowed_at=timezone.now() + timedelta(minutes=1)
    )
    second = client.post(RESET, {"email": P1})
    after_second = sent()
    SignInAttempt.objects.filter(key_kind="reset").update(
        next_allowed_at=timezone.now() - timedelta(seconds=1)
    )
    third = client.post(RESET, {"email": P1})
    after_third = sent()

    assert masked(first, P1) == masked(second, P1) == masked(third, P1)
    assert (after_first, after_second, after_third) == ((1, 1), (1, 1), (2, 2))
    assert SignInAttempt.objects.filter(key=reset_key("192.0.2.50"), key_kind="reset").exists()
    assert signing_in == list(
        SignInAttempt.objects.exclude(key_kind="reset")
        .order_by("key")
        .values_list("key", "consecutive_failures", "next_allowed_at")
    )


def test_no_reset_before_a_password_exists(
    migrated_tenant: Any, member_of: Any, invited: Any, masked: Any, outbox: Any
) -> None:
    from identity.models import PasswordReset

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    invited(migrated_tenant, WAITING, by=admin_user)
    before = len(to(outbox(migrated_tenant.number) + outbox(None), WAITING))

    unknown = ask(PLATFORM, UNKNOWN, "192.0.2.61")
    waiting = ask(PLATFORM, WAITING, "192.0.2.62")

    assert masked(unknown, UNKNOWN) == masked(waiting, WAITING)
    assert not PasswordReset.objects.exists()
    assert len(to(outbox(migrated_tenant.number) + outbox(None), WAITING)) == before == 1


def test_request_is_one_transaction(
    migrated_tenant: Any, person: Any, sending_address: Any, outbox: Any, monkeypatch: Any
) -> None:
    from identity import resets
    from identity.models import PasswordReset
    from identity.throttle import reset_key

    person(P1, migrated_tenant.name)
    sending_address(migrated_tenant.number)
    sending_address(None, "platform.sender@example.test")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("a synthetic failure")

    monkeypatch.setattr("mail.services.queue", refuse)
    with pytest.raises(RuntimeError):
        resets.request_reset(P1, reset_key("192.0.2.70"), tenant=None)

    assert current_tenant(connection) is None
    assert not PasswordReset.objects.exists()
    assert outbox(migrated_tenant.number) == [] and outbox(None) == []


def test_no_sender_writes_the_row_and_audits(
    migrated_tenant: Any, person: Any, no_sending_address: Any, masked: Any, outbox: Any
) -> None:
    from audit.models import AuditEvent
    from identity.models import PasswordReset

    a_domain(migrated_tenant, "docs.example.test")
    no_sending_address(migrated_tenant.number)
    user = person(P1, migrated_tenant.name)

    unknown = ask("docs.example.test", UNKNOWN, "192.0.2.81")
    known = ask("docs.example.test", P1, "192.0.2.82")

    assert known.status_code == 200 and SENTENCE in known.content.decode()
    assert masked(unknown, UNKNOWN) == masked(known, P1)
    [row] = PasswordReset.objects.all()
    assert row.user_id == user.id
    assert outbox(migrated_tenant.number) == [] and outbox(None) == []
    [event] = AuditEvent.objects.filter(action="password.reset_requested")
    assert event.object_id == row.id
    assert "@" not in json.dumps(event.after, default=str)


def test_reset_rows_are_swept() -> None:
    from identity.models import SignInAttempt
    from identity.tasks import sweep_sign_in_attempts

    SignInAttempt.objects.create(
        key="synthetic-reset-row",
        key_kind=SignInAttempt.KeyKind.RESET,
        consecutive_failures=1,
        last_failure_at=timezone.now() - timedelta(days=2),
    )
    SignInAttempt.objects.create(
        key="synthetic-fresh-reset-row",
        key_kind=SignInAttempt.KeyKind.RESET,
        consecutive_failures=1,
        last_failure_at=timezone.now() - timedelta(hours=1),
    )

    sweep_sign_in_attempts()

    assert not SignInAttempt.objects.filter(key="synthetic-reset-row").exists()
    assert SignInAttempt.objects.filter(key="synthetic-fresh-reset-row").exists()


def _spend(token: str, path: str = "reset") -> Any:
    return Client(headers={"host": PLATFORM}).post(
        f"/{path}/{token}/", {"password": NEW_PASSWORD, "password_again": NEW_PASSWORD}
    )


def test_a_spent_link_ends_every_other(
    migrated_tenant: Any, member_of: Any, person: Any, invited: Any
) -> None:
    """A person who resets because someone may hold a link shuts every link they hold: other
    resets, and invitations to their address — and accepting an invitation ends their resets."""
    user = person(P1)
    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    older = a_reset(user)
    invitation = invited(migrated_tenant, P1, by=admin_user)
    spent = a_reset(user)

    assert _spend(spent).status_code == 302
    assert Client(headers={"host": PLATFORM}).get(f"/reset/{older}/").status_code == 404
    assert Client(headers={"host": PLATFORM}).get(f"/invitation/{invitation}/").status_code == 404

    pending = a_reset(user)
    fresh = invited(migrated_tenant, P1, by=admin_user)
    assert _spend(fresh, "invitation").status_code == 302
    assert Client(headers={"host": PLATFORM}).get(f"/reset/{pending}/").status_code == 404


def test_the_session_names_the_sole_organisation(
    migrated_tenant: Any, make_tenant_schema: Any, person: Any
) -> None:
    sole = person(P1, migrated_tenant.name)
    other = make_tenant_schema("Another synthetic organisation")
    both = person(P2, migrated_tenant.name, other.name)
    first = Client(headers={"host": PLATFORM})
    second = Client(headers={"host": PLATFORM})

    assert first.post(f"/reset/{a_reset(sole)}/", _passwords()).status_code == 302
    assert second.post(f"/reset/{a_reset(both)}/", _passwords()).status_code == 302

    assert first.session["tenant_number"] == migrated_tenant.number
    assert "tenant_number" not in second.session


def _passwords() -> dict[str, str]:
    return {"password": NEW_PASSWORD, "password_again": NEW_PASSWORD}


def test_a_self_blocked_address_answers_as_an_unknown_one(
    migrated_tenant: Any, person: Any, sending_address: Any, masked: Any
) -> None:
    sending_address(migrated_tenant.number)
    sending_address(None, "platform.sender@example.test")
    person(P1, migrated_tenant.name, self_blocked=True)

    unknown = ask(PLATFORM, UNKNOWN, "192.0.2.91")
    blocked = ask(PLATFORM, P1, "192.0.2.92")

    assert masked(unknown, UNKNOWN) == masked(blocked, P1)


@pytest.mark.parametrize("method", ["head", "put"])
def test_a_live_link_never_reaches_the_log(person: Any, method: str) -> None:
    """A link answered with a refusal is logged by the framework with its path; the token is a
    credential while it is valid, so the log the application writes keeps the path without it
    (DL-0406). Read through the configured handler, its stream swapped for the test."""
    import io
    import logging

    from syngraphe.logs import CredentialFilter

    [handler] = [
        found
        for found in logging.getLogger().handlers
        if any(isinstance(item, CredentialFilter) for item in found.filters)
    ]
    assert isinstance(handler, logging.StreamHandler)
    token = a_reset(person(P1))
    written = io.StringIO()
    previous = handler.setStream(written)
    try:
        getattr(Client(headers={"host": PLATFORM}), method)(f"/reset/{token}/")
        Client(headers={"host": PLATFORM}, enforce_csrf_checks=True).post(
            f"/reset/{token}/", _passwords()
        )
    finally:
        handler.setStream(previous)

    assert "/reset/" in written.getvalue()
    assert token not in written.getvalue()
    assert Client(headers={"host": PLATFORM}).get(f"/reset/{token}/").status_code == 200


def test_an_organisations_outbox_page_shows_no_reset(
    migrated_tenant: Any, make_tenant_schema: Any, member_of: Any, person: Any, sending_address: Any
) -> None:
    """A reset asked on an organisation's domain is queued in its outbox (DL-0383) and left out of
    its sending-address page (DL-0410): the page reads the same whether the address asked for
    belongs to someone elsewhere or to nobody."""
    import re

    from mail.models import EmailOutbox

    other = make_tenant_schema("Another synthetic organisation")
    a_domain(migrated_tenant, "docs.example.test")
    sending_address(migrated_tenant.number)
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    person(P1, other.name)
    page = "/administration/tenant/sending-address/"

    before = admin.get(page).content.decode()
    ask("docs.example.test", P1, "192.0.2.101")
    ask("docs.example.test", UNKNOWN, "192.0.2.102")
    after = admin.get(page).content.decode()

    with schema_context(migrated_tenant.number):
        [row] = EmailOutbox.objects.filter(recipient=P1)
    assert row.kind == "reset"
    assert P1 not in after
    csrf = r'value="[^"]*" name="csrfmiddlewaretoken"|name="csrfmiddlewaretoken" value="[^"]*"'
    assert re.sub(csrf, "", before) == re.sub(csrf, "", after)


def test_a_failed_reset_is_told_to_the_platform_alone(
    migrated_tenant: Any, member_of: Any, person: Any, sending_address: Any
) -> None:
    from mail.models import EmailOutbox, Status
    from mail.services import _refused
    from notifications.models import Notification
    from tenancy.models import PlatformNotification

    sending_address(migrated_tenant.number)
    member_of("t.admin@example.test", is_tenant_admin=True)
    member_of("p.admin@example.test", is_platform_admin=True)
    person(P1, migrated_tenant.name)
    a_domain(migrated_tenant, "docs.example.test")
    ask("docs.example.test", P1, "192.0.2.103")

    with schema_context(migrated_tenant.number):
        row = EmailOutbox.objects.get(recipient=P1)
        for _ in range(3):
            _refused(row, OSError("a synthetic refusal"), timezone.now())
        row.refresh_from_db()
        assert row.status == Status.FAILED
        assert not Notification.objects.filter(event="email_failed").exists()
    with schema_context(None):
        [told] = PlatformNotification.objects.filter(event="email_failed")
    # The notice names the organisation, so it leads to the outbox that holds the row, where a
    # platform administrator — and only one — sees the reset.
    assert told.facts["tenant"] == migrated_tenant.number
    platform = Client(headers={"host": PLATFORM})
    platform.force_login(told.user)
    session = platform.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    assert P1 in platform.get("/administration/tenant/sending-address/").content.decode()


def test_spent_and_expired_resets_are_swept(person: Any) -> None:
    from datetime import timedelta as span

    from identity.models import PasswordReset
    from identity.tasks import sweep_sign_in_attempts
    from identity.tokens import hash_token

    user = person(P1)
    a_reset(user, expires_in=-span(days=2))
    a_reset(user, expires_in=-span(hours=2))
    a_reset(user)
    spent = a_reset(user)
    PasswordReset.objects.filter(token_hash=hash_token(spent)).update(
        used_at=timezone.now() - span(days=2)
    )

    sweep_sign_in_attempts()

    # Gone a day past their end: the one expired two days ago and the one used two days ago.
    assert PasswordReset.objects.count() == 2


@pytest.mark.crash
def test_a_reset_spent_is_one_transaction(person: Any, monkeypatch: Any) -> None:
    from audit import record as audit_record
    from identity import resets
    from identity.models import PasswordReset

    user = person(P1)
    token = a_reset(user)
    other = a_reset(user)
    original = audit_record.record

    def stop(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("action") == "password.reset":
            raise RuntimeError("a synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr("identity.resets.record", stop)
    with pytest.raises(RuntimeError):
        resets.reset(token, NEW_PASSWORD)

    user.refresh_from_db()
    assert user.check_password(PASSWORD)
    assert not PasswordReset.objects.filter(used_at__isnull=False).exists()
    assert resets.person_of(other) == user


def _spend_together(user: Any, spends: list[Any]) -> list[Any]:
    """Each spend in a thread of its own, started while another connection holds the person's row,
    so each has gone as far as it can before any reaches the person; then the row is let go. The
    outcomes, an exception among them when a spend raised."""
    import threading
    import time

    from django.db import transaction

    from identity.models import User

    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                holding.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    outcomes: list[Any] = []

    def run(spend: Any) -> None:
        try:
            outcomes.append(spend())
        except Exception as error:  # noqa: BLE001 — the outcome under test
            outcomes.append(error)
        finally:
            connection.close()

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=30)
    spenders = [threading.Thread(target=run, args=(spend,)) for spend in spends]
    for spender in spenders:
        spender.start()
    deadline = time.monotonic() + 15
    with connection.cursor() as cursor:
        while time.monotonic() < deadline:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0] >= len(spends):
                break
            time.sleep(0.05)
    release.set()
    holder.join(timeout=30)
    for spender in spenders:
        spender.join(timeout=30)
    return outcomes


@pytest.mark.parametrize("second", ["reset", "invitation"])
def test_two_links_spent_at_once_give_one_password_and_no_error(
    person: Any, migrated_tenant: Any, member_of: Any, invited: Any, second: str
) -> None:
    """Two links of one person spent together: one sets the password, the other answers as a link
    that no longer opens, and neither fails on the locks the two take."""
    from identity import invitations, resets

    user = person(P1)
    first = a_reset(user)
    if second == "reset":
        other = a_reset(user)
        spend_other = lambda: resets.reset(other, PASSWORD + "-other")  # noqa: E731
    else:
        _, admin, _ = member_of("t.admin@example.test", is_tenant_admin=True)
        other = invited(migrated_tenant, P1, by=admin)
        spend_other = lambda: invitations.accept(other, PASSWORD + "-other")  # noqa: E731

    outcomes = _spend_together(user, [lambda: resets.reset(first, NEW_PASSWORD), spend_other])

    assert not [o for o in outcomes if isinstance(o, Exception)], outcomes
    assert sorted(o is None for o in outcomes) == [False, True]


def _prefers(user: Any, value: str) -> None:
    from identity.views.preferences import _keep

    _keep(user, "language", value)


def test_the_email_goes_in_the_persons_language(
    person: Any, sending_address: Any, outbox: Any
) -> None:
    """A person who chose Ukrainian on an English installation gets the reset in Ukrainian, fixed
    when it is queued (DL-0501)."""
    from django.utils.translation import gettext, override

    sending_address(None, "platform.sender@example.test")
    _prefers(person(P1), "uk")

    assert ask(PLATFORM, P1, "192.0.2.51").status_code == 200

    [row] = to(outbox(None), P1)
    with override("uk"):
        assert row.subject == gettext("Reset your password") != "Reset your password"
        assert gettext("Someone asked for a new password for this address.") in row.body


def test_the_reset_page_takes_the_links_persons_language(person: Any) -> None:
    """The page a reset link opens speaks its person's language, the refusal of a weak password
    included; a spent or unknown link answers in the installation's default."""
    user = person(P1)
    _prefers(user, "uk")
    token = a_reset(user)
    client = Client(headers={"host": PLATFORM})

    page = client.get(f"/reset/{token}/").content.decode()
    refused = client.post(f"/reset/{token}/", {"password": "short", "password_again": "short"})

    assert '<html lang="uk">' in page
    assert refused.status_code == 200
    refusal = refused.content.decode()
    assert '<html lang="uk">' in refusal
    assert re.search(r'class="err[^"]*"[^>]*>[^<]*[Ѐ-ӿ]', refusal), refusal
    unknown = client.get("/reset/" + "x" * 43 + "/").content.decode()
    assert '<html lang="en">' in unknown


def test_a_link_spent_meanwhile_answers_in_the_default(person: Any, monkeypatch: Any) -> None:
    """A link spent by another hand between the page and the post answers as every spent link
    does, in the installation's default — never in its person's language."""
    user = person(P1)
    _prefers(user, "uk")
    token = a_reset(user)
    monkeypatch.setattr("identity.resets.reset", lambda token, password: None)

    answer = Client(headers={"host": PLATFORM}).post(
        f"/reset/{token}/", {"password": NEW_PASSWORD, "password_again": NEW_PASSWORD}
    )

    assert answer.status_code == 404
    assert '<html lang="en">' in answer.content.decode()
