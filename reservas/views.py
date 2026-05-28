import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from estancias.models import CargoEstancia, Estancia, Folio
from habitaciones.models import Habitacion
from reservas.forms import AcompananteFormSet, CheckinDirectoForm, ClienteFiltroForm, ReservaFiltroForm
from reservas.models import Huesped, Reserva
from reservas.services import evaluar_checkin, evaluar_checkout
from usuarios.auth import ROLES, role_required


def preparar_folio_checkout(estancia, evaluacion):
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

    if evaluacion['cargo'] > 0:
        CargoEstancia.objects.get_or_create(
            estancia=estancia,
            tipo='LATE_CHECKOUT',
            defaults={
                'concepto': 'Late check-out 50% de tarifa',
                'monto': evaluacion['cargo'],
            },
        )

    if evaluacion['penalidad_salida_anticipada'] > 0:
        CargoEstancia.objects.get_or_create(
            estancia=estancia,
            tipo='PENALIDAD',
            defaults={
                'concepto': 'Penalidad por salida anticipada',
                'monto': evaluacion['penalidad_salida_anticipada'],
            },
        )

    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    folio.estado = 'PAGADO' if folio.saldo_pendiente <= 0 else 'PENDIENTE'
    folio.save()
    return folio


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


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'])
def calendario_ocupacion(request):
    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get('anio', hoy.year))
        mes = int(request.GET.get('mes', hoy.month))
        primer_dia, ultimo_dia, dias = construir_rango_mes(anio, mes)
    except ValueError:
        anio = hoy.year
        mes = hoy.month
        primer_dia, ultimo_dia, dias = construir_rango_mes(anio, mes)

    tipo_id = request.GET.get('tipo')
    piso = request.GET.get('piso')
    habitaciones = Habitacion.objects.select_related('tipo', 'hotel').all().order_by('piso', 'numero')

    if tipo_id:
        habitaciones = habitaciones.filter(tipo_id=tipo_id)
    if piso:
        habitaciones = habitaciones.filter(piso=piso)

    reservas = Reserva.objects.select_related('huesped', 'habitacion').filter(
        habitacion__in=habitaciones,
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
        fecha_entrada__lte=ultimo_dia,
        fecha_salida__gt=primer_dia,
    )

    reservas_por_habitacion = {}
    for reserva in reservas:
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
        for dia in dias:
            reserva_dia = None
            for reserva in reservas_habitacion:
                if reserva.fecha_entrada <= dia < reserva.fecha_salida:
                    reserva_dia = reserva
                    break

            estado = 'DISPONIBLE'
            etiqueta = 'Libre'
            detalle = ''
            reserva_id = None

            if habitacion.estado in ['LIMPIEZA', 'MANTENIMIENTO']:
                estado = habitacion.estado
                etiqueta = habitacion.get_estado_display()
                resumen['bloqueadas'] += 1
            elif reserva_dia:
                estado = 'OCUPADA' if reserva_dia.estado == 'CHECKIN' else 'RESERVADA'
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
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'])
def lista_reservas(request):
    reservas = Reserva.objects.select_related(
        'hotel',
        'huesped',
        'habitacion',
        'estancia',
    ).all().order_by('-creado_en')
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

    return render(request, 'usuarios/reservas.html', {
        'reservas': reservas,
        'filtro_form': form,
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

    return render(request, 'usuarios/clientes.html', {
        'clientes': clientes,
        'filtro_form': form,
    })

@role_required(ROLES['RECEPCIONISTA'])
def checkin_directo(request):
    hoy = timezone.localdate()
    habitaciones_disponibles = Habitacion.objects.select_related('hotel', 'tipo').filter(
        estado='DISPONIBLE'
    ).order_by('piso', 'numero')

    if request.method == 'POST':
        form = CheckinDirectoForm(request.POST)
        formset = AcompananteFormSet(request.POST, prefix='acompanantes')
        if form.is_valid() and formset.is_valid():
            habitacion = form.cleaned_data['habitacion']
            fecha_salida = form.cleaned_data['fecha_salida']

            reserva_existente = Reserva.objects.filter(
                habitacion=habitacion,
                estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
                fecha_entrada__lt=fecha_salida,
                fecha_salida__gt=hoy,
            ).exists()

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
                        'habitaciones_disponibles': habitaciones_disponibles,
                    })

                with transaction.atomic():
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
                    noches = max((fecha_salida - hoy).days, 1)
                    precio_total = habitacion.tipo.precio_base * noches
                    reserva = Reserva.objects.create(
                        hotel=habitacion.hotel,
                        huesped=huesped,
                        habitacion=habitacion,
                        fecha_entrada=hoy,
                        fecha_salida=fecha_salida,
                        num_adultos=form.cleaned_data['num_adultos'],
                        estado='CHECKIN',
                        precio_total=precio_total,
                        origen=form.cleaned_data['origen'] or 'Walk-in',
                    )
                    evaluacion = evaluar_checkin(reserva)

                    habitacion.estado = 'OCUPADA'
                    habitacion.save()

                    estancia = Estancia.objects.create(
                        reserva=reserva,
                        habitacion=habitacion,
                        fecha_checkin=evaluacion['momento'],
                        precio_final=precio_total,
                        tipo_checkin=evaluacion['tipo'],
                        cargo_early_checkin=evaluacion['cargo'],
                        estado='ACTIVA',
                    )

                    if evaluacion['cargo'] > 0:
                        CargoEstancia.objects.create(
                            estancia=estancia,
                            concepto='Early check-in 5% de tarifa',
                            monto=evaluacion['cargo'],
                            tipo='EARLY_CHECKIN',
                        )

                    guardar_acompanantes(reserva, formset)

                    folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
                    folio.calcular_totales()
                    folio.save()

                messages.success(request, f'Check-in directo registrado para la habitacion {habitacion.numero}.')
                return redirect('estancias_activas')
    else:
        form = CheckinDirectoForm()
        formset = AcompananteFormSet(prefix='acompanantes')

    return render(request, 'usuarios/checkin_directo.html', {
        'form': form,
        'formset_acompanantes': formset,
        'habitaciones_disponibles': habitaciones_disponibles,
    })


