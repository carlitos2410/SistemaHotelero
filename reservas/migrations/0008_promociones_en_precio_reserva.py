from django.db import migrations, models
from django.db.models import F, Q


def completar_precio_historico(apps, schema_editor):
    Reserva = apps.get_model('reservas', 'Reserva')
    Reserva.objects.filter(precio_sin_descuento=0).update(precio_sin_descuento=F('precio_total'))


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0007_reserva_estado_no_show'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='precio_sin_descuento',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='reserva',
            name='descuento_promocion',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='reserva',
            name='detalle_tarifa',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(completar_precio_historico, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='promocion',
            constraint=models.CheckConstraint(
                condition=Q(fecha_fin__gte=F('fecha_inicio')),
                name='promocion_fin_no_anterior_inicio',
            ),
        ),
        migrations.AddConstraint(
            model_name='promocion',
            constraint=models.CheckConstraint(
                condition=Q(porcentaje_descuento__gt=0) & Q(porcentaje_descuento__lte=100),
                name='promocion_porcentaje_valido',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=Q(precio_sin_descuento__gte=0),
                name='reserva_precio_base_no_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='reserva',
            constraint=models.CheckConstraint(
                condition=Q(descuento_promocion__gte=0),
                name='reserva_descuento_no_negativo',
            ),
        ),
    ]
