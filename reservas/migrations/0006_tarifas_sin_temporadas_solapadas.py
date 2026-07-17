import django.contrib.postgres.constraints
import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0005_integridad_reservas_tarifas'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='tarifa',
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                name='tarifa_tipo_sin_temporadas_solapadas',
                expressions=[
                    (models.F('tipo_habitacion'), django.contrib.postgres.fields.RangeOperators.EQUAL),
                    (
                        models.Func(
                            models.F('fecha_inicio'),
                            models.F('fecha_fin'),
                            models.Value('[]'),
                            function='DATERANGE',
                            output_field=django.contrib.postgres.fields.DateRangeField(),
                        ),
                        django.contrib.postgres.fields.RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ),
    ]
