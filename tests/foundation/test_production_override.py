"""The production shape: the override read over the base file, the front's configuration, and the
workers (DL-0281, DL-0347)."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "deploy" / "front"
REQUIRED = (
    "RELEASE_TAG",
    "FRONT_PORT",
    "FRONT_CERT_FILE",
    "FRONT_KEY_FILE",
    "FRONT_CLIENT_IP_HEADER",
    "DATA_DIR",
    "STACK_SUBNET",
)
DOCKER = shutil.which("docker")
TEMPLATE = "/etc/nginx/templates/default.conf.template"
BODY_SIZE = "/docker-entrypoint.d/15-body-size.envsh"
needs_docker = pytest.mark.skipif(DOCKER is None, reason="docker is not installed here")


def environment(folder: Path) -> dict[str, str]:
    return {
        "RELEASE_TAG": "v0.0.0-test",
        "FRONT_PORT": "24680",
        "FRONT_CERT_FILE": str(folder / "tls.crt"),
        "FRONT_KEY_FILE": str(folder / "tls.key"),
        "FRONT_CLIENT_IP_HEADER": "CF-Connecting-IP",
        "DATA_DIR": str(folder / "data"),
        "STACK_SUBNET": "172.30.250.0/24",
        "BACKUP_KEY_FILE": "/dev/null",
    }


def compose_config(folder: Path, values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env_file = folder / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return subprocess.run(
        [
            str(DOCKER),
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(ROOT / "deploy" / "compose.prod.yaml"),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


def targets(service: dict[str, Any]) -> dict[str, str]:
    return {v["target"]: v.get("source", "") for v in service.get("volumes", [])}


@needs_docker
def test_override_resolves(tmp_path: Path) -> None:
    made = compose_config(tmp_path, environment(tmp_path))
    assert made.returncode == 0, made.stderr
    config = json.loads(made.stdout)
    services = config["services"]
    data = str(tmp_path / "data")

    assert not services["web"].get("ports")
    assert [p["published"] for p in services["front"]["ports"]] == ["24680"]
    assert [p["target"] for p in services["front"]["ports"]] == [8443]
    assert not any(services[name].get("ports") for name in services if name != "front")
    assert targets(services["web"])["/srv/repos"] == f"{data}/repos"
    assert targets(services["web"])["/srv/backup-state"] == f"{data}/backup-state"
    assert targets(services["worker"])["/srv/repos"] == f"{data}/repos"
    assert targets(services["worker"])["/srv/backup-state"] == f"{data}/backup-state"
    assert targets(services["db"])["/var/lib/postgresql/data"] == f"{data}/pgdata"
    assert targets(services["db"])["/var/spool/pgbackrest"] == f"{data}/pgspool"
    assert targets(services["backup"])["/var/lib/postgresql/data"] == f"{data}/pgdata"
    assert targets(services["backup"])["/srv/backup-state"] == f"{data}/backup-state"
    assert services["web"]["image"] == services["worker"]["image"] == "syngraphe:v0.0.0-test"
    assert services["db"]["image"] == services["backup"]["image"] == "syngraphe-db:v0.0.0-test"
    # The application believes the front's headers because the front is on the stack's network.
    assert services["web"]["environment"]["TRUSTED_PROXIES"] == "172.30.250.0/24"
    subnets = [c["subnet"] for c in config["networks"]["default"]["ipam"]["config"]]
    assert subnets == ["172.30.250.0/24"]
    assert targets(services["front"])[BODY_SIZE] == str(FRONT / "body-size.envsh")


@needs_docker
@pytest.mark.parametrize(("values", "given"), [({}, "20"), ({"UPLOAD_MAX_MB": "50"}, "50")])
def test_front_receives_the_upload_maximum(
    tmp_path: Path, values: dict[str, str], given: str
) -> None:
    """The front reads the platform's upload maximum from the same key as the application
    (DL-0432), with the same default."""
    made = compose_config(tmp_path, {**environment(tmp_path), **values})
    assert made.returncode == 0, made.stderr
    services = json.loads(made.stdout)["services"]

    for name in ("front", "web", "worker", "render"):
        assert services[name]["environment"]["UPLOAD_MAX_MB"] == given, name


@needs_docker
def test_production_archives_and_has_no_test_server(tmp_path: Path) -> None:
    """The database production runs archives its log; the test suite's server, which does not,
    is the developer override's alone."""
    made = compose_config(tmp_path, environment(tmp_path))
    assert made.returncode == 0, made.stderr
    services = json.loads(made.stdout)["services"]

    command = services["db"]["command"]
    assert "test-db" not in services
    assert "archive_mode=on" in command
    assert "archive_command=pgbackrest --stanza=syngraphe archive-push %p" in command
    assert not {"fsync=off", "synchronous_commit=off", "full_page_writes=off"} & set(command)


