from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


TRANSICIONES_HOUSEKEEPING = {
    'DISPONIBLE': {'LIMPIEZA', 'MANTENIMIENTO'},
    'OCUPADA': set(),
    'LIMPIEZA': {'DISPONIBLE', 'MANTENIMIENTO'},
    'MANTENIMIENTO': {'LIMPIEZA'},
}


def _transiciones_para_usuario(habitacion, usuario=None):
    permitidos = set(TRANSICIONES_HOUSEKEEPING.get(habitacion.estado, set()))
    es_administrador = bool(
        usuario
        and usuario.is_authenticated
        and (usuario.is_superuser or usuario.groups.filter(name='Administrador').exists())
    )
    if habitacion.estado == 'DISPONIBLE' and not es_administrador:
        permitidos.discard('LIMPIEZA')
    return permitidos


def cambiar_estado_habitacion(habitacion, nuevo_estado, *, usuario=None, motivo='', momento=None):
    """Cambia el estado y adjunta metadatos para el historial automatico."""
    if habitacion.estado == nuevo_estado:
        return habitacion
    habitacion._estado_usuario = usuario if usuario and usuario.is_authenticated else None
    habitacion._estado_motivo = motivo
    habitacion._estado_fecha = momento or timezone.now()
    habitacion.estado = nuevo_estado
    habitacion.save(update_fields=['estado'])
    return habitacion


def obtener_transiciones_housekeeping(habitacion, usuario=None):
    return sorted(_transiciones_para_usuario(habitacion, usuario))


def actualizar_estado_housekeeping(habitacion, nuevo_estado, *, usuario=None, observacion=''):
    from estancias.models import Estancia
    from .models import Habitacion, ObservacionMantenimiento

    with transaction.atomic():
        habitacion = Habitacion.objects.select_for_update().get(pk=habitacion.pk)
        if Estancia.objects.filter(habitacion=habitacion, estado='ACTIVA').exists():
            raise ValidationError('No se puede cambiar housekeeping de una habitacion con estancia activa.')
        if nuevo_estado == habitacion.estado:
            return habitacion
        permitidos = _transiciones_para_usuario(habitacion, usuario)
        if nuevo_estado not in permitidos:
            raise ValidationError(
                f'Transicion no permitida: {habitacion.get_estado_display()} a {nuevo_estado.lower()}.'
            )
        observacion = (observacion or '').strip()
        if nuevo_estado == 'MANTENIMIENTO' and not observacion:
            raise ValidationError('Debes registrar una observacion para enviar la habitacion a mantenimiento.')

        estado_anterior = habitacion.estado
        motivo = observacion
        if not motivo and estado_anterior == 'LIMPIEZA' and nuevo_estado == 'DISPONIBLE':
            motivo = 'Limpieza finalizada. Habitacion lista para recibir huespedes.'
        elif not motivo and estado_anterior == 'MANTENIMIENTO' and nuevo_estado == 'LIMPIEZA':
            motivo = 'Mantenimiento finalizado. Habitacion enviada a limpieza.'

        cambiar_estado_habitacion(
            habitacion,
            nuevo_estado,
            usuario=usuario,
            motivo=motivo or 'Actualizacion de housekeeping.',
        )
        if nuevo_estado == 'MANTENIMIENTO':
            ObservacionMantenimiento.objects.create(
                habitacion=habitacion,
                observacion=observacion,
                creado_por=usuario if usuario and usuario.is_authenticated else None,
            )
        return habitacion
