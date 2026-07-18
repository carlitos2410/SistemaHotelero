from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copiar_fechas_programadas(apps, schema_editor):
    Estancia = apps.get_model('estancias', 'Estancia')
    for estancia in Estancia.objects.select_related('reserva').iterator():
        estancia.fecha_entrada_programada = estancia.reserva.fecha_entrada
        estancia.fecha_salida_programada = estancia.reserva.fecha_salida
        estancia.save(update_fields=['fecha_entrada_programada', 'fecha_salida_programada'])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('estancias', '0009_delete_pagofolio'),
    ]

    operations = [
        migrations.AddField(
            model_name='estancia',
            name='fecha_entrada_programada',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='estancia',
            name='fecha_salida_programada',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='estancia',
            name='tipo_checkin',
            field=models.CharField(choices=[('NORMAL', 'Normal'), ('ANTICIPADO', 'Anticipado por hora'), ('ANTICIPADO_FECHA', 'Anticipado por fecha'), ('LLEGADA_TARDIA', 'Llegada tardia')], default='NORMAL', max_length=20),
        ),
        migrations.AlterField(
            model_name='estancia',
            name='tipo_checkout',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('NORMAL', 'Normal'), ('TARDIO', 'Tardio'), ('PRORROGA', 'Prorroga')], default='PENDIENTE', max_length=20),
        ),
        migrations.AlterField(
            model_name='cargoestancia',
            name='tipo',
            field=models.CharField(choices=[('HABITACION', 'Habitacion'), ('RESTAURANTE', 'Restaurante'), ('LAVANDERIA', 'Lavanderia'), ('MINIBAR', 'Minibar'), ('EARLY_CHECKIN', 'Early check-in'), ('LATE_CHECKOUT', 'Late check-out'), ('NOCHE_ADICIONAL', 'Noche adicional'), ('PENALIDAD', 'Penalidad'), ('OTRO', 'Otro')], default='OTRO', max_length=20),
        ),
        migrations.CreateModel(
            name='ProrrogaEstancia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_salida_anterior', models.DateField()),
                ('fecha_salida_nueva', models.DateField()),
                ('noches_adicionales', models.PositiveIntegerField()),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('motivo', models.CharField(blank=True, max_length=180)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('autorizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prorrogas_autorizadas', to=settings.AUTH_USER_MODEL)),
                ('estancia', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prorrogas', to='estancias.estancia')),
            ],
            options={'ordering': ['creado_en']},
        ),
        migrations.RunPython(copiar_fechas_programadas, migrations.RunPython.noop),
    ]
