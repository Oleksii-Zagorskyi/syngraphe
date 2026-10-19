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
    assert again.count(f'data-author="{author}"') >= 2
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

    turned = viewer.client.post("/preferences/show-author/", {"show_author": "on", "next": url})
    assert turned.status_code == 302 and turned["Location"] == url
    assert NOTE in viewer.client.get(url).content.decode()


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
    first = next(text for text in named if "made in writing" in text)
    last = next(text for text in named if "order they arrive" in text)
    item = next(text for text in named if "first synthetic item" in text)
    assert (named[first], named[last], named[item]) == (a, b, b)
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
