"""Compare appendices in pairs (DL-0187, DL-0208, DL-0452): the compare page's panel offers a pair —
one appendix of each version — and the pair's page shows the newer appendix whole with its changes
against the older marked, each version linked, and the way back to the comparison; across two
documents, the second's appendix marked against the first's, each document gated as its own
comparison gates it. People and titles are synthetic examples; text is invented English."""

from __future__ import annotations

import re
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Purpose\n\nThe body's sentence.\n"
TWO_OLD = "# Approval matrix\n\nLeave up to three days is approved by the line manager.\n"
TWO_NEW = "# Approval matrix\n\nLeave up to five days is approved by the line manager.\n"
ONE = "# Forms\n\nThe forms appendix's sentence.\n"
LISTED = [
    {"number": 1, "title": "Forms (example)"},
    {"number": 2, "title": "Approval matrix (example)"},
]
READ = [Right.VIEW_ACCEPTED, Right.VIEW_ALL_HISTORY]


def _accepted(tenant: Any, people: Any, commit_version: Any, two: str, title: str = "") -> str:
    """The body and appendices 1 and 2, appendix 2 holding `two`, committed and accepted; the
    acceptance's number."""
    from review import services

    listed = [LISTED[0], {**LISTED[1], "title": title or LISTED[1]["title"]}]
    commit_version(
        people.document,
        people["a"],
        BODY,
        files={"appendices/1.md": ONE.encode(), "appendices/2.md": two.encode()},
        appendices=listed,
    )
    with schema_context(tenant):
        return str(services.accept(people.document, people["r"]).number)


def _pair(tenant: Any, edition_cast: Any, commit_version: Any) -> tuple[Any, str, str]:
    people = edition_cast()
    older = _accepted(tenant, people, commit_version, TWO_OLD)
    newer = _accepted(tenant, people, commit_version, TWO_NEW)
    return people, older, newer


