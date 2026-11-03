"""A reviewer corrects a pending run in Chromium and accepts it in one act: *Correct* on the pending
tab takes the document, *Finish editing* opens the screen with *accept as 0.1*, and the document
page then says what the acceptance gave (DL-0222, DL-0332). People are synthetic examples; the
text is invented."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
WRITTEN = "# General provisions\n\nA request is made in writing.\n"


def test_end_to_end(
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
    from review.models import Acceptance

    settings.LANGUAGE_CODE = "en"
    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [reviewer_membership], reviewer)
    link_group(document, [Right.EDIT], [author_membership], reviewer)
    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        frontmatter, _ = bundle.parse(gitstore.read(repo, "document.md", head).decode())
        with document_lock(migrated_tenant.number, document.number):
            sha = gitstore.commit(
                repo,
                {"document.md": bundle.render(frontmatter, WRITTEN).encode()},
                identity_for(author),
                "Synthetic request",
                gitstore.Kind.EDIT,
            )
        services.derive_version(document, gitstore.commit_at(repo, sha), author)

    session = reviewer_client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/pending/")
    page.click("a[data-command=correct]")
    page.wait_for_url(f"**/document/{document.number}/edit/")
    page.wait_for_function(f"() => {EDITOR} !== undefined && {EDITOR}.view !== undefined")
    assert "your changes become a version of your own" in (page.text_content(".correcting") or "")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" A copy goes to the applicant.", delay=10)
    page.click("#editor button[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    assert "Accept as 0.1" in (page.text_content("button[data-command=accept]") or "")
    assert "Create version 0.0-2" in (page.text_content("button[data-command=create]") or "")
    page.click("button[data-command=accept]")
    page.wait_for_url(f"**/document/{document.number}/")
    assert "Accepted as 0.1." in (page.text_content(".notice") or "")
    with schema_context(migrated_tenant.number):
        acceptance = Acceptance.objects.get()
        assert acceptance.number == "0.1" and acceptance.reviewer_id == reviewer.pk
    page.goto(f"{browser_server}/document/{document.number}/pending/")
    assert page.locator(".nothing-pending").count() == 1
    assert page.locator(".changes ins, .changes del").count() == 0


def test_enter_in_the_summary_accepts_nothing(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
    queued_authorship: list[Any],
) -> None:
    """Enter in the summary makes the version and leaves it waiting; accepting the run is never
    the form's default."""
    from access.rights import Right
    from documents.models import Version
    from review.models import Acceptance

    settings.LANGUAGE_CODE = "en"
    client, reviewer, membership = member_of("the.reviewer@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [membership], reviewer)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_function(f"() => {EDITOR} !== undefined && {EDITOR}.view !== undefined")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" A new sentence.", delay=10)
    page.click("#editor button[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    page.focus("#summary")
    page.keyboard.press("Enter")
    page.wait_for_url(f"**/document/{document.number}/")
    with schema_context(migrated_tenant.number):
        assert not Acceptance.objects.exists()
        assert Version.objects.filter(document=document, kind="reviewer_edit").count() == 1
