from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q, Value
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

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__gte=F('fecha_inicio')),
                name='tarifa_fin_no_anterior_inicio',
            ),
            models.CheckConstraint(
                condition=Q(precio_noche__gt=0),
                name='tarifa_precio_positivo',
            ),
            ExclusionConstraint(
                name='tarifa_tipo_sin_temporadas_solapadas',
                expressions=[
                    (F('tipo_habitacion'), RangeOperators.EQUAL),
                    (
                        Func(
                            F('fecha_inicio'),
                            F('fecha_fin'),
                            Value('[]'),
                            function='DATERANGE',
                            output_field=DateRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.tipo_habitacion.nombre}'

    def clean(self):
        super().clean()
        errores = {}
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            errores['fecha_fin'] = 'La fecha final debe ser igual o posterior a la fecha inicial.'
        if self.precio_noche is not None and self.precio_noche <= 0:
            errores['precio_noche'] = 'El precio por noche debe ser mayor a cero.'
        if errores:
            raise ValidationError(errores)


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
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__gte=F('fecha_inicio')),
                name='promocion_fin_no_anterior_inicio',
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_descuento__gt=0) & Q(porcentaje_descuento__lte=100),
                name='promocion_porcentaje_valido',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.porcentaje_descuento}%'

    def clean(self):
        super().clean()
        errores = {}
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            errores['fecha_fin'] = 'La fecha final debe ser igual o posterior a la fecha inicial.'
        if self.porcentaje_descuento is not None and not 0 < self.porcentaje_descuento <= 100:
            errores['porcentaje_descuento'] = 'El descuento debe ser mayor a 0 y no superar el 100%.'
        if errores:
            raise ValidationError(errores)


