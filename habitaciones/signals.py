from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from usuarios.auditoria import registrar_evento

from .models import Habitacion, HabitacionEstadoHistorial


@receiver(pre_save, sender=Habitacion)
def recordar_estado_anterior(sender, instance, **kwargs):
    if not instance.pk:
        instance._estado_anterior = ''
        return
    instance._estado_anterior = (
        sender.objects.filter(pk=instance.pk).values_list('estado', flat=True).first() or ''
    )


@receiver(post_save, sender=Habitacion)
def registrar_cambio_estado(sender, instance, created, **kwargs):
    estado_anterior = getattr(instance, '_estado_anterior', '')
    if not created and estado_anterior == instance.estado:
        return
    HabitacionEstadoHistorial.objects.create(
        habitacion=instance,
        estado_anterior=estado_anterior,
        estado_nuevo=instance.estado,
        cambiado_por=getattr(instance, '_estado_usuario', None),
        motivo=getattr(instance, '_estado_motivo', ''),
        cambiado_en=getattr(instance, '_estado_fecha', timezone.now()),
    )
    registrar_evento(
        'habitacion_estado',
        usuario=getattr(instance, '_estado_usuario', None),
        habitacion_id=instance.id,
        estado_anterior=estado_anterior or 'INICIAL',
        estado_nuevo=instance.estado,
        resultado='registrado',
    )
