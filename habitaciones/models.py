from django.db import models
from django.conf import settings
from hoteles.models import Hotel


class TipoHabitacion(models.Model):
    nombre = models.CharField(max_length=100)
    capacidad = models.PositiveIntegerField()
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    amenidades = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.nombre


class Habitacion(models.Model):
    ESTADOS = [
        ('DISPONIBLE', 'Disponible'),
        ('OCUPADA', 'Ocupada'),
        ('LIMPIEZA', 'Limpieza'),
        ('MANTENIMIENTO', 'Mantenimiento'),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='habitaciones')
    tipo = models.ForeignKey(TipoHabitacion, on_delete=models.CASCADE, related_name='habitaciones')
    numero = models.CharField(max_length=10)
    piso = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='DISPONIBLE')

    class Meta:
        unique_together = ('hotel', 'numero')

    def __str__(self):
        return f'Hab. {self.numero} - {self.hotel.nombre}'


class ObservacionMantenimiento(models.Model):
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.CASCADE,
        related_name='observaciones_mantenimiento'
    )
    observacion = models.TextField()
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observaciones_mantenimiento'
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']

    def __str__(self):
        return f'Mantenimiento Hab. {self.habitacion.numero} - {self.creado_en:%d/%m/%Y}'


class HabitacionEstadoHistorial(models.Model):
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.CASCADE,
        related_name='historial_estados',
    )
    estado_anterior = models.CharField(max_length=20, choices=Habitacion.ESTADOS, blank=True)
    estado_nuevo = models.CharField(max_length=20, choices=Habitacion.ESTADOS)
    cambiado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_estado_habitacion',
    )
    motivo = models.CharField(max_length=180, blank=True)
    cambiado_en = models.DateTimeField()

    class Meta:
        ordering = ['-cambiado_en', '-id']
        indexes = [
            models.Index(fields=['habitacion', '-cambiado_en'], name='hab_estado_fecha_idx'),
        ]

    def __str__(self):
        anterior = self.estado_anterior or 'INICIAL'
        return f'Hab. {self.habitacion.numero}: {anterior} -> {self.estado_nuevo}'
