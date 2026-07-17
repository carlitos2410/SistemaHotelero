from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from estancias.models import ConfiguracionCobro, Estancia, MetodoPago, Pago
from estancias.services import registrar_pago_folio
from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Promocion, Tarifa
from api.serializers import CargoCreateSerializer


class ApiHotelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='clave12345')
        recepcion, _ = Group.objects.get_or_create(name='Recepcionista')
        self.user.groups.add(recepcion)
        self.client = APIClient()
        response = self.client.post('/api/auth/token/', {'username': 'apiuser', 'password': 'clave12345'}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')

        self.hotel = Hotel.objects.create(
            nombre='Win Meier Hotel',
            ruc='20611137355',
            direccion='Chiclayo',
            estrellas=5,
            telefono='987654321',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Doble Superior',
            capacidad=2,
            precio_base=Decimal('120.00'),
            amenidades={'wifi': True},
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='201',
            piso=2,
            estado='DISPONIBLE',
        )
        hoy = timezone.localdate()
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Tarifa vigente',
            precio_noche=Decimal('150.00'),
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=30),
        )

    def crear_reserva(self, confirmar=False):
        hoy = timezone.localdate()
        payload = {
            'habitacion_id': self.habitacion.id,
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=2)).isoformat(),
            'num_adultos': 2,
            'origen': 'API',
            'huesped': {
                'tipo_doc': 'DNI',
                'num_doc': '76335718',
                'nombres': 'Juan',
                'apellidos': 'Espinoza',
                'email': 'juan@example.com',
                'telefono': '966768983',
                'nacionalidad': 'Peruano',
            },
        }
        response = self.client.post('/api/reservas/', payload, format='json')
        if confirmar and response.status_code == 201:
            metodo, _ = MetodoPago.objects.get_or_create(
                nombre='Efectivo API', defaults={'tipo': 'EFECTIVO', 'activo': True}
            )
            adelanto = self.client.post(
                f'/api/reservas/{response.data["id"]}/adelantos/',
                {
                    'metodo_pago': metodo.id,
                    'monto': response.data['saldo_adelanto'],
                    'tipo_comprobante': 'BOLETA',
                    'cliente_documento': '76335718',
                    'cliente_nombre': 'Juan Espinoza',
                },
                format='json',
            )
            self.assertEqual(adelanto.status_code, 201)
        return response

    def test_disponibilidad_excluye_reservas_solapadas(self):
        response = self.crear_reserva()
        self.assertEqual(response.status_code, 201)

        hoy = timezone.localdate()
        response = self.client.get('/api/habitaciones/disponibles/', {
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=1)).isoformat(),
            'num_personas': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_reserva_valida_tarifa_vigente_y_capacidad(self):
        response = self.crear_reserva()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['precio_total'], '300.00')
        self.assertEqual(response.data['estado'], 'PENDIENTE')
        self.assertEqual(response.data['monto_adelanto_requerido'], '150.00')

    def test_adelanto_confirma_reserva_y_bloquea_sobrepago(self):
        response = self.crear_reserva()
        metodo, _ = MetodoPago.objects.get_or_create(
            nombre='Transferencia API', defaults={'tipo': 'TRANSFERENCIA', 'activo': True}
        )
        payload = {
            'metodo_pago': metodo.id,
            'monto': '150.00',
            'numero_operacion': 'OP-API-001',
            'tipo_comprobante': 'BOLETA',
            'cliente_documento': '76335718',
            'cliente_nombre': 'Juan Espinoza',
        }
        adelanto = self.client.post(
            f'/api/reservas/{response.data["id"]}/adelantos/', payload, format='json'
        )
        self.assertEqual(adelanto.status_code, 201)
        self.assertEqual(adelanto.data['reserva']['estado'], 'CONFIRMADA')
        self.assertEqual(adelanto.data['reserva']['saldo_adelanto'], Decimal('0.00'))

        repetido = self.client.post(
            f'/api/reservas/{response.data["id"]}/adelantos/', payload, format='json'
        )
        self.assertEqual(repetido.status_code, 400)

    def test_api_cancela_reserva_confirmada_y_retiene_adelanto_tardio(self):
        response = self.crear_reserva(confirmar=True)
        cancelacion = self.client.post(
            f'/api/reservas/{response.data["id"]}/cancelar/',
            {'motivo': 'Huesped cancela el mismo dia'},
            format='json',
        )
        self.assertEqual(cancelacion.status_code, 200)
        self.assertEqual(cancelacion.data['reserva']['estado'], 'CANCELADA')
        self.assertEqual(cancelacion.data['reserva']['tipo_cancelacion'], 'TARDIA')
        self.assertGreater(cancelacion.data['monto_retenido'], Decimal('0.00'))

    def test_busqueda_de_huesped_devuelve_datos_existentes(self):
        huesped = Huesped.objects.create(
            tipo_doc='DNI',
            num_doc='44556677',
            nombres='Ana',
            apellidos='Torres',
            email='ana@example.com',
            telefono='999888777',
            nacionalidad='Peruana',
        )

        response = self.client.get('/api/huespedes/buscar/', {
            'tipo_doc': 'DNI',
            'num_doc': huesped.num_doc,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['encontrado'])
        self.assertEqual(response.data['huesped']['nombres'], 'Ana')

    def test_cotizacion_devuelve_tarifa_nocturna_y_total(self):
        hoy = timezone.localdate()

        response = self.client.get('/api/reservas/cotizar/', {
            'habitacion': self.habitacion.id,
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=2)).isoformat(),
            'num_personas': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['noches'], 2)
        self.assertEqual(response.data['precio_total'], Decimal('300.00'))
        self.assertEqual(len(response.data['desglose']), 2)

    def test_cotizacion_y_reserva_api_guardan_promocion(self):
        hoy = timezone.localdate()
        Promocion.objects.create(
            nombre='API 20%',
            tipo_habitacion=self.tipo,
            porcentaje_descuento=Decimal('20.00'),
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=5),
            activo=True,
        )

        cotizacion = self.client.get('/api/reservas/cotizar/', {
            'habitacion': self.habitacion.id,
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=2)).isoformat(),
            'num_personas': 2,
        })
        reserva = self.crear_reserva()

        self.assertEqual(cotizacion.status_code, 200)
        self.assertEqual(cotizacion.data['precio_sin_descuento'], Decimal('300.00'))
        self.assertEqual(cotizacion.data['descuento_total'], Decimal('60.00'))
        self.assertEqual(cotizacion.data['precio_total'], Decimal('240.00'))
        self.assertEqual(cotizacion.data['promociones_aplicadas'][0]['nombre'], 'API 20%')
        self.assertEqual(reserva.status_code, 201)
        self.assertEqual(reserva.data['descuento_promocion'], '60.00')
        self.assertEqual(reserva.data['precio_total'], '240.00')

    def test_cotizacion_api_usa_politicas_centralizadas(self):
        configuracion = ConfiguracionCobro.actual()
        configuracion.porcentaje_garantia_reserva = Decimal('40.00')
        configuracion.horas_plazo_pago_garantia = 10
        configuracion.porcentaje_igv = Decimal('18.00')
        configuracion.porcentaje_early_checkin = Decimal('7.00')
        configuracion.porcentaje_late_checkout = Decimal('35.00')
        configuracion.save()
        hoy = timezone.localdate()

        response = self.client.get('/api/reservas/cotizar/', {
            'habitacion': self.habitacion.id,
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=2)).isoformat(),
            'num_personas': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['garantia_reserva']['porcentaje'], Decimal('40.00'))
        self.assertEqual(response.data['garantia_reserva']['monto_requerido'], Decimal('120.00'))
        self.assertEqual(response.data['garantia_reserva']['plazo_pago_horas'], 10)
        self.assertEqual(response.data['politica_cobro']['porcentaje_igv'], Decimal('18.00'))
        self.assertEqual(response.data['politica_cobro']['porcentaje_early_checkin'], Decimal('7.00'))
        self.assertEqual(response.data['politica_cobro']['porcentaje_late_checkout'], Decimal('35.00'))

    def test_api_no_permite_crear_early_o_late_checkout_manual(self):
        serializer = CargoCreateSerializer(data={
            'concepto': 'Early manual',
            'cantidad': 1,
            'precio_unitario': '25.00',
            'tipo': 'EARLY_CHECKIN',
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn('tipo', serializer.errors)

    def test_cotizacion_rechaza_habitacion_ya_reservada(self):
        self.assertEqual(self.crear_reserva().status_code, 201)
        hoy = timezone.localdate()

        response = self.client.get('/api/reservas/cotizar/', {
            'habitacion': self.habitacion.id,
            'fecha_entrada': hoy.isoformat(),
            'fecha_salida': (hoy + timedelta(days=1)).isoformat(),
            'num_personas': 1,
        })

        self.assertEqual(response.status_code, 409)

    def test_checkin_bloquea_habitacion_en_mantenimiento(self):
        response = self.crear_reserva(confirmar=True)
        reserva_id = response.data['id']
        self.habitacion.estado = 'MANTENIMIENTO'
        self.habitacion.save()

        response = self.client.post(f'/api/reservas/{reserva_id}/checkin/', {}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_checkin_checkout_valida_deuda_y_pasa_limpieza(self):
        response = self.crear_reserva(confirmar=True)
        reserva_id = response.data['id']
        response = self.client.post(f'/api/reservas/{reserva_id}/checkin/', {}, format='json')
        self.assertEqual(response.status_code, 201)
        estancia_id = response.data['id']

        response = self.client.post(f'/api/estancias/{estancia_id}/checkout/', {}, format='json')
        self.assertEqual(response.status_code, 409)

        estancia = Estancia.objects.get(id=estancia_id)
        folio = estancia.folio
        folio.calcular_totales()
        folio.save()
        metodo, _ = MetodoPago.objects.get_or_create(nombre='Efectivo', defaults={'tipo': 'EFECTIVO'})
        Pago.objects.create(
            folio=folio,
            metodo_pago=metodo,
            monto=folio.total,
            estado='APROBADO',
            usuario_responsable=self.user,
        )

        response = self.client.post(f'/api/estancias/{estancia_id}/checkout/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, 'LIMPIEZA')

    def test_flujo_end_to_end_reserva_folio_checkout_housekeeping_y_reporte(self):
        hoy = timezone.localdate()
        Promocion.objects.create(
            nombre='E2E 10%',
            tipo_habitacion=self.tipo,
            porcentaje_descuento=Decimal('10.00'),
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=2),
            activo=True,
        )
        reserva_response = self.crear_reserva(confirmar=True)
        self.assertEqual(reserva_response.status_code, 201)
        self.assertEqual(reserva_response.data['precio_total'], '270.00')
        self.assertEqual(reserva_response.data['descuento_promocion'], '30.00')

        checkin = self.client.post(
            f'/api/reservas/{reserva_response.data["id"]}/checkin/',
            {},
            format='json',
        )
        self.assertEqual(checkin.status_code, 201)
        estancia_id = checkin.data['id']

        cargo = self.client.post(
            f'/api/estancias/{estancia_id}/cargos/',
            {
                'concepto': 'Lavanderia E2E',
                'cantidad': 2,
                'precio_unitario': '25.00',
                'tipo': 'LAVANDERIA',
            },
            format='json',
        )
        self.assertEqual(cargo.status_code, 201)
        self.assertEqual(cargo.data['monto'], '50.00')

        folio_response = self.client.get(f'/api/estancias/{estancia_id}/folio/')
        self.assertEqual(folio_response.status_code, 200)
        self.assertTrue(any(item['concepto'] == 'Lavanderia E2E' for item in folio_response.data['cargos']))

        checkout_bloqueado = self.client.post(
            f'/api/estancias/{estancia_id}/checkout/', {}, format='json'
        )
        self.assertEqual(checkout_bloqueado.status_code, 409)
        estancia = Estancia.objects.get(pk=estancia_id)
        self.assertIsNone(estancia.fecha_checkout)
        folio = estancia.folio
        folio.refresh_from_db()
        saldo = folio.saldo_pendiente
        metodo = MetodoPago.objects.get(nombre='Efectivo API')
        registrar_pago_folio(
            folio,
            metodo_pago=metodo,
            monto=saldo,
            tipo_comprobante='BOLETA',
            cliente_documento='76335718',
            cliente_nombre='Juan Espinoza',
            usuario=self.user,
        )

        checkout = self.client.post(f'/api/estancias/{estancia_id}/checkout/', {}, format='json')
        self.assertEqual(checkout.status_code, 200)
        estancia.refresh_from_db()
        self.habitacion.refresh_from_db()
        self.assertEqual(estancia.estado, 'FINALIZADA')
        self.assertIsNotNone(estancia.fecha_checkout)
        self.assertEqual(self.habitacion.estado, 'LIMPIEZA')

        limpieza = User.objects.create_user(username='limpieza_e2e', password='clave12345')
        grupo_limpieza, _ = Group.objects.get_or_create(name='Limpieza')
        limpieza.groups.add(grupo_limpieza)
        cliente_limpieza = APIClient()
        token_limpieza = cliente_limpieza.post(
            '/api/auth/token/',
            {'username': 'limpieza_e2e', 'password': 'clave12345'},
            format='json',
        )
        cliente_limpieza.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token_limpieza.data["access"]}'
        )
        housekeeping = cliente_limpieza.patch(
            f'/api/habitaciones/{self.habitacion.id}/housekeeping/',
            {'estado': 'DISPONIBLE'},
            format='json',
        )
        self.assertEqual(housekeeping.status_code, 200)
        self.assertEqual(housekeeping.data['estado'], 'DISPONIBLE')

        gerencia = User.objects.create_user(username='gerencia_e2e', password='clave12345')
        grupo_gerencia, _ = Group.objects.get_or_create(name='Gerencia')
        gerencia.groups.add(grupo_gerencia)
        cliente_gerencia = APIClient()
        token_gerencia = cliente_gerencia.post(
            '/api/auth/token/',
            {'username': 'gerencia_e2e', 'password': 'clave12345'},
            format='json',
        )
        cliente_gerencia.credentials(
            HTTP_AUTHORIZATION=f'Bearer {token_gerencia.data["access"]}'
        )
        reporte = cliente_gerencia.get('/api/reportes/ocupacion/', {'fecha': hoy.isoformat()})
        self.assertEqual(reporte.status_code, 200)
        folio.refresh_from_db()
        self.assertEqual(Decimal(str(reporte.data['revenue_dia'])), folio.total)
        self.assertEqual(reporte.data['habitaciones_ocupadas'], 1)

    def test_api_autoriza_prorroga_y_agrega_noche_al_folio(self):
        reserva_response = self.crear_reserva(confirmar=True)
        checkin = self.client.post(
            f'/api/reservas/{reserva_response.data["id"]}/checkin/', {}, format='json'
        )
        nueva_salida = timezone.localdate() + timedelta(days=3)

        response = self.client.post(
            f'/api/estancias/{checkin.data["id"]}/prorroga/',
            {'fecha_salida_nueva': nueva_salida.isoformat(), 'motivo': 'Huesped solicita una noche'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['noches_adicionales'], 1)
        self.assertEqual(response.data['monto'], Decimal('150.00'))

    def test_usuario_autenticado_sin_rol_no_puede_listar_reservas(self):
        usuario = User.objects.create_user(username='sinrol', password='clave12345')
        cliente = APIClient()
        token = cliente.post(
            '/api/auth/token/',
            {'username': usuario.username, 'password': 'clave12345'},
            format='json',
        )
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {token.data["access"]}')

        response = cliente.get('/api/reservas/')

        self.assertEqual(response.status_code, 403)

    def test_recepcionista_no_puede_actualizar_housekeeping(self):
        response = self.client.patch(
            f'/api/habitaciones/{self.habitacion.id}/housekeeping/',
            {'estado': 'LIMPIEZA'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_limpieza_solo_actualiza_habitaciones_en_flujo_housekeeping(self):
        usuario = User.objects.create_user(username='limpieza', password='clave12345')
        limpieza, _ = Group.objects.get_or_create(name='Limpieza')
        usuario.groups.add(limpieza)
        cliente = APIClient()
        token = cliente.post(
            '/api/auth/token/',
            {'username': usuario.username, 'password': 'clave12345'},
            format='json',
        )
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {token.data["access"]}')

        response = cliente.patch(
            f'/api/habitaciones/{self.habitacion.id}/housekeeping/',
            {'estado': 'LIMPIEZA'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, 'DISPONIBLE')

        Habitacion.objects.filter(pk=self.habitacion.pk).update(estado='LIMPIEZA')
        response = cliente.patch(
            f'/api/habitaciones/{self.habitacion.id}/housekeeping/',
            {'estado': 'DISPONIBLE'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, 'DISPONIBLE')

    def test_api_reservas_no_expone_actualizacion_ni_eliminacion(self):
        response = self.crear_reserva()
        reserva_id = response.data['id']

        patch_response = self.client.patch(
            f'/api/reservas/{reserva_id}/',
            {'estado': 'CANCELADA'},
            format='json',
        )
        delete_response = self.client.delete(f'/api/reservas/{reserva_id}/')

        self.assertEqual(patch_response.status_code, 405)
        self.assertEqual(delete_response.status_code, 405)

    def test_openapi_documenta_endpoints_minimos_y_cotizacion(self):
        response = self.client.get(
            '/api/schema/',
            HTTP_ACCEPT='application/vnd.oai.openapi+json',
        )
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        paths = schema['paths']
        self.assertIn('/api/habitaciones/disponibles/', paths)
        self.assertIn('/api/reservas/', paths)
        self.assertIn('/api/reservas/{id}/checkin/', paths)
        self.assertIn('/api/estancias/{id}/checkout/', paths)
        self.assertIn('/api/estancias/{id}/cargos/', paths)
        self.assertIn('/api/estancias/{id}/folio/', paths)
        self.assertIn('/api/habitaciones/{id}/housekeeping/', paths)
        self.assertIn('/api/reportes/ocupacion/', paths)
        self.assertIn('/api/reservas/cotizar/', paths)

        reserva = schema['components']['schemas']['Reserva']
        self.assertEqual(reserva['properties']['garantia_completa']['type'], 'boolean')
        self.assertEqual(reserva['properties']['saldo_adelanto']['type'], 'number')
        self.assertEqual(reserva['properties']['saldo_adelanto']['format'], 'double')
        self.assertEqual(self.client.get('/api/docs/').status_code, 200)
