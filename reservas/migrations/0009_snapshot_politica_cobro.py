from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


def completar_politica_reservas(apps, schema_editor):
    Reserva = apps.get_model('reservas', 'Reserva')
    Reserva.objects.filter(politica_cobro_checkout='').update(
        politica_cobro_checkout='ESTADIA_REAL_PENALIDAD',
        porcentaje_penalidad_salida_anticipada=Decimal('50.00'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0008_promociones_en_precio_reserva'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='politica_cobro_checkout',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ESTADIA_REAL', 'Cobrar solo estadia real'),
                    ('RESERVA_COMPLETA', 'Cobrar reserva completa'),
                    ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad'),
                ],
                default='',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='reserva',
            name='porcentaje_penalidad_salida_anticipada',
            field=models.DecimalField(decimal_places=2, default=50, max_digits=5),
        ),
        migrations.RunPython(completar_politica_reservas, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=(
                    Q(porcentaje_penalidad_salida_anticipada__gte=0)
                    & Q(porcentaje_penalidad_salida_anticipada__lte=100)
                ),
                name='reserva_penalidad_porcentaje_valido',
            ),
        ),
    ]
