from django.contrib import admin
from .models import (
    CargoEstancia,
    Comprobante,
    ConfiguracionCobro,
    CorrelativoComprobante,
    Estancia,
    Folio,
    MetodoPago,
    MovimientoCaja,
    Pago,
    ProrrogaEstancia,
    ProductoServicio,
)


class RegistroFinancieroSoloLecturaAdmin:
    """Los registros operativos se generan desde servicios transaccionales."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CorrelativoComprobante)
class CorrelativoComprobanteAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('tipo', 'serie', 'ultimo_numero')


@admin.register(ProrrogaEstancia)
class ProrrogaEstanciaAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('estancia', 'fecha_salida_anterior', 'fecha_salida_nueva', 'noches_adicionales', 'monto', 'autorizado_por', 'creado_en')
    list_filter = ('fecha_salida_nueva', 'creado_en')
    search_fields = ('estancia__reserva__huesped__nombres', 'estancia__reserva__huesped__apellidos', 'motivo')


@admin.register(ProductoServicio)
class ProductoServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio', 'activo')
    list_filter = ('categoria', 'activo')
    search_fields = ('nombre',)


@admin.register(ConfiguracionCobro)
class ConfiguracionCobroAdmin(admin.ModelAdmin):
    list_display = (
        'politica_checkout',
        'porcentaje_garantia_reserva',
        'horas_plazo_pago_garantia',
        'porcentaje_igv',
        'porcentaje_early_checkin',
        'porcentaje_late_checkout',
        'porcentaje_penalidad_salida_anticipada',
        'horas_cancelacion_gratuita',
        'porcentaje_retencion_cancelacion_tardia',
        'actualizado_en',
    )
    list_filter = ('politica_checkout',)
    readonly_fields = ('politica_checkout',)

    def has_add_permission(self, request):
        return not ConfiguracionCobro.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Estancia)
class EstanciaAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = (
        'id',
        'reserva',
        'habitacion',
        'fecha_checkin',
        'tipo_checkin',
        'fecha_checkout',
        'tipo_checkout',
        'precio_final',
        'politica_cobro_checkout',
        'noches_reservadas',
        'noches_reales',
        'monto_estadia_real',
        'cargo_early_checkin',
        'cargo_late_checkout',
        'cargo_penalidad_salida_anticipada',
        'estado',
    )
    list_filter = ('estado', 'tipo_checkin', 'tipo_checkout', 'fecha_checkin')
    search_fields = ('reserva__huesped__nombres', 'reserva__huesped__apellidos')


@admin.register(CargoEstancia)
class CargoEstanciaAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('id', 'estancia', 'concepto', 'cantidad', 'precio_unitario', 'monto', 'fecha', 'tipo', 'pagado')
    list_filter = ('tipo', 'pagado', 'fecha')
    search_fields = ('concepto',)


@admin.register(Folio)
class FolioAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('id', 'estancia', 'subtotal', 'porcentaje_igv', 'igv', 'total', 'total_pagado', 'saldo_pendiente', 'estado')
    list_filter = ('estado',)


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre',)


@admin.register(Pago)
class PagoAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('id', 'folio', 'reserva', 'metodo_pago', 'monto', 'numero_operacion', 'estado', 'usuario_responsable', 'creado_en')
    list_filter = ('estado', 'metodo_pago', 'creado_en')
    search_fields = (
        'numero_operacion',
        'folio__estancia__reserva__huesped__nombres',
        'folio__estancia__reserva__huesped__apellidos',
        'reserva__huesped__nombres',
        'reserva__huesped__apellidos',
    )


@admin.register(Comprobante)
class ComprobanteAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('correlativo', 'tipo', 'cliente_nombre', 'cliente_documento', 'estado', 'fecha_emision')
    list_filter = ('tipo', 'estado', 'fecha_emision')
    search_fields = ('serie', 'numero', 'cliente_documento', 'cliente_nombre')


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(RegistroFinancieroSoloLecturaAdmin, admin.ModelAdmin):
    list_display = ('id', 'tipo', 'concepto', 'monto', 'metodo_pago', 'usuario_responsable', 'fecha')
    list_filter = ('tipo', 'concepto', 'metodo_pago', 'fecha')
    search_fields = ('numero_operacion', 'observacion')
