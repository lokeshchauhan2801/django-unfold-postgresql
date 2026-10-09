from django.apps import AppConfig


class DocsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "docs"
    label = "documents"
    verbose_name = "Documents"
