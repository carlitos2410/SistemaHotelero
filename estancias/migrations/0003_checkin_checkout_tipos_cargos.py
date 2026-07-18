from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='estancia',
            name='cargo_early_checkin',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='estancia',
            name='cargo_late_checkout',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='estancia',
            name='tipo_checkin',
            field=models.CharField(
                choices=[('NORMAL', 'Normal'), ('ANTICIPADO', 'Anticipado')],
                default='NORMAL',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='estancia',
            name='tipo_checkout',
            field=models.CharField(
                choices=[('PENDIENTE', 'Pendiente'), ('NORMAL', 'Normal'), ('TARDIO', 'Tardio')],
                default='PENDIENTE',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='cargoestancia',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('HABITACION', 'Habitacion'),
                    ('RESTAURANTE', 'Restaurante'),
                    ('LAVANDERIA', 'Lavanderia'),
                    ('MINIBAR', 'Minibar'),
                    ('EARLY_CHECKIN', 'Early check-in'),
                    ('LATE_CHECKOUT', 'Late check-out'),
                    ('OTRO', 'Otro'),
                ],
                default='OTRO',
                max_length=20,
            ),
        ),
    ]
