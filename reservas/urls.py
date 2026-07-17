from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_reservas, name='lista_reservas'),
    path('calendario/', views.calendario_ocupacion, name='calendario_ocupacion'),
    path('alertas/', views.alertas_operativas, name='alertas_operativas'),
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('checkin-directo/', views.checkin_directo, name='checkin_directo'),
    path('checkin-pendientes/', views.checkin_pendientes, name='checkin_pendientes'),
    path('no-show/<int:reserva_id>/', views.marcar_no_show, name='marcar_no_show'),
    path('<int:reserva_id>/adelanto/', views.pagar_reserva, name='pagar_reserva'),
    path('<int:reserva_id>/cancelar/', views.cancelar_reserva_web, name='cancelar_reserva'),
    path('<int:reserva_id>/', views.detalle_reserva, name='detalle_reserva'),
    path('checkout-pendientes/', views.checkout_pendientes, name='checkout_pendientes'),
    path('prorroga/<int:reserva_id>/', views.autorizar_prorroga, name='autorizar_prorroga'),
    path('caja/', views.caja_recepcion, name='caja_recepcion'),
    path('estado-habitaciones/', views.estado_habitaciones, name='estado_habitaciones'),
    path('estado-habitaciones/datos/', views.estado_habitaciones_datos, name='estado_habitaciones_datos'),
    path('checkin/<int:reserva_id>/', views.realizar_checkin, name='realizar_checkin'),
    path('checkout/<int:reserva_id>/', views.realizar_checkout, name='realizar_checkout'),
]