@role_required(ROLES['RECEPCIONISTA'])
def checkin_pendientes(request):
    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo').filter(
        estado__in=['PENDIENTE', 'CONFIRMADA'],
        estancia__isnull=True,
    ).order_by('fecha_entrada', 'habitacion__numero')

    return render(request, 'usuarios/checkin_pendientes.html', {
        'reservas': reservas,
    })


@role_required(ROLES['RECEPCIONISTA'])
def checkout_pendientes(request):
    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__tipo', 'estancia__folio').filter(
        estado='CHECKIN',
        estancia__estado='ACTIVA',
    ).order_by('fecha_salida', 'habitacion__numero')

    return render(request, 'usuarios/checkout_pendientes.html', {
        'reservas': reservas,
    })


@role_required(ROLES['RECEPCIONISTA'])
def caja_recepcion(request):
    folios = Folio.objects.select_related(
        'estancia__reserva__huesped',
        'estancia__habitacion',
    ).filter(estado='PENDIENTE').order_by('-estancia__fecha_checkin')

    for folio in folios:
        folio.calcular_totales()
        folio.save()

    return render(request, 'usuarios/caja.html', {
        'folios': folios,
    })


@role_required(ROLES['RECEPCIONISTA'], ROLES['GERENCIA'])
def estado_habitaciones(request):
    hoy = timezone.localdate()
    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('piso', 'numero')
    habitaciones_reservadas = set(
        Reserva.objects.filter(
            estado__in=['PENDIENTE', 'CONFIRMADA'],
            fecha_entrada__lte=hoy,
            fecha_salida__gt=hoy,
            habitacion__isnull=False,
        ).values_list('habitacion_id', flat=True)
    )

    resumen = {
        'DISPONIBLE': 0,
        'RESERVADA': 0,
        'OCUPADA': 0,
        'LIMPIEZA': 0,
        'MANTENIMIENTO': 0,
    }
    habitaciones_estado = []

    for habitacion in habitaciones:
        estado_general = habitacion.estado
        if habitacion.estado == 'DISPONIBLE' and habitacion.id in habitaciones_reservadas:
            estado_general = 'RESERVADA'
        resumen[estado_general] = resumen.get(estado_general, 0) + 1
        habitaciones_estado.append({
            'habitacion': habitacion,
            'estado_general': estado_general,
        })

    return render(request, 'usuarios/estado_habitaciones.html', {
        'habitaciones_estado': habitaciones_estado,
        'resumen': resumen,
    })


@role_required(ROLES['RECEPCIONISTA'])
def realizar_checkin(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related('habitacion__tipo', 'huesped'), id=reserva_id)

    if reserva.estado in ['CHECKIN', 'CHECKOUT', 'CANCELADA']:
        messages.error(request, 'No se puede realizar check-in a esta reserva.')
        return redirect('lista_reservas')

    if reserva.habitacion is None:
        messages.error(request, 'La reserva no tiene una habitacion asignada.')
        return redirect('lista_reservas')

    if hasattr(reserva, 'estancia'):
        messages.error(request, 'Esta reserva ya tiene una estancia registrada.')
        return redirect('lista_reservas')

    evaluacion = evaluar_checkin(reserva)
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
        })

    formset = AcompananteFormSet(request.POST, prefix='acompanantes')
    if not formset.is_valid():
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': [],
        })

    acompanantes_ok, errores_acompanantes = validar_cantidad_acompanantes(reserva, formset)
    if not acompanantes_ok:
        return render(request, 'usuarios/confirmar_checkin.html', {
            'reserva': reserva,
            'evaluacion': evaluacion,
            'formset_acompanantes': formset,
            'errores_acompanantes': errores_acompanantes,
        })

    reserva.estado = 'CHECKIN'
    reserva.save()

    habitacion = reserva.habitacion
    habitacion.estado = 'OCUPADA'
    habitacion.save()

    estancia = Estancia.objects.create(
        reserva=reserva,
        habitacion=habitacion,
        fecha_checkin=evaluacion['momento'],
        precio_final=reserva.precio_total,
        tipo_checkin=evaluacion['tipo'],
        cargo_early_checkin=evaluacion['cargo'],
        estado='ACTIVA',
    )

    if evaluacion['cargo'] > 0:
        CargoEstancia.objects.create(
            estancia=estancia,
            concepto='Early check-in 5% de tarifa',
            monto=evaluacion['cargo'],
            tipo='EARLY_CHECKIN',
        )

    guardar_acompanantes(reserva, formset)

    folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
    folio.calcular_totales()
    folio.save()

    if evaluacion['tipo'] == 'ANTICIPADO':
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
    folio = preparar_folio_checkout(estancia, evaluacion)

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

    estancia.estado = 'FINALIZADA'
    estancia.save()

    reserva.estado = 'CHECKOUT'
    reserva.save()

    habitacion = reserva.habitacion
    if habitacion:
        habitacion.estado = 'LIMPIEZA'
        habitacion.save()

    if evaluacion['tipo'] == 'TARDIO':
        messages.success(request, f'Check-out tardio registrado. Cargo aplicado: S/ {evaluacion["cargo"]}.')
    else:
        messages.success(request, 'Check-out normal registrado correctamente. La habitacion paso a limpieza.')
    return redirect('lista_reservas')
