"""The configuration loader: every missing key at once, and typed values."""

from __future__ import annotations

import pytest

from syngraphe import config

COMPLETE = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DJANGO_DEBUG": "true",
    "DJANGO_ADMIN_PATH": "operator/",
    "SITE_HTTPS": "false",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5433",
    "POSTGRES_DB": "syngraphe",
    "POSTGRES_USER": "syngraphe",
    "POSTGRES_PASSWORD": "test-only-not-a-password",
    "REDIS_URL": "redis://redis:6379/0",
    "CELERY_BROKER_URL": "redis://redis:6379/1",
    "GIT_REPO_ROOT": "/srv/repos",
    "TRUSTED_PROXIES": "127.0.0.1, 172.16.0.0/12",
    "DISPLAY_TIMEZONE": "Europe/Madrid",
    "DEFAULT_LANGUAGE": "uk",
}

pytestmark = pytest.mark.fast


def test_missing_keys_reported_together() -> None:
    environ = dict(COMPLETE, POSTGRES_HOST="???", POSTGRES_DB="???", REDIS_URL="???")

    with pytest.raises(config.ConfigurationError) as caught:
        config.load(environ)

    assert caught.value.missing == ["POSTGRES_DB", "POSTGRES_HOST", "REDIS_URL"]
    message = str(caught.value)
    for key in ("POSTGRES_DB", "POSTGRES_HOST", "REDIS_URL"):
        assert key in message


def test_complete_environment_loads() -> None:
    loaded = config.load(COMPLETE)

    assert loaded.secret_key == "test-only-not-a-secret"
    assert loaded.debug is True
    assert loaded.site_https is False
    assert loaded.postgres_port == 5433
    assert loaded.postgres_host == "db"
    assert loaded.redis_url == "redis://redis:6379/0"
    assert loaded.git_repo_root.as_posix() == "/srv/repos"
    assert [str(n) for n in loaded.trusted_proxies] == ["127.0.0.1/32", "172.16.0.0/12"]
    assert loaded.default_language == "uk"


def test_absent_key_counts_as_missing() -> None:
    environ = {k: v for k, v in COMPLETE.items() if k != "DJANGO_SECRET_KEY"}

    with pytest.raises(config.ConfigurationError) as caught:
        config.load(environ)

    assert caught.value.missing == ["DJANGO_SECRET_KEY"]


def test_empty_value_counts_as_missing() -> None:
    environ = dict(COMPLETE, POSTGRES_PASSWORD="", POSTGRES_DB="   ")

    with pytest.raises(config.ConfigurationError) as caught:
        config.load(environ)

    assert caught.value.missing == ["POSTGRES_DB", "POSTGRES_PASSWORD"]


def test_malformed_values_reported_with_the_missing() -> None:
    environ = dict(
        COMPLETE,
        DJANGO_DEBUG="maybe",
        POSTGRES_PORT="five",
        TRUSTED_PROXIES="lan, 10.0.0.0/8, also-not",
        DJANGO_ADMIN_PATH="admin/",
        DISPLAY_TIMEZONE="Mars/Olympus",
    )

    with pytest.raises(config.ConfigurationError) as caught:
        config.load(environ)

    assert caught.value.malformed == [
        "DISPLAY_TIMEZONE",
        "DJANGO_ADMIN_PATH",
        "DJANGO_DEBUG",
        "POSTGRES_PORT",
        "TRUSTED_PROXIES",
    ]


@pytest.mark.parametrize("path", ["/operator/", "operator", "admin/"])
def test_admin_path_shape_is_checked(path: str) -> None:
    with pytest.raises(config.ConfigurationError) as caught:
        config.load(dict(COMPLETE, DJANGO_ADMIN_PATH=path))

    assert caught.value.malformed == ["DJANGO_ADMIN_PATH"]


def test_relative_repo_root_is_taken_from_the_repository() -> None:
    loaded = config.load(dict(COMPLETE, GIT_REPO_ROOT=".repos"))

    assert loaded.git_repo_root == config.REPOSITORY_ROOT / ".repos"
    assert loaded.git_repo_root.is_absolute()


def test_secrets_stay_out_of_the_repr() -> None:
    text = repr(config.load(COMPLETE))

    assert "test-only-not-a-secret" not in text
    assert "test-only-not-a-password" not in text


def test_none_trusts_no_proxy() -> None:
    loaded = config.load(dict(COMPLETE, TRUSTED_PROXIES="none"))

    assert loaded.trusted_proxies == ()


@pytest.mark.parametrize("value", ["", "???"])
def test_trusted_proxies_must_be_decided(value: str) -> None:
    with pytest.raises(config.ConfigurationError) as refused:
        config.load(dict(COMPLETE, TRUSTED_PROXIES=value))

    assert "TRUSTED_PROXIES" in str(refused.value)


def test_a_network_of_every_address_is_refused() -> None:
    with pytest.raises(config.ConfigurationError) as refused:
        config.load(dict(COMPLETE, TRUSTED_PROXIES="0.0.0.0/0"))

    assert "TRUSTED_PROXIES" in str(refused.value)


def test_upload_maximum() -> None:
    """One platform maximum for an upload, in megabytes, 20 unless set (DL-0432)."""
    assert config.load(COMPLETE).upload_max_bytes == 20 * 1024 * 1024
    assert config.load(dict(COMPLETE, UPLOAD_MAX_MB="50")).upload_max_bytes == 50 * 1024 * 1024
    assert config.load(dict(COMPLETE, UPLOAD_MAX_MB="???")).upload_max_bytes == 20 * 1024 * 1024


# The front's helper reads plain ASCII digits; the application refuses what the helper refuses.
@pytest.mark.parametrize("value", ["twenty", "0", "-5", "20MB", "+5", "1_000", "٢٠"])
def test_upload_maximum_malformed(value: str) -> None:
    with pytest.raises(config.ConfigurationError) as caught:
        config.load(dict(COMPLETE, UPLOAD_MAX_MB=value))

    assert caught.value.malformed == ["UPLOAD_MAX_MB"]


def test_settings_expose_the_upload_maximum() -> None:
    from django.conf import settings

    assert settings.UPLOAD_MAX_BYTES == config.load().upload_max_bytes


def test_help_work_in_progress_malformed() -> None:
    assert config.load(COMPLETE).help_work_in_progress is False
    assert config.load(dict(COMPLETE, HELP_WORK_IN_PROGRESS="true")).help_work_in_progress is True
    with pytest.raises(config.ConfigurationError) as caught:
        config.load(dict(COMPLETE, HELP_WORK_IN_PROGRESS="maybe"))
    assert caught.value.malformed == ["HELP_WORK_IN_PROGRESS"]
