"""The generated views (DL-0073, DL-0437, DL-0448): the role directory — each declared role with
every heading or clause marking it, numbered and linked to its place — and *see also*, each
document the text mentions, linked where the reader may follow it and its words where not; derived
at render from the version shown. People and titles are synthetic examples; text is invented."""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

BODY = (
    "# One\n\n"
    "A first clause marks [the clerk]{.role #clerk}.\n\n"
    "The second clause stands before a table.\n\n"
    "| Who | Does |\n| --- | --- |\n| [The clerk]{.role #clerk} | files |\n\n"
    "# Two [the approver]{.role #approver}\n\n"
    "A clause with [the approver]{.role #approver}.\n\n"
    "Also [a stranger]{.role #ghost} and [a helper]{.role} help.\n\n"
    "# Three\n\n"
    "## Three one\n\n"
    "The first clause here.\n\n"
    "Then [the approver]{.role #approver} again.\n"
)


def declared() -> list[Any]:
    from documents.entities import Declared

    return [
        Declared("role", "approver", "the approver"),
        Declared("role", "clerk", "the clerk"),
        Declared("role", "auditor", "the auditor"),
    ]


def stream(body: str, **more: str) -> Any:
    from rendering import directory, outline
    from rendering.renderer import labelled

    tokens = labelled(body)
    outline.anchor_clauses(tokens)
    return directory.Stream(tokens, **more)


@pytest.mark.fast
def test_the_role_directory(settings: Any) -> None:
    from rendering import directory

    settings.LANGUAGE_CODE = "en"
    roles = directory.roles([stream(BODY)], declared(), context=None)

    assert [(r.key, r.label) for r in roles] == [
        ("approver", "the approver"),
        ("clerk", "the clerk"),
        ("auditor", "the auditor"),
        ("ghost", "a stranger"),
        (None, "a helper"),
    ]
    approver, clerk, auditor, ghost, helper = roles
    assert [(p.label, p.href) for p in approver.places] == [
        ("2", "#h-2"),
        ("2-1", "#c-2-1"),
        ("3.1-2", "#c-3.1-2"),
    ]
    # A place's text as the page renders it, the role in its own formatting.
    assert approver.places[1].html == (
        'A clause with <span class="entity entity-role" data-id="approver">the approver</span>.'
    )
    assert [(p.label, p.href) for p in clerk.places] == [
        ("1-1", "#c-1-1"),
        ("1-2 (table)", "#c-1-2"),
    ]
    assert auditor.places == []
    assert [p.label for p in ghost.places] == ["2-2"] == [p.label for p in helper.places]


@pytest.mark.fast
def test_a_role_marked_without_a_key_is_shown_as_not_declared(settings: Any) -> None:
    """A role marked without a key declares nothing: the panel says so beside its words, so it
    is told apart from a declared role of the same label."""
    from django.template.loader import render_to_string

    from rendering import directory

    settings.LANGUAGE_CODE = "en"
    body = "Here [the clerk]{.role #clerk} and [the clerk]{.role} meet.\n"
    roles = directory.roles([stream(body)], declared(), context=None)
    html = render_to_string("rendering/generated_views.html", {"roles": roles, "see_also": []})

    assert html.count("<strong>the clerk</strong>") == 2
    assert html.count("not declared") == 1
    assert '<strong>the clerk</strong> <span class="muted">(not declared)</span>' in html


@pytest.mark.fast
def test_a_role_is_labelled_as_the_commit_would_declare_it(settings: Any) -> None:
    """The directory's label for a role the file does not declare is the label the commit would
    write: its words with inline code's, cut where a label is."""
    from documents import entities
    from rendering import directory

    settings.LANGUAGE_CODE = "en"
    long = "w" * 250
    body = f"Here [the `form` clerk]{{.role #x}} and [{long}]{{.role #y}} meet.\n"
    roles = directory.roles([stream(body)], [], context=None)
    committed = entities.parse(entities.declared_with("", body))

    assert [r.label for r in roles] == [e.label for e in committed]
    assert [e.label for e in committed] == ["the form clerk", "w" * entities.LABEL_MAX]


@pytest.mark.fast
def test_clause_anchors_are_set_in_the_views_tokens_alone() -> None:
    from rendering.renderer import render, render_tokens

    plain = render(BODY)
    anchored = render_tokens(stream(BODY).tokens)

    assert 'id="c-' not in plain
    assert '<p id="c-1-1"><span class="num">1-1</span>' in anchored


@pytest.mark.fast
def test_several_streams(settings: Any) -> None:
    """A part of the document passes as a stream of its own: its page and its name on each
    place; *see also* reads every body, a document only the second mentions listed after the
    first's."""
    from rendering import directory, mentions

    settings.LANGUAGE_CODE = "en"
    calendar = stream(
        "# Holidays\n\nThe holidays name [the approver]{.role #approver}.\n",
        link="/x/",
        label="Holiday calendar, ",
    )

    [approver, *_] = directory.roles([stream(BODY), calendar], declared(), context=None)

    assert (approver.places[-1].label, approver.places[-1].href) == (
        "Holiday calendar, 1-1",
        "/x/#c-1-1",
    )

    found = mentions.targets(
        "See [the rules]{.document #7} and [the guide]{.document #8}.\n",
        "Also [the calendar]{.document #9}, [these rules]{.document #7}.\n",
    )
    listed = mentions.see_also(None, found, own=8, reachable=frozenset())
    assert [(e.number, e.words) for e in listed] == [(7, "the rules"), (9, "the calendar")]


