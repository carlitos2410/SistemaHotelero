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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(activo=False) | models.Q(precio__gt=0),
                name='producto_activo_precio_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - S/ {self.precio}'

    def clean(self):
        super().clean()
        if self.activo and self.precio is not None and self.precio <= 0:
            from django.core.exceptions import ValidationError
            raise ValidationError({'precio': 'Un producto o servicio activo debe tener un precio mayor a cero.'})


class ConfiguracionCobro(models.Model):
    POLITICA_FIJA = 'ESTADIA_REAL_PENALIDAD'
    POLITICA_CHOICES = [
        ('ESTADIA_REAL', 'Cobrar solo estadia real'),
        ('RESERVA_COMPLETA', 'Cobrar reserva completa'),
        ('ESTADIA_REAL_PENALIDAD', 'Cobrar estadia real mas penalidad'),
    ]

    politica_checkout = models.CharField(
        max_length=30,
        choices=POLITICA_CHOICES,
        default='ESTADIA_REAL_PENALIDAD',
    )
    porcentaje_penalidad_salida_anticipada = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text='Porcentaje aplicado sobre las noches reservadas no usadas.',
    )
    horas_cancelacion_gratuita = models.PositiveIntegerField(
        default=48,
        help_text='Horas minimas antes del check-in para devolver el adelanto.',
    )
    porcentaje_retencion_cancelacion_tardia = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text='Porcentaje del adelanto que retiene el hotel por cancelacion tardia.',
    )
    porcentaje_garantia_reserva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text='Porcentaje del total que debe pagarse para confirmar una reserva.',
    )
    horas_plazo_pago_garantia = models.PositiveIntegerField(
        default=24,
        help_text='Horas disponibles para completar la garantia antes de liberar la habitacion.',
    )
    porcentaje_igv = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=18,
        help_text='IGV incluido en las tarifas y productos del hotel.',
    )
    porcentaje_early_checkin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5,
        help_text='Recargo sobre una noche por ingresar antes de la hora de check-in.',
    )
    porcentaje_late_checkout = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text='Recargo sobre una noche por salir después de la hora de check-out.',
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuracion de cobro'
        verbose_name_plural = 'Configuraciones de cobro'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(porcentaje_retencion_cancelacion_tardia__gte=0)
                    & models.Q(porcentaje_retencion_cancelacion_tardia__lte=100)
                ),
                name='config_retencion_cancelacion_valida',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(porcentaje_garantia_reserva__gt=0)
                    & models.Q(porcentaje_garantia_reserva__lte=100)
                ),
                name='config_garantia_reserva_valida',
            ),
            models.CheckConstraint(
                condition=models.Q(horas_plazo_pago_garantia__gt=0),
                name='config_plazo_garantia_positivo',
            ),
            models.CheckConstraint(
                condition=models.Q(porcentaje_igv__gte=0) & models.Q(porcentaje_igv__lte=100),
                name='config_igv_valido',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(porcentaje_early_checkin__gte=0)
                    & models.Q(porcentaje_early_checkin__lte=100)
                ),
                name='config_early_checkin_valido',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(porcentaje_late_checkout__gte=0)
                    & models.Q(porcentaje_late_checkout__lte=100)
                ),
                name='config_late_checkout_valido',
            ),
        ]

    def __str__(self):
        return self.get_politica_checkout_display()

    @classmethod
    def actual(cls):
        config = cls.objects.order_by('id').first()
        if config:
            if config.politica_checkout != cls.POLITICA_FIJA:
                config.politica_checkout = cls.POLITICA_FIJA
                config.save(update_fields=['politica_checkout', 'actualizado_en'])
            return config
        return cls.objects.create()

    def save(self, *args, **kwargs):
        self.politica_checkout = self.POLITICA_FIJA
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'politica_checkout'}
        super().save(*args, **kwargs)


class Estancia(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('FINALIZADA', 'Finalizada'),
    ]
    TIPO_CHECKIN_CHOICES = [
        ('NORMAL', 'Normal'),
        ('ANTICIPADO', 'Anticipado por hora'),
        ('ANTICIPADO_FECHA', 'Anticipado por fecha'),
        ('LLEGADA_TARDIA', 'Llegada tardia'),
    ]
    TIPO_CHECKOUT_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('NORMAL', 'Normal'),
        ('TARDIO', 'Tardio'),
        ('PRORROGA', 'Prorroga'),
    ]

    reserva = models.OneToOneField(
        Reserva,
        on_delete=models.PROTECT,
        related_name='estancia'
    )
    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.PROTECT,
        related_name='estancias'
    )
    fecha_checkin = models.DateTimeField()
    fecha_checkout = models.DateTimeField(null=True, blank=True)
    fecha_entrada_programada = models.DateField(null=True, blank=True)
    fecha_salida_programada = models.DateField(null=True, blank=True)
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

    class Meta:
        indexes = [
            models.Index(fields=['habitacion', '-fecha_checkout'], name='est_hab_checkout_idx'),
            models.Index(fields=['estado', 'fecha_salida_programada'], name='est_estado_salida_idx'),
        ]

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
        ('NOCHE_ADICIONAL', 'Noche adicional'),
        ('PENALIDAD', 'Penalidad'),
        ('OTRO', 'Otro'),
    ]
    TIPOS_MANUALES = ['RESTAURANTE', 'LAVANDERIA', 'MINIBAR', 'OTRO']

    estancia = models.ForeignKey(
        Estancia,
        on_delete=models.PROTECT,
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

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name='cargo_cantidad_positiva'),
            models.CheckConstraint(condition=models.Q(precio_unitario__gte=0), name='cargo_precio_no_negativo'),
            models.CheckConstraint(condition=models.Q(monto__gte=0), name='cargo_monto_no_negativo'),
        ]

    def __str__(self):
        return f'{self.concepto} - S/ {self.monto}'


