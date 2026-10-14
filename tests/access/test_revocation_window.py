"""The revocation window (DL-0375): an act reads the person's rights under the document's lock, and
a right revoked — here, by taking the person out of the group — by a transaction of its own after
that read is not seen by that one act. The window is one act wide — the act under way completes,
and the next act by the same person is refused.

People, groups and the document's text are synthetic examples."""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from django.db import connection

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "access_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
# Registered before it runs: its dataclass looks its own module up by name.
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)

# The review tests' fixtures; `cast` needs `new_document` and `link_group`.
new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version
cast = _review.cast

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# Синтетичні положення\n\nЗаяву на синтетичне погодження подають письмово.\n"
SECOND = FIRST + "\nКопію синтетичного рішення надсилають того ж дня.\n"


def test_the_window_is_one_act_wide(
    migrated_tenant: Any,
    cast: Any,
    commit_version: Any,
    monkeypatch: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import rights_on
    from review import services
    from review.models import Acceptance

    people = cast(editors=("a",), reviewers=("r",))
    document, reviewer = people.document, people["r"]
    reviewers, membership = people.groups["reviewers"], people.memberships["r"]
    commit_version(document, people["a"], FIRST, "edit")
    revoked: list[bool] = []

    def revoke_elsewhere() -> None:
        # Another request, on a connection of its own, removes the reviewer from the group; the
        # change commits while the acceptance holds the document's lock.
        try:
            with schema_context(migrated_tenant.number):
                reviewers.remove_member(membership, by=people["a"])
            revoked.append(True)
        finally:
            connection.close()

    def read_then_revoke(user: Any, target: Any) -> frozenset[Any]:
        rights = rights_on(user, target)
        if not revoked:
            other = threading.Thread(target=revoke_elsewhere)
            other.start()
            other.join(timeout=30)
            # Between the act's read and its commit, inside its transaction, under its lock.
            assert not other.is_alive() and revoked == [True]
            assert connection.in_atomic_block
        return rights

    monkeypatch.setattr("review.services.rights_on", read_then_revoke)
    with schema_context(migrated_tenant.number):
        accepted = services.accept(document, reviewer)

    assert revoked == [True]
    with schema_context(migrated_tenant.number):
        # The act that read *accept* before the revocation completes, recorded as any other.
        assert Acceptance.objects.filter(pk=accepted.pk).exists()
    commit_version(document, people["a"], SECOND, "edit")
    with schema_context(migrated_tenant.number), pytest.raises(services.AcceptRefused) as refused:
        services.accept(document, reviewer)
    assert str(refused.value) == "not_a_reviewer"
