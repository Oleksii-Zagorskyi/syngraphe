from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "tenancy"

    def ready(self) -> None:
        # Connects the reconnect receiver and registers the app-list check.
        from tenancy import routers, schemas  # noqa: F401
