from decimal import Decimal

from django.db import migrations, models


def crear_configuracion_cobro(apps, schema_editor):
    ConfiguracionCobro = apps.get_model('estancias', 'ConfiguracionCobro')
    ConfiguracionCobro.objects.get_or_create(
        activo=True,
        defaults={
            'politica_checkout': 'ESTADIA_REAL',
            'porcentaje_penalidad_salida_anticipada': Decimal('50.00'),
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0004_productos_servicios_cargos'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionCobro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('politica_checkout', models.CharField(choices=[('ESTADIA_REAL', 'Cobrar solo estadia real'), ('RESERVA_COMPLETA', 'Cobrar reserva completa'), ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad')], default='ESTADIA_REAL', max_length=30)),
                ('porcentaje_penalidad_salida_anticipada', models.DecimalField(decimal_places=2, default=Decimal('50.00'), help_text='Porcentaje aplicado sobre las noches reservadas no usadas.', max_digits=5)),
                ('activo', models.BooleanField(default=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuracion de cobro',
                'verbose_name_plural': 'Configuraciones de cobro',
            },
        ),
        migrations.AddField(
            model_name='estancia',
            name='cargo_penalidad_salida_anticipada',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='estancia',
            name='monto_estadia_real',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='estancia',
            name='noches_reales',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='estancia',
            name='noches_reservadas',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='estancia',
            name='politica_cobro_checkout',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AlterField(
            model_name='cargoestancia',
            name='tipo',
            field=models.CharField(choices=[('HABITACION', 'Habitacion'), ('RESTAURANTE', 'Restaurante'), ('LAVANDERIA', 'Lavanderia'), ('MINIBAR', 'Minibar'), ('EARLY_CHECKIN', 'Early check-in'), ('LATE_CHECKOUT', 'Late check-out'), ('PENALIDAD', 'Penalidad'), ('OTRO', 'Otro')], default='OTRO', max_length=20),
        ),
        migrations.RunPython(crear_configuracion_cobro, migrations.RunPython.noop),
    ]
