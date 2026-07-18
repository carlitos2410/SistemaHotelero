from django.urls import path

from . import views


urlpatterns = [
    path('', views.estancias_activas, name='estancias_activas'),
    path('configuracion-cobro/', views.configurar_cobro, name='configurar_cobro'),
    path('caja/historial-pagos/', views.historial_pagos, name='historial_pagos'),
    path('caja/reporte-diario/', views.reporte_caja_diario, name='reporte_caja_diario'),
    path('folios/<int:folio_id>/pagar/', views.pagar_folio, name='pagar_folio'),
    path('comprobantes/<int:comprobante_id>/pdf/', views.exportar_comprobante, name='exportar_comprobante'),
    path('<int:estancia_id>/consumos/', views.cargar_consumo, name='cargar_consumo'),
]
