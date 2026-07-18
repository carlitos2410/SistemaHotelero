from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportes.pdf import generar_comprobante_adelanto_pdf, generar_comprobante_pdf
from usuarios.auth import ROLES, role_required, usuario_en_rol
from usuarios.pagination import paginar_queryset

from .forms import CargoHabitacionForm, ConfiguracionCobroForm, PagoForm, ReporteCajaFiltroForm
from .models import Comprobante, ConfiguracionCobro, Estancia, Folio, MovimientoCaja, Pago
from .services import agregar_cargo_estancia, recalcular_folio, registrar_pago_folio


def inicio_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


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

            agregar_cargo_estancia(
                estancia,
                producto_servicio=producto,
                concepto=concepto,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                tipo=producto.categoria,
            )

            messages.success(request, f'Consumo cargado a la habitacion. Total: S/ {monto}.')
            return redirect('cargar_consumo', estancia_id=estancia.id)
    else:
        form = CargoHabitacionForm()

    cargos = estancia.cargos.select_related('producto_servicio').all().order_by('-fecha')
    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio = recalcular_folio(folio)
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
    puede_editar = usuario_en_rol(request.user, [ROLES['ADMINISTRADOR']])

    if request.method == 'POST':
        if not puede_editar:
            messages.error(request, 'Gerencia puede consultar la politica, pero solo Administracion puede modificarla.')
            return redirect('configurar_cobro')
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
        'puede_editar': puede_editar,
    })


@role_required(ROLES['RECEPCIONISTA'])
def pagar_folio(request, folio_id):
    folio = get_object_or_404(
        Folio.objects.select_related('estancia__reserva__huesped', 'estancia__habitacion'),
        id=folio_id,
    )
    folio = recalcular_folio(folio)

    if request.method == 'POST':
        form = PagoForm(request.POST, folio=folio)
        if form.is_valid():
            try:
                pago, comprobante, folio = registrar_pago_folio(
                    folio,
                    metodo_pago=form.cleaned_data['metodo_pago'],
                    monto=form.cleaned_data['monto'],
                    numero_operacion=form.cleaned_data['numero_operacion'],
                    tipo_comprobante=form.cleaned_data['tipo_comprobante'],
                    cliente_documento=form.cleaned_data['cliente_documento'],
                    cliente_nombre=form.cleaned_data['cliente_nombre'],
                    cliente_direccion=form.cleaned_data['cliente_direccion'],
                    observacion=form.cleaned_data['observacion'],
                    usuario=request.user,
                )
                messages.success(request, f'Pago registrado por S/ {pago.monto}. Comprobante {comprobante.correlativo} emitido.')
                return redirect('pagar_folio', folio_id=folio.id)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
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
            'pago__reserva__huesped',
            'pago__reserva__habitacion__tipo',
            'pago__reserva__hotel',
            'pago__metodo_pago',
        ),
        id=comprobante_id,
        estado='EMITIDO',
    )
    pago = comprobante.pago
    folio = pago.folio
    if folio is None:
        reserva = pago.reserva
        pdf = generar_comprobante_adelanto_pdf(
            comprobante,
            reserva,
            reserva.huesped,
            reserva.hotel,
        )
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="adelanto_{comprobante.tipo.lower()}_{comprobante.correlativo}.pdf"'
        return response
    estancia = folio.estancia
    reserva = estancia.reserva
    huesped = reserva.huesped
    hotel = estancia.habitacion.hotel
    cargos = estancia.cargos.all().order_by('fecha')

    folio = recalcular_folio(folio)

    pdf = generar_comprobante_pdf(comprobante, folio, estancia, reserva, huesped, hotel, cargos)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="comprobante_{comprobante.tipo.lower()}_{comprobante.correlativo}.pdf"'
    return response


@role_required(ROLES['RECEPCIONISTA'])
def historial_pagos(request):
    pagos = Pago.objects.select_related(
        'folio__estancia__reserva__huesped',
        'folio__estancia__habitacion',
        'reserva__huesped',
        'reserva__habitacion',
        'metodo_pago',
        'comprobante',
        'usuario_responsable',
    ).prefetch_related('movimientos_caja').all()
    form = ReporteCajaFiltroForm(request.GET or None)

    if form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        metodo_pago = form.cleaned_data.get('metodo_pago')
        tipo_comprobante = form.cleaned_data.get('tipo_comprobante')
        estado = form.cleaned_data.get('estado')

        if fecha_desde:
            pagos = pagos.filter(creado_en__gte=inicio_dia(fecha_desde))
        if fecha_hasta:
            pagos = pagos.filter(creado_en__lt=inicio_dia(fecha_hasta + timedelta(days=1)))
        if metodo_pago:
            pagos = pagos.filter(metodo_pago=metodo_pago)
        if tipo_comprobante:
            pagos = pagos.filter(comprobante__tipo=tipo_comprobante)
        if estado:
            pagos = pagos.filter(comprobante__estado=estado)

    pagos_aprobados = pagos.filter(estado='APROBADO')
    total_bruto = pagos_aprobados.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total_devuelto = MovimientoCaja.objects.filter(
        pago_id__in=pagos_aprobados.values('pk'),
        tipo='EGRESO',
        concepto='DEVOLUCION_RESERVA',
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    total = total_bruto - total_devuelto
    pagina, querystring = paginar_queryset(request, pagos)

    return render(request, 'estancias/historial_pagos.html', {
        'pagos': pagina,
        'pagina': pagina,
        'querystring': querystring,
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
        'pago__reserva__huesped',
    ).filter(fecha__gte=inicio_dia(hoy), fecha__lt=inicio_dia(hoy + timedelta(days=1)))
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
                'pago__reserva__huesped',
            ).all()
        if fecha_desde:
            movimientos = movimientos.filter(fecha__gte=inicio_dia(fecha_desde))
        if fecha_hasta:
            movimientos = movimientos.filter(fecha__lt=inicio_dia(fecha_hasta + timedelta(days=1)))
        if metodo_pago:
            movimientos = movimientos.filter(metodo_pago=metodo_pago)
        if tipo_comprobante:
            movimientos = movimientos.filter(pago__comprobante__tipo=tipo_comprobante)
        if estado:
            movimientos = movimientos.filter(pago__comprobante__estado=estado)

    ingresos = movimientos.filter(tipo='INGRESO').aggregate(total=Sum('monto'))['total'] or 0
    egresos = movimientos.filter(tipo='EGRESO').aggregate(total=Sum('monto'))['total'] or 0
    pagina, querystring = paginar_queryset(request, movimientos)

    return render(request, 'estancias/reporte_caja_diario.html', {
        'movimientos': pagina,
        'pagina': pagina,
        'querystring': querystring,
        'form': form,
        'ingresos': ingresos,
        'egresos': egresos,
        'saldo': ingresos - egresos,
    })
