from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from habitaciones.models import Habitacion
from reservas.models import Promocion, Reserva, Tarifa
from usuarios.auditoria import registrar_evento


HORA_CHECKIN = time(15, 0)
HORA_CHECKOUT = time(12, 0)
HORAS_ALERTA_GARANTIA = 6


def porcentaje_texto(valor):
    return format(Decimal(valor).normalize(), 'f')


def validar_rango_reserva(fecha_entrada, fecha_salida):
    if not fecha_entrada or not fecha_salida:
        raise ValidationError('Las fechas de entrada y salida son obligatorias.')
    if fecha_salida <= fecha_entrada:
        raise ValidationError('La fecha de salida debe ser posterior a la fecha de entrada.')


def calcular_tarifa_estadia(tipo_habitacion, fecha_entrada, fecha_salida, *, promocion_id=None):
    """Calcula tarifa y mejor promocion vigente por cada noche de la estancia."""
    validar_rango_reserva(fecha_entrada, fecha_salida)
    tarifas = list(
        Tarifa.objects.filter(
            tipo_habitacion=tipo_habitacion,
            fecha_inicio__lt=fecha_salida,
            fecha_fin__gte=fecha_entrada,
        ).order_by('fecha_inicio', 'id')
    )
    promociones = list(
        Promocion.objects.filter(
            Q(tipo_habitacion=tipo_habitacion) | Q(tipo_habitacion__isnull=True),
            activo=True,
            fecha_inicio__lt=fecha_salida,
            fecha_fin__gte=fecha_entrada,
        ).order_by('id')
    )
    promocion_seleccionada = None
    if promocion_id:
        promocion_seleccionada = next(
            (promocion for promocion in promociones if promocion.id == int(promocion_id)),
            None,
        )
        if not promocion_seleccionada:
            raise ValidationError(
                'La promocion seleccionada no esta activa o no corresponde al tipo y fechas solicitadas.'
            )

    desglose = []
    total = Decimal('0.00')
    total_sin_descuento = Decimal('0.00')
    descuento_total = Decimal('0.00')
    promociones_usadas = {}
    noche = fecha_entrada
    while noche < fecha_salida:
        vigentes = [tarifa for tarifa in tarifas if tarifa.fecha_inicio <= noche <= tarifa.fecha_fin]
        if len(vigentes) > 1:
            raise ValidationError(
                f'Existe mas de una tarifa vigente para {tipo_habitacion.nombre} el {noche:%d/%m/%Y}.'
            )

        tarifa = vigentes[0] if vigentes else None
        precio_original = redondear_monto(tarifa.precio_noche if tarifa else tipo_habitacion.precio_base)
        vigentes_promocion = [
            promocion for promocion in promociones
            if promocion.fecha_inicio <= noche <= promocion.fecha_fin
        ]
        if promocion_seleccionada:
            promocion = promocion_seleccionada if promocion_seleccionada in vigentes_promocion else None
        else:
            promocion = max(
                vigentes_promocion,
                key=lambda item: (
                    item.porcentaje_descuento,
                    item.tipo_habitacion_id is not None,
                    -item.id,
                ),
            ) if vigentes_promocion else None
        descuento = redondear_monto(
            precio_original * promocion.porcentaje_descuento / Decimal('100')
        ) if promocion else Decimal('0.00')
        precio = redondear_monto(precio_original - descuento)
        desglose.append({
            'fecha': noche,
            'tarifa_id': tarifa.id if tarifa else None,
            'tarifa_nombre': tarifa.nombre if tarifa else 'Tarifa base',
            'precio_original': precio_original,
            'promocion_id': promocion.id if promocion else None,
            'promocion_nombre': promocion.nombre if promocion else '',
            'porcentaje_descuento': promocion.porcentaje_descuento if promocion else Decimal('0.00'),
            'descuento': descuento,
            'precio_noche': precio,
        })
        total_sin_descuento += precio_original
        descuento_total += descuento
        total += precio
        if promocion:
            promociones_usadas[promocion.id] = {
                'id': promocion.id,
                'nombre': promocion.nombre,
                'porcentaje_descuento': promocion.porcentaje_descuento,
            }
        noche += timedelta(days=1)

    return {
        'noches': len(desglose),
        'precio_sin_descuento': redondear_monto(total_sin_descuento),
        'descuento_total': redondear_monto(descuento_total),
        'precio_total': redondear_monto(total),
        'promociones_aplicadas': list(promociones_usadas.values()),
        'promociones_disponibles': [
            {
                'id': promocion.id,
                'nombre': promocion.nombre,
                'porcentaje_descuento': promocion.porcentaje_descuento,
                'fecha_inicio': promocion.fecha_inicio,
                'fecha_fin': promocion.fecha_fin,
                'tipo_habitacion_id': promocion.tipo_habitacion_id,
            }
            for promocion in promociones
        ],
        'desglose': desglose,
    }


