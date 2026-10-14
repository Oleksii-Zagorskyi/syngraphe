"""The production shape: the override read over the base file, the front's configuration, and the
workers (DL-0281, DL-0347)."""

from __future__ import annotations

import ipaddress
import json
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


def test_gunicorn_access_log_hides_link_tokens() -> None:
    """A credential link's token is a password while it is valid; the access log keeps the path
    and drops the token."""
    from types import SimpleNamespace

    namespace: dict[str, Any] = {}
    exec((ROOT / "deploy" / "gunicorn.conf.py").read_text(), namespace)  # noqa: S102
    logger = namespace["logger_class"](SimpleNamespace(**_gunicorn_defaults()))
    token = "A" * 43
    request = SimpleNamespace(
        method="GET", path=f"/invitation/{token}/", query="", version=(1, 1), headers=[]
    )
    response = SimpleNamespace(status="200 OK", sent=10, headers=[], response_length=10)
    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": f"/reset/{token}/",
        "PATH_INFO": f"/reset/{token}/",
        "QUERY_STRING": "",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "192.0.2.1",
    }
    atoms = logger.atoms(response, request, environ, timedelta(seconds=0))

    assert token not in " ".join(str(value) for value in atoms.values())
    assert "/reset/" in atoms["r"]


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


@needs_docker
def test_front_renders(tmp_path: Path) -> None:
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "1", "-nodes",
            "-subj", "/CN=front.test",
            "-keyout", str(tmp_path / "tls.key"), "-out", str(tmp_path / "tls.crt"),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    made = subprocess.run(
        [
            str(DOCKER), "run", "--rm",
            "-e", "FRONT_CLIENT_IP_HEADER=CF-Connecting-IP",
            "-e", "FRONT_SERVER_NAME=_",
            "-v", f"{FRONT / 'default.conf.template'}:{TEMPLATE}:ro",
            "-v", f"{FRONT / 'client-ip.envsh'}:/docker-entrypoint.d/15-client-ip.envsh:ro",
            "-v", f"{tmp_path / 'tls.crt'}:/etc/nginx/tls/server.crt:ro",
            "-v", f"{tmp_path / 'tls.key'}:/etc/nginx/tls/server.key:ro",
            "nginx:1.27-alpine", "nginx", "-T",
        ],
        capture_output=True,
        text=True,
    )  # fmt: skip
    assert made.returncode == 0, made.stderr
    assert "proxy_set_header X-Forwarded-For $http_cf_connecting_ip;" in made.stdout
    assert "proxy_set_header Host $http_host;" in made.stdout
    assert "map $request $logged_request" in made.stdout


def test_front_helper_executable_and_keys_documented() -> None:
    staged = subprocess.run(
        ["git", "ls-files", "-s", "deploy/front/client-ip.envsh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert staged.startswith("100755")
    example = (ROOT / ".env.example").read_text()
    keys = dict(re.findall(r"^([A-Z_]+)=(.*)$", example, re.MULTILINE))
    for key in REQUIRED:
        assert keys[key] == "???", key
    assert keys["FRONT_SERVER_NAME"] == "_"
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
