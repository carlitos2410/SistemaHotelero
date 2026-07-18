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

    class Meta:
        ordering = ['piso', 'numero']
        constraints = [
            models.UniqueConstraint(
                fields=['hotel', 'numero'],
                name='habitacion_hotel_numero_unico',
            ),
        ]

    def __str__(self):
        return f'{self.numero} - {self.hotel.nombre}'

    def clean(self):
        super().clean()
        errores = {}
        if self.piso is not None and self.piso < 1:
            errores['piso'] = 'El piso debe ser mayor a cero.'
        if errores:
            raise ValidationError(errores)


class HabitacionEstadoHistorial(models.Model):
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.CASCADE,
        related_name='historial_estados',
    )
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    motivo = models.CharField(max_length=250, blank=True)
    cambiado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    cambiado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cambiado_en', '-id']

    def __str__(self):
        return f'{self.habitacion}: {self.estado_anterior or "INICIAL"} -> {self.estado_nuevo}'
