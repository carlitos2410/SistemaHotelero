import django.contrib.postgres.constraints
import django.contrib.postgres.fields
import django.contrib.postgres.operations
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0004_acompanante'),
    ]

    operations = [
        django.contrib.postgres.operations.BtreeGistExtension(),
        migrations.AddConstraint(
            model_name='tarifa',
            constraint=models.CheckConstraint(
                condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')),
                name='tarifa_fin_no_anterior_inicio',
            ),
        ),
        migrations.AddConstraint(
            model_name='tarifa',
            constraint=models.CheckConstraint(
                condition=models.Q(precio_noche__gt=0),
                name='tarifa_precio_positivo',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=models.Q(fecha_salida__gt=models.F('fecha_entrada')),
                name='reserva_salida_posterior_entrada',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=models.Q(num_adultos__gt=0),
                name='reserva_adultos_positivos',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=models.Q(precio_total__gte=0),
                name='reserva_precio_no_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                name='reserva_habitacion_sin_solapamiento_activo',
                expressions=[
                    (models.F('habitacion'), django.contrib.postgres.fields.RangeOperators.EQUAL),
                    (
                        models.Func(
                            models.F('fecha_entrada'),
                            models.F('fecha_salida'),
                            models.Value('[)'),
                            function='DATERANGE',
                            output_field=django.contrib.postgres.fields.DateRangeField(),
                        ),
                        django.contrib.postgres.fields.RangeOperators.OVERLAPS,
                    ),
                ],
                condition=models.Q(
                    habitacion__isnull=False,
                    estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
                ),
            ),
        ),
    ]
