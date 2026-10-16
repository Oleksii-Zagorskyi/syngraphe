"""The folder tree a person sees (DL-0206): only folders holding, at any depth, an active document
they may read — every folder to an administrator — alphabetically, a hidden folder's address
answering as a missing one (ADR-0008).

Folder names, groups, people and titles are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def _folder(migrated_tenant: Any, by: Any, name: str, parent: Any = None) -> Any:
    from documents import folders
    from documents.models import Folder

    with schema_context(migrated_tenant.number):
        return folders.create_folder(parent or Folder.objects.get(number=1), name, by=by)


def _read_by(migrated_tenant: Any, by: Any, membership: Any, *documents: Any) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=by, actor_kind="user")
        group.grant(Right.VIEW_ACCEPTED, by=by)
        group.add_member(membership, by=by)
        for document in documents:
            DocumentGroup.link(document, group, by=by)


def uniform(body: bytes) -> str:
    """A page's body with its per-request token taken out, so two answers compare."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", body.decode())


def _tree_names(body: str) -> list[str]:
    pane = body.split('class="folder-tree"', 1)[1].split("</nav>", 1)[0]
    return re.findall(r'<a href="/folder/\d+/"[^>]*>([^<]+)</a>', pane)


@pytest.fixture
def corpus(migrated_tenant: Any, member_of: Any, make_document: Any) -> dict[str, Any]:
    """*A / B / C* holding a document the member reads; *D* one they may not read; *E* an archived
    one they read."""
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, membership = member_of("a.member@example.test")
    a = _folder(migrated_tenant, admin_user, "A (synthetic example)")
    b = _folder(migrated_tenant, admin_user, "B (synthetic example)", a)
    c = _folder(migrated_tenant, admin_user, "C (synthetic example)", b)
    d = _folder(migrated_tenant, admin_user, "D (synthetic example)")
    e = _folder(migrated_tenant, admin_user, "E (synthetic example)")
    readable = make_document(title="Synthetic readable", folder=c, author_only=False)
    make_document(title="Synthetic unreadable", folder=d, author_only=False)
    archived = make_document(
        title="Synthetic archived", folder=e, author_only=False, state="archived"
    )
    _read_by(migrated_tenant, admin_user, membership, readable, archived)
    return {
        "admin": admin,
        "admin_user": admin_user,
        "member": member,
        "membership": membership,
        "folders": {"A": a, "B": b, "C": c, "D": d, "E": e},
    }


def test_a_member_sees_only_folders_above_what_they_read(
    migrated_tenant: Any, corpus: dict[str, Any]
) -> None:
    from documents.tree import visible_folders
    from identity.models import User

    folders = corpus["folders"]
    member = User.objects.get(email="a.member@example.test")
    with schema_context(migrated_tenant.number):
        seen = visible_folders(member, administrator=False)
        everything = visible_folders(corpus["admin_user"], administrator=True)

    assert seen == {1, folders["A"].number, folders["B"].number, folders["C"].number}
    assert everything == {1, *(f.number for f in folders.values())}
    member_tree = _tree_names(corpus["member"].get("/folder/1/").content.decode())
    admin_tree = _tree_names(corpus["admin"].get("/folder/1/").content.decode())
    assert member_tree == [
        "Example Org",
        "A (synthetic example)",
        "B (synthetic example)",
        "C (synthetic example)",
    ]
    assert len(admin_tree) == 6


