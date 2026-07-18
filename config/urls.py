from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    path('hoteles/', include('hoteles.urls')),
    path('habitaciones/', include('habitaciones.urls')),
    path('reservas/', include('reservas.urls')),
    path('estancias/', include('estancias.urls')),
    path('reportes/', include('reportes.urls')),
    path('api/', include('api.urls')),

    path('', include('usuarios.urls')),
]
