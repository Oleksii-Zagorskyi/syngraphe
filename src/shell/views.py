"""The shell's views."""

from __future__ import annotations

import redis
from django.conf import settings
from django.db import Error, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

PROBE_TIMEOUT_SECONDS = 2


def _database_answers() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Error:
        return False
    return True


def _redis_answers() -> bool:
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        socket_timeout=PROBE_TIMEOUT_SECONDS,
    )
    try:
        return bool(client.ping())
    except (redis.RedisError, OSError):
        return False
    finally:
        client.close()


@never_cache
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """`200` when the database and Redis answer, `503` naming the one that does not.

    Never a version or a host.
    """
    checks = {
        "database": "ok" if _database_answers() else "unreachable",
        "redis": "ok" if _redis_answers() else "unreachable",
    }
    status = 200 if all(value == "ok" for value in checks.values()) else 503
    return JsonResponse(checks, status=status)