@pytest.mark.fast
def test_a_clause_in_a_tight_list_and_a_table_first_are_linked(settings: Any) -> None:
    """Every place links to an anchor the page carries: a tight list's item, whose paragraph is
    not drawn, carries its clause's; a table before any heading or clause carries its own."""
    from rendering import directory
    from rendering.renderer import render_tokens

    settings.LANGUAGE_CODE = "en"
    body = (
        "| Who |\n| --- |\n| [the auditor]{.role #auditor} |\n\n"
        "Intro.\n\n- one [the clerk]{.role #clerk}\n- two\n"
    )
    shown = stream(body)
    html = render_tokens(shown.tokens)

    roles = {r.key: r for r in directory.roles([shown], declared(), context=None)}

    assert [(p.label, p.href) for p in roles["clerk"].places] == [("2", "#c-2")]
    assert [(p.label, p.href) for p in roles["auditor"].places] == [("(table)", "#t-1")]
    assert '<li id="c-2">' in html and '<table id="t-1">' in html


@pytest.mark.fast
def test_a_clause_of_many_roles_is_shown_in_linear_space(settings: Any) -> None:
    """A clause holding thousands of roles is rendered once, and each place shows at most a
    clause's opening: the directory's size is linear in the text's."""
    from rendering import directory

    settings.LANGUAGE_CODE = "en"
    body = "# One\n\nA clause " + " ".join(f"[w{n}]{{.role}}" for n in range(3000)) + ".\n"

    roles = directory.roles([stream(body)], [], context=None)

    assert len(roles) == 3000
    shown = sum(len(place.html) for role in roles for place in role.places)
    assert shown < 200 * len(body)


@pytest.mark.budget
def test_a_clause_of_many_roles_costs_about_its_length(settings: Any) -> None:
    import time

    from rendering import directory
    from rendering.renderer import RENDERER

    settings.LANGUAGE_CODE = "en"
    body = "# One\n\nA clause " + " ".join(f"[w{n}]{{.role}}" for n in range(16_000)) + ".\n"
    started = time.perf_counter()
    RENDERER.parse(body)
    parsed = time.perf_counter() - started
    shown = stream(body)
    started = time.perf_counter()
    directory.roles([shown], [], context=None)
    assert time.perf_counter() - started < 3 * parsed + 0.1


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_see_also(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """Each document mentioned once, in order of first mention, the document itself left out: its
    number and title where the reader may follow it, its first words where not (DL-0437)."""
    settings.LANGUAGE_CODE = "en"
    client, _, membership = member_of("the.reader@example.test")
    _, owner, _ = member_of("the.owner@example.test")
    here = new_document(owner, "Synthetic leave rules")
    open_ = new_document(owner, "Synthetic travel rules")
    closed = new_document(owner, "Synthetic procurement rules")
    for document in (here, open_):
        link_group(document, [Right.VIEW_PENDING], [membership], owner)
    body = (
        f"See [the travel rules]{{.document #{open_.number}}} "
        f"and [the purchasing rules]{{.document #{closed.number}}}.\n\n"
        f"Then [the buying guide]{{.document #{closed.number}}}.\n\n"
        f"Again [these rules]{{.document #{open_.number}}}, "
        f"and [this one]{{.document #{here.number}}}.\n"
    )
    commit_version(here, owner, body)

    page = client.get(f"/document/{here.number}/").content.decode()

    listed = page[page.index('class="see-also"') :]
    assert (
        f'<a href="/document/{open_.number}/">#{open_.number} Synthetic travel rules</a>' in listed
    )
    assert listed.count(f"/document/{open_.number}/") == 1
    assert "the purchasing rules" in listed and "Synthetic procurement rules" not in listed
    assert "the buying guide" not in listed
    assert f"/document/{here.number}/" not in listed and "this one" not in listed
    assert "Generated by the system from the version shown." in page


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_panel_escapes_and_leaves_archived_targets_untitled(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """Every label, word and title in the panel is escaped; an archived document is its words
    alone, whatever right the reader holds on it (DL-0084)."""
    from documents.models import Document, DocumentState

    settings.LANGUAGE_CODE = "en"
    client, _, membership = member_of("the.reader@example.test")
    _, owner, _ = member_of("the.owner@example.test")
    here = new_document(owner, "Synthetic leave rules")
    titled = new_document(owner, "<script>alert(1)</script>")
    archived = new_document(owner, "Synthetic archived rules")
    for document in (here, titled, archived):
        link_group(document, [Right.VIEW_PENDING], [membership], owner)
    roles = '- kind: "role"\n  key: "clerk"\n  label: "<b>the clerk</b>"\n'
    commit_version(
        here,
        owner,
        f"The [clerk]{{.role #clerk}} and [<i>]{{.role}} read "
        f"[the guide]{{.document #{titled.number}}} "
        f"and [the old rules]{{.document #{archived.number}}}.\n",
        files={"entities.yaml": roles.encode()},
    )
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=archived.pk).update(state=DocumentState.ARCHIVED)

    page = client.get(f"/document/{here.number}/").content.decode()
    panel = page[page.index('class="generated-views"') :]

    assert "<b>the clerk</b>" not in panel and "&lt;b&gt;the clerk&lt;/b&gt;" in panel
    assert "<script>" not in panel and "&lt;script&gt;alert(1)&lt;/script&gt;" in panel
    assert "<strong>&lt;i&gt;</strong>" in panel
    assert "the old rules" in panel and f"/document/{archived.number}/" not in panel


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_an_unreadable_declarations_file_groups_by_key(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    settings: Any,
    caplog: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(
        document, author, "The [clerk]{.role #clerk} files it.\n", files={"entities.yaml": b"- {"}
    )

    response = client.get(f"/document/{document.number}/")

    assert response.status_code == 200
    panel = response.content.decode()
    panel = panel[panel.index('class="role-directory"') :]
    assert "<strong>clerk</strong>" in panel
    assert "entities.yaml does not read" in caplog.text
