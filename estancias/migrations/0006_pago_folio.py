from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0005_politica_cobro_checkout'),
    ]

    operations = [
        migrations.CreateModel(
            name='PagoFolio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metodo', models.CharField(choices=[('EFECTIVO', 'Efectivo'), ('TARJETA', 'Tarjeta'), ('BILLETERA', 'Billetera digital')], max_length=20)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('referencia', models.CharField(blank=True, max_length=80)),
                ('estado', models.CharField(choices=[('APROBADO', 'Aprobado'), ('RECHAZADO', 'Rechazado')], default='APROBADO', max_length=20)),
                ('es_simulado', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('folio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagos', to='estancias.folio')),
            ],
            options={
                'ordering': ['-creado_en'],
            },
        ),
    ]
