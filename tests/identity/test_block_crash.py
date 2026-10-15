"""A membership's block is one transaction (ST-0004, DL-0256): stopped while it ends the person's
holds, it leaves nothing behind — the membership still active, no history row, the hold open, no
audit event and no word to the platform's administrators.

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "identity_block_crash_editing_fixtures",
    Path(__file__).resolve().parents[1] / "editing" / "conftest.py",
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
# Registered before it runs, as `tests/access/test_revocation_window.py` loads its fixtures.
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

new_document = _editing.new_document
link_group = _editing.link_group

pytestmark = [
    pytest.mark.integration,
    pytest.mark.crash,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

PASSWORD = "test-only-not-a-password"


def test_block_is_one_transaction(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from access.rights import Right
    from audit.models import AuditEvent
    from editing import holds
    from identity import blocking
    from identity.models import Membership, MembershipHistory, User
    from tenancy.models import PlatformNotification, Tenant

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, editor, membership = member_of("an.editor@example.test")
    # Active elsewhere, with a platform administrator to tell: a block that completed would
    # write a platform notification.
    elsewhere = Tenant.objects.create(
        name="Another Synthetic Org", state="active", actor_kind="system"
    )
    Membership.objects.create(tenant=elsewhere, user=editor, actor_kind="system")
    User.objects.create_user("platform.one@example.test", PASSWORD, is_platform_admin=True)
    document = new_document(admin_user, "Synthetic leave procedure")
    link_group(document, [Right.EDIT], [membership], admin_user)
    with schema_context(migrated_tenant.number):
        hold = holds.take(document, editor)
    seen = set(AuditEvent.objects.values_list("id", flat=True))

    def stopped(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("stopped while ending the holds")

    monkeypatch.setattr("identity.blocking.end_holds", stopped)

    with schema_context(migrated_tenant.number), pytest.raises(RuntimeError):
        blocking.block_membership(membership, by=admin_user)

    assert Membership.objects.get(pk=membership.pk).state == "active"
    assert not MembershipHistory.objects.filter(membership=membership).exists()
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
    assert not AuditEvent.objects.exclude(id__in=seen).exists()
    with schema_context(None):
        assert not PlatformNotification.objects.exists()
