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
