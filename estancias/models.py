from decimal import Decimal
from decimal import ROUND_HALF_UP

from django.conf import settings
from django.db import models

from habitaciones.models import Habitacion
from reservas.models import Reserva


def redondear_dinero(monto):
    return Decimal(monto or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ProductoServicio(models.Model):
    CATEGORIA_CHOICES = [
        ('RESTAURANTE', 'Restaurante'),
        ('LAVANDERIA', 'Lavanderia'),
        ('MINIBAR', 'Minibar'),
        ('OTRO', 'Otro'),
    ]

    nombre = models.CharField(max_length=120)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['categoria', 'nombre']

    def __str__(self):
        return f'{self.nombre} - S/ {self.precio}'


class ConfiguracionCobro(models.Model):
    POLITICA_CHOICES = [
        ('ESTADIA_REAL', 'Cobrar solo estadia real'),
        ('RESERVA_COMPLETA', 'Cobrar reserva completa'),
        ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad'),
    ]

    politica_checkout = models.CharField(
        max_length=30,
        choices=POLITICA_CHOICES,
        default='ESTADIA_REAL',
    )
    porcentaje_penalidad_salida_anticipada = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text='Porcentaje aplicado sobre las noches reservadas no usadas.',
    )
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuracion de cobro'
        verbose_name_plural = 'Configuraciones de cobro'

    def __str__(self):
        return self.get_politica_checkout_display()

    @classmethod
    def actual(cls):
        config = cls.objects.filter(activo=True).order_by('-actualizado_en').first()
        if config:
            return config
        return cls.objects.create()


class Estancia(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('FINALIZADA', 'Finalizada'),
    ]
    TIPO_CHECKIN_CHOICES = [
        ('NORMAL', 'Normal'),
        ('ANTICIPADO', 'Anticipado'),
    ]
    TIPO_CHECKOUT_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('NORMAL', 'Normal'),
        ('TARDIO', 'Tardio'),
    ]

    reserva = models.OneToOneField(
        Reserva,
        on_delete=models.CASCADE,
        related_name='estancia'
    )
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.CASCADE,
        related_name='estancias'
    )
    fecha_checkin = models.DateTimeField()
    fecha_checkout = models.DateTimeField(null=True, blank=True)
    precio_final = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tipo_checkin = models.CharField(max_length=20, choices=TIPO_CHECKIN_CHOICES, default='NORMAL')
    tipo_checkout = models.CharField(max_length=20, choices=TIPO_CHECKOUT_CHOICES, default='PENDIENTE')
    cargo_early_checkin = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cargo_late_checkout = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    politica_cobro_checkout = models.CharField(max_length=30, blank=True, default='')
    noches_reservadas = models.PositiveIntegerField(default=1)
    noches_reales = models.PositiveIntegerField(default=1)
    monto_estadia_real = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cargo_penalidad_salida_anticipada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='ACTIVA')

    def __str__(self):
        return f'Estancia #{self.id} - {self.reserva.huesped}'


class CargoEstancia(models.Model):
    TIPO_CHOICES = [
        ('HABITACION', 'Habitacion'),
        ('RESTAURANTE', 'Restaurante'),
        ('LAVANDERIA', 'Lavanderia'),
        ('MINIBAR', 'Minibar'),
        ('EARLY_CHECKIN', 'Early check-in'),
        ('LATE_CHECKOUT', 'Late check-out'),
        ('PENALIDAD', 'Penalidad'),
        ('OTRO', 'Otro'),
    ]

    estancia = models.ForeignKey(
        Estancia,
        on_delete=models.CASCADE,
        related_name='cargos'
    )
    producto_servicio = models.ForeignKey(
        ProductoServicio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargos'
    )
    concepto = models.CharField(max_length=150)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='OTRO')
    pagado = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.concepto} - S/ {self.monto}'


class Folio(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
    ]

    estancia = models.OneToOneField(
        Estancia,
        on_delete=models.CASCADE,
        related_name='folio'
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    def calcular_totales(self):
        subtotal_cargos = sum((cargo.monto for cargo in self.estancia.cargos.all()), Decimal('0.00'))
        subtotal = redondear_dinero(self.estancia.precio_final + subtotal_cargos)
        igv = redondear_dinero(subtotal * Decimal('0.18'))
        total = redondear_dinero(subtotal + igv)

        self.subtotal = subtotal
        self.igv = igv
        self.total = total

    @property
    def total_pagado(self):
        pagos_normalizados = sum(
            (pago.monto for pago in self.pagos_normalizados.filter(estado='APROBADO')),
            Decimal('0.00')
        )
        return redondear_dinero(pagos_normalizados)

    @property
    def saldo_pendiente(self):
        saldo = redondear_dinero(self.total - self.total_pagado)
        return max(saldo, Decimal('0.00'))

    def __str__(self):
        return f'Folio #{self.id} - Estancia #{self.estancia.id}'


class MetodoPago(models.Model):
    TIPO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('BILLETERA', 'Billetera digital'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]

    nombre = models.CharField(max_length=80, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return self.nombre


class Pago(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('ANULADO', 'Anulado'),
    ]

    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name='pagos_normalizados')
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    numero_operacion = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='APROBADO')
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos_registrados'
    )
    observacion = models.CharField(max_length=180, blank=True)
    es_simulado = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado_en']

    def __str__(self):
        return f'Pago #{self.id} - S/ {self.monto}'


class Comprobante(models.Model):
    TIPO_CHOICES = [
        ('BOLETA', 'Boleta'),
        ('FACTURA', 'Factura'),
    ]
    ESTADO_CHOICES = [
        ('EMITIDO', 'Emitido'),
        ('ANULADO', 'Anulado'),
        ('PENDIENTE', 'Pendiente'),
    ]

    pago = models.OneToOneField(Pago, on_delete=models.CASCADE, related_name='comprobante')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    serie = models.CharField(max_length=10, default='B001')
    numero = models.PositiveIntegerField()
    cliente_documento = models.CharField(max_length=20)
    cliente_nombre = models.CharField(max_length=180)
    cliente_direccion = models.CharField(max_length=220, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='EMITIDO')
    fecha_emision = models.DateTimeField(auto_now_add=True)
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comprobantes_emitidos'
    )

    class Meta:
        ordering = ['-fecha_emision']
        unique_together = ('tipo', 'serie', 'numero')

    @property
    def correlativo(self):
        return f'{self.serie}-{self.numero:06d}'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.correlativo}'


class MovimientoCaja(models.Model):
    TIPO_CHOICES = [
        ('INGRESO', 'Ingreso'),
        ('EGRESO', 'Egreso'),
    ]
    CONCEPTO_CHOICES = [
        ('PAGO_FOLIO', 'Pago de folio'),
        ('ANULACION', 'Anulacion'),
        ('AJUSTE', 'Ajuste'),
    ]

    pago = models.OneToOneField(
        Pago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimiento_caja'
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='INGRESO')
    concepto = models.CharField(max_length=30, choices=CONCEPTO_CHOICES, default='PAGO_FOLIO')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name='movimientos_caja')
    numero_operacion = models.CharField(max_length=100, blank=True)
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_caja'
    )
    fecha = models.DateTimeField(auto_now_add=True)
    observacion = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.get_tipo_display()} S/ {self.monto}'
