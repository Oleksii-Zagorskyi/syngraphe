"""The marks of a change keep their own colours in the browser whatever the organisation's
stylesheet says (T-23, DL-0477): the served sheet ends with the platform's guard. People are
synthetic examples; the text is invented."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

ACCEPTED = "# General provisions\n\n> [!note]\n> A request is made **in writing**.\n"
REFORMATTED = "# General provisions\n\n> [!note]\n> A request is made *in writing*.\n"


def test_a_mark_keeps_its_colour(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from documents import bundle, gitstore, services
    from documents.identity import identity_for
    from documents.locks import document_lock
    from rendering.models import Stylesheet
    from review import services as review

    settings.LANGUAGE_CODE = "en"
    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT, Right.VIEW_PENDING], [reviewer_membership], reviewer)
    link_group(document, [Right.EDIT], [author_membership], reviewer)

    def commit(body: str) -> None:
        with schema_context(migrated_tenant.number):
            repo = gitstore.open_repository(migrated_tenant.number, document.number)
            head = gitstore.head(repo)
            assert head is not None
            frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
            with document_lock(migrated_tenant.number, document.number):
                sha = gitstore.commit(
                    repo,
                    {"document.md": bundle.render(frontmatter, body).encode()},
                    identity_for(author),
                    "Synthetic edit",
                    gitstore.Kind.EDIT,
                )
            services.derive_version(document, gitstore.commit_at(repo, sha), author)

    commit(ACCEPTED)
    with schema_context(migrated_tenant.number):
        review.accept(document, reviewer)
        Stylesheet.objects.update(text=".callout span { background-color: #ffffff }\n")
    commit(REFORMATTED)

    session = reviewer_client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/pending/")
    page.wait_for_selector(".format-changed")

    assert page.locator('link[href^="/document-styles/"]').count() == 1
    background = page.evaluate(
        "getComputedStyle(document.querySelector('.format-changed')).backgroundColor"
    )
    assert background == "rgb(255, 243, 196)"
