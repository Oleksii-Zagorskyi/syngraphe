"""Shared fixtures: the database, a client on the platform host, the Celery worker, a migrated
tenant and its members, and the live server the browser tests run against."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import Client

# The values a host-side run cannot take from `.env`: they describe the test process, not an
# installation. CI sets every one of them explicitly and wins.
_TEST_DEFAULTS = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DJANGO_DEBUG": "false",
    "DJANGO_ADMIN_PATH": "operator/",
    "SITE_HTTPS": "false",
    "TRUSTED_PROXIES": "none",
    "DISPLAY_TIMEZONE": "UTC",
    "DEFAULT_LANGUAGE": "uk",
    "GIT_REPO_ROOT": str(Path(tempfile.gettempdir()) / "syngraphe-test-repos"),
    # Thirty-two zero bytes, for the tests alone.
    "MAIL_PASSWORD_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
}
for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
# Playwright's synchronous API keeps an event loop running in the test thread from its first use
# on, and Django refuses the ORM beside a running loop; the suite has no asynchronous code for that
# guard to protect.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

pytest_plugins = ("celery.contrib.pytest",)


@pytest.fixture(autouse=True)
def unhashed_static_files(settings: Any) -> None:
    """Static names as written: the suite renders pages without collecting the files first."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def queued_authorship(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int, str]]:
    """The authorship jobs a test asks the worker for, recorded rather than sent: the broker the
    suite reaches is a development stack's, whose worker must not take them."""
    queued: list[tuple[int, int, str]] = []
    monkeypatch.setattr(
        "editing.tasks.queue_authorship", lambda *job: queued.append(job), raising=True
    )
    return queued


@pytest.fixture(autouse=True)
def queued_exports(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """The export jobs a test queues, recorded rather than sent, for the same reason: the web
    process sends through the configured app, whose route leads to a development stack's
    `render`. A test runs a job itself (`tests/rendering/conftest.py::exports`)."""
    queued: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "rendering.tasks.render_export.delay", lambda *args: queued.append(args), raising=True
    )
    return queued


@pytest.fixture(autouse=True)
def fresh_host_cache() -> None:
    """Each test sees the hosts it creates: the thirty-second cache never carries across tests."""
    from tenancy.middleware import invalidate_host_cache

    invalidate_host_cache()


# A queue of this run alone, so a worker container sharing the broker never takes the test's task.
TEST_QUEUE = f"test-{uuid.uuid4().hex}"


@pytest.fixture
def client() -> Client:
    """A client whose requests carry the host `127.0.0.1`."""
    return Client(headers={"host": "127.0.0.1"})


@pytest.fixture(scope="session")
def celery_app() -> Any:
    """The application's own Celery app, so its tasks are the ones the test worker runs."""
    from syngraphe.celery import app

    return app


@pytest.fixture(scope="session")
def celery_worker_parameters() -> dict[str, Any]:
    return {"queues": (TEST_QUEUE,), "perform_ping_check": False, "shutdown_timeout": 30}


@pytest.fixture(scope="session")
def test_queue() -> str:
    return TEST_QUEUE


@pytest.fixture
def repo_root(tmp_path: Path, settings: Any) -> Iterator[Path]:
    """An empty repository root for the test, in place of the configured one."""
    root = tmp_path / "repos"
    root.mkdir()
    settings.GIT_REPO_ROOT = root
    yield root


@pytest.fixture
def drop_tenant_schemas() -> Iterator[None]:
    """Drop every `tenant_N` schema the test created, since a schema outlives a rolled-back row."""
    yield
    with connection.cursor() as cursor:
        cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant\\_%'")
        for (name,) in cursor.fetchall():
            cursor.execute(f'DROP SCHEMA "{name}" CASCADE')


@pytest.fixture
def migrated_tenant(drop_tenant_schemas: None) -> Any:
    """An active tenant whose schema holds every tenant table.

    `drop_tenant_schemas` is requested first so it tears down last: the tenant schema's rows
    reference `identity_membership`, which the flush after the test truncates.
    """
    from tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
    call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)
    tenant.refresh_from_db()
    return tenant


@pytest.fixture
def make_tenant_schema(drop_tenant_schemas: None) -> Callable[[str], Any]:
    """Another active tenant with its schema migrated."""
    from tenancy.models import Tenant

    def make(name: str) -> Any:
        tenant = Tenant.objects.create(name=name, actor_kind="system")
        call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)
        tenant.refresh_from_db()
        return tenant

    return make


@pytest.fixture
def member_of(migrated_tenant: Any) -> Callable[..., tuple[Client, Any, Any]]:
    """A client signed in as a member of the migrated tenant, the tenant chosen in the session."""

    def make(
        email: str, *, is_tenant_admin: bool = False, is_platform_admin: bool = False
    ) -> tuple[Client, Any, Any]:
        from identity.models import Membership, User

        user = User.objects.create_user(
            email, "test-only-not-a-password", is_platform_admin=is_platform_admin
        )
        membership = Membership.objects.create(
            tenant=migrated_tenant, user=user, is_tenant_admin=is_tenant_admin, actor_kind="system"
        )
        client = Client(headers={"host": "127.0.0.1"})
        client.force_login(user)
        session = client.session
        session["tenant_number"] = migrated_tenant.number
        session.save()
        return client, user, membership

    return make


@pytest.fixture
def signed_in_without_tenant() -> Callable[..., Client]:
    """A client signed in with no organisation chosen in its session."""

    def make(email: str, *, is_platform_admin: bool = False) -> Client:
        from identity.models import User

        user = User.objects.create_user(
            email, "test-only-not-a-password", is_platform_admin=is_platform_admin
        )
        client = Client(headers={"host": "127.0.0.1"})
        client.force_login(user)
        return client

    return make