def aplicar_cotizacion_reserva(reserva, cotizacion):
    """Copia el precio acordado a la reserva en un formato estable para auditoria."""
    reserva.precio_sin_descuento = cotizacion['precio_sin_descuento']
    reserva.descuento_promocion = cotizacion['descuento_total']
    reserva.precio_total = cotizacion['precio_total']
    from estancias.models import ConfiguracionCobro

    configuracion = ConfiguracionCobro.actual()
    es_nueva = reserva.pk is None
    if es_nueva:
        reserva.porcentaje_adelanto = configuracion.porcentaje_garantia_reserva
        reserva.porcentaje_igv = configuracion.porcentaje_igv
        reserva.porcentaje_early_checkin = configuracion.porcentaje_early_checkin
        reserva.porcentaje_late_checkout = configuracion.porcentaje_late_checkout
    reserva.monto_adelanto_requerido = redondear_monto(
        reserva.precio_total * reserva.porcentaje_adelanto / Decimal('100')
    )
    if not reserva.fecha_limite_pago:
        reserva.fecha_limite_pago = timezone.now() + timedelta(
            hours=configuracion.horas_plazo_pago_garantia
        )
    reserva.detalle_tarifa = [
        {
            'fecha': linea['fecha'].isoformat(),
            'tarifa_id': linea['tarifa_id'],
            'tarifa_nombre': linea['tarifa_nombre'],
            'precio_original': str(linea['precio_original']),
            'promocion_id': linea['promocion_id'],
            'promocion_nombre': linea['promocion_nombre'],
            'porcentaje_descuento': str(linea['porcentaje_descuento']),
            'descuento': str(linea['descuento']),
            'precio_noche': str(linea['precio_noche']),
        }
        for linea in cotizacion['desglose']
    ]
    if not reserva.politica_cobro_checkout:
        reserva.politica_cobro_checkout = configuracion.politica_checkout
        reserva.porcentaje_penalidad_salida_anticipada = (
            configuracion.porcentaje_penalidad_salida_anticipada
        )
        reserva.horas_cancelacion_gratuita = configuracion.horas_cancelacion_gratuita
        reserva.porcentaje_retencion_cancelacion_tardia = (
            configuracion.porcentaje_retencion_cancelacion_tardia
        )
    return reserva


def aplicar_adelantos_al_folio(reserva, folio):
    """Aplica al folio los pagos anticipados sin perder su vinculo de origen."""
    from estancias.models import Pago

    Pago.objects.filter(
        reserva=reserva,
        folio__isnull=True,
        estado='APROBADO',
    ).update(folio=folio)
    return folio


def calcular_periodo_segun_precio_acordado(reserva, fecha_entrada, fecha_salida):
    """Usa el snapshot de la reserva; cae al motor vigente para registros antiguos."""
    validar_rango_reserva(fecha_entrada, fecha_salida)
    detalle = {linea.get('fecha'): linea for linea in (reserva.detalle_tarifa or [])}
    fechas = []
    noche = fecha_entrada
    while noche < fecha_salida:
        fechas.append(noche.isoformat())
        noche += timedelta(days=1)
    if fechas and all(fecha in detalle for fecha in fechas):
        return redondear_monto(sum(
            (Decimal(detalle[fecha]['precio_noche']) for fecha in fechas),
            Decimal('0.00'),
        ))
    return calcular_tarifa_estadia(reserva.habitacion.tipo, fecha_entrada, fecha_salida)['precio_total']


