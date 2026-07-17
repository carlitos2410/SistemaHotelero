from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from estancias.models import ConfiguracionCobro, Estancia, Folio
from reservas.models import Huesped, Reserva, Tarifa
from reservas.services import obtener_panel_reservas_dia
from usuarios.auth import ROLES, usuario_en_rol


def contenido_estatico(ruta):
    return Path(finders.find(ruta)).read_text(encoding='utf-8')


class LoginExperienciaTests(TestCase):
    def test_login_incluye_controles_accesibles_y_modo_password_seguro(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="login-form"')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'id="password-toggle"')
        self.assertContains(response, 'type="password"')

    def test_error_conserva_usuario_pero_no_la_password(self):
        response = self.client.post(reverse('login'), {
            'username': 'carlos.recepcion',
            'password': 'clave-no-valida',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El usuario o la contraseña no son correctos')
        self.assertContains(response, 'value="carlos.recepcion"')
        self.assertNotContains(response, 'clave-no-valida')


class NuevaReservaWebTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='recepcionweb', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Prueba Web',
            ruc='20123456789',
            direccion='Chiclayo',
            estrellas=4,
            telefono='999111222',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Matrimonial Web',
            capacidad=2,
            precio_base=Decimal('100.00'),
            amenidades={'wifi': True},
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='401',
            piso=4,
            estado='DISPONIBLE',
        )
        self.entrada = timezone.localdate() + timedelta(days=1)
        self.salida = self.entrada + timedelta(days=2)
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Temporada web',
            precio_noche=Decimal('175.00'),
            fecha_inicio=self.entrada,
            fecha_fin=self.salida,
        )

    def test_formulario_incluye_busqueda_disponibilidad_y_cotizacion(self):
        response = self.client.get(reverse('nueva_reserva'), {
            'habitacion': self.habitacion.id,
            'fecha_entrada': self.entrada.isoformat(),
            'fecha_salida': self.salida.isoformat(),
            'num_personas': 2,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'js/pages/nueva_reserva.js')
        self.assertContains(response, 'id="habitacion-disponible"')
        self.assertContains(response, 'id="id_promocion"')
        script = contenido_estatico('js/pages/nueva_reserva.js')
        self.assertIn('/api/huespedes/buscar/', script)
        self.assertIn('/api/habitaciones/disponibles/', script)
        self.assertIn('/api/reservas/cotizar/', script)

    def test_post_recalcula_tarifa_y_guarda_reserva(self):
        response = self.client.post(reverse('nueva_reserva'), {
            'tipo_doc': 'DNI',
            'num_doc': '77889911',
            'nombres': 'Lucia',
            'apellidos': 'Mendoza',
            'email': 'lucia@example.com',
            'telefono': '987123456',
            'nacionalidad': 'Peruana',
            'habitacion': self.habitacion.id,
            'fecha_entrada': self.entrada.isoformat(),
            'fecha_salida': self.salida.isoformat(),
            'num_adultos': 2,
            'estado': 'CONFIRMADA',
            'origen': 'Web',
        })

        self.assertEqual(response.status_code, 302)
        reserva = Reserva.objects.get(habitacion=self.habitacion)
        self.assertEqual(reserva.precio_total, Decimal('350.00'))
        self.assertEqual(reserva.estado, 'PENDIENTE')
        self.assertEqual(reserva.monto_adelanto_requerido, Decimal('175.00'))
        self.assertEqual(reserva.huesped.num_doc, '77889911')
        self.assertEqual(reserva.politica_cobro_checkout, 'ESTADIA_REAL_PENALIDAD')
        self.assertEqual(reserva.porcentaje_penalidad_salida_anticipada, Decimal('50.00'))

    def test_plantilla_base_incluye_modo_nocturno_persistente(self):
        response = self.client.get(reverse('recepcion_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'data-bs-theme')
        self.assertContains(response, 'id="hotel-sidebar"')
        self.assertContains(response, 'id="mobile-menu-toggle"')
        self.assertContains(response, 'css/base.css')
        self.assertContains(response, 'js/base.js')
        self.assertContains(response, "localStorage.getItem('hotel-theme')")
        script = contenido_estatico('js/base.js')
        self.assertIn("localStorage.setItem('hotel-theme', nuevoTema)", script)
        self.assertIn('hotel-sidebar-collapsed', script)
        estilos = contenido_estatico('css/base.css')
        self.assertIn('html[data-theme="dark"] .table tbody > tr:hover > *', estilos)
        self.assertIn('html[data-theme="dark"] .table-reservas thead > tr > th', estilos)
        self.assertIn('html[data-theme="dark"] .table > tbody > tr.table-warning', estilos)

    def test_recepcion_tiene_acceso_directo_a_bandeja_reservas(self):
        dashboard = self.client.get(reverse('recepcion_dashboard'))
        self.assertContains(dashboard, reverse('lista_reservas'))

        response = self.client.get(reverse('lista_reservas'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bandeja de reservas')
        self.assertContains(response, 'Pendientes de pago')
        self.assertContains(response, 'Listas para check-in')

    def test_detalle_reserva_concentra_operacion_pagos_e_historial(self):
        huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='44556677', nombres='Ana', apellidos='Torres',
            telefono='987654321', nacionalidad='Peruana',
        )
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=huesped,
            habitacion=self.habitacion,
            fecha_entrada=self.entrada,
            fecha_salida=self.salida,
            num_adultos=1,
            estado='PENDIENTE',
            precio_total=Decimal('350.00'),
            precio_sin_descuento=Decimal('350.00'),
            porcentaje_adelanto=Decimal('50.00'),
            monto_adelanto_requerido=Decimal('175.00'),
        )

        response = self.client.get(reverse('detalle_reserva', args=[reserva.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Datos de la reserva')
        self.assertContains(response, 'Pagos y comprobantes')
        self.assertContains(response, 'Historial de estados')
        self.assertContains(response, 'Reserva creada.')
        self.assertContains(response, reverse('pagar_reserva', args=[reserva.id]))

        bandeja = self.client.get(reverse('lista_reservas'))
        self.assertContains(bandeja, reverse('detalle_reserva', args=[reserva.id]))

        gerencia = User.objects.create_user(username='gerencia_detalle', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Gerencia')
        gerencia.groups.add(grupo)
        self.client.force_login(gerencia)
        response = self.client.get(reverse('detalle_reserva', args=[reserva.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('pagar_reserva', args=[reserva.id]))

    def test_bandeja_reservas_pagina_y_conserva_filtros(self):
        huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='10101010', nombres='Cliente', apellidos='Paginado',
            nacionalidad='Peruana',
        )
        for indice in range(30):
            Reserva.objects.create(
                hotel=self.hotel,
                huesped=huesped,
                habitacion=self.habitacion,
                fecha_entrada=self.entrada + timedelta(days=indice),
                fecha_salida=self.salida + timedelta(days=indice),
                num_adultos=1,
                estado='CANCELADA',
                precio_total=Decimal('100.00'),
            )

        response = self.client.get(reverse('lista_reservas'), {'estado': 'CANCELADA', 'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pagina'].paginator.count, 30)
        self.assertEqual(len(response.context['reservas']), 5)
        self.assertEqual(response.context['querystring'], 'estado=CANCELADA')
        self.assertContains(response, 'Paginación de resultados')

    def test_clientes_se_muestran_en_paginas_de_25(self):
        Huesped.objects.bulk_create([
            Huesped(
                tipo_doc='DNI',
                num_doc=f'8{indice:07d}',
                nombres=f'Cliente {indice}',
                apellidos='Paginacion',
                nacionalidad='Peruana',
            )
            for indice in range(30)
        ])

        response = self.client.get(reverse('lista_clientes'), {'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pagina'].paginator.count, 30)
        self.assertEqual(len(response.context['clientes']), 5)


class MenuSuperusuarioTests(TestCase):
    def setUp(self):
        self.superusuario = User.objects.create_superuser(
            username='supermenu', email='super@example.com', password='clave12345'
        )
        self.client.force_login(self.superusuario)

    def test_muestra_un_solo_perfil_sin_perder_permisos(self):
        response = self.client.get(reverse('administrador_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="role-pill">Superusuario</span>', count=1, html=True)
        self.assertNotContains(response, '<span class="role-pill">Gerencia</span>', html=True)
        self.assertNotContains(response, '<span class="role-pill">Administrador</span>', html=True)
        self.assertNotContains(response, '<span class="role-pill">Recepcion</span>', html=True)
        self.assertNotContains(response, '<span class="role-pill">Limpieza</span>', html=True)
        self.assertContains(response, reverse('admin:index'))
        for rol in ROLES.values():
            self.assertTrue(usuario_en_rol(self.superusuario, [rol]))


class MatrizRolesHotelTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='usuario_heredado', password='clave12345', is_staff=True)
        grupo_anterior = Group.objects.create(name='Administracion')
        self.usuario.groups.add(grupo_anterior)
        call_command('crear_roles_hotel', verbosity=0)

    def _tiene(self, grupo, codename):
        return Group.objects.get(name=grupo).permissions.filter(codename=codename).exists()

    def test_consolida_grupos_y_asigna_responsabilidades(self):
        self.usuario.refresh_from_db()

        self.assertTrue(self.usuario.groups.filter(name='Administrador').exists())
        self.assertFalse(Group.objects.filter(name='Administracion').exists())
        self.assertEqual(
            set(Group.objects.values_list('name', flat=True)),
            {'Gerencia', 'Administrador', 'Recepcionista', 'Limpieza'},
        )
        self.assertTrue(self._tiene('Administrador', 'add_tarifa'))
        self.assertTrue(self._tiene('Administrador', 'change_promocion'))
        self.assertTrue(self._tiene('Administrador', 'view_user'))
        self.assertFalse(self._tiene('Administrador', 'change_group'))
        self.assertTrue(self._tiene('Recepcionista', 'add_reserva'))
        self.assertTrue(self._tiene('Recepcionista', 'add_pago'))
        self.assertFalse(self._tiene('Recepcionista', 'view_tarifa'))
        self.assertFalse(self._tiene('Recepcionista', 'change_metodopago'))
        self.assertTrue(self._tiene('Gerencia', 'view_reserva'))
        self.assertFalse(self._tiene('Gerencia', 'add_reserva'))
        self.assertTrue(self._tiene('Limpieza', 'change_habitacion'))
        self.assertFalse(self._tiene('Limpieza', 'view_reserva'))

    def test_administrador_ve_y_abre_tarifas_recepcion_no(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('administrador_dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, reverse('admin_maestro_lista', args=['tarifas']))

        recepcion = User.objects.create_user(username='solo_recepcion', password='clave12345')
        recepcion.groups.add(Group.objects.get(name='Recepcionista'))
        self.client.force_login(recepcion)
        respuesta = self.client.get(reverse('admin_maestro_lista', args=['tarifas']))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse('inicio'))

    def test_administrador_puede_consultar_bandeja_de_reservas(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse('lista_reservas'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Bandeja de reservas')
        self.assertContains(respuesta, reverse('calendario_ocupacion'))

    def test_gerencia_consulta_politica_y_solo_administrador_modifica(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse('configurar_cobro'), {
            'politica_checkout': 'RESERVA_COMPLETA',
            'porcentaje_garantia_reserva': '40.00',
            'horas_plazo_pago_garantia': '12',
            'porcentaje_igv': '18.00',
            'porcentaje_early_checkin': '8.00',
            'porcentaje_late_checkout': '35.00',
            'porcentaje_penalidad_salida_anticipada': '25.00',
            'horas_cancelacion_gratuita': '48',
            'porcentaje_retencion_cancelacion_tardia': '100.00',
        })
        self.assertEqual(respuesta.status_code, 302)
        configuracion = ConfiguracionCobro.actual()
        self.assertEqual(configuracion.politica_checkout, 'ESTADIA_REAL_PENALIDAD')
        self.assertEqual(configuracion.porcentaje_penalidad_salida_anticipada, Decimal('25.00'))
        self.assertEqual(configuracion.porcentaje_garantia_reserva, Decimal('40.00'))
        self.assertEqual(configuracion.horas_plazo_pago_garantia, 12)
        self.assertEqual(configuracion.porcentaje_early_checkin, Decimal('8.00'))
        self.assertEqual(configuracion.porcentaje_late_checkout, Decimal('35.00'))

        gerencia = User.objects.create_user(username='solo_gerencia', password='clave12345')
        gerencia.groups.add(Group.objects.get(name='Gerencia'))
        self.client.force_login(gerencia)
        respuesta = self.client.get(reverse('configurar_cobro'))
        self.assertContains(respuesta, 'Vista de consulta para Gerencia')
        respuesta = self.client.post(reverse('configurar_cobro'), {
            'politica_checkout': 'ESTADIA_REAL',
            'porcentaje_penalidad_salida_anticipada': '0.00',
        })
        self.assertEqual(respuesta.status_code, 302)
        configuracion.refresh_from_db()
        self.assertEqual(configuracion.politica_checkout, 'ESTADIA_REAL_PENALIDAD')
        self.assertEqual(configuracion.porcentaje_penalidad_salida_anticipada, Decimal('25.00'))

    def test_modelo_impide_cambiar_la_politica_fija(self):
        configuracion = ConfiguracionCobro.actual()
        configuracion.politica_checkout = 'RESERVA_COMPLETA'
        configuracion.save()
        configuracion.refresh_from_db()
        self.assertEqual(configuracion.politica_checkout, 'ESTADIA_REAL_PENALIDAD')


class CheckinDirectoDisponibilidadTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.usuario = User.objects.create_user(username='walkinrecepcion', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Walk-in', ruc='20666666661', direccion='Chiclayo', estrellas=3, telefono='966666661'
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Doble Walk-in', capacidad=2, precio_base=Decimal('120.00')
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='308', piso=3, estado='DISPONIBLE'
        )
        self.huesped_futuro = Huesped.objects.create(
            tipo_doc='DNI', num_doc='71111111', nombres='Reserva', apellidos='Futura', nacionalidad='Peruana'
        )

    def datos_checkin(self, fecha_salida):
        return {
            'tipo_doc': 'DNI',
            'num_doc': '72222222',
            'nombres': 'Cliente',
            'apellidos': 'Walkin',
            'email': 'walkin@example.com',
            'telefono': '955555555',
            'nacionalidad': 'Peruana',
            'habitacion': self.habitacion.id,
            'fecha_salida': fecha_salida.isoformat(),
            'num_adultos': 2,
            'origen': 'Walk-in',
            'acompanantes-TOTAL_FORMS': '0',
            'acompanantes-INITIAL_FORMS': '0',
            'acompanantes-MIN_NUM_FORMS': '0',
            'acompanantes-MAX_NUM_FORMS': '1000',
        }

    def crear_reserva_futura(self, entrada, salida):
        return Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped_futuro,
            habitacion=self.habitacion,
            fecha_entrada=entrada,
            fecha_salida=salida,
            num_adultos=1,
            estado='CONFIRMADA',
            precio_total=Decimal('120.00'),
        )

    def test_pantalla_filtra_por_salida_tipo_y_capacidad(self):
        response = self.client.get(reverse('checkin_directo'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filtro-tipo"')
        self.assertContains(response, 'js/pages/checkin_directo.js')
        self.assertContains(response, 'id="id_promocion"')
        script = contenido_estatico('js/pages/checkin_directo.js')
        self.assertIn('/api/habitaciones/disponibles/', script)
        self.assertIn('/api/reservas/cotizar/', script)
        self.assertIn('num_personas', script)

    def test_rechaza_habitacion_con_reserva_durante_la_estancia(self):
        entrada_futura = self.hoy + timedelta(days=2)
        self.crear_reserva_futura(entrada_futura, entrada_futura + timedelta(days=2))

        response = self.client.post(
            reverse('checkin_directo'),
            self.datos_checkin(self.hoy + timedelta(days=4)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ya no esta disponible para esas fechas')
        self.assertFalse(Reserva.objects.filter(huesped__num_doc='72222222').exists())

    def test_permite_salida_justo_antes_de_la_proxima_reserva(self):
        entrada_futura = self.hoy + timedelta(days=2)
        self.crear_reserva_futura(entrada_futura, entrada_futura + timedelta(days=2))

        response = self.client.post(
            reverse('checkin_directo'),
            self.datos_checkin(entrada_futura),
        )

        self.assertEqual(response.status_code, 302)
        walkin = Reserva.objects.get(huesped__num_doc='72222222')
        self.assertEqual(walkin.fecha_salida, entrada_futura)
        self.assertEqual(walkin.estado, 'CHECKIN')


class PanelReservasDiaTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.usuario = User.objects.create_user(username='panelrecepcion', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Panel', ruc='20777777771', direccion='Chiclayo', estrellas=3, telefono='977777771'
        )
        self.tipo = TipoHabitacion.objects.create(nombre='Tipo Panel', capacidad=2, precio_base=Decimal('100.00'))
        self.contador = 0

    def _reserva(self, entrada, salida, estado='CONFIRMADA'):
        self.contador += 1
        habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero=f'7{self.contador:02d}',
            piso=7,
            estado='OCUPADA' if estado == 'CHECKIN' else 'DISPONIBLE',
        )
        huesped = Huesped.objects.create(
            tipo_doc='DNI',
            num_doc=f'9000000{self.contador}',
            nombres=f'Huesped{self.contador}',
            apellidos='Panel',
            nacionalidad='Peruana',
        )
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=huesped,
            habitacion=habitacion,
            fecha_entrada=entrada,
            fecha_salida=salida,
            num_adultos=1,
            estado=estado,
            precio_total=Decimal('200.00'),
        )
        if estado == 'CHECKIN':
            estancia = Estancia.objects.create(
                reserva=reserva,
                habitacion=habitacion,
                fecha_checkin=timezone.make_aware(datetime.combine(entrada, time(15, 0))),
                fecha_entrada_programada=entrada,
                fecha_salida_programada=salida,
                precio_final=reserva.precio_total,
                estado='ACTIVA',
            )
            Folio.objects.create(estancia=estancia, subtotal=200, igv=36, total=236)
        return reserva

    def test_clasifica_llegadas_estancias_salidas_y_alertas(self):
        self._reserva(self.hoy, self.hoy + timedelta(days=2))
        self._reserva(self.hoy - timedelta(days=1), self.hoy + timedelta(days=1))
        self._reserva(self.hoy - timedelta(days=2), self.hoy)
        self._reserva(self.hoy - timedelta(days=2), self.hoy + timedelta(days=1), 'CHECKIN')
        self._reserva(self.hoy - timedelta(days=2), self.hoy, 'CHECKIN')
        self._reserva(self.hoy - timedelta(days=3), self.hoy - timedelta(days=1), 'CHECKIN')

        panel = obtener_panel_reservas_dia(self.hoy)

        self.assertEqual(len(panel['llegadas_hoy']), 1)
        self.assertEqual(len(panel['llegadas_atrasadas']), 1)
        self.assertEqual(len(panel['no_show_pendientes']), 1)
        self.assertEqual(panel['total_en_casa'], 3)
        self.assertEqual(len(panel['salidas_hoy']), 1)
        self.assertEqual(len(panel['salidas_vencidas']), 1)
        self.assertEqual(panel['total_alertas'], 3)

    def test_dashboard_presenta_accesos_rapidos_operativos(self):
        llegada = self._reserva(self.hoy, self.hoy + timedelta(days=1))
        en_casa = self._reserva(self.hoy - timedelta(days=1), self.hoy, 'CHECKIN')

        response = self.client.get(reverse('recepcion_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Panel de reservas del día')
        self.assertContains(response, reverse('realizar_checkin', args=[llegada.id]))
        self.assertContains(response, reverse('cargar_consumo', args=[en_casa.estancia.id]))
        self.assertContains(response, reverse('pagar_folio', args=[en_casa.estancia.folio.id]))
        self.assertContains(response, reverse('realizar_checkout', args=[en_casa.id]))

    def test_alerta_garantia_seis_horas_y_bandeja_por_rol(self):
        reserva = self._reserva(
            self.hoy + timedelta(days=1),
            self.hoy + timedelta(days=3),
            'PENDIENTE',
        )
        reserva.fecha_limite_pago = timezone.now() + timedelta(hours=2)
        reserva.porcentaje_adelanto = Decimal('50.00')
        reserva.monto_adelanto_requerido = Decimal('100.00')
        reserva.save(update_fields=[
            'fecha_limite_pago', 'porcentaje_adelanto', 'monto_adelanto_requerido',
        ])

        panel = obtener_panel_reservas_dia(self.hoy)
        self.assertEqual(panel['garantias_por_vencer'], [reserva])
        self.assertEqual(panel['total_alertas'], 1)

        dashboard = self.client.get(reverse('recepcion_dashboard'))
        self.assertContains(dashboard, 'Garantías próximas a vencer')
        self.assertContains(dashboard, reverse('pagar_reserva', args=[reserva.id]))

        bandeja = self.client.get(reverse('alertas_operativas'))
        self.assertEqual(bandeja.status_code, 200)
        self.assertContains(bandeja, 'Completar garantía')
        self.assertContains(bandeja, reverse('detalle_reserva', args=[reserva.id]))

        gerencia = User.objects.create_user(username='gerencia_alertas', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Gerencia')
        gerencia.groups.add(grupo)
        self.client.force_login(gerencia)
        bandeja = self.client.get(reverse('alertas_operativas'))
        self.assertEqual(bandeja.status_code, 200)
        self.assertContains(bandeja, reverse('detalle_reserva', args=[reserva.id]))
        self.assertNotContains(bandeja, 'Completar garantía')

    def test_dashboard_procesa_garantia_vencida_automaticamente(self):
        reserva = self._reserva(
            self.hoy + timedelta(days=1),
            self.hoy + timedelta(days=2),
            'PENDIENTE',
        )
        Reserva.objects.filter(pk=reserva.pk).update(
            fecha_limite_pago=timezone.now() - timedelta(minutes=1),
            monto_adelanto_requerido=Decimal('100.00'),
        )

        response = self.client.get(reverse('recepcion_dashboard'))
        self.assertEqual(response.status_code, 200)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, 'CANCELADA')
        self.assertEqual(reserva.tipo_cancelacion, 'VENCIMIENTO_PAGO')
        self.assertEqual(
            reserva.historial_estados.first().motivo,
            'Plazo de pago de garantia vencido.',
        )
