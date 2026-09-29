"""Gunicorn's settings: the bind address, the workers, and every log line as JSON on stdout."""

bind = "0.0.0.0:8000"
# Threaded workers: an idle browser connection holds a thread, not the worker (DL-0347).
worker_class = "gthread"
workers = 2
threads = 4
accesslog = "-"
errorlog = "-"
# Gunicorn trusts no forwarded header itself: the application's TRUSTED_PROXIES is the one list
# that decides which peer's headers are believed (DL-0292).
forwarded_allow_ips = ""
# The peer, the request line, the status and the size; no referer and no user agent. The peer is
# the proxy behind a proxy: the client address, resolved per request by the application, is in
# the application's own log lines, never taken from a header Gunicorn cannot judge.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s'

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "syngraphe.logs.JsonFormatter"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["stdout"], "level": "INFO"},
    "loggers": {
        "gunicorn.error": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "gunicorn.access": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
    },
}