def obtener_habitaciones_disponibles(
    fecha_entrada,
    fecha_salida,
    *,
    tipo_id=None,
    num_personas=None,
    hotel_id=None,
):
    """Retorna un queryset disponible usando la misma regla para web y API."""
    validar_rango_reserva(fecha_entrada, fecha_salida)
    liberar_reservas_sin_garantia_vencidas()
    reservas_solapadas = Reserva.objects.filter(
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
        fecha_entrada__lt=fecha_salida,
        fecha_salida__gt=fecha_entrada,
    ).values_list('habitacion_id', flat=True)

    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').filter(
        estado='DISPONIBLE',
    ).exclude(id__in=reservas_solapadas)

    if tipo_id:
        habitaciones = habitaciones.filter(tipo_id=tipo_id)
    if num_personas:
        habitaciones = habitaciones.filter(tipo__capacidad__gte=num_personas)
    if hotel_id:
        habitaciones = habitaciones.filter(hotel_id=hotel_id)

    return habitaciones.order_by('hotel__nombre', 'piso', 'numero')


def liberar_reservas_sin_garantia_vencidas(momento=None):
    """Cancela reservas que no completaron la garantia dentro de su plazo."""
    momento = momento or timezone.now()
    procesadas = []
    with transaction.atomic():
        vencidas = list(
            Reserva.objects.select_for_update().filter(
                estado='PENDIENTE',
                fecha_limite_pago__isnull=False,
                fecha_limite_pago__lt=momento,
            ).prefetch_related('adelantos__movimientos_caja')
        )
        for reserva in vencidas:
            reserva.estado = 'CANCELADA'
            reserva._estado_motivo = 'Plazo de pago de garantia vencido.'
            reserva.tipo_cancelacion = 'VENCIMIENTO_PAGO'
            reserva.motivo_cancelacion = 'Plazo de pago de garantia vencido.'
            reserva.cancelada_en = momento
            reserva.monto_retenido = reserva.total_adelantado
            reserva.save(update_fields=[
                'estado', 'tipo_cancelacion', 'motivo_cancelacion', 'cancelada_en', 'monto_retenido'
            ])
            procesadas.append((reserva.id, reserva.monto_retenido))
    for reserva_id, monto in procesadas:
        registrar_evento(
            'reserva_garantia_vencida',
            reserva_id=reserva_id,
            estado_nuevo='CANCELADA',
            monto=monto,
            resultado='procesada',
        )
    return len(procesadas)


def _aplicar_no_show(reserva, *, usuario=None):
    monto_retenido = reserva.total_adelantado
    reserva.estado = 'NO_SHOW'
    reserva._estado_usuario = usuario
    reserva._estado_motivo = 'Reserva vencida sin llegada del huesped.'
    reserva.monto_retenido = monto_retenido
    reserva.save(update_fields=['estado', 'monto_retenido'])
    return monto_retenido


def marcar_reserva_no_show(reserva, *, fecha=None, usuario=None):
    fecha = fecha or timezone.localdate()
    with transaction.atomic():
        reserva = (
            Reserva.objects.select_for_update()
            .prefetch_related('adelantos__movimientos_caja')
            .get(pk=reserva.pk)
        )
        if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
            raise ValidationError('La reserva ya no puede marcarse como no-show.')
        if hasattr(reserva, 'estancia'):
            raise ValidationError('La reserva ya tiene una estancia y no puede marcarse como no-show.')
        if fecha < reserva.fecha_salida:
            raise ValidationError('Solo se puede marcar no-show cuando la reserva ya vencio.')
        monto_retenido = _aplicar_no_show(reserva, usuario=usuario)
    registrar_evento(
        'reserva_no_show',
        usuario=usuario,
        reserva_id=reserva.id,
        estado_nuevo='NO_SHOW',
        monto=monto_retenido,
        resultado='procesada',
    )
    return reserva


