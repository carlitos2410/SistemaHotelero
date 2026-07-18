from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hoteles.models import Hotel

from .forms import ReporteFiltroForm
from .pdf import PDFGenerator, construir_reporte_pdf
from .services import calcular_ocupacion, calcular_ingresos, resumen_habitaciones, resumen_reservas


class ReporteServicioTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre='Hotel Reportes', ruc='20111111111',
            direccion='Lima', estrellas=4, telefono='999',
        )

    def test_ocupacion_sin_datos(self):
        resultado = calcular_ocupacion()
        self.assertEqual(resultado['total_habitaciones'], 0)
        self.assertEqual(resultado['porcentaje_ocupacion'], Decimal('0.00'))

    def test_ocupacion_con_hotel(self):
        resultado = calcular_ocupacion(hotel_id=self.hotel.id)
        self.assertEqual(resultado['total_habitaciones'], 0)

    def test_ingresos_vacios(self):
        resultado = calcular_ingresos()
        self.assertEqual(resultado['total_pagos'], Decimal('0.00'))
        self.assertEqual(resultado['cantidad_pagos'], 0)

    def test_resumen_reservas_vacio(self):
        resultado = resumen_reservas()
        self.assertEqual(resultado['total'], 0)

    def test_habitaciones_vacias(self):
        resultado = resumen_habitaciones()
        self.assertEqual(len(resultado), 0)


class ReporteFormTests(TestCase):
    def test_formulario_valido(self):
        form = ReporteFiltroForm(data={
            'fecha_desde': '2026-01-01',
            'fecha_hasta': '2026-01-31',
        })
        self.assertTrue(form.is_valid())

    def test_formulario_vacio_valido(self):
        form = ReporteFiltroForm(data={})
        self.assertTrue(form.is_valid())


class PDFTests(TestCase):
    def test_pdf_generar(self):
        pdf = PDFGenerator(titulo='Test', subtitulo='Sub test')
        pdf.agregar_parrafo('Linea de prueba')
        resultado = pdf.generar()
        self.assertTrue(resultado.read().startswith(b'%PDF-1.4'))

    def test_construir_reporte(self):
        datos = {
            'titulo': 'Reporte Test',
            'subtitulo': 'Periodo: Enero',
            'ocupacion': {
                'total_habitaciones': 10,
                'ocupadas_promedio': 5,
                'porcentaje_ocupacion': Decimal('50.00'),
                'dias_analizados': 30,
            },
            'ingresos': {
                'total_pagos': Decimal('5000.00'),
                'cantidad_pagos': 20,
                'ingresos_caja': Decimal('5000.00'),
                'egresos_caja': Decimal('500.00'),
                'flujo_neto': Decimal('4500.00'),
            },
            'reservas': {
                'total': 15,
                'pendientes': 3,
                'confirmadas': 5,
                'en_casa': 4,
                'finalizadas': 2,
                'canceladas': 1,
                'no_show': 0,
                'ingreso_total': Decimal('8000.00'),
            },
            'habitaciones': {'DISPONIBLE': 5, 'OCUPADA': 5},
        }
        buffer = construir_reporte_pdf(datos)
        contenido = buffer.read()
        self.assertIn(b'%PDF-1.4', contenido)


class ReporteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin_reportes', password='test1234', is_superuser=True,
        )

    def test_dashboard_reportes(self):
        self.client.login(username='admin_reportes', password='test1234')
        response = self.client.get(reverse('dashboard_reportes'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_con_filtros(self):
        self.client.login(username='admin_reportes', password='test1234')
        response = self.client.get(reverse('dashboard_reportes'), {
            'fecha_desde': '2026-01-01',
            'fecha_hasta': '2026-01-31',
        })
        self.assertEqual(response.status_code, 200)

    def test_exportar_pdf(self):
        self.client.login(username='admin_reportes', password='test1234')
        response = self.client.get(reverse('exportar_reporte_pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])

    def test_exportar_pdf_con_filtros(self):
        self.client.login(username='admin_reportes', password='test1234')
        response = self.client.get(reverse('exportar_reporte_pdf'), {
            'fecha_desde': '2026-01-01',
            'fecha_hasta': '2026-01-31',
        })
        self.assertEqual(response.status_code, 200)
