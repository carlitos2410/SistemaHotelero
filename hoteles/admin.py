from django.contrib import admin
from .models import Hotel


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ruc', 'direccion', 'estrellas', 'telefono')
    search_fields = ('nombre', 'ruc')

    def has_add_permission(self, request):
        return not Hotel.objects.exists()
