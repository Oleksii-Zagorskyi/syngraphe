"""*Show edit authors* on the historical page (DL-0040, DL-0266, DL-0489): a past version's edit
authors are asked of the worker on demand; until they come the text reads without them under a
line asking for a reload, and once they do each line names its edit author as the pending tab
does.

People, documents and their text are synthetic examples; the text is invented."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right

_spec = importlib.util.spec_from_file_location(
    "historical_authors_page", Path(__file__).resolve().parent / "test_historical_page.py"
)
assert _spec is not None and _spec.loader is not None
_page = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _page
_spec.loader.exec_module(_page)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

NOTE = "Edit authors are being worked out — reload the page in a moment."


@pytest.fixture
def asked(monkeypatch: Any) -> list[tuple[Any, ...]]:
    """The on-demand jobs the page queues, captured rather than sent."""
    queued: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "editing.tasks.compute_authorship_at.delay", lambda *args: queued.append(args)
    )
    return queued


def _showing_authors(client: Any) -> None:
    """*Show edit authors* turned on as the person turns it on."""
    assert client.post("/preferences/show-author/", {"show_author": "on"}).status_code == 302


def test_authors_arrive_on_reload(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    from editing.tasks import compute_authorship_at

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    version = history.versions["0.0-2"]
    url = f"/document/{history.document.number}/version/0.0-2/"

    first = viewer.client.get(url).content.decode()

    assert NOTE in first and "data-author" not in first
    assert asked == [(migrated_tenant.number, history.document.number, version.commit_sha)]

    compute_authorship_at(*asked[0])
    again = viewer.client.get(url).content.decode()

    assert NOTE not in again
    author = history.people["a"].display_name or "anonymous editor"
    # Against 0.0-1, 0.0-2 added one paragraph: it alone names its edit author (DL-0504).
    assert again.count(f'data-author="{author}"') == 1
    named = re.search(rf'<p\b[^>]*data-author="{author}"[^>]*>(.*?)</p>', again, re.S)
    assert named is not None and _page.ONLY_IN_SECOND in named.group(1)
    # The outline still reaches the headings and clauses it links to.
    assert 'id="' in again.split('class="document-text"', 1)[1]


def test_authors_named_through_person(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    from editing.tasks import compute_authorship_at
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    User.objects.filter(pk=history.people["a"].pk).update(display_name="")
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    url = f"/document/{history.document.number}/version/0.0-2/"
    viewer.client.get(url)
    compute_authorship_at(*asked[0])

    page = viewer.client.get(url).content.decode()

    assert 'data-author="anonymous editor"' in page
    assert history.people["a"].email not in page


def test_no_authors_asked_for(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)

    off = viewer.client.get(f"/document/{history.document.number}/version/0.0-2/").content.decode()

    assert NOTE not in off and "data-author" not in off
    assert asked == []

    # A blank body has no rows by design, and nothing is asked (DL-0326).
    commit_version(history.document, history.people["a"], "")
    _showing_authors(viewer.client)
    blank = viewer.client.get(f"/document/{history.document.number}/version/1.0-3/")
    assert blank.status_code == 200
    assert NOTE not in blank.content.decode() and asked == []


def test_the_toggle_on_the_historical_page(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    """The pending tab's own form, its label *Show edit authors*, returning to this page."""
    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    url = f"/document/{history.document.number}/version/0.0-2/"

    page = viewer.client.get(url).content.decode()
    assert 'action="/preferences/show-author/"' in page
    assert f'name="next" value="{url}"' in page
    assert "Show edit authors" in page
    # A checkbox, the column's title, submitted by the platform's own script (DL-0504, DL-0493).
    box = re.search(r'<input type="checkbox"[^>]*>', page)
    assert box is not None and "checked" not in box.group(0)
    assert 'name="show_author" value="on"' in page
    assert re.search(r'<script src="[^"]*show-author\.js" defer></script>', page)
    assert "<button" not in page.split('class="show-author"')[1].split("</form>")[0]
    # It heads the text's column, not the row of actions above the panes.
    assert page.index('<div class="centre') < page.index('class="show-author"')
    assert page.index('class="show-author"') < page.index('<article class="document-text"')

    turned = viewer.client.post("/preferences/show-author/", {"show_author": "on", "next": url})
    assert turned.status_code == 302 and turned["Location"] == url
    on = viewer.client.get(url).content.decode()
    assert NOTE in on
    box = re.search(r'<input type="checkbox"[^>]*>', on)
    assert box is not None and "checked" in box.group(0)
    assert 'name="show_author" value="off"' in on