class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CONFIRMADA', 'Confirmada'),
        ('CHECKIN', 'Check-in'),
        ('CHECKOUT', 'Check-out'),
        ('CANCELADA', 'Cancelada'),
        ('NO_SHOW', 'No-show'),
    ]
    POLITICA_COBRO_CHOICES = [
        ('ESTADIA_REAL', 'Cobrar solo estadia real'),
        ('RESERVA_COMPLETA', 'Cobrar reserva completa'),
        ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad'),
    ]
    TIPO_CANCELACION_CHOICES = [
        ('', 'Sin cancelacion'),
        ('SIN_PAGO', 'Cancelacion sin pago'),
        ('GRATUITA', 'Cancelacion dentro del plazo'),
        ('TARDIA', 'Cancelacion tardia con retencion'),
        ('VENCIMIENTO_PAGO', 'Vencimiento del plazo de pago'),
    ]

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.PROTECT,
        related_name='reservas'
    )
    huesped = models.ForeignKey(
        Huesped,
        on_delete=models.PROTECT,
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
    precio_sin_descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_promocion = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    porcentaje_adelanto = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    monto_adelanto_requerido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_limite_pago = models.DateTimeField(null=True, blank=True)
    horas_cancelacion_gratuita = models.PositiveIntegerField(default=48)
    porcentaje_retencion_cancelacion_tardia = models.DecimalField(
        max_digits=5, decimal_places=2, default=100
    )
    tipo_cancelacion = models.CharField(
        max_length=30, choices=TIPO_CANCELACION_CHOICES, blank=True, default=''
    )
    motivo_cancelacion = models.CharField(max_length=250, blank=True)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservas_canceladas',
    )
    monto_reembolsado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_retenido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    detalle_tarifa = models.JSONField(default=list, blank=True)
    politica_cobro_checkout = models.CharField(
        max_length=30,
        choices=POLITICA_COBRO_CHOICES,
        blank=True,
        default='',
    )
    porcentaje_penalidad_salida_anticipada = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
    )
    porcentaje_igv = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    porcentaje_early_checkin = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    porcentaje_late_checkout = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    origen = models.CharField(max_length=100, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['estado', 'fecha_entrada', 'fecha_salida'], name='res_estado_fechas_idx'),
            models.Index(fields=['-creado_en'], name='res_creado_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_salida__gt=F('fecha_entrada')),
                name='reserva_salida_posterior_entrada',
            ),
            models.CheckConstraint(
                condition=Q(num_adultos__gt=0),
                name='reserva_adultos_positivos',
            ),
            models.CheckConstraint(
                condition=Q(precio_total__gte=0),
                name='reserva_precio_no_negativo',
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_adelanto__gte=0) & Q(porcentaje_adelanto__lte=100),
                name='reserva_porcentaje_adelanto_valido',
            ),
            models.CheckConstraint(
                condition=Q(monto_adelanto_requerido__gte=0),
                name='reserva_adelanto_no_negativo',
            ),
            models.CheckConstraint(
                condition=(
                    Q(porcentaje_retencion_cancelacion_tardia__gte=0)
                    & Q(porcentaje_retencion_cancelacion_tardia__lte=100)
                ),
                name='reserva_retencion_cancelacion_valida',
            ),
            models.CheckConstraint(
                condition=Q(monto_reembolsado__gte=0),
                name='reserva_reembolso_no_negativo',
            ),
            models.CheckConstraint(
                condition=Q(monto_retenido__gte=0),
                name='reserva_retencion_no_negativa',
            ),
            models.CheckConstraint(
                condition=Q(precio_sin_descuento__gte=0),
                name='reserva_precio_base_no_negativo',
            ),
            models.CheckConstraint(
                condition=Q(descuento_promocion__gte=0),
                name='reserva_descuento_no_negativo',
            ),
            models.CheckConstraint(
                condition=(
                    Q(porcentaje_penalidad_salida_anticipada__gte=0)
                    & Q(porcentaje_penalidad_salida_anticipada__lte=100)
                ),
                name='reserva_penalidad_porcentaje_valido',
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_igv__gte=0) & Q(porcentaje_igv__lte=100),
                name='reserva_porcentaje_igv_valido',
            ),
            models.CheckConstraint(
                condition=(
                    Q(porcentaje_early_checkin__gte=0)
                    & Q(porcentaje_early_checkin__lte=100)
                ),
                name='reserva_early_checkin_valido',
            ),
            models.CheckConstraint(
                condition=(
                    Q(porcentaje_late_checkout__gte=0)
                    & Q(porcentaje_late_checkout__lte=100)
                ),
                name='reserva_late_checkout_valido',
            ),
            ExclusionConstraint(
                name='reserva_habitacion_sin_solapamiento_activo',
                expressions=[
                    (F('habitacion'), RangeOperators.EQUAL),
                    (
                        Func(
                            F('fecha_entrada'),
                            F('fecha_salida'),
                            Value('[)'),
                            function='DATERANGE',
                            output_field=DateRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(
                    habitacion__isnull=False,
                    estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
                ),
            ),
        ]

    @property
    def total_adelantado(self):
        from decimal import Decimal, ROUND_HALF_UP
        total = sum(
            (pago.monto for pago in self.adelantos.all() if pago.estado == 'APROBADO'),
            Decimal('0.00'),
        )
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def saldo_adelanto(self):
        from decimal import Decimal, ROUND_HALF_UP
        saldo = Decimal(self.monto_adelanto_requerido or 0) - self.total_adelantado
        return max(saldo, Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def garantia_completa(self):
        return self.monto_adelanto_requerido > 0 and self.saldo_adelanto <= 0

    @property
    def total_acompanantes(self):
        return self.acompanantes.count()

    def __str__(self):
        return f'Reserva #{self.id} - {self.huesped}'

    def clean(self):
        super().clean()
        errores = {}

        if self.fecha_entrada and self.fecha_salida and self.fecha_salida <= self.fecha_entrada:
            errores['fecha_salida'] = 'La fecha de salida debe ser posterior a la fecha de entrada.'

        if self.habitacion_id:
            if self.hotel_id and self.hotel_id != self.habitacion.hotel_id:
                errores['hotel'] = 'El hotel de la reserva debe coincidir con el hotel de la habitacion.'
            if self.num_adultos and self.num_adultos > self.habitacion.tipo.capacidad:
                errores['num_adultos'] = (
                    f'La habitacion permite maximo {self.habitacion.tipo.capacidad} persona(s).'
                )

        if errores:
            raise ValidationError(errores)


class ReservaEstadoHistorial(models.Model):
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.PROTECT,
        related_name='historial_estados',
    )
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20, choices=Reserva.ESTADO_CHOICES)
    cambiado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_estado_reserva',
    )
    motivo = models.CharField(max_length=250, blank=True)
    cambiado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cambiado_en', '-id']

    def __str__(self):
        return f'Reserva #{self.reserva_id}: {self.estado_anterior or "INICIAL"} -> {self.estado_nuevo}'

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
