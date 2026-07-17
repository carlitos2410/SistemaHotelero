from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usuarios'

    def ready(self):
        from django.contrib.auth.models import Group
        from django.db.models.signals import post_migrate

        def crear_roles(sender, **kwargs):
            for nombre in ['Gerencia', 'Administrador', 'Recepcionista', 'Limpieza']:
                Group.objects.get_or_create(name=nombre)

        post_migrate.connect(crear_roles, sender=self)
