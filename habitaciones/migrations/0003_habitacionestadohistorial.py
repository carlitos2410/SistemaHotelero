from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def reconstruir_historial(apps, schema_editor):
    Habitacion = apps.get_model('habitaciones', 'Habitacion')
    Historial = apps.get_model('habitaciones', 'HabitacionEstadoHistorial')
    Observacion = apps.get_model('habitaciones', 'ObservacionMantenimiento')
    Estancia = apps.get_model('estancias', 'Estancia')

    for habitacion in Habitacion.objects.all():
        eventos = []
        for estancia in Estancia.objects.filter(habitacion_id=habitacion.id):
            eventos.append((
                estancia.fecha_checkin,
                'OCUPADA',
                'Check-in reconstruido desde la estancia.',
                None,
            ))
            if estancia.fecha_checkout:
                eventos.append((
                    estancia.fecha_checkout,
                    'LIMPIEZA',
                    'Checkout reconstruido desde la estancia.',
                    None,
                ))
        for observacion in Observacion.objects.filter(habitacion_id=habitacion.id):
            eventos.append((
                observacion.creado_en,
                'MANTENIMIENTO',
                observacion.observacion or 'Mantenimiento reconstruido desde observacion.',
                observacion.creado_por_id,
            ))

        eventos.sort(key=lambda evento: evento[0])
        estado_anterior = ''
        registros = []
        for momento, estado_nuevo, motivo, usuario_id in eventos:
            if estado_anterior == estado_nuevo:
                continue
            registros.append(Historial(
                habitacion_id=habitacion.id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                cambiado_por_id=usuario_id,
                motivo=motivo[:180],
                cambiado_en=momento,
            ))
            estado_anterior = estado_nuevo

        if estado_anterior != habitacion.estado:
            registros.append(Historial(
                habitacion_id=habitacion.id,
                estado_anterior=estado_anterior,
                estado_nuevo=habitacion.estado,
                motivo='Estado actual al habilitar el historial.',
                cambiado_en=timezone.now(),
            ))
        if registros:
            Historial.objects.bulk_create(registros)


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0009_delete_pagofolio'),
        ('habitaciones', '0002_observacionmantenimiento'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HabitacionEstadoHistorial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado_anterior', models.CharField(blank=True, choices=[('DISPONIBLE', 'Disponible'), ('OCUPADA', 'Ocupada'), ('LIMPIEZA', 'Limpieza'), ('MANTENIMIENTO', 'Mantenimiento')], max_length=20)),
                ('estado_nuevo', models.CharField(choices=[('DISPONIBLE', 'Disponible'), ('OCUPADA', 'Ocupada'), ('LIMPIEZA', 'Limpieza'), ('MANTENIMIENTO', 'Mantenimiento')], max_length=20)),
                ('motivo', models.CharField(blank=True, max_length=180)),
                ('cambiado_en', models.DateTimeField()),
                ('cambiado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_estado_habitacion', to=settings.AUTH_USER_MODEL)),
                ('habitacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial_estados', to='habitaciones.habitacion')),
            ],
            options={
                'ordering': ['-cambiado_en', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='habitacionestadohistorial',
            index=models.Index(fields=['habitacion', '-cambiado_en'], name='hab_estado_fecha_idx'),
        ),
        migrations.RunPython(reconstruir_historial, migrations.RunPython.noop),
    ]
