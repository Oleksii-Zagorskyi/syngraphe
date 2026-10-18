"""Administration › template (ST-0058, DL-0169): the outline every new document starts from and
the title-page switch, edited by the organisation's administrators, checked at save and again at
creation, and never reaching an existing document.

Outlines, titles and people are synthetic examples."""

from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/template/"
LOAD = Path(__file__).resolve().parents[1] / "fixtures" / "load"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    # The refusals' wording is read in English; the catalogue test reads the page in `uk`.
    settings.LANGUAGE_CODE = "en"


def _chosen_by_a_platform_administrator(migrated_tenant: Any, signed_in: Any) -> Client:
    client = signed_in("p.admin@example.test", is_platform_admin=True)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    return client


def _template(migrated_tenant: Any) -> Any:
    from documents.models import DocumentTemplate

    with schema_context(migrated_tenant.number):
        return DocumentTemplate.objects.get()


def _events(action: str) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.filter(action=action).order_by("at"))


def test_only_administrators_open_the_template(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    platform = _chosen_by_a_platform_administrator(migrated_tenant, signed_in_without_tenant)
    template = _template(migrated_tenant)
    outline = template.outline
    created = template.created_at.strftime("%-d %B %Y")

    for client in (admin, platform):
        response = client.get(PAGE)
        assert response.status_code == 200
        page = html.unescape(response.content.decode())
        assert outline.strip() in page
        assert 'name="title_page"' in page
        assert "New documents get a title page" in page
        # The date the organisation's template was made, while nobody has changed it.
        assert f"Not changed since {created}" in page
        assert "Changing it never touches existing documents." in page
    assert member.get(PAGE).status_code == 404
    assert member.post(PAGE, {"outline": "# Purpose\n"}).status_code == 404


def test_saving_the_template_is_audited(migrated_tenant: Any, member_of: Any) -> None:
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    admin_user.display_name = "An Administrator"
    admin_user.save(update_fields=["display_name"])
    before = _template(migrated_tenant)
    outline = "# Purpose\nWhy this synthetic document exists.\n\n# Scope\n"

    response = admin.post(PAGE, {"outline": outline, "title_page": "on"})

    assert response.status_code == 303
    assert response["Location"] == PAGE
    after = _template(migrated_tenant)
    assert (after.outline, after.title_page, after.updated_by_id) == (outline, True, admin_user.pk)
    (event,) = _events("template.changed")
    assert event.object_type == "documenttemplate" and event.object_id == after.pk
    assert event.before == {
        "outline": before.outline,
        "title_page": False,
        "title_page_layout": "",
    }
    assert event.after == {"outline": outline, "title_page": True, "title_page_layout": ""}
    assert "Last changed by An Administrator" in admin.get(PAGE).content.decode()


def test_a_refused_template_names_each_line(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    before = _template(migrated_tenant)

    response = admin.post(PAGE, {"outline": "Starting text\n<div>raw</div>\n# Scope\n"})

    assert response.status_code == 400
    page = html.unescape(response.content.decode())
    assert "Line 2: HTML" in page
    assert "Line 1: The template must begin with a # heading" in page
    # What was typed stays in the box, for the administrator to correct.
    assert "&lt;div&gt;raw&lt;/div&gt;" in response.content.decode()
    after = _template(migrated_tenant)
    assert (after.outline, after.updated_at) == (before.outline, before.updated_at)
    assert _events("template.changed") == []


def test_the_template_refuses_an_image_a_long_text_and_one_without_a_normal_form(
    migrated_tenant: Any, member_of: Any, monkeypatch: Any
) -> None:
    from documents import template
    from editing.normalizer import NormalizerDefect
    from identity.models import Language

    Language.objects.get_or_create(code="en", defaults={"label": "en", "actor_kind": "system"})
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    image = "images/" + "a" * 64 + ".png"

    pictured = admin.post(PAGE, {"outline": f"# Purpose\n\n![A synthetic picture]({image})\n"})
    long = admin.post(PAGE, {"outline": "# Purpose\n\n" + "Synthetic words. " * 1_200})

    def refused_by_the_normaliser(previous: bytes, submitted: str, lists: Any) -> bytes:
        raise NormalizerDefect("synthetic")

    # A text the whitelist accepts that the normaliser cannot put in its form: none is known, so
    # the normaliser is made to refuse.
    monkeypatch.setattr(template, "normalize", refused_by_the_normaliser)
    unformed = admin.post(PAGE, {"outline": "# Purpose\nA synthetic sentence unformed.\n"})

    assert pictured.status_code == 400
    assert "Line 3: A template cannot hold an image" in html.unescape(pictured.content.decode())
    assert long.status_code == 400
    assert "Line 1: a text longer than the platform accepts" in html.unescape(long.content.decode())
    assert unformed.status_code == 400
    refused = html.unescape(unformed.content.decode())
    # About the whole outline, so no line is named.
    assert "The template cannot be put in the platform's form in en" in refused
    assert "Line 1: The template cannot" not in refused
    assert _events("template.changed") == []


def _author(migrated_tenant: Any, member_of: Any) -> tuple[Client, Any]:
    from access.models import AccessGroup
    from access.rights import Right
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    client, user, membership = member_of("an.author@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Authors", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)
    return client, user


def _created(migrated_tenant: Any, user: Any, title: str) -> Any:
    from documents import services
    from documents.models import DocumentType, Folder

    with schema_context(migrated_tenant.number):
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        return services.create_document(user, title, "uk", kind, root)


def _first_body(migrated_tenant: Any, document: Any) -> str:
    from documents import bundle, gitstore

    repo = gitstore.open_repository(migrated_tenant.number, document.number)
    first = list(gitstore.history(repo))[-1]
    return bundle.parse(gitstore.read(repo, "document.md", str(first.id)).decode())[1]


def test_a_change_reaches_only_documents_created_after(
    migrated_tenant: Any, member_of: Any, repo_root: Path
) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user = _author(migrated_tenant, member_of)
    old = _template(migrated_tenant).outline
    first = _created(migrated_tenant, user, "Synthetic first")

    saved = admin.post(PAGE, {"outline": "# Purpose\nOne sentence. Another sentence.\n"})
    second = _created(migrated_tenant, user, "Synthetic second")

    assert saved.status_code == 303
    assert _first_body(migrated_tenant, first) == old
    assert _first_body(migrated_tenant, second) == (
        "# Purpose\n\nOne sentence.\nAnother sentence.\n"
    )


def test_creation_refuses_a_template_that_does_not_pass(
    migrated_tenant: Any, member_of: Any, repo_root: Path, tmp_path: Path
) -> None:
    from documents import loading, services
    from documents.models import Document, DocumentTemplate, DocumentType, Folder
    from documents.template import TemplateRefused

    client, user = _author(migrated_tenant, member_of)
    with schema_context(migrated_tenant.number):
        # Written outside the page, as no administrator's save could.
        DocumentTemplate.objects.update(outline="# Purpose\n\n<div>raw</div>\n")
        kind = DocumentType.objects.get(code="document")
        root = Folder.objects.get(number=1)
        with pytest.raises(TemplateRefused):
            services.create_document(user, "Synthetic refused", "uk", kind, root)
        # Past the template's size, as no administrator's save could leave it.
        DocumentTemplate.objects.update(outline="# Purpose\n\n" + "Synthetic words. " * 1_200)
        with pytest.raises(TemplateRefused):
            services.create_document(user, "Synthetic refused", "uk", kind, root)
        DocumentTemplate.objects.update(outline="# Purpose\n\n<div>raw</div>\n")
        assert not Document.objects.exists()
        form = {
            "title": "Synthetic refused",
            "language": "uk",
            "document_type": str(kind.id),
            "folder": str(root.id),
        }

    response = client.post("/document/new/", form)

    assert response.status_code == 409
    page = html.unescape(response.content.decode())
    assert "The organisation's document template holds what the platform does not accept." in page
    assert 'value="Synthetic refused"' in page
    with schema_context(migrated_tenant.number):
        assert not Document.objects.exists()
        # The next creation takes the number the refused ones never took.
        DocumentTemplate.objects.update(outline="# Purpose\n")
        created = services.create_document(user, "Synthetic accepted", "uk", kind, root)
    assert created.number == 1

    # The loader is refused the same way, before anything is written.
    from access.models import AccessGroup
    from access.rights import Right

    folder = tmp_path / "procedure-ukr"
    shutil.copytree(LOAD / "procedure-ukr", folder)
    with schema_context(migrated_tenant.number):
        DocumentTemplate.objects.update(outline="# Purpose\n\n<div>raw</div>\n")
        group = AccessGroup.objects.create(
            name="Operators (synthetic example)", actor_kind="system"
        )
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.grant(Right.ACCEPT, by=None)
        group.add_member(user.memberships.get(tenant=migrated_tenant), by=None)
        with pytest.raises(loading.Refused) as refused:
            loading.load(folder, user, group)
        assert Document.objects.count() == 1
    assert "template" in " ".join(refused.value.reasons)
