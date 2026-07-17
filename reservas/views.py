import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from estancias.forms import PagoForm
from estancias.models import CargoEstancia, Estancia, Folio
from estancias.services import recalcular_folio, registrar_adelanto_reserva, sincronizar_cargo_calculado
from habitaciones.models import Habitacion, HabitacionEstadoHistorial, TipoHabitacion
from habitaciones.services import cambiar_estado_habitacion
from reservas.forms import AcompananteFormSet, CancelarReservaForm, CheckinDirectoForm, ClienteFiltroForm, ReservaFiltroForm
from reservas.models import Huesped, Reserva
from reservas.services import (
    aplicar_cotizacion_reserva,
    aplicar_adelantos_al_folio,
    autorizar_prorroga_estancia,
    calcular_tarifa_estadia,
    cancelar_reserva,
    evaluar_cancelacion_reserva,
    evaluar_checkin,
    evaluar_checkout,
    obtener_habitaciones_disponibles,
    obtener_fecha_salida_vigente,
    obtener_panel_reservas_dia,
    liberar_reservas_sin_garantia_vencidas,
    marcar_reserva_no_show,
    validar_ingreso_reserva,
)
from usuarios.auth import ROLES, role_required, usuario_en_rol
from usuarios.pagination import paginar_queryset


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def alertas_operativas(request):
    liberar_reservas_sin_garantia_vencidas()
    panel = obtener_panel_reservas_dia()
    return render(request, 'usuarios/alertas_operativas.html', {
        'panel': panel,
        'puede_operar': usuario_en_rol(request.user, [ROLES['RECEPCIONISTA']]),
    })


def preparar_folio_checkout(estancia, evaluacion, registrar_salida=False):
    if registrar_salida:
        estancia.fecha_checkout = evaluacion['momento']
        estancia.tipo_checkout = evaluacion['tipo']
    estancia.cargo_late_checkout = evaluacion['cargo']
    estancia.politica_cobro_checkout = evaluacion['politica']
    estancia.noches_reservadas = evaluacion['noches_reservadas']
    estancia.noches_reales = evaluacion['noches_reales']
    estancia.monto_estadia_real = evaluacion['monto_estadia_real']
    estancia.cargo_penalidad_salida_anticipada = evaluacion['penalidad_salida_anticipada']
    estancia.precio_final = evaluacion['monto_habitacion']
    estancia.save()

    sincronizar_cargo_calculado(
        estancia,
        tipo='LATE_CHECKOUT',
        concepto=evaluacion['concepto_cargo'],
        monto=evaluacion['cargo'],
    )
    sincronizar_cargo_calculado(
        estancia,
        tipo='PENALIDAD',
        concepto='Penalidad por salida anticipada',
        monto=evaluacion['penalidad_salida_anticipada'],
    )
    sincronizar_cargo_calculado(
        estancia,
        tipo='NOCHE_ADICIONAL',
        concepto='Noches adicionales no autorizadas previamente',
        monto=evaluacion['monto_noches_adicionales'],
        cantidad=evaluacion['noches_adicionales'] or 1,
    )

    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    return recalcular_folio(folio)


def guardar_acompanantes(reserva, formset):
    reserva.acompanantes.all().delete()
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get('DELETE'):
            continue
        if not any(form.cleaned_data.get(campo) for campo in ['num_doc', 'nombres', 'apellidos']):
            continue
        acompanante = form.save(commit=False)
        acompanante.reserva = reserva
        acompanante.save()


def validar_cantidad_acompanantes(reserva, formset):
    acompanantes_validos = 0
    documentos = set()
    errores = []

    for form in formset:
        if not getattr(form, 'cleaned_data', None) or form.cleaned_data.get('DELETE'):
            continue
        if not any(form.cleaned_data.get(campo) for campo in ['num_doc', 'nombres', 'apellidos']):
            continue

        acompanantes_validos += 1
        num_doc = form.cleaned_data.get('num_doc')
        if num_doc:
            if num_doc == reserva.huesped.num_doc:
                form.add_error('num_doc', 'El acompanante no puede tener el mismo documento del huesped principal.')
            if num_doc in documentos:
                form.add_error('num_doc', 'Documento repetido en acompanantes.')
            documentos.add(num_doc)

    max_acompanantes = max(reserva.num_adultos - 1, 0)
    capacidad = reserva.habitacion.tipo.capacidad if reserva.habitacion else 0

    if acompanantes_validos > max_acompanantes:
        errores.append(
            f'La reserva indica {reserva.num_adultos} persona(s). Solo puedes registrar hasta {max_acompanantes} acompanante(s).'
        )

    if reserva.num_adultos > capacidad:
        errores.append(
            f'La habitacion permite maximo {capacidad} persona(s).'
        )

    return not errores and not any(form.errors for form in formset), errores


