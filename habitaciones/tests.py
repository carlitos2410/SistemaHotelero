from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Habitacion, HabitacionEstadoHistorial, ObservacionMantenimiento, TipoHabitacion
from .services import cambiar_estado_habitacion
from hoteles.models import Hotel


class TipoHabitacionTests(TestCase):
    def setUp(self):
        self.tipo = TipoHabitacion.objects.create(
            nombre='Doble',
            capacidad=2,
            precio_base=Decimal('120.00'),
        )

    def test_str_devuelve_nombre(self):
        self.assertEqual(str(self.tipo), 'Doble')

    def test_crea_tipo_con_amenidades(self):
        tipo = TipoHabitacion.objects.create(
            nombre='Suite',
            capacidad=3,
            precio_base=Decimal('250.00'),
            amenidades={'wifi': True, 'minibar': True},
        )
        self.assertEqual(tipo.amenidades['wifi'], True)

    def test_precio_base_negativo_rechaza(self):
        tipo = TipoHabitacion(
            nombre='Invalida',
            capacidad=1,
            precio_base=Decimal('-50.00'),
        )
        with self.assertRaises(ValidationError):
            tipo.full_clean()

    def test_capacidad_cero_rechaza(self):
        tipo = TipoHabitacion(
            nombre='Sin capacidad',
            capacidad=0,
            precio_base=Decimal('100.00'),
        )
        with self.assertRaises(ValidationError):
            tipo.full_clean()

    def test_amenidades_vacias_por_defecto(self):
        tipo = TipoHabitacion.objects.create(
            nombre='Simple',
            capacidad=1,
            precio_base=Decimal('80.00'),
        )
        self.assertEqual(tipo.amenidades, {})

    def test_orden_por_nombre(self):
        TipoHabitacion.objects.create(nombre='Zzz', capacidad=1, precio_base=Decimal('50.00'))
        TipoHabitacion.objects.create(nombre='Aaa', capacidad=1, precio_base=Decimal('50.00'))
        tipos = list(TipoHabitacion.objects.values_list('nombre', flat=True))
        self.assertEqual(tipos, ['Aaa', 'Doble', 'Zzz'])


class HabitacionTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre='Hotel Test',
            ruc='20123456789',
            direccion='Direccion test',
            estrellas=3,
            telefono='999999999',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Doble',
            capacidad=2,
            precio_base=Decimal('120.00'),
        )

    def test_crea_habitacion_disponible_por_defecto(self):
        habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='101',
            piso=1,
        )
        self.assertEqual(habitacion.estado, 'DISPONIBLE')
        self.assertEqual(str(habitacion), '101 - Hotel Test')

    def test_numero_duplicado_en_mismo_hotel_rechaza(self):
        Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='101', piso=1,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            with self.atomic():
                Habitacion.objects.create(
                    hotel=self.hotel, tipo=self.tipo, numero='101', piso=2,
                )

    def test_numero_igual_en_otro_hotel_permite(self):
        Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='101', piso=1,
        )
        otro_hotel = Hotel.objects.create(
            nombre='Otro Hotel', ruc='20987654321',
            direccion='Otra', estrellas=4, telefono='888888888',
        )
        otra = Habitacion.objects.create(
            hotel=otro_hotel, tipo=self.tipo, numero='101', piso=1,
        )
        self.assertIsNotNone(otra.pk)

    def test_piso_negativo_rechaza(self):
        habitacion = Habitacion(
            hotel=self.hotel, tipo=self.tipo, numero='999', piso=-1,
        )
        with self.assertRaises(ValidationError):
            habitacion.full_clean()

    def test_orden_por_piso_y_numero(self):
        Habitacion.objects.create(hotel=self.hotel, tipo=self.tipo, numero='201', piso=2)
        Habitacion.objects.create(hotel=self.hotel, tipo=self.tipo, numero='101', piso=1)
        nums = list(Habitacion.objects.values_list('numero', flat=True))
        self.assertEqual(nums, ['101', '201'])


class HabitacionEstadoHistorialTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='testuser', password='clave12345')
        self.hotel = Hotel.objects.create(
            nombre='Hotel Historial', ruc='20111111111',
            direccion='Dir', estrellas=3, telefono='999999999',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Suite', capacidad=2, precio_base=Decimal('200.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='501', piso=5,
        )

    def test_cambiar_estado_registra_historial(self):
        cambiar_estado_habitacion(
            self.habitacion, 'OCUPADA', usuario=self.usuario, motivo='Check-in.',
        )
        self.habitacion.refresh_from_db()
        self.assertEqual(self.habitacion.estado, 'OCUPADA')
        historial = HabitacionEstadoHistorial.objects.get(habitacion=self.habitacion)
        self.assertEqual(historial.estado_anterior, 'DISPONIBLE')
        self.assertEqual(historial.estado_nuevo, 'OCUPADA')
        self.assertEqual(historial.motivo, 'Check-in.')
        self.assertEqual(historial.cambiado_por, self.usuario)

    def test_cambiar_al_mismo_estado_no_registra(self):
        cambiar_estado_habitacion(self.habitacion, 'DISPONIBLE')
        self.assertEqual(HabitacionEstadoHistorial.objects.count(), 0)

    def test_estado_invalido_rechaza(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            cambiar_estado_habitacion(self.habitacion, 'INVALIDO')

    def test_cadena_cambios_registra_todos(self):
        cambiar_estado_habitacion(self.habitacion, 'OCUPADA', usuario=self.usuario)
        cambiar_estado_habitacion(self.habitacion, 'LIMPIEZA', usuario=self.usuario)
        cambiar_estado_habitacion(self.habitacion, 'DISPONIBLE', usuario=self.usuario)
        cambios = list(
            HabitacionEstadoHistorial.objects.filter(habitacion=self.habitacion)
            .order_by('cambiado_en')
            .values_list('estado_anterior', 'estado_nuevo')
        )
        self.assertEqual(cambios, [
            ('DISPONIBLE', 'OCUPADA'),
            ('OCUPADA', 'LIMPIEZA'),
            ('LIMPIEZA', 'DISPONIBLE'),
        ])

    def test_historial_str(self):
        cambiar_estado_habitacion(self.habitacion, 'MANTENIMIENTO', motivo='Falla.')
        h = HabitacionEstadoHistorial.objects.first()
        self.assertIn('501', str(h))
        self.assertIn('MANTENIMIENTO', str(h))


class ObservacionMantenimientoTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre='Hotel Mant', ruc='20222222222',
            direccion='Dir', estrellas=3, telefono='777777777',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Simple', capacidad=1, precio_base=Decimal('80.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='101', piso=1,
        )

    def test_crea_observacion(self):
        obs = ObservacionMantenimiento.objects.create(
            habitacion=self.habitacion,
            observacion='Falla en el aire acondicionado.',
        )
        self.assertIn('101', str(obs))
        self.assertEqual(obs.observacion, 'Falla en el aire acondicionado.')

    def test_orden_por_mas_reciente(self):
        ObservacionMantenimiento.objects.create(
            habitacion=self.habitacion, observacion='Primera',
        )
        ObservacionMantenimiento.objects.create(
            habitacion=self.habitacion, observacion='Segunda',
        )
        observaciones = list(ObservacionMantenimiento.objects.values_list('observacion', flat=True))
        self.assertEqual(observaciones, ['Segunda', 'Primera'])

    def test_habitacion_eliminada_cascade(self):
        ObservacionMantenimiento.objects.create(
            habitacion=self.habitacion, observacion='Test',
        )
        self.habitacion.delete()
        self.assertEqual(ObservacionMantenimiento.objects.count(), 0)


class CambiarEstadoHabitacionTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='svc_user', password='clave12345')
        self.hotel = Hotel.objects.create(
            nombre='Hotel SVC', ruc='20333333333',
            direccion='Dir', estrellas=3, telefono='666666666',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Estandar', capacidad=2, precio_base=Decimal('100.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='201', piso=2,
        )

    def test_ocupar_habitacion(self):
        h = cambiar_estado_habitacion(self.habitacion, 'OCUPADA', usuario=self.usuario, motivo='Check-in')
        self.assertEqual(h.estado, 'OCUPADA')

    def test_limpieza_despues_ocupada(self):
        cambiar_estado_habitacion(self.habitacion, 'OCUPADA')
        h = cambiar_estado_habitacion(self.habitacion, 'LIMPIEZA', motivo='Checkout')
        self.assertEqual(h.estado, 'LIMPIEZA')

    def test_volver_a_disponible(self):
        cambiar_estado_habitacion(self.habitacion, 'OCUPADA')
        cambiar_estado_habitacion(self.habitacion, 'LIMPIEZA')
        h = cambiar_estado_habitacion(self.habitacion, 'DISPONIBLE', motivo='Limpieza completada')
        self.assertEqual(h.estado, 'DISPONIBLE')

    def test_mantenimiento_y_regreso(self):
        cambiar_estado_habitacion(self.habitacion, 'MANTENIMIENTO', motivo='Falla electrica')
        h = cambiar_estado_habitacion(self.habitacion, 'DISPONIBLE', motivo='Reparado')
        self.assertEqual(h.estado, 'DISPONIBLE')
        self.assertEqual(HabitacionEstadoHistorial.objects.filter(habitacion=self.habitacion).count(), 2)

    def test_retorna_misma_instancia(self):
        h = cambiar_estado_habitacion(self.habitacion, 'OCUPADA')
        self.assertEqual(h.pk, self.habitacion.pk)
