from django.db import migrations, models


def desactivar_productos_sin_precio(apps, schema_editor):
    ProductoServicio = apps.get_model('estancias', 'ProductoServicio')
    ProductoServicio.objects.filter(activo=True, precio__lte=0).update(activo=False)


class Migration(migrations.Migration):

    dependencies = [
        ('estancias', '0011_integridad_folio_correlativos'),
    ]

    operations = [
        migrations.RunPython(desactivar_productos_sin_precio, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='productoservicio',
            constraint=models.CheckConstraint(
                condition=models.Q(activo=False) | models.Q(precio__gt=0),
                name='producto_activo_precio_positivo',
            ),
        ),
    ]
