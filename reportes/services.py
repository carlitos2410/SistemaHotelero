from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from estancias.models import Estancia, Folio, MovimientoCaja, Pago
from habitaciones.models import Habitacion, TipoHabitacion


def _rango_dias(fecha_desde, fecha_hasta):
    actual = fecha_desde
    while actual <= fecha_hasta:
        yield actual
        actual += timedelta(days=1)


def _dias_ocupados(estancia, fecha_desde, fecha_hasta):
    inicio = timezone.localtime(estancia.fecha_checkin).date()
    if estancia.fecha_checkout:
        fin_exclusivo = timezone.localtime(estancia.fecha_checkout).date()
        if fin_exclusivo <= inicio:
            fin_exclusivo = inicio + timedelta(days=1)
    else:
        fin_exclusivo = min(fecha_hasta, timezone.localdate()) + timedelta(days=1)

    inicio = max(inicio, fecha_desde)
    fin_exclusivo = min(fin_exclusivo, fecha_hasta + timedelta(days=1))
    if fin_exclusivo <= inicio:
        return []
    return list(_rango_dias(inicio, fin_exclusivo - timedelta(days=1)))


def calcular_reporte_ocupacion(fecha_desde, fecha_hasta, *, incluir_revenue=True):
    if fecha_hasta < fecha_desde:
        raise ValueError('La fecha final debe ser posterior o igual a la fecha inicial.')

    habitaciones = list(Habitacion.objects.select_related('tipo').order_by('tipo__nombre', 'numero'))
    tipos = list(TipoHabitacion.objects.order_by('nombre'))
    total_habitaciones = len(habitaciones)
    cantidad_dias = (fecha_hasta - fecha_desde).days + 1

    estancias = list(
        Estancia.objects.select_related('habitacion__tipo', 'reserva__huesped').filter(
            fecha_checkin__date__lte=fecha_hasta,
        ).filter(Q(fecha_checkout__isnull=True) | Q(fecha_checkout__date__gte=fecha_desde))
    )

    ocupadas_por_dia = defaultdict(set)
    ocupadas_tipo_por_dia = defaultdict(set)
    for estancia in estancias:
        for dia in _dias_ocupados(estancia, fecha_desde, fecha_hasta):
            ocupadas_por_dia[dia].add(estancia.habitacion_id)
            ocupadas_tipo_por_dia[(estancia.habitacion.tipo_id, dia)].add(estancia.habitacion_id)

    serie_diaria = []
    for dia in _rango_dias(fecha_desde, fecha_hasta):
        ocupadas = len(ocupadas_por_dia[dia])
        tasa = round((ocupadas / total_habitaciones) * 100, 2) if total_habitaciones else 0
        serie_diaria.append({
            'fecha': dia,
            'habitaciones_ocupadas': ocupadas,
            'habitaciones_disponibles': max(total_habitaciones - ocupadas, 0),
            'total_habitaciones': total_habitaciones,
            'tasa_ocupacion': tasa,
        })

    habitaciones_por_tipo = defaultdict(int)
    for habitacion in habitaciones:
        habitaciones_por_tipo[habitacion.tipo_id] += 1

    revenue_por_tipo = defaultdict(lambda: Decimal('0.00'))
    cobrado_por_tipo = defaultdict(lambda: Decimal('0.00'))
    cobrado_sin_tipo = Decimal('0.00')

    if incluir_revenue:
        folios_por_tipo = Folio.objects.filter(
            estancia__fecha_checkin__date__gte=fecha_desde,
            estancia__fecha_checkin__date__lte=fecha_hasta,
        ).values(
            tipo_habitacion_id=F('estancia__habitacion__tipo_id'),
        ).annotate(total=Sum('total'))
        for fila in folios_por_tipo:
            revenue_por_tipo[fila['tipo_habitacion_id']] = fila['total'] or Decimal('0.00')

        tipo_pago = Coalesce(
            'pago__folio__estancia__habitacion__tipo_id',
            'pago__reserva__habitacion__tipo_id',
        )
        monto_firmado = Case(
            When(tipo='INGRESO', then=F('monto')),
            default=-F('monto'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        movimientos_por_tipo = MovimientoCaja.objects.filter(
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta,
            pago__isnull=False,
        ).annotate(
            tipo_habitacion_id=tipo_pago,
        ).values('tipo_habitacion_id').annotate(total=Sum(monto_firmado))
        for fila in movimientos_por_tipo:
            tipo_id = fila['tipo_habitacion_id']
            total = fila['total'] or Decimal('0.00')
            if tipo_id is None:
                cobrado_sin_tipo += total
            else:
                cobrado_por_tipo[tipo_id] += total

        # Compatibilidad con pagos antiguos cargados antes de existir MovimientoCaja.
        pagos_legacy_por_tipo = Pago.objects.filter(
            estado='APROBADO',
            creado_en__date__gte=fecha_desde,
            creado_en__date__lte=fecha_hasta,
            movimientos_caja__isnull=True,
        ).annotate(
            tipo_habitacion_id=Coalesce(
                'folio__estancia__habitacion__tipo_id',
                'reserva__habitacion__tipo_id',
            ),
        ).values('tipo_habitacion_id').annotate(total=Sum('monto'))
        for fila in pagos_legacy_por_tipo:
            tipo_id = fila['tipo_habitacion_id']
            total = fila['total'] or Decimal('0.00')
            if tipo_id is None:
                cobrado_sin_tipo += total
            else:
                cobrado_por_tipo[tipo_id] += total

    desglose_tipos = []
    for tipo in tipos:
        total_tipo = habitaciones_por_tipo[tipo.id]
        ocupadas_noche = sum(
            len(ocupadas_tipo_por_dia[(tipo.id, dia)])
            for dia in _rango_dias(fecha_desde, fecha_hasta)
        )
        capacidad_noches = total_tipo * cantidad_dias
        tasa = round((ocupadas_noche / capacidad_noches) * 100, 2) if capacidad_noches else 0
        desglose_tipos.append({
            'tipo_id': tipo.id,
            'tipo': tipo.nombre,
            'habitaciones': total_tipo,
            'habitaciones_noche_ocupadas': ocupadas_noche,
            'habitaciones_noche_disponibles': max(capacidad_noches - ocupadas_noche, 0),
            'tasa_ocupacion': tasa,
            'revenue_facturado': revenue_por_tipo[tipo.id],
            'revenue_cobrado': cobrado_por_tipo[tipo.id],
        })

    habitaciones_noche_ocupadas = sum(item['habitaciones_ocupadas'] for item in serie_diaria)
    capacidad_total = total_habitaciones * cantidad_dias
    tasa_periodo = round((habitaciones_noche_ocupadas / capacidad_total) * 100, 2) if capacidad_total else 0

    return {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'cantidad_dias': cantidad_dias,
        'total_habitaciones': total_habitaciones,
        'habitaciones_noche_ocupadas': habitaciones_noche_ocupadas,
        'habitaciones_noche_disponibles': max(capacidad_total - habitaciones_noche_ocupadas, 0),
        'tasa_ocupacion_periodo': tasa_periodo,
        'revenue_facturado': sum(revenue_por_tipo.values(), Decimal('0.00')),
        'revenue_cobrado': sum(cobrado_por_tipo.values(), cobrado_sin_tipo),
        'revenue_cobrado_sin_tipo': cobrado_sin_tipo,
        'serie_diaria': serie_diaria,
        'desglose_tipos': desglose_tipos,
    }
