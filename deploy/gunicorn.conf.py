"""Gunicorn's settings: the bind address, the workers, and every log line as JSON on stdout."""

bind = "0.0.0.0:8000"
workers = 2
accesslog = "-"
errorlog = "-"
# The client, the request line, the status and the size; no referer and no user agent.
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