@pytest.fixture
def make_document(migrated_tenant: Any) -> Callable[..., Any]:
    """A document row in the migrated tenant's root folder, with no repository behind it."""

    def make(
        *,
        title: str = "Документ",
        created_by: Any = None,
        author_only: bool = True,
        state: str = "active",
        language: str = "uk",
    ) -> Any:
        from documents.models import Document, DocumentType, Folder, next_document_number
        from identity.models import Language
        from tenancy.schemas import schema_context

        Language.objects.get_or_create(
            code=language, defaults={"label": language, "actor_kind": "system"}
        )
        with schema_context(migrated_tenant.number):
            return Document.objects.create(
                number=next_document_number(),
                title=title,
                language_id=language,
                document_type=DocumentType.objects.get(code="document"),
                folder=Folder.objects.get(number=1),
                created_by=created_by,
                actor_kind="system" if created_by is None else "user",
                author_only=author_only,
                state=state,
            )

    return make


CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"
CORPUS_DOMAIN = "users.noreply.syngraphe.local"
# The generator's fixed clock: commit `n` is dated `CORPUS_EPOCH + n` hours.
CORPUS_EPOCH = 1_800_000_000


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, env=env, capture_output=True, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return result.stdout


def _platform_frontmatter(text: str) -> str:
    """The corpus's document with its frontmatter as the platform writes it."""
    from documents import bundle

    lines = text.split("\n")
    fields = dict(line.split(": ", 1) for line in lines[1:4])
    return bundle.render(
        bundle.Frontmatter(title=fields["title"], language=fields["language"]),
        "\n".join(lines[6:]),
    )


@pytest.fixture(scope="session")
def platform_corpus(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The invented Ukrainian corpus of `tests/fixtures/corpus/` with the platform's frontmatter,
    as a bare repository: `repo`, its `commits` — the generator's, each with the repository's
    `sha` and its time `at` — and the generator's record of who wrote every sentence, `truth`."""
    out = tmp_path_factory.mktemp("platform-corpus")
    generated, truth_path = out / "generated.git", out / "truth.json"
    result = subprocess.run(
        [sys.executable, str(CORPUS / "corpus.py"), "--lang", "ukr", "--repo", str(generated)]
        + ["--truth", str(truth_path)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    commits = truth["commits"]
    batch = _git(
        generated,
        "cat-file",
        "--batch",
        stdin="".join(f"{c['sha']}:document.md\n" for c in commits).encode(),
    )
    repo = out / "corpus-ukr.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(repo)], check=True)
    stream, at = bytearray(), 0
    for mark, commit in enumerate(commits, 1):
        header_end = batch.index(b"\n", at)
        size = int(batch[at:header_end].split(b" ")[2])
        text = batch[header_end + 1 : header_end + 1 + size].decode("utf-8")
        at = header_end + 1 + size + 1
        data = _platform_frontmatter(text).encode("utf-8")
        when = CORPUS_EPOCH + commit["n"] * 3600
        who = f"{commit['author']} <{commit['author']}@{CORPUS_DOMAIN}> {when} +0000"
        stream += f"commit refs/heads/main\nmark :{mark}\nauthor {who}\ncommitter {who}\n".encode()
        stream += b"data 6\nCommit\n"
        if mark > 1:
            stream += f"from :{mark - 1}\n".encode()
        stream += f"M 100644 inline document.md\ndata {len(data)}\n".encode() + data + b"\n"
    marks = out / "marks"
    _git(repo, "fast-import", "--quiet", f"--export-marks={marks}", stdin=bytes(stream))
    shas = dict(line.split(" ") for line in marks.read_text().splitlines())
    return {
        "repo": repo,
        "commits": [
            {**c, "sha": shas[f":{m}"], "at": CORPUS_EPOCH + c["n"] * 3600}
            for m, c in enumerate(commits, 1)
        ],
        "truth": truth,
    }


BUNDLE = (
    Path(__file__).resolve().parents[1] / "src" / "editing" / "static" / "editing" / "editor.js"
)
# The seeded rows as the test database was created with them, by connection alias.
_SEEDED: dict[str, str] = {}


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup: None) -> Iterator[None]:
    """pytest-django's test database, and a copy of the rows its migrations seed, kept for the
    browser tests (`browser_server`)."""
    from django.db import connections

    for connection_ in connections.all(initialized_only=True):
        contents = getattr(connection_, "_test_serialized_contents", None)
        if contents is not None:
            _SEEDED[connection_.alias] = contents
    yield


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every browser test runs against committed rows, which a live server needs, with the rows the
    migrations seed restored after it; and the browser tests run last. Playwright's synchronous API
    leaves an event loop running in the test thread, and Django's connections are local to it, so
    every later test would meet a connection without the seeded rows to restore."""
    browser = []
    for item in items:
        if "browser_server" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.django_db(transaction=True, serialized_rollback=True))
            browser.append(item)
    items[:] = [item for item in items if item not in browser] + browser


@pytest.fixture
def browser_server(live_server: Any, settings: Any) -> str:
    """The live application for a browser test, with its conformance page on; its address."""
    from django.db import connections

    if not BUNDLE.exists():
        pytest.fail("the editor's bundle is not built: npm ci && npm run build")
    for alias, contents in _SEEDED.items():
        connection_ = connections[alias]
        if not hasattr(connection_, "_test_serialized_contents"):
            # A connection made after Playwright's loop started: nothing was restored on it.
            connection_._test_serialized_contents = contents  # type: ignore[attr-defined]
            connection_.creation.deserialize_db_from_string(contents)
    settings.EDITING_CONFORMANCE_PAGE = True
    return str(live_server.url)
