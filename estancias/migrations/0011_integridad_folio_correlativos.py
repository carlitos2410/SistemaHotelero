from django.db import migrations, models


def inicializar_correlativos(apps, schema_editor):
    Comprobante = apps.get_model('estancias', 'Comprobante')
    Correlativo = apps.get_model('estancias', 'CorrelativoComprobante')
    for tipo, serie in Comprobante.objects.values_list('tipo', 'serie').distinct():
        ultimo = Comprobante.objects.filter(tipo=tipo, serie=serie).order_by('-numero').values_list('numero', flat=True).first() or 0
        Correlativo.objects.update_or_create(tipo=tipo, serie=serie, defaults={'ultimo_numero': ultimo})


class Migration(migrations.Migration):
    dependencies = [('estancias', '0010_prorrogas_y_fechas_programadas')]

    operations = [
        migrations.CreateModel(
            name='CorrelativoComprobante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('BOLETA', 'Boleta'), ('FACTURA', 'Factura')], max_length=20)),
                ('serie', models.CharField(max_length=10)),
                ('ultimo_numero', models.PositiveIntegerField(default=0)),
            ],
            options={'unique_together': {('tipo', 'serie')}},
        ),
        migrations.AddConstraint(model_name='cargoestancia', constraint=models.CheckConstraint(condition=models.Q(('cantidad__gt', 0)), name='cargo_cantidad_positiva')),
        migrations.AddConstraint(model_name='cargoestancia', constraint=models.CheckConstraint(condition=models.Q(('precio_unitario__gte', 0)), name='cargo_precio_no_negativo')),
        migrations.AddConstraint(model_name='cargoestancia', constraint=models.CheckConstraint(condition=models.Q(('monto__gte', 0)), name='cargo_monto_no_negativo')),
        migrations.AddConstraint(model_name='folio', constraint=models.CheckConstraint(condition=models.Q(('subtotal__gte', 0)), name='folio_subtotal_no_negativo')),
        migrations.AddConstraint(model_name='folio', constraint=models.CheckConstraint(condition=models.Q(('igv__gte', 0)), name='folio_igv_no_negativo')),
        migrations.AddConstraint(model_name='folio', constraint=models.CheckConstraint(condition=models.Q(('total__gte', 0)), name='folio_total_no_negativo')),
        migrations.AddConstraint(model_name='pago', constraint=models.CheckConstraint(condition=models.Q(('monto__gt', 0)), name='pago_monto_positivo')),
        migrations.RunPython(inicializar_correlativos, migrations.RunPython.noop),
    ]
