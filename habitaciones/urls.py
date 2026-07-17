from django.urls import path
from . import views

urlpatterns = [
    path('', views.modulo_habitaciones, name='modulo_habitaciones'),
    path('listado/', views.lista_habitaciones, name='lista_habitaciones'),
    path('cambiar-estado/<int:habitacion_id>/', views.cambiar_estado_habitacion, name='cambiar_estado_habitacion'),
]
