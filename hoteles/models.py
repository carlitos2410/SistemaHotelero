from django.db import models


class Hotel(models.Model):
    nombre = models.CharField(max_length=150)
    ruc = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=255)
    estrellas = models.PositiveIntegerField()
    telefono = models.CharField(max_length=20)

    def __str__(self):
        return self.nombre