def marcar_reservas_no_show_vencidas(fecha=None):
    """Marca ausencias cuyo periodo reservado ya finalizo; es seguro repetirlo."""
    fecha = fecha or timezone.localdate()
    procesadas = []
    with transaction.atomic():
        reservas = list(
            Reserva.objects.select_for_update(of=('self',)).filter(
                estado__in=['PENDIENTE', 'CONFIRMADA'],
                estancia__isnull=True,
                fecha_salida__lte=fecha,
            ).prefetch_related('adelantos__movimientos_caja')
        )
        for reserva in reservas:
            monto = _aplicar_no_show(reserva)
            procesadas.append((reserva.id, monto))
    for reserva_id, monto in procesadas:
        registrar_evento(
            'reserva_no_show',
            reserva_id=reserva_id,
            estado_nuevo='NO_SHOW',
            monto=monto,
            resultado='procesada',
        )
    return len(procesadas)


def evaluar_cancelacion_reserva(reserva, momento=None):
    """Calcula reembolso y retencion usando la politica guardada en la reserva."""
    momento = timezone.localtime(momento or timezone.now())
    entrada = timezone.make_aware(datetime.combine(reserva.fecha_entrada, HORA_CHECKIN))
    entrada = timezone.localtime(entrada)
    horas_anticipacion = Decimal(str((entrada - momento).total_seconds() / 3600))
    pagos = list(reserva.adelantos.filter(estado='APROBADO').prefetch_related('movimientos_caja'))
    pagado_neto = redondear_monto(sum((pago.monto_neto for pago in pagos), Decimal('0.00')))
    dentro_plazo = horas_anticipacion >= Decimal(reserva.horas_cancelacion_gratuita)
    porcentaje_retencion = (
        Decimal('0.00')
        if dentro_plazo
        else Decimal(reserva.porcentaje_retencion_cancelacion_tardia)
    )
    monto_retenido = redondear_monto(pagado_neto * porcentaje_retencion / Decimal('100'))
    monto_reembolsar = redondear_monto(pagado_neto - monto_retenido)
    if pagado_neto <= 0:
        tipo = 'SIN_PAGO'
    elif dentro_plazo:
        tipo = 'GRATUITA'
    else:
        tipo = 'TARDIA'
    return {
        'tipo': tipo,
        'dentro_plazo': dentro_plazo,
        'horas_anticipacion': max(horas_anticipacion, Decimal('0.00')).quantize(Decimal('0.01')),
        'horas_cancelacion_gratuita': reserva.horas_cancelacion_gratuita,
        'porcentaje_retencion': porcentaje_retencion,
        'pagado_neto': pagado_neto,
        'monto_reembolsar': monto_reembolsar,
        'monto_retenido': monto_retenido,
    }


