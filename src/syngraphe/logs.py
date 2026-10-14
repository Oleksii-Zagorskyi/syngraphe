"""Structured logging: one JSON object per line, with the request id and the tenant where known."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from django.http import HttpRequest, HttpResponse
from pythonjsonlogger.json import JsonFormatter as _JsonFormatter

from syngraphe.redaction import without_credentials

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_number_var: ContextVar[int | None] = ContextVar("tenant_number", default=None)


class RequestContextFilter(logging.Filter):
    """Attach the current request id and tenant number to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.tenant = tenant_number_var.get()
        return True


class CredentialFilter(logging.Filter):
    """Drops a credential link's token from a record before any handler writes it: the framework
    logs a refused request's path, and a link's path carries its token (DL-0406)."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = without_credentials(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


class JsonFormatter(_JsonFormatter):
    """The fixed field set of every line; keys with no value are dropped."""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "time", "levelname": "level", "name": "logger"},
        )

    def add_fields(
        self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        # The development server attaches its socket and clock to each record; neither informs.
        for noise in ("request", "server_time"):
            log_record.pop(noise, None)
        for key in ("request_id", "tenant"):
            value = getattr(record, key, None)
            if value is None:
                log_record.pop(key, None)
            else:
                log_record[key] = value


class RequestContextMiddleware:
    """Give each request an id for its log lines and echo it in the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
            tenant_number_var.set(None)
        response["X-Request-Id"] = request_id
        return response
