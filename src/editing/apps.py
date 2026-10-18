from django.apps import AppConfig


class EditingConfig(AppConfig):
    name = "editing"

    def ready(self) -> None:
        # The frontmatter's keys a draft may change, known to every process before any list of
        # changes is drawn (DL-0463, DL-0476).
        from editing import title_page

        title_page.register()