def test_compare_a_pair(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    people, older, newer = _pair(migrated_tenant.number, edition_cast, commit_version)
    client, _ = kit.reader(member_of, link_group, people, READ, "pair")
    m = people.document.number
    page = client.get(f"/document/{m}/compare/?from={older}&to={newer}").content.decode()
    picker = page[page.index('class="appendix-pair"') :]
    picker = picker[: picker.index("</form>")]
    assert f'action="/document/{m}/compare/appendix/"' in picker
    assert f'<option value="{older}:2">Approval matrix (example)</option>' in picker
    assert f'<option value="{newer}:1">Forms (example)</option>' in picker
    assert "Compare appendices" in picker

    pair = client.get(f"/document/{m}/compare/appendix/?from={older}:2&to={newer}:2")
    assert pair.status_code == 200
    html = pair.content.decode()
    assert "Comparing appendices of" in html and "— read only" in html
    assert f'href="/document/{m}/version/{older}/"' in html
    assert f'href="/document/{m}/version/{newer}/"' in html
    assert f'href="/document/{m}/version/{newer}/appendix/2/"' in html
    assert "<del>three</del>" in html and "<ins>five</ins>" in html
    assert f'href="/document/{m}/compare/?from={older}&amp;to={newer}"' in html
    assert "Back to the comparison" in html


def test_order_and_any_pair(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people, older, newer = _pair(migrated_tenant.number, edition_cast, commit_version)
    client, _ = kit.reader(member_of, link_group, people, READ, "order")
    m = people.document.number
    reversed_ = client.get(f"/document/{m}/compare/appendix/?from={newer}:2&to={older}:2")
    html = reversed_.content.decode()
    assert "<del>three</del>" in html and "<ins>five</ins>" in html
    across = client.get(f"/document/{m}/compare/appendix/?from={older}:1&to={newer}:2")
    assert across.status_code == 200
    changes = across.content.decode()
    changes = changes[changes.index('class="changes') :]
    # Appendix 2 of the newer version whole, appendix 1's words marked as gone.
    assert re.search(r"<del>[^<]*forms appendix", changes)
    assert re.search(r"(?<!<del>)approved by the line manager", changes)


def test_what_cannot_be_compared_is_missing(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people, older, newer = _pair(migrated_tenant.number, edition_cast, commit_version)
    m = people.document.number
    history, _ = kit.reader(member_of, link_group, people, READ, "history")
    accepted, _ = kit.reader(member_of, link_group, people, [Right.VIEW_ACCEPTED], "accepted")
    uniform = accepted.get("/document/99999/").content
    for client, query in (
        (accepted, f"from={older}:2&to={newer}:2"),
        (history, f"from={older}:9&to={newer}:2"),
        (history, f"from={older}&to={newer}:2"),
        (history, f"from=:2&to={newer}:2"),
        (history, f"from={older}:x&to={newer}:2"),
    ):
        answer = client.get(f"/document/{m}/compare/appendix/?{query}")
        assert answer.status_code == 404, query
        # Each reader's own uniform body, the form tokens aside.
        own = client.get("/document/99999/").content
        assert re.sub(rb'value="[^"]*"', b"", answer.content) == re.sub(
            rb'value="[^"]*"', b"", own
        ), query
    assert uniform


def _second(
    tenant: Any, people: Any, new_document: Any, link_group: Any, commit_version: Any
) -> tuple[Any, str]:
    """Document M, appendix 1 holding the newer wording; accepted by the same reviewer. M and its
    number."""
    from review import services

    other = new_document(people["a"], "Synthetic travel rules")
    link_group(other, [Right.ACCEPT], [people.memberships["r"]], people["a"])
    commit_version(
        other,
        people["a"],
        BODY,
        files={"appendices/1.md": TWO_NEW.encode()},
        appendices=[{"number": 1, "title": "Travel matrix (example)"}],
    )
    with schema_context(tenant):
        return other, str(services.accept(other, people["r"]).number)


def test_a_pair_across_two_documents(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    older = _accepted(migrated_tenant.number, people, commit_version, TWO_OLD)
    other, theirs = _second(
        migrated_tenant.number, people, new_document, link_group, commit_version
    )
    client, _, membership = member_of("both.synthetic@example.test")
    link_group(people.document, READ, [membership], people["a"])
    link_group(other, READ, [membership], people["a"])
    n, m = people.document.number, other.number
    page = client.get(f"/document/{n}/compare/?from={older}&with={m}&to={theirs}").content.decode()
    picker = page[page.index('class="appendix-pair"') :]
    picker = picker[: picker.index("</form>")]
    assert f'<input type="hidden" name="with" value="{m}">' in picker
    assert f'<option value="{older}:2">Approval matrix (example)</option>' in picker
    assert f'<option value="{theirs}:1">Travel matrix (example)</option>' in picker

    pair = client.get(f"/document/{n}/compare/appendix/?from={older}:2&with={m}&to={theirs}:1")
    assert pair.status_code == 200
    html = pair.content.decode()
    assert "<del>three</del>" in html and "<ins>five</ins>" in html
    assert f'href="/document/{n}/compare/?from={older}&amp;with={m}&amp;to={theirs}"' in html


def test_the_second_document_is_gated(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    older = _accepted(migrated_tenant.number, people, commit_version, TWO_OLD)
    other, theirs = _second(
        migrated_tenant.number, people, new_document, link_group, commit_version
    )
    client, _ = kit.reader(member_of, link_group, people, READ, "one")
    n, m = people.document.number, other.number
    uniform = re.sub(rb'value="[^"]*"', b"", client.get("/document/99999/").content)
    for query in (f"with={m}&to={theirs}:1", "with=99999&to=1.0:1", "with=x&to=1.0:1"):
        answer = client.get(f"/document/{n}/compare/appendix/?from={older}:2&{query}")
        assert answer.status_code == 404, query
        assert re.sub(rb'value="[^"]*"', b"", answer.content) == uniform, query


def test_mentions_are_filtered_in_a_pair(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    hidden = new_document(people["a"], "Synthetic hidden rules")
    older = _accepted(migrated_tenant.number, people, commit_version, TWO_OLD)
    mention = TWO_NEW + f"\nAs [the hidden rules]{{.document #{hidden.number}}} say.\n"
    newer = _accepted(migrated_tenant.number, people, commit_version, mention)
    client, _ = kit.reader(member_of, link_group, people, READ, "mentions")
    m = people.document.number
    html = client.get(f"/document/{m}/compare/appendix/?from={older}:2&to={newer}:2").content
    page = html.decode()
    assert "the hidden rules" in page
    assert f'href="/document/{hidden.number}/"' not in page


def test_the_same_document_named_twice_is_its_own_pair(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    """`with` naming the pair's own document: the one-document page, the newer side whole."""
    people, older, newer = _pair(migrated_tenant.number, edition_cast, commit_version)
    client, _ = kit.reader(member_of, link_group, people, READ, "same")
    m = people.document.number
    html = client.get(
        f"/document/{m}/compare/appendix/?from={newer}:2&with={m}&to={older}:2"
    ).content.decode()
    assert "<del>three</del>" in html and "<ins>five</ins>" in html
    assert f'href="/document/{m}/compare/?from={older}&amp;to={newer}"' in html


def test_across_two_documents_the_banner_names_both(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
) -> None:
    people = edition_cast()
    older = _accepted(migrated_tenant.number, people, commit_version, TWO_OLD)
    other, theirs = _second(
        migrated_tenant.number, people, new_document, link_group, commit_version
    )
    client, _, membership = member_of("banner.synthetic@example.test")
    link_group(people.document, READ, [membership], people["a"])
    link_group(other, READ, [membership], people["a"])
    n, m = people.document.number, other.number
    html = client.get(
        f"/document/{n}/compare/appendix/?from={older}:2&with={m}&to={theirs}:1"
    ).content.decode()
    banner = html[html.index('class="band historical"') :]
    banner = banner[: banner.index("</p>")]
    assert f'<a href="/document/{n}/">#{n}</a>' in banner
    assert f'<a href="/document/{m}/">#{m}</a>' in banner


def test_a_side_without_appendices_says_so(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    settings: Any,
) -> None:
    from review import services

    settings.LANGUAGE_CODE = "en"
    people = edition_cast()
    commit_version(people.document, people["a"], BODY)
    with schema_context(migrated_tenant.number):
        bare = str(services.accept(people.document, people["r"]).number)
    listed = _accepted(migrated_tenant.number, people, commit_version, TWO_OLD)
    client, _ = kit.reader(member_of, link_group, people, READ, "bare")
    m = people.document.number
    page = client.get(f"/document/{m}/compare/?from={bare}&to={listed}").content.decode()
    picker = page[page.index('class="appendix-pair"') :]
    assert f"{bare} has no appendices." in picker[: picker.index("</form>")]
    commit_version(
        people.document,
        people["a"],
        BODY,
        files={"appendices/1.md": None, "appendices/2.md": None},
        appendices=[],
    )
    with schema_context(migrated_tenant.number):
        none = str(services.accept(people.document, people["r"]).number)
    page = client.get(f"/document/{m}/compare/?from={bare}&to={none}").content.decode()
    panel = page[page.index('class="panel"') :]
    assert "No appendices" in panel and 'class="appendix-pair"' not in panel


def test_a_listed_appendix_without_its_file_is_missing(
    migrated_tenant: Any,
    edition_cast: Any,
    member_of: Any,
    link_group: Any,
    commit_version: Any,
    kit: Any,
    caplog: Any,
) -> None:
    import logging

    from review import services

    people, older, _newer = _pair(migrated_tenant.number, edition_cast, commit_version)
    commit_version(
        people.document,
        people["a"],
        BODY,
        files={"appendices/2.md": None},
        appendices=LISTED,
    )
    with schema_context(migrated_tenant.number):
        broken = str(services.accept(people.document, people["r"]).number)
    client, _ = kit.reader(member_of, link_group, people, READ, "broken")
    m = people.document.number
    with caplog.at_level(logging.ERROR):
        answer = client.get(f"/document/{m}/compare/appendix/?from={older}:2&to={broken}:2")
    assert answer.status_code == 404
    assert any(r.getMessage() == "a listed appendix without its file" for r in caplog.records)
