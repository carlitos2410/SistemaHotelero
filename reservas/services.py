from datetime import time
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


HORA_CHECKIN = time(15, 0)
HORA_CHECKOUT = time(12, 0)
PORCENTAJE_EARLY_CHECKIN = Decimal('0.05')
PORCENTAJE_LATE_CHECKOUT = Decimal('0.50')


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
    es_anticipado = momento.date() == reserva.fecha_entrada and momento.time() < HORA_CHECKIN
    cargo = redondear_monto(tarifa_noche * PORCENTAJE_EARLY_CHECKIN) if es_anticipado else Decimal('0.00')

    return {
        'momento': momento,
        'hora_limite': HORA_CHECKIN,
        'tipo': 'ANTICIPADO' if es_anticipado else 'NORMAL',
        'cargo': cargo,
        'tarifa_noche': tarifa_noche,
        'porcentaje': PORCENTAJE_EARLY_CHECKIN * 100,
    }


def evaluar_checkout(reserva, estancia=None, momento=None):
    from estancias.models import ConfiguracionCobro

    momento = timezone.localtime(momento or timezone.now())
    tarifa_noche = obtener_tarifa_noche(reserva)
    es_tardio = momento.date() == reserva.fecha_salida and momento.time() > HORA_CHECKOUT
    cargo = redondear_monto(tarifa_noche * PORCENTAJE_LATE_CHECKOUT) if es_tardio else Decimal('0.00')
    config = ConfiguracionCobro.actual()
    noches_reservadas = obtener_noches(reserva)
    noches_reales = obtener_noches_reales(estancia.fecha_checkin, momento) if estancia else noches_reservadas
    monto_estadia_real = redondear_monto(tarifa_noche * Decimal(noches_reales))
    monto_reserva_completa = redondear_monto(tarifa_noche * Decimal(noches_reservadas))
    noches_no_usadas = max(noches_reservadas - noches_reales, 0)
    penalidad = Decimal('0.00')

    if config.politica_checkout == 'RESERVA_COMPLETA':
        monto_habitacion = monto_reserva_completa
    elif config.politica_checkout == 'ESTADIA_REAL_PENALIDAD':
        porcentaje = config.porcentaje_penalidad_salida_anticipada / Decimal('100')
        penalidad = redondear_monto(tarifa_noche * Decimal(noches_no_usadas) * porcentaje)
        monto_habitacion = monto_estadia_real
    else:
        monto_habitacion = monto_estadia_real

    return {
        'momento': momento,
        'hora_limite': HORA_CHECKOUT,
        'tipo': 'TARDIO' if es_tardio else 'NORMAL',
        'cargo': cargo,
        'tarifa_noche': tarifa_noche,
        'porcentaje': PORCENTAJE_LATE_CHECKOUT * 100,
        'politica': config.politica_checkout,
        'politica_nombre': config.get_politica_checkout_display(),
        'noches_reservadas': noches_reservadas,
        'noches_reales': noches_reales,
        'noches_no_usadas': noches_no_usadas,
        'monto_estadia_real': monto_estadia_real,
        'monto_reserva_completa': monto_reserva_completa,
        'monto_habitacion': redondear_monto(monto_habitacion),
        'penalidad_salida_anticipada': penalidad,
        'porcentaje_penalidad': config.porcentaje_penalidad_salida_anticipada,
    }
