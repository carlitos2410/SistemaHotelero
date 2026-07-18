from django.db import models


class TipoHabitacion(models.Model):
    nombre = models.CharField(max_length=80)
    capacidad = models.PositiveIntegerField(default=2)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    amenidades = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.nombre
