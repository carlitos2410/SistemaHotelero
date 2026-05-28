from django.db import models
from hoteles.models import Hotel
from habitaciones.models import Habitacion, TipoHabitacion


class Huesped(models.Model):
    TIPO_DOC_CHOICES = [
        ('DNI', 'DNI'),
        ('PASAPORTE', 'Pasaporte'),
        ('CE', 'Carné de Extranjería'),
    ]

    tipo_doc = models.CharField(max_length=20, choices=TIPO_DOC_CHOICES)
    num_doc = models.CharField(max_length=20, unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    nacionalidad = models.CharField(max_length=50)

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'


class Tarifa(models.Model):
    tipo_habitacion = models.ForeignKey(
        TipoHabitacion,
        on_delete=models.CASCADE,
        related_name='tarifas'
    )
    nombre = models.CharField(max_length=100)
    precio_noche = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    def __str__(self):
        return f'{self.nombre} - {self.tipo_habitacion.nombre}'


class Promocion(models.Model):
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    tipo_habitacion = models.ForeignKey(
        TipoHabitacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promociones'
    )
    porcentaje_descuento = models.DecimalField(max_digits=5, decimal_places=2)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['-activo', 'fecha_inicio', 'nombre']

    def __str__(self):
        return f'{self.nombre} - {self.porcentaje_descuento}%'


class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CONFIRMADA', 'Confirmada'),
        ('CHECKIN', 'Check-in'),
        ('CHECKOUT', 'Check-out'),
        ('CANCELADA', 'Cancelada'),
    ]

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='reservas'
    )
    huesped = models.ForeignKey(
        Huesped,
        on_delete=models.CASCADE,
        related_name='reservas'
    )
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservas'
    )
    fecha_entrada = models.DateField()
    fecha_salida = models.DateField()
    num_adultos = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    origen = models.CharField(max_length=100, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Reserva #{self.id} - {self.huesped}'

    @property
    def total_acompanantes(self):
        return self.acompanantes.count()


class Acompanante(models.Model):
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.CASCADE,
        related_name='acompanantes'
    )
    tipo_doc = models.CharField(max_length=20, choices=Huesped.TIPO_DOC_CHOICES)
    num_doc = models.CharField(max_length=20)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    nacionalidad = models.CharField(max_length=50, blank=True)
    parentesco = models.CharField(max_length=50, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'
