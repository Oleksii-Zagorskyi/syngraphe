"""Every page of the documents app renders in Ukrainian from the one catalogue, and the
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
    """Every live `(context, message id)` and its translation, continuation lines joined; a
    plural entry's translation is its first form, or empty when any of its forms is empty."""
    return {key: value for key, (value, _plural, _forms) in _parsed(catalogue).items()}


def plurals(catalogue: str) -> dict[tuple[str, str], tuple[str, list[str]]]:
    """Every plural entry's `(context, message id)`, its plural message id and its forms."""
    return {
        key: (plural, forms)
        for key, (_value, plural, forms) in _parsed(catalogue).items()
        if plural
    }


def _parsed(catalogue: str) -> dict[tuple[str, str], tuple[str, str, list[str]]]:
    found: dict[tuple[str, str], tuple[str, str, list[str]]] = {}
    for block in catalogue.split("\n\n"):
        parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgid_plural": []}
        forms: dict[str, list[str]] = {}
        current: list[str] | None = None
        for line in block.splitlines():
            if line.startswith("#"):
                continue
            keyword = line.split(" ", 1)[0]
            if keyword in parts:
                current = parts[keyword]
            elif keyword.startswith("msgstr"):
                current = forms.setdefault(keyword, [])
            elif line.startswith('"') and current is not None:
                current.append(line.strip('"'))
                continue
            else:
                continue
            current.append(line[len(keyword) + 1 :].strip('"'))
        message = "".join(parts["msgid"])
        if message:
            key = ("".join(parts["msgctxt"]), message)
            texts = ["".join(f).replace('\\"', '"') for _k, f in sorted(forms.items())]
            value = texts[0] if texts and all(texts) else ""
            found[key] = (value, "".join(parts["msgid_plural"]), texts)
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
        # The document has no repository to render: its header is read on the Info tab.
        (author, f"/document/{linked.number}/info/"),
    ]

    for client, path in pages:
        response = client.get(path)
        assert response.status_code == 200, path
        body = text_of(response.content.decode())
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"


# Epic 10
@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_epic_10_pages(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any, repo_root: Path
) -> None:
    """The corpus's pages in `uk`: every string from the catalogue, a type's label as the
    organisation stores it (DL-0310)."""
    from documents import types

    settings.LANGUAGE_CODE = "uk"
    admin, admin_user, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Синтетичний документ")
    with schema_context(migrated_tenant.number):
        retired = types.add_type("застарілий (synthetic example)", by=admin_user)
        types.retire_type(retired, by=admin_user)
    ids = [
        message for _, message in entries(CATALOGUE.read_text(encoding="utf-8")) if len(message) > 2
    ]
    from documents import folders
    from documents.models import Folder

    with schema_context(migrated_tenant.number):
        policies = folders.create_folder(
            Folder.objects.get(number=1), "Політики (synthetic example)", by=admin_user
        )
    make_document(title="Архівний документ", folder=policies, state="archived")
    # A second type on an active document, so the type filter is drawn.
    make_document(title="Синтетичний наказ", document_type=retired)
    pages = [
        (admin, "/administration/tenant/document-types/"),
        (admin, f"/document/{document.number}/info/"),
        (admin, "/administration/tenant/folders/"),
        (admin, f"/administration/tenant/folders/?folder={policies.number}"),
        (admin, f"/administration/tenant/folders/{policies.number}/move/"),
        (admin, "/folder/1/"),
        (admin, f"/folder/{policies.number}/"),
        (admin, "/search/?q=Синтетичний"),
        (admin, f"/search/?type={retired.code}"),
        (admin, "/search/?q=nothing-at-all"),
        (admin, "/administration/tenant/archive/"),
        (admin, f"/document/{document.number}/info/?archived"),
    ]

    with schema_context(migrated_tenant.number):
        from documents.models import Document

        # The archived document's own tab, its tag and disabled choice in `uk`: archived by row,
        # the act being its own tests' subject.
        archived_doc = make_document(title="Синтетичний архівний")
        Document.objects.filter(pk=archived_doc.pk).update(state="archived")
    pages[-1] = (admin, f"/document/{archived_doc.number}/info/")
    # The copy dialog and a copy's *Info*, on a document with a repository.
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import copying, services
    from documents.models import DocumentType
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(
            name="Оператори (synthetic example)", created_by=admin_user, actor_kind="user"
        )
        for right in Right:
            group.grant(right, by=admin_user)
        group.add_member(admin_membership, by=admin_user)
        kind, root = DocumentType.objects.get(code="document"), Folder.objects.get(number=1)
        source = services.create_document(admin_user, "Синтетичне джерело", "uk", kind, root)
        DocumentGroup.link(source, group, by=admin_user)
        copied = copying.copy_document(
            admin_user,
            source,
            title="Синтетична копія",
            document_type=kind,
            folder=root,
            view="accepted",
            number="0.0",
            appendices=[],
        )
    pages += [
        (admin, f"/document/{source.number}/copy/"),
        (admin, f"/document/{copied.number}/info/"),
    ]
    for client, path in pages:
        response = client.get(path)
        assert response.status_code == 200, path
        body = text_of(response.content.decode())
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"
        if path == "/folder/1/":
            assert "Усі типи" in body, path
        if path.endswith("/copy/"):
            assert "Копіювати документ" in response.content.decode(), path
        if path == f"/document/{copied.number}/info/":
            assert "Скопійовано з" in body, path
        if path.endswith("/folders/"):
            # The glossary's *тека*, and a count in its Ukrainian plural form.
            assert "Теки" in body and "1 документ" in body, path
        if "document-types" in path or "/info/" in path:
            # The seeded type's label, as data: a cell or a choice of its own.
            assert re.search(r">\s*Документ\s*<", response.content.decode()), path


@pytest.mark.integration
def test_makemessages_adds_no_entry(tmp_path: Path) -> None:
    # In a copy of the source tree, as its own process: the committed catalogue is never touched.
    copy = tmp_path / "src"
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__", "staticfiles"))
    made = subprocess.run(
        [sys.executable, "manage.py", "makemessages", "-l", "uk", "--verbosity", "0"],
        cwd=copy,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(copy)},
    )
    assert made.returncode == 0, made.stderr.decode(errors="replace")
    before = entries(CATALOGUE.read_text(encoding="utf-8"))
    after = entries(
        (copy / "shell" / "locale" / "uk" / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
    )

    assert sorted(set(after) - set(before)) == []
    assert [key for key, value in after.items() if not value] == []


@pytest.mark.fast
def test_the_compiled_catalogue_is_the_catalogue() -> None:
    compiled = gettext.GNUTranslations((LOCALE / "uk" / "LC_MESSAGES" / "django.mo").open("rb"))

    catalogue = CATALOGUE.read_text(encoding="utf-8")
    plural = plurals(catalogue)
    # One count per Ukrainian form: 1 takes the first, 2 the second, 5 the third.
    counts = (1, 2, 5)

    def compiled_forms(key: tuple[str, str]) -> list[str]:
        other = plural[key][0]
        if key[0]:
            return [compiled.npgettext(key[0], key[1], other, n) for n in counts]
        return [compiled.ngettext(key[1], other, n) for n in counts]

    stale = [
        key
        for key, value in entries(catalogue).items()
        if key not in plural
        and (compiled.pgettext(*key) if key[0] else compiled.gettext(key[1])) != value
    ]
    stale += [key for key, (_other, forms) in plural.items() if compiled_forms(key) != forms]

    assert stale == []
