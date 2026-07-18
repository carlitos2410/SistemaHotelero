from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Hotel
from .forms import HotelForm
from .services import obtener_o_crear_hotel, validar_hotel_unico


class HotelModelTests(TestCase):
    def test_crear_hotel(self):
        hotel = Hotel.objects.create(
            nombre='Hotel Test', ruc='20123456789', direccion='Lima',
            estrellas=4, telefono='999888777',
        )
        self.assertEqual(str(hotel), 'Hotel Test')
        self.assertEqual(hotel.estrellas, 4)
        self.assertTrue(hotel.activo)

    def test_ruc_unico(self):
        Hotel.objects.create(
            nombre='Hotel Uno', ruc='20123456789', direccion='Lima',
            estrellas=3, telefono='111',
        )
        with self.assertRaises(Exception):
            Hotel.objects.create(
                nombre='Hotel Dos', ruc='20123456789', direccion='Cusco',
                estrellas=4, telefono='222',
            )

    def test_estrellas_validas(self):
        hotel = Hotel(nombre='Test', ruc='20123456789', estrellas=6, direccion='X', telefono='1')
        with self.assertRaises(ValidationError) as ctx:
            hotel.clean()
        self.assertIn('estrellas', ctx.exception.message_dict)

    def test_ruc_longitud(self):
        hotel = Hotel(nombre='Test', ruc='123', estrellas=3, direccion='X', telefono='1')
        with self.assertRaises(ValidationError) as ctx:
            hotel.clean()
        self.assertIn('ruc', ctx.exception.message_dict)


class HotelFormTests(TestCase):
    def test_formulario_valido(self):
        form = HotelForm(data={
            'nombre': 'Hotel Form', 'ruc': '20987654321',
            'direccion': 'Arequipa', 'estrellas': 5,
            'telefono': '999111222', 'email': 'info@test.com',
            'activo': True,
        })
        self.assertTrue(form.is_valid())

    def test_formulario_invalido(self):
        form = HotelForm(data={
            'nombre': '', 'ruc': '123', 'direccion': '',
            'estrellas': 0, 'telefono': '',
        })
        self.assertFalse(form.is_valid())


class HotelServiceTests(TestCase):
    def test_obtener_o_crear(self):
        hotel, creado = obtener_o_crear_hotel({
            'nombre': 'Hotel Servicio', 'ruc': '20111111111',
            'direccion': 'Trujillo', 'estrellas': 3, 'telefono': '888',
        })
        self.assertTrue(creado)
        self.assertEqual(hotel.nombre, 'Hotel Servicio')

    def test_obtener_existente(self):
        Hotel.objects.create(
            nombre='Existente', ruc='20222222222', direccion='X',
            estrellas=3, telefono='1',
        )
        hotel, creado = obtener_o_crear_hotel({
            'nombre': 'Otro nombre', 'ruc': '20222222222',
        })
        self.assertFalse(creado)
        self.assertEqual(hotel.nombre, 'Existente')

    def test_validar_unico_ok(self):
        validar_hotel_unico('Test', '20123456789')

    def test_validar_unico_duplicado(self):
        Hotel.objects.create(
            nombre='Dup', ruc='20123456789', direccion='X',
            estrellas=3, telefono='1',
        )
        with self.assertRaises(ValidationError):
            validar_hotel_unico('Dup', '20123456789')


class HotelViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='test1234', is_superuser=True)

    def test_lista_hoteles(self):
        self.client.login(username='admin_test', password='test1234')
        response = self.client.get(reverse('hoteles_lista'))
        self.assertEqual(response.status_code, 200)

    def test_crear_hotel(self):
        self.client.login(username='admin_test', password='test1234')
        response = self.client.post(reverse('hoteles_crear'), {
            'nombre': 'Hotel Nuevo', 'ruc': '20333333333',
            'direccion': 'Piura', 'estrellas': 3,
            'telefono': '777666555', 'activo': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Hotel.objects.filter(ruc='20333333333').exists())

    def test_editar_hotel(self):
        hotel = Hotel.objects.create(
            nombre='Editar', ruc='20444444444', direccion='X',
            estrellas=3, telefono='1',
        )
        self.client.login(username='admin_test', password='test1234')
        response = self.client.post(reverse('hoteles_editar', args=[hotel.id]), {
            'nombre': 'Editado', 'ruc': '20444444444',
            'direccion': 'Y', 'estrellas': 4,
            'telefono': '2', 'activo': True,
        })
        self.assertEqual(response.status_code, 302)
        hotel.refresh_from_db()
        self.assertEqual(hotel.nombre, 'Editado')

    def test_eliminar_hotel(self):
        hotel = Hotel.objects.create(
            nombre='Eliminar', ruc='20555555555', direccion='X',
            estrellas=3, telefono='1',
        )
        self.client.login(username='admin_test', password='test1234')
        response = self.client.post(reverse('hoteles_eliminar', args=[hotel.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Hotel.objects.filter(pk=hotel.id).exists())
