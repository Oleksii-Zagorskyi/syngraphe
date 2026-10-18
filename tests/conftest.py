"""Shared fixtures: the database, a client on the platform host, the Celery worker, a migrated
tenant and its members, and the live server the browser tests run against."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
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

# A growth guard's bound on the time at four times a size over the time at that size: linear cost
# reads about 4, quadratic about 16, so 8 tells them apart on any machine (`test-strategy.md`).
GROWTH_BOUND = 8.0


@pytest.fixture
def grows_linearly() -> Callable[..., float]:
    """`grows_linearly(prepare, work, size)`: asserts that the median time of
    `work(prepare(4 * size))` over the median time of `work(prepare(size))`, three runs each, the
    inputs prepared and the garbage collector paused outside the clock, stays below
    `GROWTH_BOUND`; returns that ratio. A growth guard asserts this, never a time, which a slower
    machine breaks while the code is linear."""
    import gc
    import statistics
    import time

    def measure(prepare: Callable[[int], Any], work: Callable[[Any], object], size: int) -> float:
        def median(n: int) -> float:
            given = prepare(n)
            times = []
            for _ in range(3):
                # The collector's passes grow with the objects alive, a large input's above all:
                # timed, they read as the code's own growth.
                gc.collect()
                gc.disable()
                try:
                    started = time.perf_counter()
                    work(given)
                    times.append(time.perf_counter() - started)
                finally:
                    gc.enable()
            return statistics.median(times)

        small, large = median(size), median(4 * size)
        ratio = large / small
        print(f"growth x4: {ratio:.1f} ({small:.3f} s, then {large:.3f} s)")
        assert ratio < GROWTH_BOUND, f"four times the input took {ratio:.1f} times as long"
        return ratio

    return measure


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
def queued_samples(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """The samples a test queues, recorded rather than sent, as the exports are: a test runs a
    sample itself."""
    queued: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        "rendering.tasks.render_sample.delay", lambda *args: queued.append(args), raising=True
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
    """Drop every `tenant_N` schema the test created, since a schema outlives a rolled-back row;
    the run's own tenant schema (`tenant_schema`) stays."""
    yield
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant\\_%%' AND nspname <> %s",
            [_KEPT_SCHEMA.get("name", "")],
        )
        for (name,) in cursor.fetchall():
            cursor.execute(f'DROP SCHEMA "{name}" CASCADE')


# The name of the schema `tenant_schema` keeps for the run, once it exists.
_KEPT_SCHEMA: dict[str, str] = {}
# Where a tenant schema's rows as its migrations seed them are kept: never `tenant_…`, so neither
# `drop_tenant_schemas` nor a tenant's search path reaches it.
PRISTINE_SCHEMA = "pristine_tenant"


