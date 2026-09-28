"""The database refuses a provenance row whose actor kind contradicts its creator."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_system_rows_have_no_creator() -> None:
    from identity.models import User
    from tenancy.models import PlatformHost

    creator = User.objects.create_user("a.person@example.test", "test-only-not-a-password")

    with pytest.raises(IntegrityError), transaction.atomic():
        PlatformHost.objects.create(
            host="one.example.test", actor_kind="system", created_by=creator
        )


def test_user_rows_name_their_creator() -> None:
    from tenancy.models import PlatformHost

    with pytest.raises(IntegrityError), transaction.atomic():
        PlatformHost.objects.create(host="two.example.test", actor_kind="user", created_by=None)


def test_every_model_carries_provenance_or_its_own_columns() -> None:
    from django.apps import apps

    from syngraphe.provenance import Provenanced

    own_columns = {
        "audit.AuditEvent",
        "identity.MembershipHistory",
        "identity.AccountBlockHistory",
        "identity.SignInAttempt",
        "identity.SetupToken",
        "tenancy.TenantStateHistory",
    }
    for model in apps.get_models():
        if model._meta.app_label in ("admin", "auth", "contenttypes", "sessions"):
            continue
        assert issubclass(model, Provenanced) or model._meta.label in own_columns, model
