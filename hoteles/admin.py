from django.contrib import admin

from .models import Hotel


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'ruc', 'direccion', 'estrellas', 'telefono', 'activo']
    list_filter = ['activo', 'estrellas']
    search_fields = ['nombre', 'ruc', 'direccion']
    readonly_fields = ['creado_en', 'actualizado_en']
