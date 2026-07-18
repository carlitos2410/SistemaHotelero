from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from usuarios.auditoria import registrar_evento

from .models import (
    CargoEstancia,
    Comprobante,
    CorrelativoComprobante,
    Estancia,
    Folio,
    MovimientoCaja,
    Pago,
)


def normalizar_monto(monto):
    return Decimal(monto).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def recalcular_folio(folio, *, bloquear=False):
    if bloquear:
        folio = Folio.objects.select_for_update().get(pk=folio.pk)
    if folio.estado == 'PAGADO' and folio.estancia.estado == 'FINALIZADA' and folio.total_pagado > 0:
        return folio
    folio.calcular_totales()
    folio.estado = 'PAGADO' if folio.saldo_pendiente <= 0 else 'PENDIENTE'
    folio.save(update_fields=['subtotal', 'igv', 'total', 'estado'])
    return folio


def agregar_cargo_estancia(
    estancia,
    *,
    concepto,
    cantidad,
    precio_unitario,
    tipo,
    producto_servicio=None,
):
    cantidad = int(cantidad)
    precio_unitario = normalizar_monto(precio_unitario)
    if cantidad <= 0 or precio_unitario <= 0:
        raise ValidationError('La cantidad y el precio del cargo no son validos.')

    with transaction.atomic():
        estancia = Estancia.objects.select_for_update().get(pk=estancia.pk)
        if estancia.estado != 'ACTIVA':
            raise ValidationError('Solo se pueden agregar cargos a una estancia activa.')
        monto = normalizar_monto(precio_unitario * cantidad)
        cargo = CargoEstancia.objects.create(
            estancia=estancia,
            producto_servicio=producto_servicio,
            concepto=concepto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            monto=monto,
            tipo=tipo,
        )
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio = recalcular_folio(folio, bloquear=True)
        registrar_evento(
            'cargo_estancia',
            estancia_id=estancia.id,
            folio_id=folio.id,
            monto=monto,
            resultado='registrado',
        )
        return cargo, folio


def sincronizar_cargo_calculado(estancia, *, tipo, concepto, monto, cantidad=1):
    monto = normalizar_monto(monto)
    cantidad = max(int(cantidad), 1)
    existentes = CargoEstancia.objects.filter(estancia=estancia, tipo=tipo, concepto=concepto).order_by('id')
    cargo = existentes.first()
    if monto <= 0:
        existentes.delete()
        return None
    precio_unitario = normalizar_monto(monto / cantidad)
    if cargo:
        cargo.cantidad = cantidad
        cargo.precio_unitario = precio_unitario
        cargo.monto = monto
        cargo.save(update_fields=['cantidad', 'precio_unitario', 'monto'])
        existentes.exclude(pk=cargo.pk).delete()
        return cargo
    return CargoEstancia.objects.create(
        estancia=estancia,
        concepto=concepto,
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        monto=monto,
        tipo=tipo,
    )


def _siguiente_correlativo(tipo, serie):
    CorrelativoComprobante.objects.get_or_create(tipo=tipo, serie=serie)
    correlativo = CorrelativoComprobante.objects.select_for_update().get(tipo=tipo, serie=serie)
    correlativo.ultimo_numero += 1
    correlativo.save(update_fields=['ultimo_numero'])
    return correlativo.ultimo_numero


def registrar_pago_folio(
    folio,
    *,
    metodo_pago,
    monto,
    tipo_comprobante,
    cliente_documento,
    cliente_nombre,
    cliente_direccion='',
    numero_operacion='',
    observacion='',
    usuario=None,
):
    monto = normalizar_monto(monto)
    numero_operacion = (numero_operacion or '').strip()
    cliente_documento = (cliente_documento or '').strip()
    cliente_nombre = (cliente_nombre or '').strip()
    if not metodo_pago.activo:
        raise ValidationError('El metodo de pago seleccionado no esta activo.')
    if metodo_pago.tipo != 'EFECTIVO' and not numero_operacion:
        raise ValidationError('Ingresa el numero de operacion para pagos no efectivos.')
    if tipo_comprobante not in dict(Comprobante.TIPO_CHOICES):
        raise ValidationError('El tipo de comprobante no es valido.')
    if not cliente_documento or not cliente_nombre:
        raise ValidationError('El documento y nombre del cliente son obligatorios.')
    if tipo_comprobante == 'FACTURA' and (len(cliente_documento) != 11 or not cliente_documento.isdigit()):
        raise ValidationError('Para factura ingresa un RUC valido de 11 digitos.')
    with transaction.atomic():
        folio = Folio.objects.select_for_update().select_related('estancia').get(pk=folio.pk)
        folio = recalcular_folio(folio)
        saldo = folio.saldo_pendiente
        if monto <= 0:
            raise ValidationError('El monto debe ser mayor a cero.')
        if saldo <= 0:
            raise ValidationError('El folio ya se encuentra pagado.')
        if monto > saldo:
            raise ValidationError(f'El monto supera el saldo pendiente de S/ {saldo}.')

        pago = Pago.objects.create(
            folio=folio,
            metodo_pago=metodo_pago,
            monto=monto,
            numero_operacion=numero_operacion,
            estado='APROBADO',
            usuario_responsable=usuario,
            observacion=observacion,
            es_simulado=True,
        )
        serie = 'F001' if tipo_comprobante == 'FACTURA' else 'B001'
        numero = _siguiente_correlativo(tipo_comprobante, serie)
        comprobante = Comprobante.objects.create(
            pago=pago,
            tipo=tipo_comprobante,
            serie=serie,
            numero=numero,
            cliente_documento=cliente_documento,
            cliente_nombre=cliente_nombre,
            cliente_direccion=cliente_direccion,
            estado='EMITIDO',
            usuario_responsable=usuario,
        )
        MovimientoCaja.objects.create(
            pago=pago,
            tipo='INGRESO',
            concepto='PAGO_FOLIO',
            monto=monto,
            metodo_pago=metodo_pago,
            numero_operacion=numero_operacion,
            usuario_responsable=usuario,
            observacion=observacion,
        )
        folio = recalcular_folio(folio)
        registrar_evento(
            'pago_folio',
            usuario=usuario,
            estancia_id=folio.estancia_id,
            folio_id=folio.id,
            pago_id=pago.id,
            monto=monto,
            resultado='aprobado',
        )
        return pago, comprobante, folio


