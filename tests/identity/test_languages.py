"""The abbreviation lists are seeded from one file per language and never overwritten silently."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def seed(*args: str) -> str:
    out = StringIO()
    call_command("seed_languages", *args, stdout=out)
    return out.getvalue()


def test_seeded_abbreviation_lists() -> None:
    from identity.models import Language

    output = seed()

    uk = Language.objects.get(code="uk")
    en = Language.objects.get(code="en")
    assert "uk: seeded" in output and "en: seeded" in output
    assert {"п", "ст"} <= set(uk.never_final_list())
    assert {"р", "грн"} <= set(uk.may_be_final_list())
    assert "e.g" in en.never_final_list()
    assert "etc" in en.may_be_final_list()
    assert "may" not in en.never_final_list()
    for language in (uk, en):
        for item in language.never_final_list() + language.may_be_final_list():
            assert item == item.lower() and not item.endswith(".")


def test_second_run_changes_nothing() -> None:
    seed()

    output = seed()

    assert "uk: unchanged" in output and "en: unchanged" in output


def test_seed_reports_divergence() -> None:
    from audit.models import AuditEvent
    from identity.models import Language

    seed()
    uk = Language.objects.get(code="uk")
    en_before = Language.objects.get(code="en").never_final
    edited = [item for item in uk.never_final_list() if item != "п"]
    uk.never_final = "\n".join(edited)
    uk.save()

    output = seed()
    uk.refresh_from_db()
    assert "uk: differs from its file (never_final)" in output
    assert "en: unchanged" in output
    assert "п" not in uk.never_final_list()

    output = seed("--overwrite")
    uk.refresh_from_db()
    assert "uk: overwritten (never_final)" in output
    assert "en: unchanged" in output
    assert "п" in uk.never_final_list()
    assert uk.updated_by is None
    assert Language.objects.get(code="en").never_final == en_before
    reseeded = AuditEvent.objects.get(action="language.reseeded")
    assert reseeded.actor_kind == "system" and reseeded.after["code"] == "uk"