@needs_docker
@pytest.mark.parametrize("key", REQUIRED)
def test_override_names_missing_keys(tmp_path: Path, key: str) -> None:
    values = environment(tmp_path)
    del values[key]
    made = compose_config(tmp_path, values)
    assert made.returncode != 0
    assert key in made.stderr


def test_gunicorn_threads() -> None:
    namespace: dict[str, Any] = {}
    exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), namespace)  # noqa: S102
    assert namespace["worker_class"] == "gthread"
    assert (namespace["workers"], namespace["threads"]) == (2, 4)


TOKEN = "A" * 43

# Each as the client sends it: a route spelled with an escape, which the server decodes before
# routing, and a second route inside the query.
CREDENTIAL_REQUESTS = (
    f"/reset/{TOKEN}/",
    f"/invitation/{TOKEN}/",
    f"/%72eset/{TOKEN}/",
    f"/invit%61tion/{TOKEN}/",
    f"/reset/{TOKEN}/?next=/reset/other",
)


@pytest.mark.parametrize("raw", CREDENTIAL_REQUESTS)
def test_gunicorn_access_log_hides_link_tokens(raw: str) -> None:
    """A credential link's token is a password while it is valid; the access log keeps the path
    and drops the token, however the route is spelled."""
    from types import SimpleNamespace
    from urllib.parse import unquote

    namespace: dict[str, Any] = {}
    exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), namespace)  # noqa: S102
    logger = namespace["logger_class"](SimpleNamespace(**_gunicorn_defaults()))
    path, _, query = raw.partition("?")
    request = SimpleNamespace(method="GET", path=path, query=query, version=(1, 1), headers=[])
    response = SimpleNamespace(status="200 OK", sent=10, headers=[], response_length=10)
    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": raw,
        "PATH_INFO": unquote(path),
        "QUERY_STRING": query,
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "192.0.2.1",
    }
    atoms = logger.atoms(response, request, environ, timedelta(seconds=0))

    assert TOKEN not in " ".join(str(value) for value in atoms.values())
    assert atoms["r"].startswith("GET /")
    assert "/reset/" in atoms["r"] or "/invitation/" in atoms["r"]
    assert "next=" not in atoms["r"]


def test_gunicorn_access_log_keeps_other_requests_whole() -> None:
    from types import SimpleNamespace

    namespace: dict[str, Any] = {}
    exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), namespace)  # noqa: S102
    logger = namespace["logger_class"](SimpleNamespace(**_gunicorn_defaults()))
    request = SimpleNamespace(
        method="GET", path="/folder/1/", query="tab=shared", version=(1, 1), headers=[]
    )
    response = SimpleNamespace(status="200 OK", sent=10, headers=[], response_length=10)
    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": "/folder/1/?tab=shared",
        "PATH_INFO": "/folder/1/",
        "QUERY_STRING": "tab=shared",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "192.0.2.1",
    }
    atoms = logger.atoms(response, request, environ, timedelta(seconds=0))

    assert atoms["r"] == "GET /folder/1/?tab=shared HTTP/1.1"