def cancelar_reserva(reserva, *, motivo, usuario=None, momento=None):
    """Cancela una reserva y registra devoluciones como egresos de caja auditables."""
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise ValidationError('Ingresa un motivo de cancelacion de al menos 5 caracteres.')

    from estancias.models import MovimientoCaja, Pago
    from django.db import transaction

    with transaction.atomic():
        reserva = Reserva.objects.select_for_update().get(pk=reserva.pk)
        if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
            raise ValidationError('Solo se pueden cancelar reservas pendientes o confirmadas.')
        if hasattr(reserva, 'estancia'):
            raise ValidationError('La reserva ya tiene estancia; debe gestionarse mediante checkout.')

        pagos = list(
            Pago.objects.select_for_update()
            .filter(reserva=reserva, estado='APROBADO')
            .select_related('metodo_pago')
            .prefetch_related('movimientos_caja')
            .order_by('creado_en', 'id')
        )
        evaluacion = evaluar_cancelacion_reserva(reserva, momento=momento)
        pendiente_reembolso = evaluacion['monto_reembolsar']
        for pago in pagos:
            if pendiente_reembolso <= 0:
                break
            disponible = pago.monto_neto
            monto = min(disponible, pendiente_reembolso)
            if monto <= 0:
                continue
            MovimientoCaja.objects.create(
                pago=pago,
                tipo='EGRESO',
                concepto='DEVOLUCION_RESERVA',
                monto=monto,
                metodo_pago=pago.metodo_pago,
                numero_operacion=pago.numero_operacion,
                usuario_responsable=usuario,
                observacion=f'Devolucion por cancelacion de reserva #{reserva.id}: {motivo}',
            )
            pendiente_reembolso = redondear_monto(pendiente_reembolso - monto)

        reserva.estado = 'CANCELADA'
        reserva._estado_usuario = usuario
        reserva._estado_motivo = motivo
        reserva.tipo_cancelacion = evaluacion['tipo']
        reserva.motivo_cancelacion = motivo
        reserva.cancelada_en = momento or timezone.now()
        reserva.cancelada_por = usuario
        reserva.monto_reembolsado = evaluacion['monto_reembolsar']
        reserva.monto_retenido = evaluacion['monto_retenido']
        reserva.save(update_fields=[
            'estado', 'tipo_cancelacion', 'motivo_cancelacion', 'cancelada_en',
            'cancelada_por', 'monto_reembolsado', 'monto_retenido',
        ])
        return reserva, evaluacion


def redondear_monto(monto):
    return monto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def obtener_noches(reserva):
    return max((reserva.fecha_salida - reserva.fecha_entrada).days, 1)


def obtener_noches_reales(fecha_checkin, fecha_checkout):
    checkin = timezone.localtime(fecha_checkin)
    checkout = timezone.localtime(fecha_checkout)
    noches = (checkout.date() - checkin.date()).days
    return max(noches, 1)


def obtener_tarifa_noche(reserva):
    if reserva.precio_total and reserva.precio_total > 0:
        return redondear_monto(reserva.precio_total / Decimal(obtener_noches(reserva)))

    if reserva.habitacion and reserva.habitacion.tipo:
        return redondear_monto(reserva.habitacion.tipo.precio_base)

    return Decimal('0.00')


def evaluar_checkin(reserva, momento=None):
    momento = timezone.localtime(momento or timezone.now())
    tarifa_noche = obtener_tarifa_noche(reserva)
    fecha_real = momento.date()
    noches_anticipadas = max((reserva.fecha_entrada - fecha_real).days, 0)
    desglose_anticipado = []

    if fecha_real < reserva.fecha_entrada:
        tipo = 'ANTICIPADO_FECHA'
        cotizacion = calcular_tarifa_estadia(reserva.habitacion.tipo, fecha_real, reserva.fecha_entrada)
        cargo = cotizacion['precio_total']
        desglose_anticipado = cotizacion['desglose']
    elif fecha_real == reserva.fecha_entrada and momento.time() < HORA_CHECKIN:
        tipo = 'ANTICIPADO'
        porcentaje_early = Decimal(reserva.porcentaje_early_checkin) / Decimal('100')
        cargo = redondear_monto(tarifa_noche * porcentaje_early)
    elif fecha_real > reserva.fecha_entrada:
        tipo = 'LLEGADA_TARDIA'
        cargo = Decimal('0.00')
    else:
        tipo = 'NORMAL'
        cargo = Decimal('0.00')

    return {
        'momento': momento,
        'hora_limite': HORA_CHECKIN,
        'tipo': tipo,
        'cargo': cargo,
        'tarifa_noche': tarifa_noche,
        'porcentaje': reserva.porcentaje_early_checkin if tipo == 'ANTICIPADO' else Decimal('0.00'),
        'concepto_cargo': (
            f'Early check-in {porcentaje_texto(reserva.porcentaje_early_checkin)}% de tarifa'
            if tipo == 'ANTICIPADO' else ''
        ),
        'noches_anticipadas': noches_anticipadas,
        'desglose_anticipado': desglose_anticipado,
        'permitido': fecha_real < reserva.fecha_salida,
        'mensaje_bloqueo': (
            'La reserva ya alcanzo su fecha de salida. Debe marcarse como no-show o crear una nueva reserva.'
            if fecha_real >= reserva.fecha_salida else ''
        ),
    }


