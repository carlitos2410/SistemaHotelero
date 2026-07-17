from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('reservas', '0006_tarifas_sin_temporadas_solapadas')]

    operations = [
        migrations.AlterField(
            model_name='reserva',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('CONFIRMADA', 'Confirmada'), ('CHECKIN', 'Check-in'), ('CHECKOUT', 'Check-out'), ('CANCELADA', 'Cancelada'), ('NO_SHOW', 'No-show')], default='PENDIENTE', max_length=20),
        ),
    ]