def test_a_hidden_folder_answers_as_a_missing_one(
    migrated_tenant: Any, corpus: dict[str, Any], settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    folders = corpus["folders"]
    member = corpus["member"]

    answers = [
        member.get(f"/folder/{folders['D'].number}/"),
        member.get(f"/folder/{folders['E'].number}/"),
        member.get("/folder/999/"),
    ]
    shown = member.get(f"/folder/{folders['C'].number}/")
    above = member.get(f"/folder/{folders['A'].number}/")

    assert [a.status_code for a in answers] == [404, 404, 404]
    assert all("Nothing to show here" in a.content.decode() for a in answers)
    # Exactly as a missing folder answers: one body, no name.
    assert len({uniform(a.content) for a in answers}) == 1
    assert shown.status_code == 200 and "Synthetic readable" in shown.content.decode()
    # A folder above what the member reads lists only its own documents: none.
    assert above.status_code == 200 and "Synthetic readable" not in above.content.decode()
    assert corpus["admin"].get(f"/folder/{folders['D'].number}/").status_code == 200


def test_folders_and_paths_sort_alphabetically(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Siblings in `uk-x-icu` order, paths component by component (the Cyrillic collation is
    the subject)."""
    from documents.tree import Tree

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    ye = _folder(migrated_tenant, admin_user, "Євро")
    be = _folder(migrated_tenant, admin_user, "Бета")
    ge = _folder(migrated_tenant, admin_user, "Ґанок")
    inner = _folder(migrated_tenant, admin_user, "Явка", be)
    deeper = _folder(migrated_tenant, admin_user, "апельсин", be)
    with schema_context(migrated_tenant.number):
        tree = Tree("Example Org")
        flat = [node.folder.name or "root" for node in tree.flat()]
        keys = sorted((tree.path_key(f), tree.path_of(f)) for f in (ye, ge, inner, deeper, be))

    assert flat == ["root", "Бета", "апельсин", "Явка", "Ґанок", "Євро"]
    assert [path for _key, path in keys] == [
        "Бета",
        "Бета / апельсин",
        "Бета / Явка",
        "Ґанок",
        "Євро",
    ]
    for folder in (ye, ge, inner):
        make_document(title=f"Synthetic in {folder.number}", folder=folder, author_only=False)
    tree_names = _tree_names(admin.get("/folder/1/").content.decode())
    assert tree_names == ["Example Org", "Бета", "апельсин", "Явка", "Ґанок", "Євро"]


def test_a_member_who_reads_nothing_sees_the_root_alone(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents.tree import visible_folders
    from identity.models import User

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    folder = _folder(migrated_tenant, admin_user, "Policies (synthetic example)")
    make_document(title="Synthetic unread", folder=folder, author_only=False)
    with schema_context(migrated_tenant.number):
        seen = visible_folders(User.objects.get(email="a.member@example.test"), administrator=False)

    assert seen == {1}
    assert _tree_names(member.get("/folder/1/").content.decode()) == ["Example Org"]


def test_the_pane_opens_the_selected_folder_and_its_ancestors(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """*A / B / C* and a sibling *D / E*: on *B*, the root, *A* and *B* open, *D* shut, *B* bold;
    every list in the pane closed."""
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    a = _folder(migrated_tenant, admin_user, "A (synthetic example)")
    b = _folder(migrated_tenant, admin_user, "B (synthetic example)", a)
    _folder(migrated_tenant, admin_user, "C (synthetic example)", b)
    d = _folder(migrated_tenant, admin_user, "D (synthetic example)")
    _folder(migrated_tenant, admin_user, "E (synthetic example)", d)

    body = admin.get(f"/folder/{b.number}/").content.decode()
    pane = body.split('class="folder-tree"', 1)[1].split("</nav>", 1)[0]

    def item(name: str) -> str:
        return pane.split(f">{name}</a>", 1)[0].rsplit("<li", 1)[1]

    assert 'class="shut"' not in item("A (synthetic example)")
    assert 'class="shut"' not in item("B (synthetic example)")
    assert 'class="shut"' in item("D (synthetic example)")
    assert re.search(r'aria-current="page">B \(synthetic example\)</a>', pane)
    assert pane.count("<ul") == pane.count("</ul>")
    assert pane.count("<li") == pane.count("</li>")


def test_a_folder_deleted_while_its_page_is_read_is_missing(
    migrated_tenant: Any, member_of: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another administrator deletes the folder after the page has read who sees it and before
    it reads the tree: the page answers as for a missing folder, never a server error."""
    from documents import tree
    from documents.models import Folder

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    leaf = _folder(migrated_tenant, admin_user, "Leaf (synthetic example)")
    seen = tree.visible_folders

    def deleted_after(user: Any, *, administrator: bool) -> set[int]:
        numbers = seen(user, administrator=administrator)
        Folder.objects.filter(pk=leaf.pk).delete()
        return numbers

    monkeypatch.setattr(tree, "visible_folders", deleted_after)

    assert admin.get(f"/folder/{leaf.number}/").status_code == 404