class ProrrogaEstancia(models.Model):
    estancia = models.ForeignKey(Estancia, on_delete=models.PROTECT, related_name='prorrogas')
    fecha_salida_anterior = models.DateField()
    fecha_salida_nueva = models.DateField()
    noches_adicionales = models.PositiveIntegerField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prorrogas_autorizadas',
    )
    motivo = models.CharField(max_length=180, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']

    def __str__(self):
        return f'Prorroga estancia #{self.estancia_id} hasta {self.fecha_salida_nueva}'


class Folio(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
    ]

    estancia = models.OneToOneField(
        Estancia,
        on_delete=models.PROTECT,
        related_name='folio'
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igv = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    porcentaje_igv = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(subtotal__gte=0), name='folio_subtotal_no_negativo'),
            models.CheckConstraint(condition=models.Q(igv__gte=0), name='folio_igv_no_negativo'),
            models.CheckConstraint(condition=models.Q(total__gte=0), name='folio_total_no_negativo'),
            models.CheckConstraint(
                condition=models.Q(total=models.F('subtotal') + models.F('igv')),
                name='folio_total_cuadra_subtotal_igv',
            ),
            models.CheckConstraint(
                condition=models.Q(porcentaje_igv__gte=0) & models.Q(porcentaje_igv__lte=100),
                name='folio_porcentaje_igv_valido',
            ),
        ]

    def calcular_totales(self):
        subtotal_cargos = sum((cargo.monto for cargo in self.estancia.cargos.all()), Decimal('0.00'))
        total = redondear_dinero(self.estancia.precio_final + subtotal_cargos)
        # Las tarifas y productos del hotel son precios de venta con IGV incluido.
        factor_igv = Decimal('1.00') + Decimal(self.porcentaje_igv or 0) / Decimal('100')
        subtotal = redondear_dinero(total / factor_igv)
        igv = redondear_dinero(total - subtotal)

        self.subtotal = subtotal
        self.igv = igv
        self.total = total
        self.estado = 'PAGADO' if self.total <= self.total_pagado else 'PENDIENTE'

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

    def save(self, *args, **kwargs):
        if self._state.adding and self.estancia_id:
            self.porcentaje_igv = self.estancia.reserva.porcentaje_igv
        super().save(*args, **kwargs)


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

    folio = models.ForeignKey(
        Folio,
        on_delete=models.PROTECT,
        related_name='pagos_normalizados',
        null=True,
        blank=True,
    )
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.PROTECT,
        related_name='adelantos',
        null=True,
        blank=True,
    )
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
        indexes = [
            models.Index(fields=['estado', '-creado_en'], name='pago_estado_fecha_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name='pago_monto_positivo'),
            models.CheckConstraint(
                condition=models.Q(folio__isnull=False) | models.Q(reserva__isnull=False),
                name='pago_tiene_destino',
            ),
        ]

    def __str__(self):
        return f'Pago #{self.id} - S/ {self.monto}'

    @property
    def total_reembolsado(self):
        total = sum(
            (
                movimiento.monto
                for movimiento in self.movimientos_caja.all()
                if movimiento.tipo == 'EGRESO' and movimiento.concepto == 'DEVOLUCION_RESERVA'
            ),
            Decimal('0.00'),
        )
        return redondear_dinero(total)

    @property
    def monto_neto(self):
        return max(redondear_dinero(self.monto - self.total_reembolsado), Decimal('0.00'))


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

    pago = models.OneToOneField(Pago, on_delete=models.PROTECT, related_name='comprobante')
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
        constraints = [
            models.CheckConstraint(condition=models.Q(numero__gt=0), name='comprobante_numero_positivo'),
        ]

    @property
    def correlativo(self):
        return f'{self.serie}-{self.numero:06d}'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.correlativo}'


class CorrelativoComprobante(models.Model):
    tipo = models.CharField(max_length=20, choices=Comprobante.TIPO_CHOICES)
    serie = models.CharField(max_length=10)
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('tipo', 'serie')

    def __str__(self):
        return f'{self.tipo} {self.serie}: {self.ultimo_numero}'


class MovimientoCaja(models.Model):
    TIPO_CHOICES = [
        ('INGRESO', 'Ingreso'),
        ('EGRESO', 'Egreso'),
    ]
    CONCEPTO_CHOICES = [
        ('PAGO_FOLIO', 'Pago de folio'),
        ('ADELANTO_RESERVA', 'Adelanto de reserva'),
        ('DEVOLUCION_RESERVA', 'Devolucion de reserva'),
        ('ANULACION', 'Anulacion'),
        ('AJUSTE', 'Ajuste'),
    ]

    pago = models.ForeignKey(
        Pago,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_caja'
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
        indexes = [
            models.Index(fields=['tipo', '-fecha'], name='mov_tipo_fecha_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name='movimiento_caja_monto_positivo'),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} S/ {self.monto}'
