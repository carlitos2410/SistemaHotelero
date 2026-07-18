from django.core.exceptions import ValidationError
from django.db import models


class Hotel(models.Model):
    nombre = models.CharField(max_length=150)
    ruc = models.CharField(max_length=11, unique=True)
    direccion = models.CharField(max_length=250)
    estrellas = models.PositiveIntegerField(default=3)
    telefono = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        errores = {}
        if self.estrellas is not None and not 1 <= self.estrellas <= 5:
            errores['estrellas'] = 'La cantidad de estrellas debe estar entre 1 y 5.'
        if self.ruc and len(self.ruc) != 11:
            errores['ruc'] = 'El RUC debe tener exactamente 11 digitos.'
        if errores:
            raise ValidationError(errores)
