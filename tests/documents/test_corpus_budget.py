"""The corpus held to ASR-21's page budget at about two hundred documents (DL-0454): no paging in
release 0.1, so the limit shows here before it bites. Measured alone (`-m budget`).

Titles, folders and people are synthetic examples."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.budget,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

# ASR-21: a page answers within two seconds, its 95th percentile read as the slowest of ten.
PAGE_BUDGET_SECONDS = 2.0
ROWS = re.compile(r'<tr class="document"[^>]*data-number="(\d+)"')


def slowest_of_ten(get: Callable[[], Any]) -> tuple[float, Any]:
    get()  # one warm-up
    times = []
    answer = None
    for _ in range(10):
        started = time.perf_counter()
        answer = get()
        times.append(time.perf_counter() - started)
    return max(times), answer


@pytest.fixture
def reader_of(migrated_tenant: Any, member_of: Any, repo_root: Any) -> Callable[..., Any]:
    """`count` documents created through the service in `folders`, round robin, a reader linked
    to all of them through one group; the reader's client. Built per test: the tenant's rows and
    `repo_root` are restored for each."""

    def make(count: int, folders: list[Any]) -> Any:
        from access.models import AccessGroup, DocumentGroup
        from access.rights import Right
        from documents import services
        from documents.models import DocumentType
        from identity.models import Language

        Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
        client, _, membership = member_of("a.reader@example.test")
        _, author, _ = member_of("an.author@example.test")
        with schema_context(migrated_tenant.number):
            kind = DocumentType.objects.get(code="document")
            group = AccessGroup.objects.create(name="Readers", created_by=author, actor_kind="user")
            group.grant(Right.VIEW_PENDING, by=author)
            group.add_member(membership, by=author)
            for i in range(count):
                document = services.create_document(
                    author,
                    f"Synthetic budget document {i:03}",
                    "uk",
                    kind,
                    folders[i % len(folders)],
                )
                DocumentGroup.link(document, group, by=author)
        return client

    return make


def test_a_folder_of_two_hundred_meets_the_page_budget(
    migrated_tenant: Any, member_of: Any, reader_of: Callable[..., Any]
) -> None:
    from documents import folders
    from documents.models import Folder

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        folder = folders.create_folder(Folder.objects.get(number=1), "Budget (synthetic)", by=admin)
    client = reader_of(200, [folder])

    slowest, answer = slowest_of_ten(lambda: client.get(f"/folder/{folder.number}/"))

    assert answer.status_code == 200
    assert len(ROWS.findall(answer.content.decode())) == 200
    print(f"folder of 200: slowest of ten {slowest:.3f} s")
    assert slowest < PAGE_BUDGET_SECONDS, f"slowest of ten {slowest:.3f} s"
