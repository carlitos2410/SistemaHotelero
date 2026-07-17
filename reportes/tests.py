from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from estancias.models import Estancia, Folio, MetodoPago, MovimientoCaja, Pago
from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva

from .services import calcular_reporte_ocupacion


class ReporteOcupacionHistoricaTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.hotel = Hotel.objects.create(
            nombre='Hotel Reportes', ruc='20888888881', direccion='Chiclayo', estrellas=4, telefono='988888881'
        )
        self.tipo_simple = TipoHabitacion.objects.create(nombre='Simple reporte', capacidad=1, precio_base=100)
        self.tipo_doble = TipoHabitacion.objects.create(nombre='Doble reporte', capacidad=2, precio_base=180)
        self.habitacion_simple = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_simple, numero='601', piso=6, estado='DISPONIBLE'
        )
        self.habitacion_doble = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo_doble, numero='602', piso=6, estado='OCUPADA'
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='10101010', nombres='Luis', apellidos='Reporte', nacionalidad='Peruana'
        )

        reserva_finalizada = self._reserva(
            self.habitacion_simple, self.hoy - timedelta(days=2), self.hoy, 'CHECKOUT', Decimal('200.00')
        )
        Estancia.objects.create(
            reserva=reserva_finalizada,
            habitacion=self.habitacion_simple,
            fecha_checkin=self._momento(self.hoy - timedelta(days=2), time(15, 0)),
            fecha_checkout=self._momento(self.hoy, time(10, 0)),
            fecha_entrada_programada=reserva_finalizada.fecha_entrada,
            fecha_salida_programada=reserva_finalizada.fecha_salida,
            precio_final=Decimal('200.00'),
            estado='FINALIZADA',
        )

        reserva_activa = self._reserva(
            self.habitacion_doble, self.hoy, self.hoy + timedelta(days=2), 'CHECKIN', Decimal('360.00')
        )
        self.estancia_activa = Estancia.objects.create(
            reserva=reserva_activa,
            habitacion=self.habitacion_doble,
            fecha_checkin=self._momento(self.hoy, time(15, 0)),
            fecha_entrada_programada=reserva_activa.fecha_entrada,
            fecha_salida_programada=reserva_activa.fecha_salida,
            precio_final=Decimal('360.00'),
            estado='ACTIVA',
        )
        self.folio = Folio.objects.create(
            estancia=self.estancia_activa, subtotal=Decimal('360.00'), igv=Decimal('64.80'), total=Decimal('424.80')
        )
        self.metodo = MetodoPago.objects.create(nombre='Efectivo reporte', tipo='EFECTIVO')
        self.pago = Pago.objects.create(
            folio=self.folio,
            metodo_pago=self.metodo,
            monto=Decimal('424.80'),
            estado='APROBADO',
        )

    def _momento(self, fecha, hora):
        return timezone.make_aware(datetime.combine(fecha, hora))

    def _reserva(self, habitacion, entrada, salida, estado, precio):
        return Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=habitacion,
            fecha_entrada=entrada,
            fecha_salida=salida,
            num_adultos=1,
            estado=estado,
            precio_total=precio,
        )

    def test_ocupacion_del_dia_usa_fechas_reales_y_checkout_es_exclusivo(self):
        reporte = calcular_reporte_ocupacion(self.hoy, self.hoy)

        self.assertEqual(reporte['serie_diaria'][0]['habitaciones_ocupadas'], 1)
        self.assertEqual(reporte['serie_diaria'][0]['tasa_ocupacion'], 50.0)

    def test_revenue_se_desglosa_por_tipo_y_separa_cobrado(self):
        reporte = calcular_reporte_ocupacion(self.hoy, self.hoy)
        doble = next(item for item in reporte['desglose_tipos'] if item['tipo_id'] == self.tipo_doble.id)

        self.assertEqual(doble['revenue_facturado'], Decimal('424.80'))
        self.assertEqual(doble['revenue_cobrado'], Decimal('424.80'))
        self.assertEqual(doble['tasa_ocupacion'], 100.0)

    def test_revenue_cobrado_usa_fecha_real_de_ingresos_y_devoluciones(self):
        ingreso = MovimientoCaja.objects.create(
            pago=self.pago,
            tipo='INGRESO',
            concepto='PAGO_FOLIO',
            monto=Decimal('424.80'),
            metodo_pago=self.metodo,
        )
        MovimientoCaja.objects.filter(pk=ingreso.pk).update(
            fecha=timezone.now() - timedelta(days=1),
        )
        MovimientoCaja.objects.create(
            pago=self.pago,
            tipo='EGRESO',
            concepto='DEVOLUCION_RESERVA',
            monto=Decimal('100.00'),
            metodo_pago=self.metodo,
        )

        reporte_hoy = calcular_reporte_ocupacion(self.hoy, self.hoy)
        doble = next(
            item for item in reporte_hoy['desglose_tipos']
            if item['tipo_id'] == self.tipo_doble.id
        )
        self.assertEqual(reporte_hoy['revenue_cobrado'], Decimal('-100.00'))
        self.assertEqual(doble['revenue_cobrado'], Decimal('-100.00'))

    def test_ocupacion_sin_revenue_no_consulta_folios_pagos_ni_caja(self):
        with CaptureQueriesContext(connection) as consultas:
            reporte = calcular_reporte_ocupacion(
                self.hoy - timedelta(days=6),
                self.hoy,
                incluir_revenue=False,
            )

        sql = ' '.join(consulta['sql'].lower() for consulta in consultas.captured_queries)
        self.assertNotIn('estancias_folio', sql)
        self.assertNotIn('estancias_pago', sql)
        self.assertNotIn('estancias_movimientocaja', sql)
        self.assertEqual(reporte['revenue_facturado'], Decimal('0.00'))
        self.assertEqual(reporte['revenue_cobrado'], Decimal('0.00'))

    def test_dashboard_muestra_barras_y_metricas_historicas(self):
        usuario = User.objects.create_user(username='gerenciareporte', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Gerencia')
        usuario.groups.add(grupo)
        self.client.force_login(usuario)

        response = self.client.get(reverse('dashboard_reportes'), {
            'fecha_desde': self.hoy.isoformat(),
            'fecha_hasta': self.hoy.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ocupación diaria histórica')
        self.assertContains(response, 'Ocupación y revenue por tipo')
        self.assertEqual(response.context['ocupacion_actual'], 50.0)

    def test_pdf_y_api_comparten_indicadores_del_reporte(self):
        usuario = User.objects.create_user(username='gerenciaexporta', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Gerencia')
        usuario.groups.add(grupo)
        self.client.force_login(usuario)
        parametros = {'fecha': self.hoy.isoformat()}

        api_response = self.client.get('/api/reportes/ocupacion/', parametros)
        pdf_response = self.client.get(reverse('exportar_reporte_pdf'), {
            'fecha_desde': self.hoy.isoformat(),
            'fecha_hasta': self.hoy.isoformat(),
        })

        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()['tasa_ocupacion'], 50.0)
        self.assertEqual(api_response.json()['revenue_dia'], 424.8)
        self.assertEqual(len(api_response.json()['por_tipo_habitacion']), 2)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))

        fecha_invalida = self.client.get('/api/reportes/ocupacion/', {'fecha': '15-07-2026'})
        self.assertEqual(fecha_invalida.status_code, 400)
        self.assertIn('fecha', fecha_invalida.json())
