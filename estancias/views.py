from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hoteles.models import Hotel
from reportes.pdf import generar_comprobante_pdf
from usuarios.auth import ROLES, role_required

from .forms import CargoHabitacionForm, ConfiguracionCobroForm, PagoForm, ReporteCajaFiltroForm
from .models import CargoEstancia, Comprobante, ConfiguracionCobro, Estancia, Folio, MovimientoCaja, Pago


@role_required(ROLES['RECEPCIONISTA'])
def estancias_activas(request):
    estancias = Estancia.objects.select_related(
        'reserva__huesped',
        'habitacion__tipo',
        'folio',
    ).filter(estado='ACTIVA').order_by('habitacion__numero')

    return render(request, 'estancias/estancias_activas.html', {
        'estancias': estancias,
    })


@role_required(ROLES['RECEPCIONISTA'])
def cargar_consumo(request, estancia_id):
    estancia = get_object_or_404(
        Estancia.objects.select_related('reserva__huesped', 'habitacion__tipo', 'folio'),
        id=estancia_id,
        estado='ACTIVA',
    )

    if request.method == 'POST':
        form = CargoHabitacionForm(request.POST)
        if form.is_valid():
            producto = form.cleaned_data['producto_servicio']
            cantidad = form.cleaned_data['cantidad']
            observacion = form.cleaned_data['observacion']
            monto = producto.precio * cantidad
            concepto = producto.nombre

            if observacion:
                concepto = f'{concepto} - {observacion}'

            CargoEstancia.objects.create(
                estancia=estancia,
                producto_servicio=producto,
                concepto=concepto,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                monto=monto,
                tipo=producto.categoria,
            )

            folio, _ = Folio.objects.get_or_create(estancia=estancia)
            folio.calcular_totales()
            folio.save()

            messages.success(request, f'Consumo cargado a la habitacion. Total: S/ {monto}.')
            return redirect('cargar_consumo', estancia_id=estancia.id)
    else:
        form = CargoHabitacionForm()

    cargos = estancia.cargos.select_related('producto_servicio').all().order_by('-fecha')
    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    folio.save()
    folio.refresh_from_db()

    return render(request, 'estancias/cargar_consumo.html', {
        'estancia': estancia,
        'form': form,
        'cargos': cargos,
        'folio': folio,
    })


