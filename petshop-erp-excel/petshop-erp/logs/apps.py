from django.apps import AppConfig


class LogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logs"
    verbose_name = "Logs de auditoria"

    def ready(self):
        # Registra os receptores de login, logout e falha de login.
        from . import signals  # noqa: F401