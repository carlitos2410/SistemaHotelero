from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Q, F, Avg
from django.utils import timezone


def _rango_fechas_defecto():
    hoy = timezone.localdate()
    primer_dia_mes = hoy.replace(day=1)
    return primer_dia_mes, hoy


def calcular_ocupacion(fecha_desde=None, fecha_hasta=None, hotel_id=None):
    from habitaciones.models import Habitacion
    from reservas.models import Reserva

    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = _rango_fechas_defecto()

    total_habitaciones = Habitacion.objects.all()
    if hotel_id:
        total_habitaciones = total_habitaciones.filter(hotel_id=hotel_id)
    total = total_habitaciones.count()

    if total == 0:
        return {
            'total_habitaciones': 0,
            'ocupadas_promedio': 0,
            'porcentaje_ocupacion': Decimal('0.00'),
            'dias_analizados': 0,
        }

    dias = (fecha_hasta - fecha_desde).days + 1
    reserva_qs = Reserva.objects.filter(
        estado__in=['CHECKIN', 'CHECKOUT'],
        fecha_entrada__lte=fecha_hasta,
        fecha_salida__gt=fecha_desde,
    )
    if hotel_id:
        reserva_qs = reserva_qs.filter(hotel_id=hotel_id)

    ocupadas_por_dia = []
    for offset in range(dias):
        dia = fecha_desde + timedelta(days=offset)
        ocupadas = reserva_qs.filter(
            fecha_entrada__lte=dia,
            fecha_salida__gt=dia,
        ).values('habitacion').distinct().count()
        ocupadas_por_dia.append(ocupadas)

    promedio_ocupadas = sum(ocupadas_por_dia) / len(ocupadas_por_dia) if ocupadas_por_dia else 0
    porcentaje = Decimal(str(promedio_ocupadas * 100 / total)).quantize(Decimal('0.01'))

    return {
        'total_habitaciones': total,
        'ocupadas_promedio': round(promedio_ocupadas, 1),
        'porcentaje_ocupacion': porcentaje,
        'dias_analizados': dias,
    }


def calcular_ingresos(fecha_desde=None, fecha_hasta=None, hotel_id=None):
    from estancias.models import Pago, MovimientoCaja

    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = _rango_fechas_defecto()

    pagos = Pago.objects.filter(
        estado='APROBADO',
        creado_en__date__gte=fecha_desde,
        creado_en__date__lte=fecha_hasta,
    )
    if hotel_id:
        pagos = pagos.filter(reserva__hotel_id=hotel_id)

    ingresos = pagos.aggregate(
        total=Sum('monto'),
        cantidad=Count('id'),
    )

    movimientos = MovimientoCaja.objects.filter(
        fecha__date__gte=fecha_desde,
        fecha__date__lte=fecha_hasta,
    )
    if hotel_id:
        movimientos = movimientos.filter(pago__reserva__hotel_id=hotel_id)

    ingresos_caja = movimientos.filter(tipo='INGRESO').aggregate(total=Sum('monto'))
    egresos_caja = movimientos.filter(tipo='EGRESO').aggregate(total=Sum('monto'))

    return {
        'total_pagos': ingresos['total'] or Decimal('0.00'),
        'cantidad_pagos': ingresos['cantidad'] or 0,
        'ingresos_caja': ingresos_caja['total'] or Decimal('0.00'),
        'egresos_caja': egresos_caja['total'] or Decimal('0.00'),
        'flujo_neto': (ingresos_caja['total'] or Decimal('0.00')) - (egresos_caja['total'] or Decimal('0.00')),
    }


def resumen_reservas(fecha_desde=None, fecha_hasta=None, hotel_id=None):
    from reservas.models import Reserva

    if fecha_desde is None or fecha_hasta is None:
        fecha_desde, fecha_hasta = _rango_fechas_defecto()

    qs = Reserva.objects.filter(
        creado_en__date__gte=fecha_desde,
        creado_en__date__lte=fecha_hasta,
    )
    if hotel_id:
        qs = qs.filter(hotel_id=hotel_id)

    resumen = qs.aggregate(
        total=Count('id'),
        pendientes=Count('id', filter=Q(estado='PENDIENTE')),
        confirmadas=Count('id', filter=Q(estado='CONFIRMADA')),
        en_casa=Count('id', filter=Q(estado='CHECKIN')),
        finalizadas=Count('id', filter=Q(estado='CHECKOUT')),
        canceladas=Count('id', filter=Q(estado='CANCELADA')),
        no_show=Count('id', filter=Q(estado='NO_SHOW')),
        ingreso_total=Sum('precio_total'),
    )

    return resumen


def resumen_habitaciones(hotel_id=None):
    from habitaciones.models import Habitacion

    qs = Habitacion.objects.all()
    if hotel_id:
        qs = qs.filter(hotel_id=hotel_id)

    estados = qs.values('estado').annotate(total=Count('id')).order_by('estado')
    return {
        item['estado']: item['total']
        for item in estados
    }
