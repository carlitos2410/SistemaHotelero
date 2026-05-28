from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from estancias.models import Estancia, MetodoPago, Pago
from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Tarifa


class ApiHotelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='clave12345')
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

    def crear_reserva(self):
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
        return self.client.post('/api/reservas/', payload, format='json')

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

    def test_checkin_bloquea_habitacion_en_mantenimiento(self):
        response = self.crear_reserva()
        reserva_id = response.data['id']
        self.habitacion.estado = 'MANTENIMIENTO'
        self.habitacion.save()

        response = self.client.post(f'/api/reservas/{reserva_id}/checkin/', {}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_checkin_checkout_valida_deuda_y_pasa_limpieza(self):
        response = self.crear_reserva()
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
