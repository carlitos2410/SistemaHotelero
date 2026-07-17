import logging


logger = logging.getLogger('hotel.operaciones')

CAMPOS_SEGUROS = {
    'usuario_id',
    'reserva_id',
    'estancia_id',
    'folio_id',
    'habitacion_id',
    'pago_id',
    'estado_anterior',
    'estado_nuevo',
    'monto',
    'cantidad',
    'resultado',
}


def registrar_evento(evento, *, usuario=None, nivel='info', **datos):
    """Registra operaciones sin aceptar contraseñas, documentos ni datos personales."""
    usuario_id = getattr(usuario, 'pk', None)
    campos = {'usuario_id': usuario_id, **datos}
    partes = [f'evento={evento}']
    partes.extend(
        f'{clave}={valor}'
        for clave, valor in sorted(campos.items())
        if clave in CAMPOS_SEGUROS and valor is not None
    )
    metodo = getattr(logger, nivel, logger.info)
    metodo(' '.join(partes))
