from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Crea los grupos operativos del hotel y asigna permisos base.'

    grupos = ['Gerencia', 'Administrador', 'Recepcionista', 'Limpieza']
    grupos_heredados = {
        'Administracion': 'Administrador',
        'Recepcion': 'Recepcionista',
        'Heuspeekin': 'Limpieza',
        'Housekeeping': 'Limpieza',
    }

    def permisos(self, app_label, modelos, acciones):
        permisos = Permission.objects.none()
        for modelo in modelos:
            content_type = ContentType.objects.filter(app_label=app_label, model=modelo).first()
            if not content_type:
                continue
            codenames = [f'{accion}_{modelo}' for accion in acciones]
            permisos = permisos | Permission.objects.filter(content_type=content_type, codename__in=codenames)
        return permisos

    def asignar(self, nombre_grupo, mapa_modelos, acciones):
        grupo = Group.objects.get(name=nombre_grupo)
        for app_label, modelos in mapa_modelos.items():
            grupo.permissions.add(*self.permisos(app_label, modelos, acciones))

    def handle(self, *args, **options):
        for nombre in self.grupos:
            Group.objects.get_or_create(name=nombre)

        for nombre_anterior, nombre_actual in self.grupos_heredados.items():
            anterior = Group.objects.filter(name=nombre_anterior).first()
            if anterior:
                actual = Group.objects.get(name=nombre_actual)
                for usuario in anterior.user_set.all():
                    usuario.groups.add(actual)
                anterior.delete()
        Group.objects.filter(name='Cliente').delete()

        for nombre in self.grupos:
            Group.objects.get(name=nombre).permissions.clear()

        gerencia = {
            'hoteles': ['hotel'],
            'habitaciones': ['tipohabitacion', 'habitacion', 'observacionmantenimiento'],
            'reservas': ['huesped', 'tarifa', 'promocion', 'reserva', 'acompanante'],
            'estancias': [
                'productoservicio',
                'configuracioncobro',
                'estancia',
                'cargoestancia',
                'folio',
                'metodopago',
                'pago',
                'comprobante',
                'movimientocaja',
            ],
        }
        administracion = {
            'hoteles': ['hotel'],
            'habitaciones': ['tipohabitacion', 'habitacion'],
            'reservas': ['tarifa', 'promocion'],
            'estancias': ['productoservicio', 'configuracioncobro', 'metodopago'],
        }
        recepcion = {
            'habitaciones': ['habitacion'],
            'reservas': ['huesped', 'reserva', 'acompanante'],
            'estancias': ['estancia', 'cargoestancia', 'folio', 'pago', 'comprobante', 'movimientocaja'],
        }
        limpieza = {
            'habitaciones': ['habitacion', 'observacionmantenimiento'],
        }

        self.asignar('Gerencia', gerencia, ['view'])
        self.asignar('Administrador', administracion, ['view', 'add', 'change'])
        self.asignar('Administrador', {'auth': ['user']}, ['view', 'add', 'change'])
        self.asignar('Administrador', {'auth': ['group']}, ['view'])
        self.asignar('Recepcionista', recepcion, ['view', 'add', 'change'])
        self.asignar('Limpieza', limpieza, ['view', 'add', 'change'])

        self.stdout.write(self.style.SUCCESS('Grupos del hotel creados y permisos asignados.'))
        for nombre in self.grupos:
            total = Group.objects.get(name=nombre).permissions.count()
            self.stdout.write(f'- {nombre}: {total} permisos')
