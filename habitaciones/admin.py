from django.contrib import admin
from .models import Habitacion, ObservacionMantenimiento, TipoHabitacion


@admin.register(TipoHabitacion)
class TipoHabitacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'capacidad', 'precio_base')
    search_fields = ('nombre',)


@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ('numero', 'hotel', 'tipo', 'piso', 'estado')
    list_filter = ('estado', 'hotel', 'tipo', 'piso')
    search_fields = ('numero',)


@admin.register(ObservacionMantenimiento)
class ObservacionMantenimientoAdmin(admin.ModelAdmin):
    list_display = ('habitacion', 'creado_por', 'creado_en')
    list_filter = ('creado_en',)
    search_fields = ('habitacion__numero', 'observacion')
