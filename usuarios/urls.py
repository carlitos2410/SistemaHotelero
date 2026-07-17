from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView

from .views import (
    administrador_dashboard,
    admin_maestro_crear,
    admin_maestro_editar,
    admin_maestro_lista,
    buscar_disponibilidad,
    gerencia_dashboard,
    inicio,
    limpieza_dashboard,
    nueva_reserva,
    recepcion_dashboard,
)


urlpatterns = [
    path('login/', LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', inicio, name='inicio'),
    path('gerencia/', gerencia_dashboard, name='gerencia_dashboard'),
    path('administrador/', administrador_dashboard, name='administrador_dashboard'),
    path('administrador/<str:tipo>/', admin_maestro_lista, name='admin_maestro_lista'),
    path('administrador/<str:tipo>/crear/', admin_maestro_crear, name='admin_maestro_crear'),
    path('administrador/<str:tipo>/<int:pk>/editar/', admin_maestro_editar, name='admin_maestro_editar'),
    path('recepcion/', recepcion_dashboard, name='recepcion_dashboard'),
    path('limpieza/', limpieza_dashboard, name='limpieza_dashboard'),

    path('reservas/nueva/', nueva_reserva, name='nueva_reserva'),
    path('disponibilidad/', buscar_disponibilidad, name='buscar_disponibilidad'),
]
