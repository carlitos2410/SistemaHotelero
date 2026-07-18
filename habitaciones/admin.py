from django.contrib import admin

from .models import Habitacion, HabitacionEstadoHistorial, ObservacionMantenimiento, TipoHabitacion


@admin.register(TipoHabitacion)
class TipoHabitacionAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'capacidad', 'precio_base']
    search_fields = ['nombre']


@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ['numero', 'hotel', 'tipo', 'piso', 'estado']
    list_filter = ['estado', 'hotel', 'tipo', 'piso']
    search_fields = ['numero']
    list_select_related = ['hotel', 'tipo']


@admin.register(HabitacionEstadoHistorial)
class HabitacionEstadoHistorialAdmin(admin.ModelAdmin):
    list_display = ['habitacion', 'estado_anterior', 'estado_nuevo', 'cambiado_por', 'cambiado_en']
    list_filter = ['estado_nuevo', 'cambiado_en']
    list_select_related = ['habitacion', 'cambiado_por']
    readonly_fields = ['cambiado_en']


@admin.register(ObservacionMantenimiento)
class ObservacionMantenimientoAdmin(admin.ModelAdmin):
    list_display = ['habitacion', 'observacion', 'creado_en']
    list_filter = ['creado_en']
    list_select_related = ['habitacion']
    readonly_fields = ['creado_en']
