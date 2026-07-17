from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estancias.models import Estancia
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva

from .models import Habitacion, HabitacionEstadoHistorial, ObservacionMantenimiento, TipoHabitacion
from .services import actualizar_estado_housekeeping


def contenido_estatico(ruta):
    return Path(finders.find(ruta)).read_text(encoding='utf-8')


class HousekeepingFlujoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='housekeepingweb', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Limpieza')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Housekeeping', ruc='20666666661', direccion='Chiclayo', estrellas=4, telefono='966666661'
        )
        self.tipo = TipoHabitacion.objects.create(nombre='Tipo limpieza', capacidad=2, precio_base=Decimal('120.00'))
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='60606060', nombres='Cliente', apellidos='Limpieza', nacionalidad='Peruana'
        )

    def _habitacion(self, numero, piso, estado='LIMPIEZA'):
        return Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero=numero, piso=piso, estado=estado
        )

    def _checkout(self, habitacion, fecha):
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=habitacion,
            fecha_entrada=fecha - timedelta(days=2),
            fecha_salida=fecha,
            num_adultos=1,
            estado='CHECKOUT',
            precio_total=Decimal('240.00'),
        )
        return Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            fecha_checkin=timezone.make_aware(datetime.combine(fecha - timedelta(days=2), time(15, 0))),
            fecha_checkout=timezone.make_aware(datetime.combine(fecha, time(10, 0))),
            fecha_entrada_programada=reserva.fecha_entrada,
            fecha_salida_programada=reserva.fecha_salida,
            precio_final=reserva.precio_total,
            estado='FINALIZADA',
        )

    def test_boton_lista_cambia_limpieza_a_disponible_y_registra_historial(self):
        habitacion = self._habitacion('801', 8)

        response = self.client.post(
            reverse('cambiar_estado_habitacion', args=[habitacion.id]),
            {'estado': 'DISPONIBLE'},
        )

        self.assertEqual(response.status_code, 302)
        habitacion.refresh_from_db()
        self.assertEqual(habitacion.estado, 'DISPONIBLE')
        cambio = HabitacionEstadoHistorial.objects.filter(habitacion=habitacion).first()
        self.assertEqual(cambio.estado_anterior, 'LIMPIEZA')
        self.assertEqual(cambio.estado_nuevo, 'DISPONIBLE')
        self.assertEqual(cambio.cambiado_por, self.usuario)

    def test_mantenimiento_debe_pasar_por_limpieza_antes_de_disponible(self):
        habitacion = self._habitacion('802', 8, 'MANTENIMIENTO')

        with self.assertRaises(ValidationError):
            actualizar_estado_housekeeping(habitacion, 'DISPONIBLE', usuario=self.usuario)

        actualizar_estado_housekeeping(habitacion, 'LIMPIEZA', usuario=self.usuario)
        habitacion.refresh_from_db()
        self.assertEqual(habitacion.estado, 'LIMPIEZA')
        actualizar_estado_housekeeping(habitacion, 'DISPONIBLE', usuario=self.usuario)
        habitacion.refresh_from_db()
        self.assertEqual(habitacion.estado, 'DISPONIBLE')

    def test_envio_a_mantenimiento_exige_y_guarda_observacion(self):
        habitacion = self._habitacion('803', 8, 'LIMPIEZA')
        with self.assertRaises(ValidationError):
            actualizar_estado_housekeeping(habitacion, 'MANTENIMIENTO', usuario=self.usuario)

        actualizar_estado_housekeeping(
            habitacion, 'MANTENIMIENTO', usuario=self.usuario, observacion='Fuga en el lavamanos'
        )
        self.assertTrue(
            ObservacionMantenimiento.objects.filter(habitacion=habitacion, observacion='Fuga en el lavamanos').exists()
        )

    def test_limpieza_no_puede_iniciar_limpieza_desde_disponible(self):
        habitacion = self._habitacion('805', 8, 'DISPONIBLE')

        inventario = self.client.get(reverse('lista_habitaciones'))
        self.assertEqual(inventario.status_code, 302)
        self.assertEqual(inventario.url, reverse('inicio'))

        formulario = self.client.get(reverse('cambiar_estado_habitacion', args=[habitacion.id]))
        self.assertNotContains(formulario, '<option value="LIMPIEZA">', html=True)

        response = self.client.post(
            reverse('cambiar_estado_habitacion', args=[habitacion.id]),
            {'estado': 'LIMPIEZA'},
        )
        self.assertEqual(response.status_code, 200)
        habitacion.refresh_from_db()
        self.assertEqual(habitacion.estado, 'DISPONIBLE')
        self.assertContains(response, 'Transicion no permitida')

    def test_administrador_conserva_correccion_manual_disponible_a_limpieza(self):
        administrador = User.objects.create_user(username='admin_habitacion', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Administrador')
        administrador.groups.add(grupo)
        habitacion = self._habitacion('806', 8, 'DISPONIBLE')

        actualizar_estado_housekeeping(habitacion, 'LIMPIEZA', usuario=administrador)

        habitacion.refresh_from_db()
        self.assertEqual(habitacion.estado, 'LIMPIEZA')

    def test_dashboard_clasifica_checkout_de_hoy_y_atrasado_y_filtra_piso(self):
        hoy = timezone.localdate()
        actual = self._habitacion('804', 8)
        atrasada = self._habitacion('901', 9)
        self._checkout(actual, hoy)
        self._checkout(atrasada, hoy - timedelta(days=1))

        response = self.client.get(reverse('limpieza_dashboard'), {'piso': '8'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item.id for item in response.context['limpieza_hoy']], [actual.id])
        self.assertEqual(
            timezone.localtime(response.context['limpieza_hoy'][0].ultimo_checkout_fecha).date(),
            hoy,
        )
        self.assertEqual(response.context['limpieza_atrasada'], [])
        self.assertContains(response, 'Marcar LISTA')
        self.assertNotContains(response, 'Habitación 901')

    def test_dashboard_ignora_piso_invalido_y_muestra_solo_ultima_observacion(self):
        habitacion = self._habitacion('902', 9, 'MANTENIMIENTO')
        ObservacionMantenimiento.objects.create(
            habitacion=habitacion,
            observacion='Observación anterior',
            creado_por=self.usuario,
        )
        ObservacionMantenimiento.objects.create(
            habitacion=habitacion,
            observacion='Reparación pendiente de validación',
            creado_por=self.usuario,
        )

        response = self.client.get(reverse('limpieza_dashboard'), {'piso': 'piso-invalido'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['piso_seleccionado'], '')
        self.assertContains(response, 'Reparación pendiente de validación')
        self.assertNotContains(response, 'Observación anterior')


class ModuloHabitacionesPorRolTests(TestCase):
    def setUp(self):
        hotel = Hotel.objects.create(
            nombre='Hotel Modulos', ruc='20666666662', direccion='Chiclayo',
            estrellas=4, telefono='966666662',
        )
        tipo = TipoHabitacion.objects.create(
            nombre='Matrimonial modular', capacidad=2, precio_base=Decimal('150.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=hotel, tipo=tipo, numero='1001', piso=10, estado='DISPONIBLE',
        )

    def _usuario(self, rol):
        usuario = User.objects.create_user(
            username=f'usuario_{rol.lower()}', password='clave12345',
        )
        grupo, _ = Group.objects.get_or_create(name=rol)
        usuario.groups.add(grupo)
        return usuario

    def test_entrada_unica_dirige_cada_rol_a_su_seccion_principal(self):
        casos = [
            ('Administrador', 'lista_habitaciones'),
            ('Gerencia', 'estado_habitaciones'),
            ('Recepcionista', 'estado_habitaciones'),
            ('Limpieza', 'limpieza_dashboard'),
        ]
        for rol, destino in casos:
            with self.subTest(rol=rol):
                self.client.force_login(self._usuario(rol))
                response = self.client.get(reverse('modulo_habitaciones'))
                self.assertRedirects(response, reverse(destino), fetch_redirect_response=False)

        superusuario = User.objects.create_superuser(
            username='super_habitaciones', email='super@hotel.test', password='clave12345',
        )
        self.client.force_login(superusuario)
        response = self.client.get(reverse('modulo_habitaciones'))
        self.assertRedirects(response, reverse('lista_habitaciones'), fetch_redirect_response=False)

    def test_pestanas_y_acciones_respetan_responsabilidades(self):
        administrador = self._usuario('Administrador')
        self.client.force_login(administrador)
        response = self.client.get(reverse('lista_habitaciones'))
        self.assertContains(response, '>Plano<')
        self.assertContains(response, '>Inventario<')
        self.assertContains(response, '>Tipos<')
        self.assertContains(response, '>Tarifas<')
        self.assertContains(response, 'Editar datos')
        self.assertContains(response, 'Cambiar estado')
        self.assertContains(response, 'data-sidebar-module="Habitaciones"')
        self.assertContains(response, 'css/pages/habitaciones_lista_habitaciones.css')
        self.assertIn('const moduloActual = document.querySelector', contenido_estatico('js/base.js'))
        self.assertIn(
            'html[data-theme="dark"] .table-habitaciones',
            contenido_estatico('css/base.css'),
        )
        self.assertIn(
            'html[data-theme="dark"] .module-tab.active',
            contenido_estatico('css/base.css'),
        )
        self.assertContains(
            response,
            f'href="{reverse("modulo_habitaciones")}" class="hotel-nav-link"',
            count=1,
        )

        gerencia = self._usuario('Gerencia')
        self.client.force_login(gerencia)
        response = self.client.get(reverse('lista_habitaciones'))
        self.assertContains(response, '>Plano<')
        self.assertContains(response, '>Inventario<')
        self.assertNotContains(response, '>Tipos<')
        self.assertNotContains(response, '>Tarifas<')
        self.assertNotContains(response, 'Cambiar estado')

        limpieza = self._usuario('Limpieza')
        self.client.force_login(limpieza)
        response = self.client.get(reverse('limpieza_dashboard'))
        self.assertContains(response, '>Housekeeping<')
        self.assertContains(response, 'Limpieza de hoy')
        self.assertContains(response, 'En mantenimiento')
        self.assertNotContains(response, '>Inventario<')
        self.assertNotContains(response, '>Plano<')