@role_required(ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def configurar_cobro(request):
    configuracion = ConfiguracionCobro.actual()

    if request.method == 'POST':
        form = ConfiguracionCobroForm(request.POST, instance=configuracion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Politica de cobro actualizada correctamente.')
            return redirect('configurar_cobro')
    else:
        form = ConfiguracionCobroForm(instance=configuracion)

    return render(request, 'estancias/configurar_cobro.html', {
        'form': form,
        'configuracion': configuracion,
    })


@role_required(ROLES['RECEPCIONISTA'])
def pagar_folio(request, folio_id):
    folio = get_object_or_404(
        Folio.objects.select_related('estancia__reserva__huesped', 'estancia__habitacion'),
        id=folio_id,
    )
    folio.calcular_totales()
    folio.save()

    if request.method == 'POST':
        form = PagoForm(request.POST, folio=folio)
        if form.is_valid():
            with transaction.atomic():
                pago = Pago.objects.create(
                    folio=folio,
                    metodo_pago=form.cleaned_data['metodo_pago'],
                    monto=form.cleaned_data['monto'],
                    numero_operacion=form.cleaned_data['numero_operacion'],
                    estado='APROBADO',
                    usuario_responsable=request.user,
                    observacion=form.cleaned_data['observacion'],
                    es_simulado=True,
                )

                tipo_comprobante = form.cleaned_data['tipo_comprobante']
                serie = 'F001' if tipo_comprobante == 'FACTURA' else 'B001'
                ultimo_numero = Comprobante.objects.filter(
                    tipo=tipo_comprobante,
                    serie=serie,
                ).aggregate(maximo=Max('numero'))['maximo'] or 0

                Comprobante.objects.create(
                    pago=pago,
                    tipo=tipo_comprobante,
                    serie=serie,
                    numero=ultimo_numero + 1,
                    cliente_documento=form.cleaned_data['cliente_documento'],
                    cliente_nombre=form.cleaned_data['cliente_nombre'],
                    cliente_direccion=form.cleaned_data['cliente_direccion'],
                    estado='EMITIDO',
                    usuario_responsable=request.user,
                )

                MovimientoCaja.objects.create(
                    pago=pago,
                    tipo='INGRESO',
                    concepto='PAGO_FOLIO',
                    monto=pago.monto,
                    metodo_pago=pago.metodo_pago,
                    numero_operacion=pago.numero_operacion,
                    usuario_responsable=request.user,
                    observacion=pago.observacion,
                )

                folio.calcular_totales()
                folio.estado = 'PAGADO' if folio.saldo_pendiente <= 0 else 'PENDIENTE'
                folio.save()
                folio.refresh_from_db()

            messages.success(request, f'Pago registrado por S/ {pago.monto}. Comprobante emitido correctamente.')
            return redirect('pagar_folio', folio_id=folio.id)
        messages.error(request, 'No se pudo registrar el pago. Revisa el metodo y el monto ingresado.')
    else:
        form = PagoForm(folio=folio)

    pagos = folio.pagos_normalizados.select_related('metodo_pago', 'comprobante', 'usuario_responsable').all()
    cargos = folio.estancia.cargos.select_related('producto_servicio').all().order_by('fecha')

    return render(request, 'estancias/pagar_folio.html', {
        'folio': folio,
        'form': form,
        'pagos': pagos,
        'cargos': cargos,
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def exportar_comprobante(request, comprobante_id):
    comprobante = get_object_or_404(
        Comprobante.objects.select_related(
            'pago__folio__estancia__reserva__huesped',
            'pago__folio__estancia__habitacion__tipo',
            'pago__folio__estancia__habitacion__hotel',
            'pago__metodo_pago',
        ),
        id=comprobante_id,
        estado='EMITIDO',
    )
    pago = comprobante.pago
    folio = pago.folio
    estancia = folio.estancia
    reserva = estancia.reserva
    huesped = reserva.huesped
    hotel = Hotel.objects.first() or estancia.habitacion.hotel
    cargos = estancia.cargos.all().order_by('fecha')

    folio.calcular_totales()
    folio.save()

    pdf = generar_comprobante_pdf(comprobante, folio, estancia, reserva, huesped, hotel, cargos)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="comprobante_{comprobante.tipo.lower()}_{comprobante.correlativo}.pdf"'
    return response


@role_required(ROLES['RECEPCIONISTA'])
def historial_pagos(request):
    pagos = Pago.objects.select_related(
        'folio__estancia__reserva__huesped',
        'folio__estancia__habitacion',
        'metodo_pago',
        'comprobante',
        'usuario_responsable',
    ).all()
    form = ReporteCajaFiltroForm(request.GET or None)

    if form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        metodo_pago = form.cleaned_data.get('metodo_pago')
        tipo_comprobante = form.cleaned_data.get('tipo_comprobante')
        estado = form.cleaned_data.get('estado')

        if fecha_desde:
            pagos = pagos.filter(creado_en__date__gte=fecha_desde)
        if fecha_hasta:
            pagos = pagos.filter(creado_en__date__lte=fecha_hasta)
        if metodo_pago:
            pagos = pagos.filter(metodo_pago=metodo_pago)
        if tipo_comprobante:
            pagos = pagos.filter(comprobante__tipo=tipo_comprobante)
        if estado:
            pagos = pagos.filter(comprobante__estado=estado)

    total = pagos.filter(estado='APROBADO').aggregate(total=Sum('monto'))['total'] or 0

    return render(request, 'estancias/historial_pagos.html', {
        'pagos': pagos,
        'form': form,
        'total': total,
    })


@role_required(ROLES['RECEPCIONISTA'])
def reporte_caja_diario(request):
    hoy = timezone.localdate()
    movimientos = MovimientoCaja.objects.select_related(
        'metodo_pago',
        'usuario_responsable',
        'pago__comprobante',
        'pago__folio__estancia__reserva__huesped',
    ).filter(fecha__date=hoy)
    form = ReporteCajaFiltroForm(request.GET or None)

    if form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        metodo_pago = form.cleaned_data.get('metodo_pago')
        tipo_comprobante = form.cleaned_data.get('tipo_comprobante')
        estado = form.cleaned_data.get('estado')

        if fecha_desde or fecha_hasta:
            movimientos = MovimientoCaja.objects.select_related(
                'metodo_pago',
                'usuario_responsable',
                'pago__comprobante',
                'pago__folio__estancia__reserva__huesped',
            ).all()
        if fecha_desde:
            movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            movimientos = movimientos.filter(fecha__date__lte=fecha_hasta)
        if metodo_pago:
            movimientos = movimientos.filter(metodo_pago=metodo_pago)
        if tipo_comprobante:
            movimientos = movimientos.filter(pago__comprobante__tipo=tipo_comprobante)
        if estado:
            movimientos = movimientos.filter(pago__comprobante__estado=estado)

    ingresos = movimientos.filter(tipo='INGRESO').aggregate(total=Sum('monto'))['total'] or 0
    egresos = movimientos.filter(tipo='EGRESO').aggregate(total=Sum('monto'))['total'] or 0

    return render(request, 'estancias/reporte_caja_diario.html', {
        'movimientos': movimientos,
        'form': form,
        'ingresos': ingresos,
        'egresos': egresos,
        'saldo': ingresos - egresos,
    })
