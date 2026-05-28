from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def crear_productos_iniciales(apps, schema_editor):
    ProductoServicio = apps.get_model('estancias', 'ProductoServicio')
    productos = [
        ('Agua mineral', 'MINIBAR', Decimal('5.00')),
        ('Gaseosa', 'MINIBAR', Decimal('8.00')),
        ('Cena ejecutiva', 'RESTAURANTE', Decimal('45.00')),
        ('Desayuno buffet', 'RESTAURANTE', Decimal('35.00')),
        ('Lavanderia por prenda', 'LAVANDERIA', Decimal('12.00')),
        ('Planchado por prenda', 'LAVANDERIA', Decimal('8.00')),
    ]

    for nombre, categoria, precio in productos:
        ProductoServicio.objects.get_or_create(
            nombre=nombre,
            defaults={
                'categoria': categoria,
                'precio': precio,
                'activo': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0003_checkin_checkout_tipos_cargos'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductoServicio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('categoria', models.CharField(choices=[('RESTAURANTE', 'Restaurante'), ('LAVANDERIA', 'Lavanderia'), ('MINIBAR', 'Minibar'), ('OTRO', 'Otro')], max_length=20)),
                ('precio', models.DecimalField(decimal_places=2, max_digits=10)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['categoria', 'nombre'],
            },
        ),
        migrations.AddField(
            model_name='cargoestancia',
            name='cantidad',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='cargoestancia',
            name='precio_unitario',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='cargoestancia',
            name='producto_servicio',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cargos', to='estancias.productoservicio'),
        ),
        migrations.RunPython(crear_productos_iniciales, migrations.RunPython.noop),
    ]
