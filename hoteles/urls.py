from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista_hoteles, name='hoteles_lista'),
    path('crear/', views.crear_hotel, name='hoteles_crear'),
    path('<int:hotel_id>/', views.detalle_hotel, name='hoteles_detalle'),
    path('<int:hotel_id>/editar/', views.editar_hotel, name='hoteles_editar'),
    path('<int:hotel_id>/eliminar/', views.eliminar_hotel, name='hoteles_eliminar'),
]