class TenantSchema:
    """A tenant schema migrated once, and the means to put it back as its migrations left it."""

    def __init__(self, number: int) -> None:
        from tenancy.schemas import schema_name

        self.number = number
        self.name = schema_name(number)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1", [self.name]
            )
            self.tables = [row[0] for row in cursor.fetchall()]
            cursor.execute(f'CREATE SCHEMA "{PRISTINE_SCHEMA}"')
            # The seeded tables, each with the columns an insert may write: never a generated one.
            self.seeded: dict[str, str] = {}
            for table in self.tables:
                source = f'"{self.name}"."{table}"'
                cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {source})")
                if cursor.fetchone()[0]:
                    cursor.execute(f'CREATE TABLE "{PRISTINE_SCHEMA}"."{table}" AS TABLE {source}')
                    cursor.execute(
                        "SELECT string_agg(quote_ident(attname), ', ' ORDER BY attnum)"
                        " FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0"
                        " AND NOT attisdropped AND attgenerated = ''",
                        [source],
                    )
                    self.seeded[table] = cursor.fetchone()[0]
            # A sequence never called is set back to its start, not past it.
            cursor.execute(
                "SELECT format('%%I.%%I', schemaname, sequencename), coalesce(last_value,"
                " start_value), last_value IS NOT NULL FROM pg_sequences WHERE schemaname = %s",
                [self.name],
            )
            self.sequences = cursor.fetchall()

    def restore(self) -> None:
        """Every row the last test left removed, the seeded rows put back, and every sequence
        set to where the migrations left it — in one statement, since this runs before every
        test that takes the tenant. Foreign keys are checked at the end of the transaction, so
        the order of the tables does not matter."""
        statements = [f'DELETE FROM "{self.name}"."{table}";' for table in self.tables]
        statements += [
            f'INSERT INTO "{self.name}"."{table}" ({columns}) OVERRIDING SYSTEM VALUE'
            f' SELECT {columns} FROM "{PRISTINE_SCHEMA}"."{table}";'
            for table, columns in self.seeded.items()
        ]
        with connection.cursor() as cursor:
            self._check_shape(cursor)
            cursor.execute("".join(statements))
            cursor.execute(
                "SELECT setval(name::regclass, value, called)"
                " FROM unnest(%s::text[], %s::bigint[], %s::bool[]) AS s(name, value, called)",
                [[s[0] for s in self.sequences], [s[1] for s in self.sequences]]
                + [[s[2] for s in self.sequences]],
            )

    def _check_shape(self, cursor: Any) -> None:
        """Fail, naming them, when the schema's tables or sequences are no longer the ones kept:
        `restore` would leave a new one's rows to the next test."""
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relnamespace = %s::regnamespace"
            " AND relkind IN ('r', 'p', 'S')",
            [self.name],
        )
        now = {row[0] for row in cursor.fetchall()}
        kept = {*self.tables, *(s[0].split(".", 1)[1].strip('"') for s in self.sequences)}
        if now != kept:
            pytest.fail(
                f"{self.name} changed since it was kept: added {sorted(now - kept)},"
                f" removed {sorted(kept - now)}"
            )

    def flushed_with(self, tables: list[str]) -> list[str]:
        """`tables` and every table of this schema: its rows reference shared tables such as
        `identity_membership`, so a flush truncating those must truncate these in the same
        statement."""
        return [*tables, *(f'"{self.name}"."{table}"' for table in self.tables)]


@pytest.fixture(scope="session")
def tenant_schema(django_db_setup: None, django_db_blocker: Any) -> Iterator[TenantSchema]:
    """One tenant schema per run — per worker — migrated once, for every test that takes
    `migrated_tenant`: migrating a schema costs over a second, and some six hundred tests take one.

    Its tenant's row is removed again, so no other test sees a tenant it did not make; each test
    that takes it makes the row anew. While it exists, a committing test's flush empties its tables
    with the shared ones (`TenantSchema.flushed_with`), and `restore` refills them.
    """
    from django.db.backends.postgresql.operations import DatabaseOperations

    from tenancy.models import Tenant, TenantStateHistory

    with django_db_blocker.unblock():
        tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
        call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)
        schema = TenantSchema(tenant.number)
        TenantStateHistory.objects.filter(tenant=tenant).delete()
        tenant.delete()
    _KEPT_SCHEMA["name"] = schema.name
    flush = DatabaseOperations.sql_flush

    def flushing_the_schema(self: Any, style: Any, tables: Any, **options: Any) -> list[str]:
        return flush(self, style, schema.flushed_with(list(tables)) if tables else [], **options)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(DatabaseOperations, "sql_flush", flushing_the_schema)
        yield schema
    _KEPT_SCHEMA.clear()
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA "{schema.name}", "{PRISTINE_SCHEMA}" CASCADE')


