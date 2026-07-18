from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista_habitaciones, name='lista_habitaciones'),
]