def conflictos_para_periodo(reserva, fecha_entrada, fecha_salida):
    return Reserva.objects.select_related('huesped').filter(
        habitacion_id=reserva.habitacion_id,
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
        fecha_entrada__lt=fecha_salida,
        fecha_salida__gt=fecha_entrada,
    ).exclude(pk=reserva.pk)


def validar_ingreso_reserva(reserva, evaluacion=None):
    evaluacion = evaluacion or evaluar_checkin(reserva)
    errores = []
    if not evaluacion['permitido']:
        errores.append(evaluacion['mensaje_bloqueo'])
    if reserva.habitacion.estado != 'DISPONIBLE':
        errores.append(
            f'No se puede hacer check-in: la habitacion esta {reserva.habitacion.get_estado_display().lower()}.'
        )
    if evaluacion['tipo'] == 'ANTICIPADO_FECHA':
        conflictos = conflictos_para_periodo(
            reserva,
            evaluacion['momento'].date(),
            reserva.fecha_entrada,
        )
        if conflictos.exists():
            errores.append('La habitacion tiene otra reserva durante los dias de ingreso anticipado.')
    return errores


def obtener_fecha_salida_vigente(estancia):
    ultima = estancia.prorrogas.order_by('-fecha_salida_nueva').first()
    return (
        ultima.fecha_salida_nueva
        if ultima else estancia.fecha_salida_programada or estancia.reserva.fecha_salida
    )


def evaluar_checkout(reserva, estancia=None, momento=None):
    from estancias.models import ConfiguracionCobro

    momento = timezone.localtime(momento or timezone.now())
    tarifa_noche = obtener_tarifa_noche(reserva)
    fecha_salida_vigente = obtener_fecha_salida_vigente(estancia) if estancia else reserva.fecha_salida
    es_prorroga_no_autorizada = momento.date() > fecha_salida_vigente
    es_tardio = momento.date() == fecha_salida_vigente and momento.time() > HORA_CHECKOUT
    porcentaje_late = Decimal(reserva.porcentaje_late_checkout) / Decimal('100')
    cargo = redondear_monto(tarifa_noche * porcentaje_late) if es_tardio else Decimal('0.00')
    cotizacion_extra = (
        calcular_tarifa_estadia(reserva.habitacion.tipo, fecha_salida_vigente, momento.date())
        if es_prorroga_no_autorizada else {'noches': 0, 'precio_total': Decimal('0.00'), 'desglose': []}
    )
    conflictos_sobreestadia = list(
        conflictos_para_periodo(reserva, fecha_salida_vigente, momento.date()).values(
            'id', 'fecha_entrada', 'fecha_salida', 'huesped__nombres', 'huesped__apellidos'
        )
    ) if es_prorroga_no_autorizada else []
    config = ConfiguracionCobro.actual()
    politica_cobro = reserva.politica_cobro_checkout or config.politica_checkout
    porcentaje_penalidad = (
        reserva.porcentaje_penalidad_salida_anticipada
        if reserva.politica_cobro_checkout
        else config.porcentaje_penalidad_salida_anticipada
    )
    noches_reservadas = obtener_noches(reserva)
    noches_reales = obtener_noches_reales(estancia.fecha_checkin, momento) if estancia else noches_reservadas
    entrada_real = timezone.localtime(estancia.fecha_checkin).date() if estancia else reserva.fecha_entrada
    inicio_usado = max(entrada_real, reserva.fecha_entrada)
    fin_usado = min(momento.date(), reserva.fecha_salida)
    if fin_usado <= inicio_usado and inicio_usado < reserva.fecha_salida:
        fin_usado = inicio_usado + timedelta(days=1)
    if fin_usado > inicio_usado:
        monto_estadia_real = calcular_periodo_segun_precio_acordado(
            reserva, inicio_usado, fin_usado
        )
        noches_reservadas_usadas = (fin_usado - inicio_usado).days
    else:
        monto_estadia_real = Decimal('0.00')
        noches_reservadas_usadas = 0
    monto_reserva_completa = redondear_monto(reserva.precio_total)
    noches_no_usadas = max(noches_reservadas - noches_reservadas_usadas, 0)
    monto_no_usado = (
        calcular_periodo_segun_precio_acordado(reserva, fin_usado, reserva.fecha_salida)
        if fin_usado < reserva.fecha_salida else Decimal('0.00')
    )
    penalidad = Decimal('0.00')

    if politica_cobro == 'RESERVA_COMPLETA':
        monto_habitacion = monto_reserva_completa
    elif politica_cobro == 'ESTADIA_REAL_PENALIDAD':
        porcentaje = porcentaje_penalidad / Decimal('100')
        penalidad = redondear_monto(monto_no_usado * porcentaje)
        monto_habitacion = monto_estadia_real
    else:
        monto_habitacion = monto_estadia_real

    return {
        'momento': momento,
        'hora_limite': HORA_CHECKOUT,
        'tipo': 'PRORROGA' if es_prorroga_no_autorizada else ('TARDIO' if es_tardio else 'NORMAL'),
        'cargo': cargo,
        'tarifa_noche': tarifa_noche,
        'porcentaje': reserva.porcentaje_late_checkout,
        'concepto_cargo': (
            f'Late check-out {porcentaje_texto(reserva.porcentaje_late_checkout)}% de tarifa'
        ),
        'politica': politica_cobro,
        'politica_nombre': dict(Reserva.POLITICA_COBRO_CHOICES)[politica_cobro],
        'noches_reservadas': noches_reservadas,
        'noches_reales': noches_reales,
        'noches_no_usadas': noches_no_usadas,
        'monto_estadia_real': monto_estadia_real,
        'monto_reserva_completa': monto_reserva_completa,
        'monto_habitacion': redondear_monto(monto_habitacion),
        'penalidad_salida_anticipada': penalidad,
        'porcentaje_penalidad': porcentaje_penalidad,
        'fecha_salida_vigente': fecha_salida_vigente,
        'prorroga_no_autorizada': es_prorroga_no_autorizada,
        'noches_adicionales': cotizacion_extra['noches'],
        'monto_noches_adicionales': cotizacion_extra['precio_total'],
        'desglose_noches_adicionales': cotizacion_extra['desglose'],
        'conflictos_sobreestadia': conflictos_sobreestadia,
    }