@pytest.fixture
def migrated_tenant(tenant_schema: TenantSchema, repo_root: Path, drop_tenant_schemas: None) -> Any:
    """An active tenant whose schema holds every tenant table, as its migrations left it.

    The schema is the run's own (`tenant_schema`), so its number is the same in every test: the
    test's repositories go under a root of its own (`repo_root`). The row is made as
    `migrate_schemas` leaves a new tenant — created, then activated with its history row.
    `drop_tenant_schemas` drops any other tenant's schema the test made.
    """
    from tenancy.management.commands.migrate_schemas import Command
    from tenancy.models import Tenant

    tenant_schema.restore()
    tenant = Tenant.objects.create(
        number=tenant_schema.number, name="Example Org", actor_kind="system"
    )
    Command.activate(tenant)
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
        title: str = "Synthetic document",
        created_by: Any = None,
        author_only: bool = True,
        state: str = "active",
        language: str = "uk",
        # A folder and a type of the caller's, the root and `document` by default.
        folder: Any = None,
        document_type: Any = None,
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
                document_type=document_type or DocumentType.objects.get(code="document"),
                folder=folder or Folder.objects.get(number=1),
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
def ukrainian_corpus(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Callable[[Path], tuple[Path, Path]]:
    """`copy(folder)`: the generator's Ukrainian corpus copied into `folder` — its bare repository
    `generated.git` and its record `truth.json`; the two paths.

    The generator runs once per run, not once per worker or per fixture: it is deterministic and
    takes seconds. The workers of one run share the generated folder under a lock; each fixture
    works on a copy of its own, as it did when it generated one."""
    workerinput = getattr(request.config, "workerinput", None)
    if workerinput is None:
        shared = tmp_path_factory.getbasetemp() / "corpus-ukr"
    else:
        shared = tmp_path_factory.getbasetemp().parent / f"corpus-ukr-{workerinput['testrunuid']}"
    shared.mkdir(exist_ok=True)
    with open(shared / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (shared / "done").exists():
            # Generated beside the shared folder and moved into it whole, so a failed or killed
            # generation leaves nothing the next worker would build on.
            for leftover in ("generated.git", "truth.json"):
                shutil.rmtree(shared / leftover, ignore_errors=True)
                (shared / leftover).unlink(missing_ok=True)
            work = Path(tempfile.mkdtemp(dir=shared))
            result = subprocess.run(
                [sys.executable, str(CORPUS / "corpus.py"), "--lang", "ukr"]
                + ["--repo", str(work / "generated.git"), "--truth", str(work / "truth.json")],
                capture_output=True,
            )
            if result.returncode != 0:
                shutil.rmtree(work)
            assert result.returncode == 0, result.stderr.decode(errors="replace")
            (work / "generated.git").rename(shared / "generated.git")
            (work / "truth.json").rename(shared / "truth.json")
            work.rmdir()
            (shared / "done").touch()

    def copy(folder: Path) -> tuple[Path, Path]:
        repo, truth = folder / "generated.git", folder / "truth.json"
        shutil.copytree(shared / "generated.git", repo)
        shutil.copyfile(shared / "truth.json", truth)
        return repo, truth

    return copy


@pytest.fixture(scope="session")
def platform_corpus(
    tmp_path_factory: pytest.TempPathFactory,
    ukrainian_corpus: Callable[[Path], tuple[Path, Path]],
) -> dict[str, Any]:
    """The invented Ukrainian corpus of `tests/fixtures/corpus/` with the platform's frontmatter,
    as a bare repository: `repo`, its `commits` — the generator's, each with the repository's
    `sha` and its time `at` — and the generator's record of who wrote every sentence, `truth`."""
    out = tmp_path_factory.mktemp("platform-corpus")
    generated, truth_path = ukrainian_corpus(out)
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


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("reuse_db", False):
        raise pytest.UsageError(
            "--reuse-db is not supported: each run names its test databases for itself"
        )


# A test database's name ends in this host and the process that started the run, so that a run
# can tell a database whose run is gone from one whose run is still going.
_HOST = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:6]


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _drop_abandoned_databases(base: str) -> None:
    """Drop every test database of `base` that a run on this host started and did not live to
    drop — killed, or stopped at a timeout. A database with anyone still connected stays."""
    from django.db import DatabaseError

    named = re.compile(rf"test_{re.escape(base)}(?:_gw\d+)?_{_HOST}p(\d+)")
    with connection._nodb_cursor() as cursor:
        cursor.execute("SELECT datname FROM pg_database WHERE datname LIKE 'test\\_%'")
        for (name,) in cursor.fetchall():
            match = named.fullmatch(name)
            if match and not _running(int(match[1])):
                try:
                    cursor.execute(f'DROP DATABASE IF EXISTS "{name}"')
                except DatabaseError:
                    pass


def _refuse_an_archiving_server() -> None:
    with connection._nodb_cursor() as cursor:
        cursor.execute("SHOW archive_mode")
        archiving = cursor.fetchone()[0] != "off"
    if archiving:
        pytest.fail(
            "the tests' database server archives its log, which would send every run to the"
            " backup store: start the developer override's `test-db` and set POSTGRES_TEST_PORT",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    request: pytest.FixtureRequest,
    django_db_modify_db_settings_parallel_suffix: None,
    django_db_blocker: Any,
) -> None:
    """The test suite's own database server, `POSTGRES_TEST_PORT` on the configured host when it
    is set, and never one that archives its log: a run's log would go to the backup store. A test
    database name of this run's own — after pytest-django's `_gw<n>` for a worker, this host and
    the run's process — so a second run on the same server, beside this one, never shares its
    database; and the databases of runs on this host that are gone, dropped."""
    from django.conf import settings

    test_port = os.environ.get("POSTGRES_TEST_PORT")
    started_by = os.getppid() if hasattr(request.config, "workerinput") else os.getpid()
    for database in settings.DATABASES.values():
        if test_port:
            database["PORT"] = test_port
        test = database.setdefault("TEST", {})
        test["NAME"] = f"{test.get('NAME') or 'test_' + database['NAME']}_{_HOST}p{started_by}"
    with django_db_blocker.unblock():
        _refuse_an_archiving_server()
        _drop_abandoned_databases(settings.DATABASES["default"]["NAME"])


@pytest.fixture(scope="session", autouse=True)
def run_directories(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """The repository root and the exports root of this process alone: tenant and document numbers
    start again in every worker's database, so two workers sharing a root would share a
    repository and its lock file. A test that needs an empty root still takes `repo_root`."""
    from django.test import override_settings

    base = tmp_path_factory.mktemp("roots")
    (base / "repos").mkdir()
    (base / "exports").mkdir()
    with override_settings(GIT_REPO_ROOT=base / "repos", EXPORT_ROOT=base / "exports"):
        yield


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


@pytest.hookimpl(trylast=True)
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


@pytest.fixture
def invented_image() -> Callable[..., bytes]:
    """Image bytes made here by Pillow, never a file from elsewhere: `kind` `png`, `jpeg` or
    `gif`, of the size given, a JPEG with an EXIF orientation when one is given. Each call with
    its own `shade` makes different bytes."""

    def make(
        kind: str = "png",
        width: int = 40,
        height: int = 20,
        *,
        orientation: int | None = None,
        shade: int = 0,
    ) -> bytes:
        import io

        from PIL import Image

        picture = Image.new("RGB", (width, height), (200, 40 + shade % 200, 40))
        buffer = io.BytesIO()
        if kind == "jpeg":
            exif = Image.Exif()
            if orientation is not None:
                exif[0x0112] = orientation
            picture.save(buffer, "JPEG", exif=exif.tobytes(), quality=90)
        elif kind == "gif":
            picture.save(buffer, "GIF")
        else:
            picture.save(buffer, "PNG")
        return buffer.getvalue()

    return make


@pytest.fixture
def frontmatter_kinds(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """An empty registry of frontmatter kinds for one test, so a kind it registers never meets one
    an app registered at start-up."""
    from editing import parts

    fresh: dict[str, Any] = {}
    monkeypatch.setattr(parts, "FRONTMATTER_KINDS", fresh)
    return fresh
