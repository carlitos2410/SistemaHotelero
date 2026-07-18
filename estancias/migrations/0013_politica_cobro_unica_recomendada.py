from decimal import Decimal

from django.db import migrations, models


def consolidar_politica(apps, schema_editor):
    ConfiguracionCobro = apps.get_model('estancias', 'ConfiguracionCobro')
    configuraciones = list(ConfiguracionCobro.objects.order_by('id'))
    if configuraciones:
        configuracion = configuraciones[0]
        ConfiguracionCobro.objects.exclude(pk=configuracion.pk).delete()
        configuracion.politica_checkout = 'ESTADIA_REAL_PENALIDAD'
        configuracion.porcentaje_penalidad_salida_anticipada = Decimal('50.00')
        configuracion.activo = True
        configuracion.save()


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0012_productos_manual_integridad'),
    ]

    operations = [
        migrations.RunPython(consolidar_politica, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='configuracioncobro',
            name='politica_checkout',
            field=models.CharField(
                choices=[
                    ('ESTADIA_REAL', 'Cobrar solo estadia real'),
                    ('RESERVA_COMPLETA', 'Cobrar reserva completa'),
                    ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad'),
                ],
                default='ESTADIA_REAL_PENALIDAD',
                max_length=30,
            ),
        ),
        migrations.RemoveField(
            model_name='configuracioncobro',
            name='activo',
        ),
    ]
