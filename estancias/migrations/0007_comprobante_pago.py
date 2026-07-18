from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0006_pago_folio'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagofolio',
            name='cliente_direccion',
            field=models.CharField(blank=True, max_length=220),
        ),
        migrations.AddField(
            model_name='pagofolio',
            name='cliente_documento',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='pagofolio',
            name='cliente_razon_social',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='pagofolio',
            name='tipo_comprobante',
            field=models.CharField(choices=[('BOLETA', 'Boleta'), ('FACTURA', 'Factura')], default='BOLETA', max_length=20),
        ),
    ]