def construir_rango_mes(anio, mes):
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    dias = [primer_dia + timedelta(days=offset) for offset in range((ultimo_dia - primer_dia).days + 1)]
    return primer_dia, ultimo_dia, dias


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def calendario_ocupacion(request):
    hoy = timezone.localdate()
    try:
        fecha_texto = request.GET.get('fecha')
        fecha_seleccionada = date.fromisoformat(fecha_texto) if fecha_texto else None
        anio = fecha_seleccionada.year if fecha_seleccionada else int(request.GET.get('anio', hoy.year))
        mes = fecha_seleccionada.month if fecha_seleccionada else int(request.GET.get('mes', hoy.month))
        primer_dia, ultimo_dia, dias = construir_rango_mes(anio, mes)
    except ValueError:
        fecha_seleccionada = None
        anio = hoy.year
        mes = hoy.month
        primer_dia, ultimo_dia, dias = construir_rango_mes(anio, mes)

    tipo_id = request.GET.get('tipo')
    piso = request.GET.get('piso')
    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').prefetch_related(
        Prefetch(
            'historial_estados',
            queryset=HabitacionEstadoHistorial.objects.order_by('cambiado_en', 'id'),
            to_attr='historial_calendario',
        )
    ).all().order_by('piso', 'numero')

    if tipo_id:
        habitaciones = habitaciones.filter(tipo_id=tipo_id)
    if piso:
        habitaciones = habitaciones.filter(piso=piso)

    reservas = Reserva.objects.select_related('huesped', 'habitacion', 'estancia').filter(
        habitacion__in=habitaciones,
        # CHECKOUT conserva la ocupacion historica en el calendario aunque la
        # habitacion actualmente ya se encuentre disponible.
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN', 'CHECKOUT'],
        fecha_entrada__lte=ultimo_dia,
        fecha_salida__gt=primer_dia,
    )

    reservas_por_habitacion = {}
    for reserva in reservas:
        reserva.inicio_calendario = reserva.fecha_entrada
        reserva.fin_calendario = reserva.fecha_salida
        if reserva.estado in ['CHECKIN', 'CHECKOUT']:
            try:
                estancia = reserva.estancia
            except Estancia.DoesNotExist:
                estancia = None
            if estancia:
                reserva.inicio_calendario = timezone.localtime(estancia.fecha_checkin).date()
                if estancia.fecha_checkout:
                    fin_real = timezone.localtime(estancia.fecha_checkout).date()
                    reserva.fin_calendario = max(
                        fin_real,
                        reserva.inicio_calendario + timedelta(days=1),
                    )
        reservas_por_habitacion.setdefault(reserva.habitacion_id, []).append(reserva)

    filas = []
    resumen = {
        'disponibles': 0,
        'reservadas': 0,
        'ocupadas': 0,
        'bloqueadas': 0,
    }

    for habitacion in habitaciones:
        celdas = []
        reservas_habitacion = reservas_por_habitacion.get(habitacion.id, [])
        cambios_por_fecha = {}
        for cambio in habitacion.historial_calendario:
            fecha_cambio = timezone.localtime(cambio.cambiado_en).date()
            cambios_por_fecha.setdefault(fecha_cambio, []).append(cambio)
        estado_historico = None
        for dia in dias:
            for cambio in cambios_por_fecha.get(dia, []):
                estado_historico = cambio.estado_nuevo
            reserva_dia = None
            for reserva in reservas_habitacion:
                if reserva.inicio_calendario <= dia < reserva.fin_calendario:
                    reserva_dia = reserva
                    break

            estado = 'DISPONIBLE'
            etiqueta = 'Libre'
            detalle = ''
            reserva_id = None

            # El historial se aplica desde cada transición hasta la siguiente,
            # únicamente para fechas ocurridas. El estado actual no se proyecta
            # sobre días futuros porque todavía pueden existir nuevos cambios.
            if dia <= hoy and estado_historico and (estado_historico != 'DISPONIBLE' or not reserva_dia):
                estado = estado_historico
                etiqueta = dict(Habitacion.ESTADOS).get(estado, estado.title())
                if estado in ['LIMPIEZA', 'MANTENIMIENTO']:
                    resumen['bloqueadas'] += 1
                elif estado == 'OCUPADA':
                    resumen['ocupadas'] += 1
                else:
                    resumen['disponibles'] += 1
                if reserva_dia and estado == 'OCUPADA':
                    detalle = f'{reserva_dia.huesped.nombres} {reserva_dia.huesped.apellidos}'
                    reserva_id = reserva_dia.id
            elif reserva_dia:
                estado = 'OCUPADA' if reserva_dia.estado in ['CHECKIN', 'CHECKOUT'] else 'RESERVADA'
                etiqueta = 'Ocupada' if estado == 'OCUPADA' else 'Reservada'
                detalle = f'{reserva_dia.huesped.nombres} {reserva_dia.huesped.apellidos}'
                reserva_id = reserva_dia.id
                if estado == 'OCUPADA':
                    resumen['ocupadas'] += 1
                else:
                    resumen['reservadas'] += 1
            else:
                resumen['disponibles'] += 1

            celdas.append({
                'dia': dia,
                'estado': estado,
                'etiqueta': etiqueta,
                'detalle': detalle,
                'reserva_id': reserva_id,
            })

        filas.append({
            'habitacion': habitacion,
            'celdas': celdas,
        })

    mes_anterior = primer_dia - timedelta(days=1)
    mes_siguiente = ultimo_dia + timedelta(days=1)
    tipos = Habitacion.objects.values('tipo_id', 'tipo__nombre').distinct().order_by('tipo__nombre')
    pisos = Habitacion.objects.values_list('piso', flat=True).distinct().order_by('piso')

    return render(request, 'usuarios/calendario_ocupacion.html', {
        'dias': dias,
        'filas': filas,
        'resumen': resumen,
        'anio': anio,
        'mes': mes,
        'nombre_mes': primer_dia.strftime('%B').capitalize(),
        'tipos': tipos,
        'pisos': pisos,
        'tipo_id': int(tipo_id) if tipo_id else None,
        'piso_seleccionado': int(piso) if piso else None,
        'mes_anterior': mes_anterior,
        'mes_siguiente': mes_siguiente,
        'hoy': hoy,
        'fecha_seleccionada': fecha_seleccionada or date(anio, mes, 1),
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def lista_reservas(request):
    liberar_reservas_sin_garantia_vencidas()
    reservas = Reserva.objects.select_related(
        'hotel',
        'huesped',
        'habitacion',
        'estancia',
    ).prefetch_related('adelantos').all().order_by('-creado_en')
    resumen = Reserva.objects.aggregate(
        total=Count('id'),
        pendientes=Count('id', filter=Q(estado='PENDIENTE')),
        confirmadas=Count('id', filter=Q(estado='CONFIRMADA')),
        en_casa=Count('id', filter=Q(estado='CHECKIN')),
        finalizadas=Count('id', filter=Q(estado='CHECKOUT')),
        no_show=Count('id', filter=Q(estado='NO_SHOW')),
        canceladas=Count('id', filter=Q(estado='CANCELADA')),
    )
    form = ReservaFiltroForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get('q')
        estado = form.cleaned_data.get('estado')
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        estancia = form.cleaned_data.get('estancia')

        if q:
            reservas = reservas.filter(
                Q(huesped__nombres__icontains=q) |
                Q(huesped__apellidos__icontains=q) |
                Q(huesped__num_doc__icontains=q) |
                Q(habitacion__numero__icontains=q) |
                Q(origen__icontains=q)
            )
        if estado:
            reservas = reservas.filter(estado=estado)
        if fecha_desde:
            reservas = reservas.filter(fecha_entrada__gte=fecha_desde)
        if fecha_hasta:
            reservas = reservas.filter(fecha_salida__lte=fecha_hasta)
        if estancia == 'SIN_CHECKIN':
            reservas = reservas.filter(estancia__isnull=True)
        elif estancia == 'CHECKIN_NORMAL':
            reservas = reservas.filter(estancia__tipo_checkin='NORMAL')
        elif estancia == 'CHECKIN_ANTICIPADO':
            reservas = reservas.filter(estancia__tipo_checkin='ANTICIPADO')
        elif estancia == 'CHECKOUT_NORMAL':
            reservas = reservas.filter(estancia__tipo_checkout='NORMAL')
        elif estancia == 'CHECKOUT_TARDIO':
            reservas = reservas.filter(estancia__tipo_checkout='TARDIO')

    pagina, querystring = paginar_queryset(request, reservas)
    return render(request, 'usuarios/reservas.html', {
        'reservas': pagina,
        'pagina': pagina,
        'querystring': querystring,
        'filtro_form': form,
        'resumen': resumen,
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def detalle_reserva(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'hotel', 'huesped', 'habitacion__tipo', 'estancia__habitacion__tipo',
            'estancia__folio', 'cancelada_por',
        ).prefetch_related(
            'acompanantes', 'historial_estados__cambiado_por',
            'adelantos__metodo_pago', 'adelantos__comprobante',
            'adelantos__movimientos_caja', 'estancia__cargos__producto_servicio',
            'estancia__prorrogas',
        ),
        pk=reserva_id,
    )
    estancia = getattr(reserva, 'estancia', None)
    folio = getattr(estancia, 'folio', None) if estancia else None
    pagos = list(reserva.adelantos.all())
    total_devuelto = sum((pago.total_reembolsado for pago in pagos), 0)
    total_neto = sum((pago.monto_neto for pago in pagos), 0)
    puede_operar = usuario_en_rol(request.user, [ROLES['RECEPCIONISTA']])

    return render(request, 'usuarios/detalle_reserva.html', {
        'reserva': reserva, 'estancia': estancia, 'folio': folio, 'pagos': pagos,
        'total_devuelto': total_devuelto, 'total_neto': total_neto,
        'puede_operar': puede_operar,
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'])
def lista_clientes(request):
    clientes = Huesped.objects.annotate(
        total_reservas=Count('reservas'),
        ultima_reserva=Max('reservas__creado_en'),
        ultimo_checkin=Max('reservas__estancia__fecha_checkin'),
    ).order_by('-ultimo_checkin', '-ultima_reserva', 'apellidos')
    form = ClienteFiltroForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get('q')
        if q:
            clientes = clientes.filter(
                Q(nombres__icontains=q) |
                Q(apellidos__icontains=q) |
                Q(num_doc__icontains=q) |
                Q(email__icontains=q) |
                Q(telefono__icontains=q)
            )

    pagina, querystring = paginar_queryset(request, clientes)
    return render(request, 'usuarios/clientes.html', {
        'clientes': pagina,
        'pagina': pagina,
        'querystring': querystring,
        'filtro_form': form,
    })

@role_required(ROLES['RECEPCIONISTA'])
def checkin_directo(request):
    hoy = timezone.localdate()
    tipos_habitacion = TipoHabitacion.objects.order_by('nombre')

    if request.method == 'POST':
        form = CheckinDirectoForm(request.POST)
        formset = AcompananteFormSet(request.POST, prefix='acompanantes')
        if form.is_valid() and formset.is_valid():
            habitacion = form.cleaned_data['habitacion']
            fecha_salida = form.cleaned_data['fecha_salida']

            reserva_existente = not obtener_habitaciones_disponibles(
                hoy,
                fecha_salida,
                num_personas=form.cleaned_data['num_adultos'],
                hotel_id=habitacion.hotel_id,
            ).filter(pk=habitacion.pk).exists()

            if habitacion.estado != 'DISPONIBLE' or reserva_existente:
                form.add_error('habitacion', 'La habitacion seleccionada ya no esta disponible para esas fechas.')
            else:
                reserva_previa = Reserva(
                    huesped=Huesped(num_doc=form.cleaned_data['num_doc']),
                    habitacion=habitacion,
                    num_adultos=form.cleaned_data['num_adultos'],
                )
                acompanantes_ok, errores_acompanantes = validar_cantidad_acompanantes(reserva_previa, formset)
                if not acompanantes_ok:
                    return render(request, 'usuarios/checkin_directo.html', {
                        'form': form,
                        'formset_acompanantes': formset,
                        'errores_acompanantes': errores_acompanantes,
                        'tipos_habitacion': tipos_habitacion,
                        'hoy': hoy,
                    })

                with transaction.atomic():
                    habitacion = (
                        Habitacion.objects.select_for_update()
                        .select_related('hotel', 'tipo')
                        .get(pk=habitacion.pk)
                    )
                    disponible = obtener_habitaciones_disponibles(
                        hoy,
                        fecha_salida,
                        num_personas=form.cleaned_data['num_adultos'],
                        hotel_id=habitacion.hotel_id,
                    ).filter(pk=habitacion.pk).exists()
                    if not disponible:
                        form.add_error(
                            'habitacion',
                            'La habitacion dejo de estar disponible para toda la estancia. Actualiza la busqueda.'
                        )
                        transaction.set_rollback(True)
                    else:
                        huesped, _ = Huesped.objects.update_or_create(
                            num_doc=form.cleaned_data['num_doc'],
                            defaults={
                                'tipo_doc': form.cleaned_data['tipo_doc'],
                                'nombres': form.cleaned_data['nombres'],
                                'apellidos': form.cleaned_data['apellidos'],
                                'email': form.cleaned_data['email'],
                                'telefono': form.cleaned_data['telefono'],
                                'nacionalidad': form.cleaned_data['nacionalidad'],
                            }
                        )
                        cotizacion = calcular_tarifa_estadia(
                            habitacion.tipo,
                            hoy,
                            fecha_salida,
                            promocion_id=(
                                form.cleaned_data['promocion'].id
                                if form.cleaned_data.get('promocion') else None
                            ),
                        )
                        reserva = Reserva(
                            hotel=habitacion.hotel,
                            huesped=huesped,
                            habitacion=habitacion,
                            fecha_entrada=hoy,
                            fecha_salida=fecha_salida,
                            num_adultos=form.cleaned_data['num_adultos'],
                            estado='CHECKIN',
                            origen=form.cleaned_data['origen'] or 'Walk-in',
                        )
                        aplicar_cotizacion_reserva(reserva, cotizacion)
                        reserva._estado_usuario = request.user
                        reserva._estado_motivo = 'Check-in directo sin reserva previa.'
                        reserva.save()
                        precio_total = reserva.precio_total
                        evaluacion = evaluar_checkin(reserva)

                        cambiar_estado_habitacion(
                            habitacion,
                            'OCUPADA',
                            usuario=request.user,
                            motivo='Check-in directo.',
                        )

                        estancia = Estancia.objects.create(
                            reserva=reserva,
                            habitacion=habitacion,
                            fecha_checkin=evaluacion['momento'],
                            fecha_entrada_programada=reserva.fecha_entrada,
                            fecha_salida_programada=reserva.fecha_salida,
                            precio_final=precio_total,
                            tipo_checkin=evaluacion['tipo'],
                            cargo_early_checkin=evaluacion['cargo'],
                            estado='ACTIVA',
                        )

                        if evaluacion['cargo'] > 0:
                            CargoEstancia.objects.create(
                                estancia=estancia,
                                concepto=evaluacion['concepto_cargo'],
                                monto=evaluacion['cargo'],
                                tipo='EARLY_CHECKIN',
                            )

                        guardar_acompanantes(reserva, formset)

                        folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
                        folio.calcular_totales()
                        folio.save()

                if not form.errors:
                    messages.success(request, f'Check-in directo registrado para la habitacion {habitacion.numero}.')
                    return redirect('estancias_activas')
    else:
        form = CheckinDirectoForm()
        formset = AcompananteFormSet(prefix='acompanantes')

    return render(request, 'usuarios/checkin_directo.html', {
        'form': form,
        'formset_acompanantes': formset,
        'tipos_habitacion': tipos_habitacion,
        'hoy': hoy,
    })


@role_required(ROLES['RECEPCIONISTA'])
def checkin_pendientes(request):
    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo').filter(
        estado__in=['PENDIENTE', 'CONFIRMADA'],
        estancia__isnull=True,
    ).order_by('fecha_entrada', 'habitacion__numero')

    hoy = timezone.localdate()
    for reserva in reservas:
        reserva.ingreso_vencido = hoy >= reserva.fecha_salida

    return render(request, 'usuarios/checkin_pendientes.html', {
        'reservas': reservas,
    })


@role_required(ROLES['RECEPCIONISTA'])
def marcar_no_show(request, reserva_id):
    if request.method != 'POST':
        return redirect('checkin_pendientes')
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    try:
        reserva = marcar_reserva_no_show(reserva, usuario=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(
            request,
            f'Reserva #{reserva.id} marcada como no-show. Adelanto retenido: S/ {reserva.monto_retenido}.',
        )
    return redirect('checkin_pendientes')


@role_required(ROLES['RECEPCIONISTA'])
def pagar_reserva(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo'),
        pk=reserva_id,
    )
    if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
        messages.error(request, 'Esta reserva ya no admite pagos anticipados.')
        return redirect('lista_reservas')

    if request.method == 'POST':
        form = PagoForm(request.POST, reserva=reserva)
        if form.is_valid():
            try:
                pago, comprobante, reserva = registrar_adelanto_reserva(
                    reserva,
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
                if reserva.estado == 'CONFIRMADA':
                    messages.success(
                        request,
                        f'Adelanto completo. Reserva #{reserva.id} confirmada. Comprobante {comprobante.correlativo}.',
                    )
                else:
                    messages.success(request, f'Adelanto registrado. Saldo de garantia: S/ {reserva.saldo_adelanto}.')
                return redirect('pagar_reserva', reserva_id=reserva.id)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
    else:
        form = PagoForm(reserva=reserva) if reserva.saldo_adelanto > 0 else None

    pagos = reserva.adelantos.select_related('metodo_pago', 'comprobante').all()
    return render(request, 'usuarios/pagar_reserva.html', {
        'reserva': reserva,
        'form': form,
        'pagos': pagos,
    })


@role_required(ROLES['RECEPCIONISTA'])
def cancelar_reserva_web(request, reserva_id):
    reserva = get_object_or_404(
        Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo')
        .prefetch_related('adelantos__metodo_pago', 'adelantos__movimientos_caja'),
        pk=reserva_id,
    )
    if reserva.estado not in ['PENDIENTE', 'CONFIRMADA'] or hasattr(reserva, 'estancia'):
        messages.error(request, 'Esta reserva ya no puede cancelarse desde este flujo.')
        return redirect('lista_reservas')

    evaluacion = evaluar_cancelacion_reserva(reserva)
    if request.method == 'POST':
        form = CancelarReservaForm(request.POST)
        if form.is_valid():
            try:
                reserva, evaluacion = cancelar_reserva(
                    reserva,
                    motivo=form.cleaned_data['motivo'],
                    usuario=request.user,
                )
                if evaluacion['monto_reembolsar'] > 0:
                    messages.success(
                        request,
                        f'Reserva #{reserva.id} cancelada. Devolucion registrada: S/ {evaluacion["monto_reembolsar"]}.',
                    )
                elif evaluacion['monto_retenido'] > 0:
                    messages.success(
                        request,
                        f'Reserva #{reserva.id} cancelada. El hotel retuvo S/ {evaluacion["monto_retenido"]}.',
                    )
                else:
                    messages.success(request, f'Reserva #{reserva.id} cancelada sin movimientos de caja.')
                return redirect('detalle_reserva', reserva_id=reserva.id)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
    else:
        form = CancelarReservaForm()

    return render(request, 'usuarios/cancelar_reserva.html', {
        'reserva': reserva,
        'evaluacion': evaluacion,
        'form': form,
    })


@role_required(ROLES['RECEPCIONISTA'])
def checkout_pendientes(request):
    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo', 'estancia__folio').filter(
        estado='CHECKIN',
        estancia__estado='ACTIVA',
    ).order_by('fecha_salida', 'habitacion__numero')

    hoy = timezone.localdate()
    for reserva in reservas:
        reserva.salida_vigente = obtener_fecha_salida_vigente(reserva.estancia)
        reserva.salida_vencida = hoy > reserva.salida_vigente
        reserva.prorrogas_historial = reserva.estancia.prorrogas.select_related('autorizado_por').all()

    return render(request, 'usuarios/checkout_pendientes.html', {
        'reservas': reservas,
        'fecha_minima_prorroga': (hoy + timedelta(days=1)).isoformat(),
    })


@role_required(ROLES['RECEPCIONISTA'])
def autorizar_prorroga(request, reserva_id):
    if request.method != 'POST':
        return redirect('checkout_pendientes')
    reserva = get_object_or_404(
        Reserva.objects.select_related('estancia__habitacion__tipo'),
        pk=reserva_id,
        estado='CHECKIN',
        estancia__estado='ACTIVA',
    )
    try:
        fecha_nueva = date.fromisoformat(request.POST.get('fecha_salida_nueva', ''))
        prorroga = autorizar_prorroga_estancia(
            reserva.estancia,
            fecha_nueva,
            usuario=request.user,
            motivo=request.POST.get('motivo', '').strip(),
        )
        messages.success(
            request,
            f'Prorroga autorizada hasta {prorroga.fecha_salida_nueva:%d/%m/%Y}. '
            f'Cargo agregado: S/ {prorroga.monto}.',
        )
    except (ValueError, ValidationError) as exc:
        mensaje = exc.messages[0] if isinstance(exc, ValidationError) else 'La fecha indicada no es valida.'
        messages.error(request, mensaje)
    return redirect('checkout_pendientes')


@role_required(ROLES['RECEPCIONISTA'])
def caja_recepcion(request):
    folios_consulta = Folio.objects.select_related(
        'estancia__reserva__huesped',
        'estancia__habitacion',
    ).order_by('-estancia__fecha_checkin')

    folios = []
    for folio in folios_consulta:
        folio = recalcular_folio(folio)
        if folio.saldo_pendiente > 0:
            folios.append(folio)

    return render(request, 'usuarios/caja.html', {
        'folios': folios,
    })


def _construir_estado_habitaciones():
    hoy = timezone.localdate()
    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').prefetch_related(
        Prefetch(
            'historial_estados',
            queryset=HabitacionEstadoHistorial.objects.select_related('cambiado_por').order_by('-cambiado_en'),
            to_attr='historial_reciente',
        )
    ).all().order_by('piso', 'numero')
    reservas_hoy = Reserva.objects.select_related('huesped').filter(
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
        fecha_entrada__lte=hoy,
        fecha_salida__gt=hoy,
        habitacion__isnull=False,
    )
    prioridad = {'CHECKIN': 3, 'CONFIRMADA': 2, 'PENDIENTE': 1}
    reserva_por_habitacion = {}
    for reserva in reservas_hoy:
        actual = reserva_por_habitacion.get(reserva.habitacion_id)
        if actual is None or prioridad[reserva.estado] > prioridad[actual.estado]:
            reserva_por_habitacion[reserva.habitacion_id] = reserva

    resumen = {
        'DISPONIBLE': 0,
        'RESERVADA': 0,
        'OCUPADA': 0,
        'LIMPIEZA': 0,
        'MANTENIMIENTO': 0,
    }
    habitaciones_estado = []

    for habitacion in habitaciones:
        reserva = reserva_por_habitacion.get(habitacion.id)
        estado_general = habitacion.estado
        if habitacion.estado == 'DISPONIBLE' and reserva:
            estado_general = 'RESERVADA'
        resumen[estado_general] = resumen.get(estado_general, 0) + 1
        habitaciones_estado.append({
            'habitacion': habitacion,
            'estado_general': estado_general,
            'reserva': reserva,
            'huesped_nombre': (
                f'{reserva.huesped.nombres} {reserva.huesped.apellidos}' if reserva else ''
            ),
        })

    return habitaciones_estado, resumen


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def estado_habitaciones(request):
    habitaciones_estado, resumen = _construir_estado_habitaciones()
    habitaciones = [item['habitacion'] for item in habitaciones_estado]

    return render(request, 'usuarios/estado_habitaciones.html', {
        'habitaciones_estado': habitaciones_estado,
        'resumen': resumen,
        'hoteles': sorted({(habitacion.hotel_id, habitacion.hotel.nombre) for habitacion in habitaciones}),
        'tipos': sorted({(habitacion.tipo_id, habitacion.tipo.nombre) for habitacion in habitaciones}),
        'pisos': sorted({habitacion.piso for habitacion in habitaciones}),
        'habitaciones_seccion': 'plano',
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def estado_habitaciones_datos(request):
    habitaciones_estado, resumen = _construir_estado_habitaciones()
    datos = []
    for item in habitaciones_estado:
        habitacion = item['habitacion']
        reserva = item['reserva']
        datos.append({
            'id': habitacion.id,
            'numero': habitacion.numero,
            'piso': habitacion.piso,
            'hotel_id': habitacion.hotel_id,
            'hotel': habitacion.hotel.nombre,
            'tipo_id': habitacion.tipo_id,
            'tipo': habitacion.tipo.nombre,
            'capacidad': habitacion.tipo.capacidad,
            'estado': item['estado_general'],
            'reserva_id': reserva.id if reserva else None,
            'huesped': item['huesped_nombre'],
            'historial': [
                {
                    'estado_anterior': cambio.estado_anterior or 'INICIAL',
                    'estado_nuevo': cambio.estado_nuevo,
                    'motivo': cambio.motivo,
                    'usuario': cambio.cambiado_por.get_full_name() or cambio.cambiado_por.username
                    if cambio.cambiado_por else 'Sistema',
                    'fecha': timezone.localtime(cambio.cambiado_en).isoformat(),
                }
                for cambio in habitacion.historial_reciente[:10]
            ],
        })

    return JsonResponse({
        'habitaciones': datos,
        'resumen': resumen,
        'actualizado_en': timezone.localtime().isoformat(),
    })


@role_required(ROLES['RECEPCIONISTA'])
def realizar_checkin(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related('habitacion__tipo', 'huesped'), id=reserva_id)

    if reserva.estado != 'CONFIRMADA':
        messages.error(request, 'Primero debe completar el adelanto del 50% para confirmar la reserva.')
        if reserva.estado == 'PENDIENTE':
            return redirect('pagar_reserva', reserva_id=reserva.id)
        return redirect('lista_reservas')

    if reserva.habitacion is None:
        messages.error(request, 'La reserva no tiene una habitacion asignada.')
        return redirect('lista_reservas')

    if hasattr(reserva, 'estancia'):
        messages.error(request, 'Esta reserva ya tiene una estancia registrada.')
        return redirect('lista_reservas')

    evaluacion = evaluar_checkin(reserva)
    errores_ingreso = validar_ingreso_reserva(reserva, evaluacion)
    cotizacion_checkin = calcular_tarifa_estadia(
        reserva.habitacion.tipo, reserva.fecha_entrada, reserva.fecha_salida
    )
    promociones_disponibles = cotizacion_checkin['promociones_disponibles']
    promocion_actual_id = next(
        (
            linea.get('promocion_id') for linea in (reserva.detalle_tarifa or [])
            if linea.get('promocion_id')
        ),
        None,
    )
    acompanantes_iniciales = [
        {
            'tipo_doc': acompanante.tipo_doc,
            'num_doc': acompanante.num_doc,
            'nombres': acompanante.nombres,
            'apellidos': acompanante.apellidos,
            'nacionalidad': acompanante.nacionalidad,
            'parentesco': acompanante.parentesco,
        }
        for acompanante in reserva.acompanantes.all()
    ]

    if request.method != 'POST':
        formset = AcompananteFormSet(initial=acompanantes_iniciales, prefix='acompanantes')
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': [],
            'errores_ingreso': errores_ingreso,
            'promociones_disponibles': promociones_disponibles,
            'promocion_actual_id': promocion_actual_id,
            'error_promocion': '',
        })

    if errores_ingreso:
        for error in errores_ingreso:
            messages.error(request, error)
        return redirect('lista_reservas')

    formset = AcompananteFormSet(request.POST, prefix='acompanantes')
    if not formset.is_valid():
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': [],
            'errores_ingreso': errores_ingreso,
            'promociones_disponibles': promociones_disponibles,
            'promocion_actual_id': promocion_actual_id,
            'error_promocion': '',
        })

    acompanantes_ok, errores_acompanantes = validar_cantidad_acompanantes(reserva, formset)
    if not acompanantes_ok:
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': errores_acompanantes,
            'errores_ingreso': errores_ingreso,
            'promociones_disponibles': promociones_disponibles,
            'promocion_actual_id': promocion_actual_id,
            'error_promocion': '',
        })

    promocion_id = request.POST.get('promocion', '').strip() or None
    try:
        cotizacion_checkin = calcular_tarifa_estadia(
            reserva.habitacion.tipo,
            reserva.fecha_entrada,
            reserva.fecha_salida,
            promocion_id=promocion_id,
        )
    except (ValueError, ValidationError) as exc:
        mensaje = exc.messages[0] if isinstance(exc, ValidationError) else 'La promocion seleccionada no es valida.'
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': [],
            'errores_ingreso': errores_ingreso,
            'promociones_disponibles': promociones_disponibles,
            'promocion_actual_id': promocion_id,
            'error_promocion': mensaje,
        })

    aplicar_cotizacion_reserva(reserva, cotizacion_checkin)
    if reserva.total_adelantado < reserva.monto_adelanto_requerido:
        reserva.estado = 'PENDIENTE'
        reserva._estado_usuario = request.user
        reserva._estado_motivo = 'Garantia insuficiente luego de actualizar la tarifa del check-in.'
        reserva.save()
        messages.warning(
            request,
            f'El precio actualizado requiere completar una garantia de S/ {reserva.monto_adelanto_requerido}.',
        )
        return redirect('pagar_reserva', reserva_id=reserva.id)
    reserva.estado = 'CHECKIN'
    reserva._estado_usuario = request.user
    reserva._estado_motivo = 'Check-in confirmado desde recepcion.'
    reserva.save()
    evaluacion = evaluar_checkin(reserva)

    habitacion = reserva.habitacion
    cambiar_estado_habitacion(
        habitacion,
        'OCUPADA',
        usuario=request.user,
        motivo=f'Check-in de reserva #{reserva.id}.',
    )

    estancia = Estancia.objects.create(
        reserva=reserva,
        habitacion=habitacion,
        fecha_checkin=evaluacion['momento'],
        fecha_entrada_programada=reserva.fecha_entrada,
        fecha_salida_programada=reserva.fecha_salida,
        precio_final=reserva.precio_total,
        tipo_checkin=evaluacion['tipo'],
        cargo_early_checkin=evaluacion['cargo'],
        estado='ACTIVA',
    )

    if evaluacion['cargo'] > 0:
        CargoEstancia.objects.create(
            estancia=estancia,
            concepto=(
                f'Ingreso anticipado: {evaluacion["noches_anticipadas"]} noche(s) adicional(es)'
                if evaluacion['tipo'] == 'ANTICIPADO_FECHA'
                else evaluacion['concepto_cargo']
            ),
            cantidad=max(evaluacion['noches_anticipadas'], 1),
            precio_unitario=evaluacion['cargo'] / max(evaluacion['noches_anticipadas'], 1),
            monto=evaluacion['cargo'],
            tipo=('NOCHE_ADICIONAL' if evaluacion['tipo'] == 'ANTICIPADO_FECHA' else 'EARLY_CHECKIN'),
        )

    guardar_acompanantes(reserva, formset)

    folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
    aplicar_adelantos_al_folio(reserva, folio)
    folio.calcular_totales()
    folio.save()

    if evaluacion['tipo'] in ['ANTICIPADO', 'ANTICIPADO_FECHA']:
        messages.success(request, f'Check-in anticipado registrado. Cargo aplicado: S/ {evaluacion["cargo"]}.')
    else:
        messages.success(request, 'Check-in normal registrado correctamente. La habitacion paso a ocupada.')
    return redirect('lista_reservas')


