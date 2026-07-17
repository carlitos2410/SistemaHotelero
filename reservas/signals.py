from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from usuarios.auditoria import registrar_evento

from .models import Reserva, ReservaEstadoHistorial


@receiver(pre_save, sender=Reserva)
def recordar_estado_anterior_reserva(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    if not instance.pk:
        instance._estado_anterior = ''
        return
    instance._estado_anterior = (
        sender.objects.filter(pk=instance.pk).values_list('estado', flat=True).first() or ''
    )


@receiver(post_save, sender=Reserva)
def registrar_estado_reserva(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    estado_anterior = getattr(instance, '_estado_anterior', '')
    usuario = instance.__dict__.pop('_estado_usuario', None)
    motivo_indicado = instance.__dict__.pop('_estado_motivo', None)
    if not created and estado_anterior == instance.estado:
        return

    if created:
        motivo_default = 'Reserva creada.'
    else:
        motivo_default = f'Cambio de {estado_anterior} a {instance.estado}.'

    ReservaEstadoHistorial.objects.create(
        reserva=instance,
        estado_anterior=estado_anterior,
        estado_nuevo=instance.estado,
        cambiado_por=usuario,
        motivo=motivo_indicado or motivo_default,
    )
    registrar_evento(
        'reserva_estado',
        usuario=usuario,
        reserva_id=instance.id,
        estado_anterior=estado_anterior or 'INICIAL',
        estado_nuevo=instance.estado,
        resultado='registrado',
    )
