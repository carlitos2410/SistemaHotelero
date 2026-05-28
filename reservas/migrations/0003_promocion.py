from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('habitaciones', '0001_initial'),
        ('reservas', '0002_reserva_tarifa'),
    ]

    operations = [
        migrations.CreateModel(
            name='Promocion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('descripcion', models.TextField(blank=True)),
                ('porcentaje_descuento', models.DecimalField(decimal_places=2, max_digits=5)),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField()),
                ('activo', models.BooleanField(default=True)),
                ('tipo_habitacion', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='promociones', to='habitaciones.tipohabitacion')),
            ],
            options={
                'ordering': ['-activo', 'fecha_inicio', 'nombre'],
            },
        ),
    ]
