from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import (
    BuscarHuespedAPIView,
    CotizacionReservaAPIView,
    EstanciaViewSet,
    HabitacionViewSet,
    HabitacionesDisponiblesAPIView,
    ReservaViewSet,
    TipoHabitacionViewSet,
    reporte_ocupacion,
)


router = DefaultRouter()
router.register('tipos-habitacion', TipoHabitacionViewSet, basename='api-tipos-habitacion')
router.register('habitaciones', HabitacionViewSet, basename='api-habitaciones')
router.register('reservas', ReservaViewSet, basename='api-reservas')
router.register('estancias', EstanciaViewSet, basename='api-estancias')

urlpatterns = [
    path('huespedes/buscar/', BuscarHuespedAPIView.as_view(), name='api-huesped-buscar'),
    path('reservas/cotizar/', CotizacionReservaAPIView.as_view(), name='api-reserva-cotizar'),
    path('habitaciones/disponibles/', HabitacionesDisponiblesAPIView.as_view(), name='api-habitaciones-disponibles'),
    path('reportes/ocupacion/', reporte_ocupacion, name='api-reporte-ocupacion'),
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('', include(router.urls)),
]

