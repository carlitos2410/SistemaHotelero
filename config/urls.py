from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    path('habitaciones/', include('habitaciones.urls')),
    path('reservas/', include('reservas.urls')),
    path('estancias/', include('estancias.urls')),
    path('reportes/', include('reportes.urls')),
    path('api/', include('api.urls')),

    path('', include('usuarios.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