def test_a_changed_paragraph_names_its_author_against_the_version_before(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    """A version names the authors of the paragraphs it changed against the version before it
    in the reader's reach, and nothing beside a paragraph it left alone; the first version within
    the reader's reach has nothing before it, so every paragraph is named (DL-0504, DL-0209)."""
    from editing.tasks import compute_authorship_at
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    User.objects.filter(pk=history.people["a"].pk).update(display_name="Synthetic Editor A")
    User.objects.filter(pk=history.people["b"].pk).update(display_name="Synthetic Editor B")

    def drawn(client: Any, url: str) -> dict[str, str]:
        client.get(url)
        compute_authorship_at(*asked[-1])
        page = client.get(url).content.decode()
        text = page.split('class="document-text"')[1].split("</article>")[0]
        return {
            re.sub(r"<[^>]+>", "", body).strip(): who
            for who, body in re.findall(
                r'<(?:p|h1|li)\b[^>]*data-author="([^"]+)"[^>]*>(.*?)</(?:p|h1|li)>', text, re.S
            )
        }

    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    sixth = drawn(viewer.client, f"/document/{history.document.number}/version/1.0-2/")
    assert list(sixth.values()) == ["Synthetic Editor B"]
    assert "order they arrive" in next(iter(sixth))

    # A reader of canonical editions alone reaches 1.0 first: nothing before it to compare with.
    editions = _page.reader(member_of, link_group, history.people, "editions", _page.READER_II)
    _showing_authors(editions.client)
    first = drawn(editions.client, f"/document/{history.document.number}/version/1.0/")
    assert len(first) >= 4
    assert set(first.values()) == {"Synthetic Editor A"}


def test_a_reader_of_the_last_two_versions_compares_within_their_reach(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    """A reader whose *view pending* alone reaches the edition and the two versions after it, and
    nothing before: each later version names the paragraph it changed against the one before it
    and leaves the rest bare; the edition has nothing within reach before it, so it names every
    paragraph."""
    from editing.tasks import compute_authorship_at
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    User.objects.filter(pk=history.people["a"].pk).update(display_name="Synthetic Editor A")
    User.objects.filter(pk=history.people["b"].pk).update(display_name="Synthetic Editor B")
    pending = _page.reader(member_of, link_group, history.people, "pending", [Right.VIEW_PENDING])
    _showing_authors(pending.client)
    number = history.document.number
    # The version before the edition in the whole history is beyond this reader's reach.
    assert pending.client.get(f"/document/{number}/version/0.0-3/").status_code == 404

    def drawn(url: str) -> tuple[dict[str, str], int]:
        pending.client.get(url)
        compute_authorship_at(*asked[-1])
        page = pending.client.get(url).content.decode()
        text = page.split('class="document-text"')[1].split("</article>")[0]
        named = {
            re.sub(r"<[^>]+>", "", body).strip(): who
            for who, body in re.findall(
                r'<(?:p|h1|li)\b[^>]*data-author="([^"]+)"[^>]*>(.*?)</(?:p|h1|li)>', text, re.S
            )
        }
        return named, len(re.findall(r"<(?:p|h1|li)\b", text))

    last, blocks = drawn(f"/document/{number}/version/1.0-2/")
    assert list(last.values()) == ["Synthetic Editor B"], last
    assert "order they arrive" in next(iter(last))
    assert blocks > 1

    middle, _ = drawn(f"/document/{number}/version/1.0-1/")
    assert list(middle.values()) == ["Synthetic Editor A"], middle
    assert "officer in charge" in next(iter(middle))

    first, blocks = drawn(f"/document/{number}/version/1.0/")
    assert len(first) == blocks, first
    assert set(first.values()) == {"Synthetic Editor A"}, first


def test_each_line_names_its_own_edit_author(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    """Two editors' lines on one page, and a tight list: each block names whoever last edited
    it, with the pending tab's dotted cue."""
    from editing.tasks import compute_authorship_at
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    User.objects.filter(pk=history.people["a"].pk).update(display_name="Synthetic Editor A")
    User.objects.filter(pk=history.people["b"].pk).update(display_name="Synthetic Editor B")
    listed = _page.SIXTH + "\n- The first synthetic item.\n- The second synthetic item.\n"
    commit_version(history.document, history.people["b"], listed)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    url = f"/document/{history.document.number}/version/1.0-3/"
    viewer.client.get(url)
    compute_authorship_at(*asked[-1])

    page = viewer.client.get(url).content.decode()

    a, b = "Synthetic Editor A", "Synthetic Editor B"
    named = dict(
        (re.sub(r"<[^>]+>", "", text).strip(), who)
        for who, text in re.findall(
            r'<(?:p|li)\b[^>]*data-author="([^"]+)"[^>]*>(.*?)</(?:p|li)>', page, re.S
        )
    )
    # Against the version before (1.0-2), only the list changed: its items name their edit
    # author, the paragraphs left as they were name nobody (DL-0504).
    item = next(text for text in named if "first synthetic item" in text)
    assert named[item] == b
    assert not any("made in writing" in text or "order they arrive" in text for text in named)
    assert a not in page.split('class="document-text"')[1].split("</article>")[0]
    assert re.search(r'<li\b[^>]*class="by"[^>]*data-author=', page) or re.search(
        r'<li\b[^>]*data-author="[^"]+"[^>]*class="by"', page
    )


def test_one_job_at_a_time_per_version(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
) -> None:
    """Reloads while a version's edit authors are worked out ask the worker once; once the job
    ends, a version still without them may be asked for again."""
    from editing.tasks import compute_authorship_at

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    url = f"/document/{history.document.number}/version/0.0-3/"

    for _ in range(3):
        assert NOTE in viewer.client.get(url).content.decode()
    assert len(asked) == 1

    compute_authorship_at(*asked[0])
    assert NOTE not in viewer.client.get(url).content.decode()
    assert len(asked) == 1


@pytest.mark.parametrize("fails", ["the mark", "the queue"])
def test_the_text_reads_when_the_authors_cannot_be_asked(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    monkeypatch: Any,
    fails: str,
) -> None:
    """The authors are optional: Redis or the broker refusing the request leaves the text
    readable without them (DL-0266), and a mark the queue never received is let go, so a reload
    asks again."""
    import redis

    from editing.past_authors import asked_key

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    version = history.versions["0.0-2"]

    def refused(*_: Any, **__: Any) -> Any:
        raise (redis.ConnectionError if fails == "the mark" else OSError)("refused")

    if fails == "the mark":
        monkeypatch.setattr(redis.Redis, "set", refused)
    else:
        monkeypatch.setattr("editing.tasks.compute_authorship_at.delay", refused)

    response = viewer.client.get(f"/document/{history.document.number}/version/0.0-2/")

    assert response.status_code == 200
    assert 'class="document-text"' in response.content.decode()
    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        key = asked_key(migrated_tenant.number, history.document.number, version.commit_sha)
        assert not client.exists(key)
    finally:
        client.close()


def test_an_unreadable_version_before_draws_the_page_unnamed(
    migrated_tenant: Any,
    edition_cast: Any,
    commit_version: Any,
    member_of: Any,
    link_group: Any,
    settings: Any,
    asked: list[tuple[Any, ...]],
    monkeypatch: Any,
) -> None:
    """The version before is read only to tell what changed: when it cannot be read, the shown
    version is still drawn, its text without names, rather than answered as missing."""
    from documents import gitstore
    from editing.tasks import compute_authorship_at

    settings.LANGUAGE_CODE = "en"
    history = _page.standard_history(migrated_tenant, edition_cast, commit_version)
    viewer = _page.reader(member_of, link_group, history.people, "viewer", _page.READER_I)
    _showing_authors(viewer.client)
    url = f"/document/{history.document.number}/version/1.0-2/"
    viewer.client.get(url)
    compute_authorship_at(*asked[-1])
    before = history.versions["1.0-1"].commit_sha
    read = gitstore.read

    def failing(repo: Any, path: str, sha: str) -> bytes:
        if sha == before:
            raise ValueError("a synthetic unreadable version")
        return read(repo, path, sha)

    monkeypatch.setattr("rendering.views.gitstore.read", failing)

    answer = viewer.client.get(url)

    assert answer.status_code == 200
    page = answer.content.decode()
    assert "order they arrive" in page
    assert "data-author" not in page.split('class="document-text"')[1]
