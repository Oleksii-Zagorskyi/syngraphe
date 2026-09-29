"""An attachment downloaded (ST-0075, DL-0342, DL-0348): the bytes of
`attachments/<n>` at the version the reader may see, never rendered by the browser, audited;
anything the reader may not have answers exactly as a missing document does (ADR-0008).

Readers hold *view accepted* in the alpha (DL-0348). People, groups and titles are synthetic
examples; every text is invented.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import pytest

from access.rights import Right

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TOKEN = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
ORDER = ("Порядок видачі доступу", "order.txt", "Синтетичний наказ про видачу доступу.\n".encode())


def directives(response: Any) -> set[str]:
    """The `Cache-Control` directives' names, whatever their order and values."""
    return {
        part.strip().split("=", 1)[0].lower()
        for part in response["Cache-Control"].split(",")
        if part.strip()
    }


def missing(client: Any) -> bytes:
    """What the client is answered for a document number nobody has, the masked token removed."""
    response = client.get("/document/9999/attachment/1/")
    assert response.status_code == 404
    return TOKEN.sub(b"", response.content)


def test_reader_downloads_the_accepted_file(
    migrated_tenant: Any, accepted_with_parts: Any, reader_in: Any
) -> None:
    from audit.models import AuditEvent

    made = accepted_with_parts()
    document = made.document
    client, reader = reader_in(Right.VIEW_ACCEPTED, document)
    _, file_name, data = made.attachments[0]

    response = client.get(f"/document/{document.number}/attachment/1/")

    assert response.status_code == 200
    assert response.content == data
    assert response["Content-Type"] == "application/octet-stream"
    disposition = response["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert f'filename="{file_name}"' in disposition
    assert response["X-Content-Type-Options"] == "nosniff"
    assert {"private", "no-store"} <= directives(response)
    events = list(AuditEvent.objects.filter(action="attachment.downloaded"))
    assert len(events) == 1
    event = events[0]
    assert event.actor_id == reader.pk
    assert event.object_id == document.pk
    assert event.tenant_id == migrated_tenant.pk
    # The commit of the version served — the accepted content version, not the acceptance's.
    assert event.after == {
        "number": document.number,
        "attachment": 1,
        "commit": made.version.commit_sha,
    }


def test_a_number_not_listed_is_missing(accepted_with_parts: Any, reader_in: Any) -> None:
    from audit.models import AuditEvent

    document = accepted_with_parts().document
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)
    expected = missing(client)

    response = client.get(f"/document/{document.number}/attachment/2/")

    assert response.status_code == 404
    assert TOKEN.sub(b"", response.content) == expected
    assert not AuditEvent.objects.filter(action="attachment.downloaded").exists()


def test_version_decides_what_is_served(
    accepted_with_parts: Any, reader_in: Any, operator: Any, commit_parts: Any
) -> None:
    made = accepted_with_parts()
    document = made.document
    # Attachment 2 arrives in a pending version, after the acceptance.
    commit_parts(document, operator.user, made.body, [*made.attachments, ORDER])
    accepted_client, _ = reader_in(Right.VIEW_ACCEPTED, document)
    pending_client, _ = reader_in(Right.VIEW_PENDING, document)
    route = f"/document/{document.number}/attachment/2/"

    assert accepted_client.get(route).status_code == 404
    served = pending_client.get(route)
    assert served.status_code == 200
    assert served.content == ORDER[2]
    # Attachment 1 is in both versions.
    assert accepted_client.get(f"/document/{document.number}/attachment/1/").status_code == 200


def test_forbidden_answers_as_missing(
    accepted_with_parts: Any, reader_in: Any, member_of: Any
) -> None:
    from audit.models import AuditEvent

    linked = accepted_with_parts().document
    unlinked = accepted_with_parts().document
    client, _ = reader_in(Right.VIEW_ACCEPTED, linked)
    canonical_client, _ = reader_in(Right.VIEW_CANONICAL, linked)

    for asking, document in ((client, unlinked), (canonical_client, linked)):
        expected = missing(asking)
        response = asking.get(f"/document/{document.number}/attachment/1/")
        assert response.status_code == 404
        assert TOKEN.sub(b"", response.content) == expected
    assert not AuditEvent.objects.filter(action="attachment.downloaded").exists()


def test_hash_mismatch_not_served(
    accepted_with_parts: Any, reader_in: Any, caplog: pytest.LogCaptureFixture
) -> None:
    from audit.models import AuditEvent

    made = accepted_with_parts(tamper=True)
    client, _ = reader_in(Right.VIEW_ACCEPTED, made.document)
    caplog.set_level(logging.ERROR)

    response = client.get(f"/document/{made.document.number}/attachment/1/")

    assert response.status_code == 404
    assert made.attachments[0][2] not in response.content
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert not AuditEvent.objects.filter(action="attachment.downloaded").exists()


def test_non_ascii_file_name(accepted_with_parts: Any, reader_in: Any) -> None:
    name = "схема погодження.txt"
    data = "Синтетична схема погодження.\n".encode()
    made = accepted_with_parts([("Схема погодження", name, data)])
    client, _ = reader_in(Right.VIEW_ACCEPTED, made.document)

    response = client.get(f"/document/{made.document.number}/attachment/1/")

    assert response.status_code == 200
    assert response.content == data
    disposition = response["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert "filename*=utf-8''" in disposition
    assert quote(name) in disposition


def test_get_only_and_members_only(
    migrated_tenant: Any, accepted_with_parts: Any, reader_in: Any
) -> None:
    from django.test import Client

    from identity.models import User

    document = accepted_with_parts().document
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)
    route = f"/document/{document.number}/attachment/1/"

    assert client.post(route).status_code == 404
    assert client.head(route).status_code == 404

    # Signed in, the tenant chosen in the session, and no membership in it.
    outsider = User.objects.create_user("outsider.synthetic@example.test", "test-only-not-a-pw")
    stranger = Client(headers={"host": "127.0.0.1"})
    stranger.force_login(outsider)
    session = stranger.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    response = stranger.get(route)
    assert response.status_code == 404
    assert b"Synthetic attachment" not in response.content


def test_missing_repository_answers_as_missing(
    migrated_tenant: Any, accepted_with_parts: Any, reader_in: Any
) -> None:
    import shutil

    from documents import gitstore

    document = accepted_with_parts().document
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)
    shutil.rmtree(gitstore.repository_path(migrated_tenant.number, document.number))

    for route in (f"/document/{document.number}/", f"/document/{document.number}/attachment/1/"):
        response = client.get(route)
        assert response.status_code == 404, route
        assert TOKEN.sub(b"", response.content) == missing(client), route


def test_created_text_is_not_called_accepted(
    migrated_tenant: Any, operator: Any, reader_in: Any, settings: Any
) -> None:
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language
    from tenancy.schemas import schema_context

    settings.LANGUAGE_CODE = "uk"
    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            operator.user,
            "Синтетичний неприйнятий документ",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    client, _ = reader_in(Right.VIEW_ACCEPTED, document)

    body = client.get(f"/document/{document.number}/").content.decode()

    # No number before any acceptance: `0.0` is never shown alone (DL-0272).
    assert "0.0" not in body
    assert "Погоджена версія" not in body and 'class="version"' not in body
