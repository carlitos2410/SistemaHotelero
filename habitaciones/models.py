from django.core.exceptions import ValidationError
from django.db import models

from hoteles.models import Hotel


class TipoHabitacion(models.Model):
    nombre = models.CharField(max_length=80)
    capacidad = models.PositiveIntegerField(default=2)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    amenidades = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        errores = {}
        if self.capacidad and self.capacidad < 1:
            errores['capacidad'] = 'La capacidad debe ser al menos 1.'
        if self.precio_base is not None and self.precio_base <= 0:
            errores['precio_base'] = 'El precio base debe ser mayor a cero.'
        if errores:
            raise ValidationError(errores)


class Habitacion(models.Model):
    ESTADOS = [
        ('DISPONIBLE', 'Disponible'),
        ('RESERVADA', 'Reservada'),
        ('OCUPADA', 'Ocupada'),
        ('LIMPIEZA', 'En limpieza'),
        ('MANTENIMIENTO', 'En mantenimiento'),
    ]

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='habitaciones',
    )
    tipo = models.ForeignKey(
        TipoHabitacion,
        on_delete=models.PROTECT,
        related_name='habitaciones',
    )
    numero = models.CharField(max_length=10)
    piso = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='DISPONIBLE',
    )

    def __str__(self):
        return f'{self.numero} - {self.hotel.nombre}'