@role_required(ROLES['RECEPCIONISTA'])
def realizar_checkout(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related('habitacion__tipo', 'huesped'), id=reserva_id)

    if reserva.estado != 'CHECKIN':
        messages.error(request, 'Solo se puede realizar check-out a reservas con check-in realizado.')
        return redirect('lista_reservas')

    try:
        estancia = reserva.estancia
    except Estancia.DoesNotExist:
        messages.error(request, 'No existe una estancia activa para esta reserva.')
        return redirect('lista_reservas')

    evaluacion = evaluar_checkout(reserva, estancia=estancia)
    folio = preparar_folio_checkout(
        estancia,
        evaluacion,
        registrar_salida=False,
    )

    if request.method != 'POST':
        return render(request, 'usuarios/confirmar_checkout.html', {
            'reserva': reserva,
            'estancia': estancia,
            'evaluacion': evaluacion,
            'folio': folio,
        })

    if folio.saldo_pendiente > 0:
        messages.warning(request, f'El folio tiene saldo pendiente de S/ {folio.saldo_pendiente}. Primero debe pasar por caja.')
        return redirect('pagar_folio', folio_id=folio.id)

    estancia.fecha_checkout = evaluacion['momento']
    estancia.tipo_checkout = evaluacion['tipo']
    estancia.estado = 'FINALIZADA'
    estancia.save(update_fields=['fecha_checkout', 'tipo_checkout', 'estado'])

    reserva.estado = 'CHECKOUT'
    reserva._estado_usuario = request.user
    reserva._estado_motivo = 'Check-out completado.'
    reserva.save()

    habitacion = reserva.habitacion
    if habitacion:
        cambiar_estado_habitacion(
            habitacion,
            'LIMPIEZA',
            usuario=request.user,
            motivo=f'Checkout de reserva #{reserva.id}.',
        )

    if evaluacion['tipo'] == 'TARDIO':
        messages.success(request, f'Check-out tardio registrado. Cargo aplicado: S/ {evaluacion["cargo"]}.')
    else:
        messages.success(request, 'Check-out normal registrado correctamente. La habitacion paso a limpieza.')
    return redirect('lista_reservas')
