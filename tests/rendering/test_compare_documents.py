"""Comparing two documents (ST-0064, DL-0187, DL-0452): the second document's whole text marked
against the first's, each version resolved through its own document's ceiling, each document's
attachments listed apart at its version; the picker; the three starts.

People, groups, titles and texts are synthetic examples; every text is invented.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIRST = "# Leave\n\nA request is made ten days in advance.\n"
SECOND = "# Leave\n\nA request is made fifteen days in advance.\n"


class Side(SimpleNamespace):
    """One document and its cast, in the shape `kit.attach` reads: `.document`, `["a"]`."""

    def __getitem__(self, name: str) -> Any:
        return self.people[name]


@pytest.fixture
def two(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> SimpleNamespace:
    """`#a` and `#b`, each at edition `1.0` with one attachment; `#a` then pending `1.0-1` and
    `1.0-2`, `#b` pending `1.0-1`. The editor, reviewer and approver are one cast on both."""
    from editions import services as editions
    from review import services as review

    tenant = migrated_tenant.number
    people: dict[str, Any] = {}
    memberships: dict[str, Any] = {}
    for name in ("a", "r", "p"):
        _client, people[name], memberships[name] = member_of(f"{name}.synthetic@example.test")
    sides = []
    for title, body, data, pending in (
        ("Synthetic leave rules", FIRST, b"first table\n", 2),
        ("Synthetic leave rules for contractors", SECOND, b"contractor form\n", 1),
    ):
        document = new_document(people["a"], title)
        link_group(document, [Right.EDIT], [memberships["a"]], people["a"])
        link_group(document, [Right.ACCEPT], [memberships["r"]], people["a"])
        link_group(document, [Right.FREEZE, Right.MAKE_CANONICAL], [memberships["p"]], people["a"])
        side = Side(document=document, people=people)
        kit.attach(tenant, side, body, data)
        with schema_context(tenant):
            review.accept(document, people["r"])
            editions.freeze(document, people["p"], "Synthetic reason")
            editions.make_canonical(document, people["p"])
        for k in range(pending):
            commit_version(document, people["a"], body + f"\nA synthetic line {k}.\n", "edit")
        sides.append(side)
    return SimpleNamespace(a=sides[0].document, b=sides[1].document, people=people)


def _reader(member_of: Any, link_group: Any, two: Any, documents: list[Any], rights: list[Any],
            name: str, **kwargs: Any) -> Any:  # fmt: skip
    client, _user, membership = member_of(f"{name}.synthetic@example.test", **kwargs)
    for document in documents:
        link_group(document, rights, [membership], two.people["a"])
    return client


def _membership(name: str) -> Any:
    from identity.models import Membership

    return Membership.objects.get(user__email=f"{name}.synthetic@example.test")


def _unmasked(page: bytes) -> bytes:
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]+"', b"", page)


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", page))


HISTORY = [Right.VIEW_ALL_HISTORY, Right.VIEW_PENDING]


def test_two_documents_compared(two: Any, member_of: Any, link_group: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    client = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "h")
    a, b = two.a.number, two.b.number

    page = client.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0-1")

    assert page.status_code == 200
    body = page.content.decode()
    assert f"Comparing #{a} 1.0 with #{b} 1.0-1 — read only" in _text(body)
    for href in (f"/document/{a}/", f"/document/{a}/version/1.0/", f"/document/{b}/",
                 f"/document/{b}/version/1.0-1/"):  # fmt: skip
        assert f'href="{href}"' in body, href
    assert "<del>ten</del><ins>fifteen</ins>" in body
    # Each document's attachments under its own number and version, linked at that version and
    # nowhere else (DL-0452).
    lists = re.findall(
        r'<section class="attachments document-attachments">(.*?)</section>', body, re.S
    )
    assert len(lists) == 2
    assert (
        f"#{a} 1.0<" in lists[0] and f'href="/document/{a}/version/1.0/attachment/1/"' in lists[0]
    )
    assert f"#{b} 1.0-1<" in lists[1]
    assert f'href="/document/{b}/version/1.0-1/attachment/1/"' in lists[1]
    assert f"/document/{b}/" not in lists[0] and f"/document/{a}/" not in lists[1]
    # No *previous* and *next* across documents.
    assert 'class="step' not in body
    assert 'name="with"' in body and 'name="from"' in body and 'name="to"' in body
    # The second document the choosers show, so a changed number drops its `to`.
    assert f'name="was" value="{b}"' in body


def test_what_may_not_be_seen_is_missing(
    two: Any, member_of: Any, link_group: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    a, b = two.a.number, two.b.number
    only_a = _reader(member_of, link_group, two, [two.a], HISTORY, "first")
    canonical = _reader(member_of, link_group, two, [two.a, two.b], [Right.VIEW_CANONICAL], "c")
    refused = [
        (only_a, only_a.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0")),
        (canonical, canonical.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0-1")),
    ]

    for client, answer in refused:
        assert answer.status_code == 404
        # The uniform body, as this reader sees any address that does not exist.
        assert _unmasked(answer.content) == _unmasked(client.get("/document/999999/").content)
    assert canonical.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0").status_code == 200

    # Each version through its own document's ceiling, never the other's.
    deep_a = _reader(member_of, link_group, two, [two.a], HISTORY, "deep-a")
    link_group(two.b, [Right.VIEW_CANONICAL], [_membership("deep-a")], two.people["a"])
    deep_b = _reader(member_of, link_group, two, [two.b], HISTORY, "deep-b")
    link_group(two.a, [Right.VIEW_CANONICAL], [_membership("deep-b")], two.people["a"])
    assert deep_a.get(f"/document/{a}/compare/?from=1.0-1&with={b}&to=1.0").status_code == 200
    assert deep_a.get(f"/document/{a}/compare/?from=1.0-1&with={b}&to=1.0-1").status_code == 404
    assert deep_b.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0-1").status_code == 200
    assert deep_b.get(f"/document/{a}/compare/?from=1.0-1&with={b}&to=1.0-1").status_code == 404


def test_the_address_rules(two: Any, member_of: Any, link_group: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    client = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "h")
    a, b = two.a.number, two.b.number
    base = f"/document/{a}/compare/"

    itself = client.get(f"{base}?from=1.0&with={a}&to=1.0-1")
    malformed = client.get(f"{base}?from=1.0&with=x{b}&to=1.0")
    superscript = client.get(f"{base}?from=1.0&with=²&to=1.0")
    newest = client.get(f"{base}?from=1.0&with={b}")
    picker = client.get(f"{base}?from=1.0&with=")
    one_document = client.get(f"{base}?from=1.0&with=&to=1.0-1")
    only_a_has = client.get(f"{base}?from=1.0&with={b}&to=1.0-2")
    from_newest = client.get(f"{base}?with={b}&to=1.0")

    assert itself.status_code == 302 and itself["Location"] == f"{base}?from=1.0&to=1.0-1"
    assert malformed.status_code == 404 and superscript.status_code == 404
    assert f"with #{b} 1.0-1" in _text(newest.content.decode())
    shown = picker.content.decode()
    assert picker.status_code == 200 and 'name="with" value=""' in shown
    assert 'class="changes' not in shown and 'name="to"' not in shown
    assert "Comparing 1.0 with 1.0-1 — read only" in _text(one_document.content.decode())
    assert only_a_has.status_code == 404
    assert f"Comparing #{a} 1.0-2 with #{b} 1.0" in _text(from_newest.content.decode())

    # A document named as its own second: its own comparison, a missing side its newest version.
    no_to = client.get(f"{base}?from=1.0&with={a}")
    assert no_to.status_code == 302 and no_to["Location"] == f"{base}?from=1.0&to=1.0-2"
    from_list = client.get(f"/compare/?first={a}&second={a}")
    assert from_list["Location"] == f"{base}?with={a}"
    followed = client.get(from_list["Location"])
    assert followed.status_code == 302 and followed["Location"] == f"{base}?from=1.0-2&to=1.0-2"
    # Which opens that version's own page, one version asked against itself.
    assert client.get(followed["Location"])["Location"] == f"/document/{a}/version/1.0-2/"
    # Another document typed over the one shown: its `to` belonged to the old one and is dropped.
    changed = client.get(f"{base}?from=1.0&with={b}&was=99&to=1.0-2")
    assert f"Comparing #{a} 1.0 with #{b} 1.0-1" in _text(changed.content.decode())
    cleared = client.get(f"{base}?from=1.0&with=&was={b}&to=1.0-1")
    assert cleared.status_code == 200 and 'class="changes' not in cleared.content.decode()
    assert 'name="with" value=""' in cleared.content.decode()


def test_a_version_asked_by_an_earlier_number(
    two: Any, member_of: Any, link_group: Any, migrated_tenant: Any, settings: Any
) -> None:
    """A version is named by its number now, as the chooser and the historical page name it."""
    from review import services as review

    settings.LANGUAGE_CODE = "en"
    client = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "h")
    with schema_context(migrated_tenant.number):
        review.accept(two.a, two.people["r"])
    a, b = two.a.number, two.b.number

    page = client.get(f"/document/{a}/compare/?from=1.0-2&with={b}&to=1.0").content.decode()

    assert f"Comparing #{a} 1.1 with #{b} 1.0 — read only" in _text(page)
    assert '<option value="1.1" selected>' in page


def test_an_administrator_compares_an_archived_document(
    two: Any, member_of: Any, link_group: Any, migrated_tenant: Any, settings: Any
) -> None:
    from documents import archive
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    admin = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "admin",
                    is_tenant_admin=True)  # fmt: skip
    reader = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "h")
    administrator = User.objects.get(email="admin.synthetic@example.test")
    with schema_context(migrated_tenant.number):
        archive.archive(two.b, administrator)
    a, b = two.a.number, two.b.number

    page = admin.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0")

    assert page.status_code == 200
    heading = re.search(r"<h1>(.*?)</h1>", page.content.decode(), re.S)
    assert heading is not None
    after_second = heading.group(1).split("Synthetic leave rules for contractors", 1)[1]
    assert after_second.lstrip().startswith('<span class="tag" data-state="archived"')
    assert heading.group(1).count('data-state="archived"') == 1
    # The first archived too: each tag beside its own document's title.
    with schema_context(migrated_tenant.number):
        archive.archive(two.a, administrator)
    both = admin.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0").content.decode()
    heading = re.search(r"<h1>(.*?)</h1>", both, re.S)
    assert heading is not None
    tag = '<span class="tag" data-state="archived"'
    assert re.search(rf"Synthetic leave rules\s*{re.escape(tag)}", heading.group(1))
    assert re.search(rf"for contractors\s*{re.escape(tag)}", heading.group(1))
    assert "<del>ten</del><ins>fifteen</ins>" in page.content.decode()
    assert reader.get(f"/document/{a}/compare/?from=1.0&with={b}&to=1.0").status_code == 404


def test_the_three_starts(two: Any, member_of: Any, link_group: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    client = _reader(member_of, link_group, two, [two.a, two.b], HISTORY, "h")
    only_a = _reader(member_of, link_group, two, [two.a], HISTORY, "first")
    a, b = two.a.number, two.b.number

    # The document page: a link to the picker, from the version the page shows.
    page = client.get(f"/document/{a}/").content.decode()
    start = re.search(rf'href="(/document/{a}/compare/\?from=1\.0-2&amp;with=)"', page)
    assert start is not None
    picker = client.get(start.group(1).replace("&amp;", "&"))
    assert picker.status_code == 200 and 'name="with" value=""' in picker.content.decode()

    # The historical page: its first form compares two versions, the second another document.
    historical = client.get(f"/document/{a}/version/1.0/").content.decode()
    forms = re.findall(r'<form class="(compare-[a-z-]+)"[^>]*>(.*?)</form>', historical, re.S)
    named = dict(forms)
    assert 'name="to"' in named["compare-with"] and 'name="from"' in named["compare-with"]
    second = named["compare-with-document"]
    assert 'name="from" value="1.0"' in second and 'name="with"' in second
    assert 'name="to"' not in second
    sent = client.get(f"/document/{a}/compare/?from=1.0&with={b}")
    assert f"Comparing #{a} 1.0 with #{b} 1.0-1" in _text(sent.content.decode())

    # The list: two numbers, to the comparison's own address.
    listed = client.get("/folder/1/").content.decode()
    assert 'action="/compare/"' in listed
    assert 'name="first"' in listed and 'name="second"' in listed
    started = client.get(f"/compare/?first={a}&second={b}")
    assert started.status_code == 302 and started["Location"] == f"/document/{a}/compare/?with={b}"
    assert only_a.get(f"/compare/?first={a}&second={b}").status_code == 404
    assert only_a.get(f"/compare/?first={b}&second={a}").status_code == 404
    assert client.get(f"/compare/?first={a}&second=x").status_code == 404


def test_each_side_reads_its_own_document(
    two: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    new_document: Any,
    pictures: Any,
    settings: Any,
) -> None:
    """Each side's images come from its own document — one both texts show, as a copy shares its
    source's, from the second — and the pair is captioned `#n version`. Neither compared document's
    mention is followed, on either side: the reader is on both, each linked in the banner
    (DL-11-012). A third document's mention is followed where its reader may read it."""
    settings.LANGUAGE_CODE = "en"
    client, _user, membership = member_of("h.synthetic@example.test")
    third = new_document(two.people["a"], "Synthetic third rules")
    for document in (two.a, two.b, third):
        link_group(document, HISTORY, [membership], two.people["a"])
    a, b, c = two.a.number, two.b.number, third.number
    first, second, shared = pictures.make(1), pictures.make(2), pictures.make(3)
    old = (
        f"\nThese are [the general rules]{{.document #{a}}}, "
        f"beside [the others]{{.document #{b}}}.\n" + shared.paragraph + first.paragraph
    )
    new = (
        f"\nAs [the general rules]{{.document #{a}}} say, [these rules]{{.document #{b}}} apply, "
        f"with [the third]{{.document #{c}}}.\n" + shared.paragraph + second.paragraph
    )
    commit_version(
        two.a,
        two.people["a"],
        FIRST + old,
        "edit",
        files={shared.path: shared.data, first.path: first.data},
    )
    commit_version(
        two.b,
        two.people["a"],
        SECOND + new,
        "edit",
        files={shared.path: shared.data, second.path: second.data},
    )

    page = client.get(f"/document/{a}/compare/?from=1.0-3&with={b}&to=1.0-2").content.decode()

    changes = page.split('class="changes', 1)[1].split("</aside>", 1)[0].split("<aside", 1)[0]
    assert f'src="/document/{a}/image/{first.name}/"' in changes
    assert f'src="/document/{b}/image/{second.name}/"' in changes
    assert f'src="/document/{b}/image/{shared.name}/"' in changes
    assert f'src="/document/{a}/image/{shared.name}/"' not in changes
    assert f"#{a} 1.0-3" in changes and f"#{b} 1.0-2" in changes
    for number in (a, b):
        assert f'href="/document/{number}/"' not in changes, number
    assert "the general rules" in changes and "these rules" in changes
    assert f'href="/document/{c}/"' in changes