def autorizar_prorroga_estancia(estancia, fecha_salida_nueva, usuario=None, motivo=''):
    from django.db import transaction
    from estancias.models import CargoEstancia, Estancia, Folio, ProrrogaEstancia

    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().select_related(
            'reserva__huesped', 'habitacion__tipo'
        ).get(pk=estancia.pk)
        if estancia.estado != 'ACTIVA':
            raise ValidationError('Solo se puede prorrogar una estancia activa.')
        fecha_anterior = obtener_fecha_salida_vigente(estancia)
        if fecha_salida_nueva <= fecha_anterior:
            raise ValidationError('La nueva salida debe ser posterior a la salida vigente.')

        conflictos = conflictos_para_periodo(estancia.reserva, fecha_anterior, fecha_salida_nueva)
        if conflictos.exists():
            conflicto = conflictos.first()
            raise ValidationError(
                f'No se puede autorizar: la habitacion esta comprometida por la reserva #{conflicto.id} '
                f'de {conflicto.huesped}.'
            )

        cotizacion = calcular_tarifa_estadia(
            estancia.habitacion.tipo, fecha_anterior, fecha_salida_nueva
        )
        CargoEstancia.objects.filter(estancia=estancia).filter(
            Q(tipo='LATE_CHECKOUT')
            | Q(concepto='Noches adicionales no autorizadas previamente')
        ).delete()
        prorroga = ProrrogaEstancia.objects.create(
            estancia=estancia,
            fecha_salida_anterior=fecha_anterior,
            fecha_salida_nueva=fecha_salida_nueva,
            noches_adicionales=cotizacion['noches'],
            monto=cotizacion['precio_total'],
            autorizado_por=usuario,
            motivo=motivo,
        )
        CargoEstancia.objects.create(
            estancia=estancia,
            concepto=f'Prorroga del {fecha_anterior:%d/%m/%Y} al {fecha_salida_nueva:%d/%m/%Y}',
            cantidad=cotizacion['noches'],
            precio_unitario=(cotizacion['precio_total'] / cotizacion['noches']),
            monto=cotizacion['precio_total'],
            tipo='NOCHE_ADICIONAL',
        )
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        folio.estado = 'PENDIENTE'
        folio.save()
        return prorroga


