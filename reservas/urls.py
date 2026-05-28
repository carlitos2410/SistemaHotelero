from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_reservas, name='lista_reservas'),
    path('calendario/', views.calendario_ocupacion, name='calendario_ocupacion'),
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('checkin-directo/', views.checkin_directo, name='checkin_directo'),
    path('checkin-pendientes/', views.checkin_pendientes, name='checkin_pendientes'),
    path('checkout-pendientes/', views.checkout_pendientes, name='checkout_pendientes'),
    path('caja/', views.caja_recepcion, name='caja_recepcion'),
    path('estado-habitaciones/', views.estado_habitaciones, name='estado_habitaciones'),
    path('checkin/<int:reserva_id>/', views.realizar_checkin, name='realizar_checkin'),
    path('checkout/<int:reserva_id>/', views.realizar_checkout, name='realizar_checkout'),
]
