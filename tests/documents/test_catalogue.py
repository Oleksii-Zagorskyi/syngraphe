"""Every page the document store added renders in Ukrainian from the one catalogue, and the
catalogue is complete and compiled.

Group names, people and titles are synthetic examples."""

from __future__ import annotations

import gettext
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

SRC = Path(__file__).resolve().parents[2] / "src"
LOCALE = SRC / "shell" / "locale"
CATALOGUE = LOCALE / "uk" / "LC_MESSAGES" / "django.po"


def entries(catalogue: str) -> dict[tuple[str, str], str]:
    """Every live `(context, message id)` and its translation, continuation lines joined."""
    found: dict[tuple[str, str], str] = {}
    for block in catalogue.split("\n\n"):
        parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
        current = None
        for line in block.splitlines():
            if line.startswith("#"):
                continue
            keyword = line.split(" ", 1)[0]
            if keyword in parts:
                current = keyword
                parts[current].append(line[len(keyword) + 1 :].strip('"'))
            elif line.startswith('"') and current:
                parts[current].append(line.strip('"'))
        message = "".join(parts["msgid"])
        if message:
            key = ("".join(parts["msgctxt"]), message)
            found[key] = "".join(parts["msgstr"]).replace('\\"', '"')
    return found


def text_of(body: str) -> str:
    """What a reader sees: the page without its tags and their attributes."""
    return re.sub(r"<[^>]*>", " ", body)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_epic_3_pages(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    settings.LANGUAGE_CODE = "uk"
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    author, author_user, membership = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Authors", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)
    linked = make_document(title="Пов’язаний", created_by=author_user, author_only=False)
    make_document(title="Чернетка", created_by=author_user, author_only=True)
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(linked, group, by=admin_user)
    ids = [
        message for _, message in entries(CATALOGUE.read_text(encoding="utf-8")) if len(message) > 2
    ]
    pages = [
        (admin, "/administration/tenant/document-links/"),
        (admin, "/folder/1/"),
        (admin, f"/document/{linked.number}/info/"),
        (author, "/folder/1/"),
        (author, "/document/new/"),
        (author, f"/document/{linked.number}/"),
    ]

    for client, path in pages:
        response = client.get(path)
        assert response.status_code == 200, path
        body = text_of(response.content.decode())
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"


@pytest.mark.integration
def test_makemessages_adds_no_entry(tmp_path: Path) -> None:
    # In a copy of the source tree, as its own process: the committed catalogue is never touched.
    copy = tmp_path / "src"
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__", "staticfiles"))
    subprocess.run(
        [sys.executable, "manage.py", "makemessages", "-l", "uk", "--verbosity", "0"],
        cwd=copy,
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(copy)},
    )
    before = entries(CATALOGUE.read_text(encoding="utf-8"))
    after = entries(
        (copy / "shell" / "locale" / "uk" / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
    )

    assert sorted(set(after) - set(before)) == []
    assert [key for key, value in after.items() if not value] == []


@pytest.mark.fast
def test_the_compiled_catalogue_is_the_catalogue() -> None:
    compiled = gettext.GNUTranslations((LOCALE / "uk" / "LC_MESSAGES" / "django.mo").open("rb"))

    stale = [
        key
        for key, value in entries(CATALOGUE.read_text(encoding="utf-8")).items()
        if (compiled.pgettext(*key) if key[0] else compiled.gettext(key[1])) != value
    ]

    assert stale == []
