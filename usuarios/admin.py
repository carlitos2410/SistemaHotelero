from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User


admin.site.site_header = 'Sistema Hotelero - Super Admin'
admin.site.site_title = 'Sistema Hotelero'
admin.site.index_title = 'Administracion del sistema'


class SistemaHoteleroUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'mostrar_roles', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')

    @admin.display(description='Roles')
    def mostrar_roles(self, obj):
        return ', '.join(obj.groups.values_list('name', flat=True)) or 'Sin rol'


admin.site.unregister(User)
admin.site.register(User, SistemaHoteleroUserAdmin)