def obtener_panel_reservas_dia(fecha=None):
    fecha = fecha or timezone.localdate()
    momento = timezone.now()
    limite_garantia = momento + timedelta(hours=HORAS_ALERTA_GARANTIA)
    garantias_por_vencer = list(
        Reserva.objects.select_related('huesped', 'habitacion__tipo').prefetch_related('adelantos').filter(
            estado='PENDIENTE',
            estancia__isnull=True,
            fecha_limite_pago__gt=momento,
            fecha_limite_pago__lte=limite_garantia,
        ).order_by('fecha_limite_pago', 'id')
    )
    for reserva in garantias_por_vencer:
        reserva.minutos_para_vencer = max(
            0,
            int((reserva.fecha_limite_pago - momento).total_seconds() // 60),
        )

    pendientes = list(
        Reserva.objects.select_related('huesped', 'habitacion__tipo').filter(
            estado__in=['PENDIENTE', 'CONFIRMADA'],
            estancia__isnull=True,
            fecha_entrada__lte=fecha,
        ).order_by('fecha_entrada', 'habitacion__numero')
    )
    llegadas_hoy = []
    llegadas_atrasadas = []
    no_show_pendientes = []
    for reserva in pendientes:
        if reserva.fecha_salida <= fecha:
            reserva.estado_operativo = 'VENCIDA'
            no_show_pendientes.append(reserva)
        elif reserva.fecha_entrada < fecha:
            reserva.estado_operativo = 'LLEGADA_TARDIA'
            llegadas_atrasadas.append(reserva)
        else:
            reserva.estado_operativo = 'LLEGADA_HOY'
            llegadas_hoy.append(reserva)

    en_casa = list(
        Reserva.objects.select_related(
            'huesped', 'habitacion__tipo', 'estancia__folio'
        ).prefetch_related('estancia__prorrogas').filter(
            estado='CHECKIN',
            estancia__estado='ACTIVA',
        ).order_by('habitacion__numero')
    )
    salidas_hoy = []
    salidas_vencidas = []
    en_casa_continuan = []
    for reserva in en_casa:
        reserva.salida_vigente = obtener_fecha_salida_vigente(reserva.estancia)
        if reserva.salida_vigente < fecha:
            reserva.estado_operativo = 'SALIDA_VENCIDA'
            salidas_vencidas.append(reserva)
        elif reserva.salida_vigente == fecha:
            reserva.estado_operativo = 'SALIDA_HOY'
            salidas_hoy.append(reserva)
        else:
            reserva.estado_operativo = 'EN_CASA'
            en_casa_continuan.append(reserva)

    return {
        'fecha': fecha,
        'garantias_por_vencer': garantias_por_vencer,
        'llegadas_hoy': llegadas_hoy,
        'llegadas_atrasadas': llegadas_atrasadas,
        'no_show_pendientes': no_show_pendientes,
        'en_casa': en_casa,
        'en_casa_continuan': en_casa_continuan,
        'salidas_hoy': salidas_hoy,
        'salidas_vencidas': salidas_vencidas,
        'total_llegadas': len(llegadas_hoy) + len(llegadas_atrasadas),
        'total_en_casa': len(en_casa),
        'total_salidas': len(salidas_hoy) + len(salidas_vencidas),
        'total_alertas': (
            len(garantias_por_vencer)
            + len(llegadas_atrasadas)
            + len(no_show_pendientes)
            + len(salidas_vencidas)
        ),
    }
