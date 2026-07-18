from django.db import models


class Hotel(models.Model):
    nombre = models.CharField(max_length=150)
    ruc = models.CharField(max_length=11, unique=True)
    direccion = models.CharField(max_length=250)
    estrellas = models.PositiveIntegerField(default=3)
    telefono = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