def registrar_adelanto_reserva(
    reserva,
    *,
    metodo_pago,
    monto,
    tipo_comprobante,
    cliente_documento,
    cliente_nombre,
    cliente_direccion='',
    numero_operacion='',
    observacion='',
    usuario=None,
):
    monto = normalizar_monto(monto)
    numero_operacion = (numero_operacion or '').strip()
    cliente_documento = (cliente_documento or '').strip()
    cliente_nombre = (cliente_nombre or '').strip()
    if not metodo_pago.activo:
        raise ValidationError('El metodo de pago seleccionado no esta activo.')
    if metodo_pago.tipo != 'EFECTIVO' and not numero_operacion:
        raise ValidationError('Ingresa el numero de operacion para pagos no efectivos.')
    if tipo_comprobante not in dict(Comprobante.TIPO_CHOICES):
        raise ValidationError('El tipo de comprobante no es valido.')
    if not cliente_documento or not cliente_nombre:
        raise ValidationError('El documento y nombre del cliente son obligatorios.')
    if tipo_comprobante == 'FACTURA' and (len(cliente_documento) != 11 or not cliente_documento.isdigit()):
        raise ValidationError('Para factura ingresa un RUC valido de 11 digitos.')

    from django.utils import timezone
    from reservas.models import Reserva
    reserva_actual = Reserva.objects.filter(pk=reserva.pk).first()
    if (
        reserva_actual
        and reserva_actual.estado == 'PENDIENTE'
        and reserva_actual.fecha_limite_pago
        and reserva_actual.fecha_limite_pago < timezone.now()
    ):
        from reservas.services import liberar_reservas_sin_garantia_vencidas
        liberar_reservas_sin_garantia_vencidas()
        raise ValidationError('El plazo de pago vencio y la habitacion fue liberada.')
    with transaction.atomic():
        reserva = Reserva.objects.select_for_update().get(pk=reserva.pk)
        if reserva.estado not in ['PENDIENTE', 'CONFIRMADA']:
            raise ValidationError('Esta reserva ya no admite adelantos.')
        saldo = reserva.saldo_adelanto
        if saldo <= 0:
            raise ValidationError('La garantia de la reserva ya esta completa.')
        if monto <= 0 or monto > saldo:
            raise ValidationError(f'El adelanto debe ser mayor a cero y no superar S/ {saldo}.')

        pago = Pago.objects.create(
            reserva=reserva,
            metodo_pago=metodo_pago,
            monto=monto,
            numero_operacion=numero_operacion,
            estado='APROBADO',
            usuario_responsable=usuario,
            observacion=observacion,
            es_simulado=True,
        )
        serie = 'F001' if tipo_comprobante == 'FACTURA' else 'B001'
        numero = _siguiente_correlativo(tipo_comprobante, serie)
        comprobante = Comprobante.objects.create(
            pago=pago,
            tipo=tipo_comprobante,
            serie=serie,
            numero=numero,
            cliente_documento=cliente_documento,
            cliente_nombre=cliente_nombre,
            cliente_direccion=cliente_direccion,
            estado='EMITIDO',
            usuario_responsable=usuario,
        )
        MovimientoCaja.objects.create(
            pago=pago,
            tipo='INGRESO',
            concepto='ADELANTO_RESERVA',
            monto=monto,
            metodo_pago=metodo_pago,
            numero_operacion=numero_operacion,
            usuario_responsable=usuario,
            observacion=observacion,
        )
        if reserva.saldo_adelanto <= 0:
            reserva.estado = 'CONFIRMADA'
            reserva._estado_usuario = usuario
            reserva._estado_motivo = 'Garantia del 50% completada.'
            reserva.save(update_fields=['estado'])
        registrar_evento(
            'adelanto_reserva',
            usuario=usuario,
            reserva_id=reserva.id,
            pago_id=pago.id,
            monto=monto,
            resultado='aprobado',
        )
        return pago, comprobante, reserva
