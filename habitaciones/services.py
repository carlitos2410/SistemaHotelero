from django.core.exceptions import ValidationError
from django.db import transaction


def cambiar_estado_habitacion(habitacion, nuevo_estado, *, usuario=None, motivo=''):
    from .models import HabitacionEstadoHistorial

    if nuevo_estado not in dict(habitacion.ESTADOS):
        raise ValidationError(f'Estado invalido: {nuevo_estado}')

    estado_anterior = habitacion.estado
    if estado_anterior == nuevo_estado:
        return habitacion

    with transaction.atomic():
        habitacion = (
            habitacion.__class__.objects.select_for_update()
            .select_related('hotel', 'tipo')
            .get(pk=habitacion.pk)
        )
        habitacion.estado = nuevo_estado
        habitacion.save(update_fields=['estado'])
        HabitacionEstadoHistorial.objects.create(
            habitacion=habitacion,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            motivo=motivo,
            cambiado_por=usuario,
        )

    return habitacion
