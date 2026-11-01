from django.apps import AppConfig


class HibiraConfig(AppConfig):
    name = "django_hibira"
    label = "django_hibira"
    verbose_name = "Hibira"

    def ready(self) -> None:
        from . import checks  # noqa: F401
