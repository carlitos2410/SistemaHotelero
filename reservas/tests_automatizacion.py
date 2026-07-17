from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva, ReservaEstadoHistorial
from usuarios.auditoria import registrar_evento


class AutomatizacionReservasTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        hotel = Hotel.objects.create(
            nombre='Hotel Automatizacion',
            ruc='20999999991',
            direccion='Chiclayo',
            estrellas=4,
            telefono='999999991',
        )
        tipo = TipoHabitacion.objects.create(
            nombre='Automatica',
            capacidad=2,
            precio_base=Decimal('100.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=hotel,
            tipo=tipo,
            numero='1101',
            piso=11,
            estado='DISPONIBLE',
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI',
            num_doc='11112222',
            nombres='Cliente',
            apellidos='Automatico',
            nacionalidad='Peruana',
        )

    def _reserva(self, *, estado, entrada, salida, limite=None):
        return Reserva.objects.create(
            hotel=self.habitacion.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=entrada,
            fecha_salida=salida,
            num_adultos=1,
            estado=estado,
            precio_total=Decimal('200.00'),
            monto_adelanto_requerido=Decimal('100.00'),
            fecha_limite_pago=limite,
        )

    def test_comando_procesa_garantias_y_no_show_de_forma_idempotente(self):
        garantia = self._reserva(
            estado='PENDIENTE',
            entrada=self.hoy + timedelta(days=2),
            salida=self.hoy + timedelta(days=4),
            limite=timezone.now() - timedelta(minutes=1),
        )
        no_show = self._reserva(
            estado='CONFIRMADA',
            entrada=self.hoy - timedelta(days=2),
            salida=self.hoy,
            limite=timezone.now() + timedelta(hours=1),
        )
        vigente = self._reserva(
            estado='CONFIRMADA',
            entrada=self.hoy,
            salida=self.hoy + timedelta(days=2),
            limite=timezone.now() + timedelta(hours=1),
        )

        salida = StringIO()
        call_command('procesar_reservas_operativas', stdout=salida)

        garantia.refresh_from_db()
        no_show.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(garantia.estado, 'CANCELADA')
        self.assertEqual(garantia.tipo_cancelacion, 'VENCIMIENTO_PAGO')
        self.assertEqual(no_show.estado, 'NO_SHOW')
        self.assertEqual(vigente.estado, 'CONFIRMADA')
        self.assertIn('1 garantia(s) cancelada(s)', salida.getvalue())
        self.assertIn('1 reserva(s) marcada(s) no-show', salida.getvalue())
        self.assertTrue(ReservaEstadoHistorial.objects.filter(
            reserva=garantia,
            estado_nuevo='CANCELADA',
            cambiado_por__isnull=True,
        ).exists())

        segunda_salida = StringIO()
        call_command('procesar_reservas_operativas', stdout=segunda_salida)
        self.assertIn('0 garantia(s) cancelada(s)', segunda_salida.getvalue())
        self.assertIn('0 reserva(s) marcada(s) no-show', segunda_salida.getvalue())

    def test_dry_run_y_auditoria_no_exponen_datos_sensibles(self):
        reserva = self._reserva(
            estado='PENDIENTE',
            entrada=self.hoy + timedelta(days=1),
            salida=self.hoy + timedelta(days=2),
            limite=timezone.now() - timedelta(minutes=1),
        )
        salida = StringIO()

        call_command('procesar_reservas_operativas', '--dry-run', stdout=salida)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, 'PENDIENTE')
        self.assertIn('Simulacion: 1 garantia(s) vencida(s)', salida.getvalue())

        usuario = User.objects.create_user(username='auditoria_segura', password='secreto-test')
        with self.assertLogs('hotel.operaciones', level='INFO') as logs:
            registrar_evento(
                'prueba_segura',
                usuario=usuario,
                reserva_id=reserva.id,
                password='secreto-test',
                num_doc='11112222',
            )
        texto = ' '.join(logs.output)
        self.assertIn(f'reserva_id={reserva.id}', texto)
        self.assertNotIn('secreto-test', texto)
        self.assertNotIn('11112222', texto)
