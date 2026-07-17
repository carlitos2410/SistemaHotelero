from django.apps import AppConfig


class HabitacionesConfig(AppConfig):
    name = 'habitaciones'

    def ready(self):
        from . import signals  # noqa: F401
