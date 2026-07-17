from django.contrib import admin
from .models import Huesped, Promocion, Reserva, ReservaEstadoHistorial, Tarifa


@admin.register(Huesped)
class HuespedAdmin(admin.ModelAdmin):
    list_display = ('tipo_doc', 'num_doc', 'nombres', 'apellidos', 'email', 'telefono', 'nacionalidad')
    search_fields = ('num_doc', 'nombres', 'apellidos')


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_habitacion', 'precio_noche', 'fecha_inicio', 'fecha_fin')
    list_filter = ('tipo_habitacion', 'fecha_inicio', 'fecha_fin')
    search_fields = ('nombre',)


@admin.register(Promocion)
class PromocionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_habitacion', 'porcentaje_descuento', 'fecha_inicio', 'fecha_fin', 'activo')
    list_filter = ('activo', 'tipo_habitacion', 'fecha_inicio', 'fecha_fin')
    search_fields = ('nombre', 'descripcion')


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'hotel', 'huesped', 'habitacion', 'fecha_entrada', 'fecha_salida', 'estado', 'precio_total')
    list_filter = ('estado', 'hotel', 'fecha_entrada', 'fecha_salida')
    search_fields = ('huesped__nombres', 'huesped__apellidos')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReservaEstadoHistorial)
class ReservaEstadoHistorialAdmin(admin.ModelAdmin):
    list_display = ('reserva', 'estado_anterior', 'estado_nuevo', 'cambiado_por', 'cambiado_en')
    list_filter = ('estado_nuevo', 'cambiado_en')
    search_fields = ('reserva__id', 'reserva__huesped__nombres', 'reserva__huesped__apellidos', 'motivo')
    readonly_fields = (
        'reserva', 'estado_anterior', 'estado_nuevo', 'cambiado_por', 'motivo', 'cambiado_en',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
