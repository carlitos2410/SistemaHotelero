import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Habitacion

logger = logging.getLogger('hotel.operaciones')


@receiver(post_save, sender=Habitacion)
def log_crear_habitacion(sender, instance, created, **kwargs):
    if created:
        logger.info(
            'Habitacion creada: %s en hotel %s (tipo %s, piso %d)',
            instance.numero,
            instance.hotel.nombre,
            instance.tipo.nombre,
            instance.piso,
        )
