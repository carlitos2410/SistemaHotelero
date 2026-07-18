from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard_reportes, name='dashboard_reportes'),
    path('pdf/', views.exportar_reporte_pdf, name='exportar_reporte_pdf'),
]