def _gunicorn_defaults() -> dict[str, Any]:
    from gunicorn.config import Config

    config = Config()
    return {name: setting.get() for name, setting in config.settings.items()}


def test_front_log_hides_link_tokens() -> None:
    template = (FRONT / "default.conf.template").read_text()
    assert '"$logged_request"' in template
    # The front keeps its own copy of the paths a credential travels in; it names the same ones.
    from syngraphe.redaction import CREDENTIAL_LINK

    [paths] = re.findall(r"\(\?:[a-z|]+\)", CREDENTIAL_LINK.pattern)
    assert f"{paths}/" in template


# A worker writes a request's log line after its answer has left, so the log is read only once
# nginx has quit gracefully and its master is gone: every worker has finished its requests then.
QUIT = (
    "pid=$(cat /var/run/nginx.pid) && nginx -s quit"
    " && while kill -0 $pid 2>/dev/null; do sleep 0.05; done"
)


@needs_docker
def test_front_access_log_hides_link_tokens(tmp_path: Path) -> None:
    """The front's own map, run by nginx: no request for a credential route leaves its token in
    the log, however it is spelled; any other request is logged whole."""
    template = (FRONT / "default.conf.template").read_text()
    [mapping] = re.findall(r"^map \S+ \$logged_request \{.*?^\}", template, re.M | re.S)
    (tmp_path / "default.conf").write_text(
        mapping
        + """
log_format probe '"$logged_request"';
server {
    listen 8080;
    access_log /tmp/access.log probe;
    location / { return 204; }
}
"""
    )
    asked = " && ".join(
        f"curl -s --path-as-is -o /dev/null 'http://127.0.0.1:8080{raw}'"
        for raw in (*CREDENTIAL_REQUESTS, "/folder/1/?tab=shared")
    )
    made = subprocess.run(
        [
            str(DOCKER), "run", "--rm",
            "-v", f"{tmp_path / 'default.conf'}:/etc/nginx/conf.d/default.conf:ro",
            "nginx:1.27-alpine", "sh", "-c", f"nginx && {asked} && {QUIT} && cat /tmp/access.log",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )  # fmt: skip
    assert made.returncode == 0, made.stderr
    lines = made.stdout.splitlines()
    assert len(lines) == len(CREDENTIAL_REQUESTS) + 1, made.stdout
    assert TOKEN not in made.stdout
    assert lines[-1] == '"GET /folder/1/?tab=shared HTTP/1.1"'


def render_front(folder: Path, *environment: str) -> subprocess.CompletedProcess[str]:
    """The front's configuration as its image's entrypoint renders it, printed by `nginx -T`."""
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "1", "-nodes",
            "-subj", "/CN=front.test",
            "-keyout", str(folder / "tls.key"), "-out", str(folder / "tls.crt"),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    given = [arg for value in environment for arg in ("-e", value)]
    return subprocess.run(
        [
            str(DOCKER), "run", "--rm",
            "-e", "FRONT_CLIENT_IP_HEADER=CF-Connecting-IP",
            "-e", "FRONT_SERVER_NAME=_",
            *given,
            "-v", f"{FRONT / 'default.conf.template'}:{TEMPLATE}:ro",
            "-v", f"{FRONT / 'client-ip.envsh'}:/docker-entrypoint.d/15-client-ip.envsh:ro",
            "-v", f"{FRONT / 'body-size.envsh'}:{BODY_SIZE}:ro",
            "-v", f"{folder / 'tls.crt'}:/etc/nginx/tls/server.crt:ro",
            "-v", f"{folder / 'tls.key'}:/etc/nginx/tls/server.key:ro",
            "nginx:1.27-alpine", "nginx", "-T",
        ],
        capture_output=True,
        text=True,
    )  # fmt: skip


@needs_docker
def test_front_renders(tmp_path: Path) -> None:
    made = render_front(tmp_path)
    assert made.returncode == 0, made.stderr
    assert "proxy_set_header X-Forwarded-For $http_cf_connecting_ip;" in made.stdout
    assert "proxy_set_header Host $http_host;" in made.stdout
    assert "$logged_request" in made.stdout
    # Unset, the application's default maximum (DL-0432), 20 MB, and a megabyte for the form's
    # other fields.
    assert "client_max_body_size 21m;" in made.stdout


@needs_docker
# `020` is twenty to the application; the shell's own arithmetic would read it as octal.
@pytest.mark.parametrize(
    ("given", "admitted"), [("50", "51m"), ("020", "21m"), ("???", "21m"), ("", "21m")]
)
def test_front_admits_the_upload_maximum_and_a_megabyte(
    tmp_path: Path, given: str, admitted: str
) -> None:
    made = render_front(tmp_path, f"UPLOAD_MAX_MB={given}")
    assert made.returncode == 0, made.stderr
    assert f"client_max_body_size {admitted};" in made.stdout


@needs_docker
@pytest.mark.parametrize("given", ["twenty", "0", "-5", "20MB", "+5", "1_000"])
def test_front_refuses_a_malformed_upload_maximum(tmp_path: Path, given: str) -> None:
    """A value the application refuses stops the front too, never a limit nobody chose."""
    made = render_front(tmp_path, f"UPLOAD_MAX_MB={given}")
    assert made.returncode != 0
    assert "UPLOAD_MAX_MB" in made.stderr


@pytest.mark.parametrize("helper", ["client-ip.envsh", "body-size.envsh"])
def test_front_helper_executable(helper: str) -> None:
    """The image's entrypoint sources an executable helper and ignores any other."""
    path = FRONT / helper
    staged = subprocess.run(
        ["git", "ls-files", "-s", str(path.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Before its first commit a helper has no mode in the index; `git add` records the file's.
    assert path.is_file()
    assert staged.startswith("100755") if staged else os.access(path, os.X_OK)


def test_front_keys_documented() -> None:
    example = (ROOT / ".env.example").read_text()
    keys = dict(re.findall(r"^([A-Z_]+)=(.*)$", example, re.MULTILINE))
    for key in REQUIRED:
        assert keys[key] == "???", key
    assert keys["FRONT_SERVER_NAME"] == "_"
    assert keys["UPLOAD_MAX_MB"] == "20"
    assert "COMPOSE_PROJECT_NAME" not in keys
    assert re.search(r"^# COMPOSE_PROJECT_NAME=", example, re.MULTILINE)


@pytest.mark.integration
@pytest.mark.django_db
def test_front_headers_reach_the_application(settings: Any) -> None:
    from django.test import Client

    from identity.models import Membership, User
    from tenancy.models import Tenant

    settings.TRUSTED_PROXIES = (ipaddress.ip_network("172.30.250.0/24"),)
    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    user = User.objects.create_user("reader@example.test", "Tr4vel-Plan-Ok")
    Membership.objects.create(tenant=tenant, user=user, actor_kind="system")
    forwarded = {
        "x-forwarded-for": "203.0.113.9",
        "x-forwarded-host": "127.0.0.1:18443",
        "x-forwarded-proto": "https",
        "host": "127.0.0.1:18443",
    }
    client = Client(enforce_csrf_checks=True, REMOTE_ADDR="172.30.250.3", headers=forwarded)
    page = client.get("/signin/")
    assert page.status_code == 200
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/signin/",
        {
            "email": "reader@example.test",
            "password": "Tr4vel-Plan-Ok",
            "csrfmiddlewaretoken": token,
        },
        headers={**forwarded, "origin": "https://127.0.0.1:18443"},
    )
    assert response.status_code == 302 and response["Location"] == "/"
    assert response.wsgi_request.META["REMOTE_ADDR"] == "203.0.113.9"
    assert response.wsgi_request.is_secure()
    assert response.wsgi_request.get_host() == "127.0.0.1:18443"
