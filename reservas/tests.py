from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from habitaciones.models import Habitacion, HabitacionEstadoHistorial, TipoHabitacion
from habitaciones.services import cambiar_estado_habitacion
from hoteles.models import Hotel
from estancias.models import CargoEstancia, ConfiguracionCobro, Estancia, Folio, ProrrogaEstancia

from .models import Huesped, Promocion, Reserva, Tarifa
from .services import (
    aplicar_cotizacion_reserva,
    autorizar_prorroga_estancia,
    calcular_tarifa_estadia,
    evaluar_checkin,
    evaluar_checkout,
    obtener_habitaciones_disponibles,
    validar_ingreso_reserva,
)


class FechasRealesEstanciaTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre='Hotel fechas reales', ruc='20999999991', direccion='Chiclayo', estrellas=4, telefono='999999991'
        )
        self.tipo = TipoHabitacion.objects.create(nombre='Suite fechas', capacidad=2, precio_base=Decimal('100.00'))
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='501', piso=5, estado='DISPONIBLE'
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='11223344', nombres='Mario', apellidos='Vega', nacionalidad='Peruana'
        )
        self.entrada = timezone.localdate() + timedelta(days=2)
        self.salida = self.entrada + timedelta(days=2)
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Tarifa fechas reales',
            precio_noche=Decimal('100.00'),
            fecha_inicio=timezone.localdate(),
            fecha_fin=self.salida + timedelta(days=10),
        )
        self.reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=self.entrada,
            fecha_salida=self.salida,
            num_adultos=1,
            estado='CONFIRMADA',
            precio_total=Decimal('200.00'),
        )

    def momento(self, fecha, hora=time(10, 0)):
        return timezone.make_aware(datetime.combine(fecha, hora))

    def crear_estancia(self):
        return Estancia.objects.create(
            reserva=self.reserva,
            habitacion=self.habitacion,
            fecha_checkin=self.momento(self.entrada, time(15, 0)),
            fecha_entrada_programada=self.entrada,
            fecha_salida_programada=self.salida,
            precio_final=self.reserva.precio_total,
            estado='ACTIVA',
        )

    def test_ingreso_un_dia_antes_cobra_noche_completa(self):
        evaluacion = evaluar_checkin(self.reserva, self.momento(self.entrada - timedelta(days=1)))

        self.assertEqual(evaluacion['tipo'], 'ANTICIPADO_FECHA')
        self.assertEqual(evaluacion['noches_anticipadas'], 1)
        self.assertEqual(evaluacion['cargo'], Decimal('100.00'))
        self.assertEqual(validar_ingreso_reserva(self.reserva, evaluacion), [])

    def test_llegada_tardia_y_reserva_totalmente_vencida(self):
        tardia = evaluar_checkin(self.reserva, self.momento(self.entrada + timedelta(days=1)))
        vencida = evaluar_checkin(self.reserva, self.momento(self.salida))

        self.assertEqual(tardia['tipo'], 'LLEGADA_TARDIA')
        self.assertTrue(tardia['permitido'])
        self.assertFalse(vencida['permitido'])

    def test_prorroga_bloquea_conflicto_y_luego_registra_historial_y_cargo(self):
        estancia = self.crear_estancia()
        otro = Huesped.objects.create(
            tipo_doc='DNI', num_doc='55667788', nombres='Rosa', apellidos='Diaz', nacionalidad='Peruana'
        )
        siguiente = Reserva.objects.create(
            hotel=self.hotel,
            huesped=otro,
            habitacion=self.habitacion,
            fecha_entrada=self.salida,
            fecha_salida=self.salida + timedelta(days=2),
            num_adultos=1,
            estado='CONFIRMADA',
            precio_total=Decimal('200.00'),
        )

        with self.assertRaises(ValidationError):
            autorizar_prorroga_estancia(estancia, self.salida + timedelta(days=1))

        siguiente.estado = 'CANCELADA'
        siguiente.save(update_fields=['estado'])
        prorroga = autorizar_prorroga_estancia(estancia, self.salida + timedelta(days=1), motivo='Solicitud')

        self.assertEqual(prorroga.monto, Decimal('100.00'))
        self.assertTrue(ProrrogaEstancia.objects.filter(estancia=estancia).exists())
        self.assertTrue(CargoEstancia.objects.filter(estancia=estancia, tipo='NOCHE_ADICIONAL', monto=100).exists())

    def test_checkout_dos_dias_despues_detecta_sobreestadia(self):
        estancia = self.crear_estancia()

        evaluacion = evaluar_checkout(
            self.reserva,
            estancia=estancia,
            momento=self.momento(self.salida + timedelta(days=2)),
        )

        self.assertEqual(evaluacion['tipo'], 'PRORROGA')
        self.assertEqual(evaluacion['noches_adicionales'], 2)
        self.assertEqual(evaluacion['monto_noches_adicionales'], Decimal('200.00'))

    def test_reserva_conserva_politica_aunque_cambie_configuracion_global(self):
        cotizacion = calcular_tarifa_estadia(self.tipo, self.entrada, self.salida)
        aplicar_cotizacion_reserva(self.reserva, cotizacion)
        self.reserva.save()
        configuracion = ConfiguracionCobro.actual()
        configuracion.porcentaje_penalidad_salida_anticipada = Decimal('20.00')
        configuracion.save()
        estancia = self.crear_estancia()

        evaluacion = evaluar_checkout(
            self.reserva,
            estancia=estancia,
            momento=self.momento(self.entrada + timedelta(days=1)),
        )

        self.assertEqual(self.reserva.politica_cobro_checkout, 'ESTADIA_REAL_PENALIDAD')
        self.assertEqual(self.reserva.porcentaje_penalidad_salida_anticipada, Decimal('50.00'))
        self.assertEqual(evaluacion['politica'], 'ESTADIA_REAL_PENALIDAD')
        self.assertEqual(evaluacion['penalidad_salida_anticipada'], Decimal('50.00'))

    def test_nueva_reserva_conserva_garantia_igv_y_recargos_configurados(self):
        configuracion = ConfiguracionCobro.actual()
        configuracion.porcentaje_garantia_reserva = Decimal('25.00')
        configuracion.horas_plazo_pago_garantia = 12
        configuracion.porcentaje_igv = Decimal('10.00')
        configuracion.porcentaje_early_checkin = Decimal('8.00')
        configuracion.porcentaje_late_checkout = Decimal('30.00')
        configuracion.save()
        habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='502',
            piso=5,
            estado='DISPONIBLE',
        )
        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=habitacion,
            fecha_entrada=self.entrada,
            fecha_salida=self.salida,
            num_adultos=1,
            estado='CONFIRMADA',
        )
        inicio = timezone.now()
        aplicar_cotizacion_reserva(
            reserva,
            calcular_tarifa_estadia(self.tipo, self.entrada, self.salida),
        )
        reserva.save()

        self.assertEqual(reserva.porcentaje_adelanto, Decimal('25.00'))
        self.assertEqual(reserva.monto_adelanto_requerido, Decimal('50.00'))
        self.assertEqual(reserva.porcentaje_igv, Decimal('10.00'))
        self.assertEqual(reserva.porcentaje_early_checkin, Decimal('8.00'))
        self.assertEqual(reserva.porcentaje_late_checkout, Decimal('30.00'))
        self.assertGreaterEqual(reserva.fecha_limite_pago, inicio + timedelta(hours=11, minutes=59))

        early = evaluar_checkin(reserva, self.momento(self.entrada, time(10, 0)))
        self.assertEqual(early['cargo'], Decimal('8.00'))
        self.assertEqual(early['concepto_cargo'], 'Early check-in 8% de tarifa')

        estancia = Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            fecha_checkin=self.momento(self.entrada, time(15, 0)),
            fecha_entrada_programada=self.entrada,
            fecha_salida_programada=self.salida,
            precio_final=reserva.precio_total,
            estado='ACTIVA',
        )
        late = evaluar_checkout(
            reserva,
            estancia=estancia,
            momento=self.momento(self.salida, time(13, 0)),
        )
        self.assertEqual(late['cargo'], Decimal('30.00'))
        self.assertEqual(late['concepto_cargo'], 'Late check-out 30% de tarifa')

        folio = Folio.objects.create(estancia=estancia)
        folio.calcular_totales()
        folio.save()
        self.assertEqual(folio.porcentaje_igv, Decimal('10.00'))
        self.assertEqual(folio.subtotal, Decimal('181.82'))
        self.assertEqual(folio.igv, Decimal('18.18'))


class IntegridadReservaTarifaTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.hotel = Hotel.objects.create(
            nombre='Hotel de prueba',
            ruc='20123456789',
            direccion='Direccion de prueba',
            estrellas=3,
            telefono='999999999',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Doble',
            capacidad=2,
            precio_base=Decimal('120.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='101',
            piso=1,
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI',
            num_doc='12345678',
            nombres='Ana',
            apellidos='Perez',
            nacionalidad='Peruana',
        )
        self.entrada = timezone.localdate() + timedelta(days=1)
        self.salida = self.entrada + timedelta(days=2)

    def crear_reserva(self, entrada=None, salida=None, estado='CONFIRMADA'):
        return Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=entrada or self.entrada,
            fecha_salida=salida or self.salida,
            num_adultos=2,
            estado=estado,
            precio_total=Decimal('240.00'),
        )

    def test_rechaza_salida_igual_a_entrada(self):
        reserva = Reserva(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=self.entrada,
            fecha_salida=self.entrada,
            num_adultos=1,
            precio_total=Decimal('120.00'),
        )

        with self.assertRaises(ValidationError):
            reserva.full_clean()

    def test_rechaza_tarifa_con_periodo_o_precio_invalido(self):
        tarifa = Tarifa(
            tipo_habitacion=self.tipo,
            nombre='Temporada invalida',
            precio_noche=Decimal('0.00'),
            fecha_inicio=self.salida,
            fecha_fin=self.entrada,
        )

        with self.assertRaises(ValidationError):
            tarifa.full_clean()

    def test_base_de_datos_rechaza_reservas_activas_solapadas(self):
        self.crear_reserva()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.crear_reserva(
                    entrada=self.entrada + timedelta(days=1),
                    salida=self.salida + timedelta(days=1),
                )

    def test_permite_reservas_contiguas_y_canceladas(self):
        self.crear_reserva()
        contigua = self.crear_reserva(
            entrada=self.salida,
            salida=self.salida + timedelta(days=1),
        )
        cancelada_solapada = self.crear_reserva(estado='CANCELADA')

        self.assertIsNotNone(contigua.pk)
        self.assertIsNotNone(cancelada_solapada.pk)

    def test_modelo_rechaza_hotel_distinto_y_exceso_de_capacidad(self):
        otro_hotel = Hotel.objects.create(
            nombre='Otro hotel',
            ruc='20987654321',
            direccion='Otra direccion',
            estrellas=2,
            telefono='988888888',
        )
        reserva = Reserva(
            hotel=otro_hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=self.entrada,
            fecha_salida=self.salida,
            num_adultos=3,
            precio_total=Decimal('240.00'),
        )

        with self.assertRaises(ValidationError) as contexto:
            reserva.full_clean()

        self.assertIn('hotel', contexto.exception.message_dict)
        self.assertIn('num_adultos', contexto.exception.message_dict)

    def test_calcula_cada_noche_con_su_temporada(self):
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Temporada uno',
            precio_noche=Decimal('150.00'),
            fecha_inicio=self.entrada,
            fecha_fin=self.entrada,
        )
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Temporada dos',
            precio_noche=Decimal('180.00'),
            fecha_inicio=self.entrada + timedelta(days=1),
            fecha_fin=self.entrada + timedelta(days=1),
        )

        cotizacion = calcular_tarifa_estadia(self.tipo, self.entrada, self.salida)

        self.assertEqual(cotizacion['noches'], 2)
        self.assertEqual(cotizacion['precio_total'], Decimal('330.00'))
        self.assertEqual(
            [linea['tarifa_nombre'] for linea in cotizacion['desglose']],
            ['Temporada uno', 'Temporada dos'],
        )

    def test_usa_precio_base_en_noche_sin_temporada(self):
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Solo primera noche',
            precio_noche=Decimal('150.00'),
            fecha_inicio=self.entrada,
            fecha_fin=self.entrada,
        )

        cotizacion = calcular_tarifa_estadia(self.tipo, self.entrada, self.salida)

        self.assertEqual(cotizacion['precio_total'], Decimal('270.00'))
        self.assertEqual(cotizacion['desglose'][1]['tarifa_nombre'], 'Tarifa base')

    def test_aplica_la_mejor_promocion_por_noche_y_tipo(self):
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Temporada promocional',
            precio_noche=Decimal('200.00'),
            fecha_inicio=self.entrada,
            fecha_fin=self.salida,
        )
        Promocion.objects.create(
            nombre='Global 10', porcentaje_descuento=Decimal('10.00'),
            fecha_inicio=self.entrada, fecha_fin=self.salida, activo=True,
        )
        Promocion.objects.create(
            nombre='Tipo 20', tipo_habitacion=self.tipo, porcentaje_descuento=Decimal('20.00'),
            fecha_inicio=self.entrada, fecha_fin=self.entrada, activo=True,
        )

        cotizacion = calcular_tarifa_estadia(self.tipo, self.entrada, self.salida)

        self.assertEqual(cotizacion['precio_sin_descuento'], Decimal('400.00'))
        self.assertEqual(cotizacion['descuento_total'], Decimal('60.00'))
        self.assertEqual(cotizacion['precio_total'], Decimal('340.00'))
        self.assertEqual(cotizacion['desglose'][0]['promocion_nombre'], 'Tipo 20')
        self.assertEqual(cotizacion['desglose'][1]['promocion_nombre'], 'Global 10')

    def test_reserva_conserva_promocion_aunque_se_edite_despues(self):
        promocion = Promocion.objects.create(
            nombre='Compra anticipada', tipo_habitacion=self.tipo,
            porcentaje_descuento=Decimal('25.00'), fecha_inicio=self.entrada,
            fecha_fin=self.salida, activo=True,
        )
        cotizacion = calcular_tarifa_estadia(self.tipo, self.entrada, self.salida)
        reserva = self.crear_reserva()
        aplicar_cotizacion_reserva(reserva, cotizacion)
        reserva.save()

        promocion.porcentaje_descuento = Decimal('5.00')
        promocion.save()
        reserva.refresh_from_db()

        self.assertEqual(reserva.descuento_promocion, Decimal('60.00'))
        self.assertEqual(reserva.precio_total, Decimal('180.00'))
        self.assertEqual(reserva.detalle_tarifa[0]['promocion_nombre'], 'Compra anticipada')

    def test_permite_elegir_una_promocion_especifica(self):
        promocion_10 = Promocion.objects.create(
            nombre='Elegida 10', porcentaje_descuento=Decimal('10.00'),
            fecha_inicio=self.entrada, fecha_fin=self.salida, activo=True,
        )
        Promocion.objects.create(
            nombre='Automatica 20', tipo_habitacion=self.tipo,
            porcentaje_descuento=Decimal('20.00'), fecha_inicio=self.entrada,
            fecha_fin=self.salida, activo=True,
        )

        cotizacion = calcular_tarifa_estadia(
            self.tipo, self.entrada, self.salida, promocion_id=promocion_10.id
        )

        self.assertEqual(cotizacion['precio_sin_descuento'], Decimal('240.00'))
        self.assertEqual(cotizacion['descuento_total'], Decimal('24.00'))
        self.assertEqual(cotizacion['precio_total'], Decimal('216.00'))
        self.assertTrue(all(
            linea['promocion_nombre'] == 'Elegida 10' for linea in cotizacion['desglose']
        ))

    def test_promocion_rechaza_porcentaje_y_fechas_invalidas(self):
        promocion = Promocion(
            nombre='Invalida', porcentaje_descuento=Decimal('120.00'),
            fecha_inicio=self.salida, fecha_fin=self.entrada,
        )

        with self.assertRaises(ValidationError) as contexto:
            promocion.full_clean()

        self.assertIn('porcentaje_descuento', contexto.exception.message_dict)
        self.assertIn('fecha_fin', contexto.exception.message_dict)

    def test_base_de_datos_rechaza_temporadas_solapadas(self):
        Tarifa.objects.create(
            tipo_habitacion=self.tipo,
            nombre='Temporada principal',
            precio_noche=Decimal('150.00'),
            fecha_inicio=self.entrada,
            fecha_fin=self.salida,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tarifa.objects.create(
                    tipo_habitacion=self.tipo,
                    nombre='Temporada duplicada',
                    precio_noche=Decimal('160.00'),
                    fecha_inicio=self.entrada + timedelta(days=1),
                    fecha_fin=self.salida + timedelta(days=1),
                )

    def test_disponibilidad_comparte_regla_de_solapamiento(self):
        self.crear_reserva()

        durante_reserva = obtener_habitaciones_disponibles(self.entrada, self.salida)
        despues_reserva = obtener_habitaciones_disponibles(
            self.salida,
            self.salida + timedelta(days=1),
        )

        self.assertNotIn(self.habitacion, durante_reserva)
        self.assertIn(self.habitacion, despues_reserva)


class PlanoHotelTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='recepcion-plano', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Plano',
            ruc='20444555666',
            direccion='Direccion',
            estrellas=4,
            telefono='977777777',
        )
        self.tipo = TipoHabitacion.objects.create(
            nombre='Simple',
            capacidad=1,
            precio_base=Decimal('100.00'),
        )
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel,
            tipo=self.tipo,
            numero='201',
            piso=2,
            estado='DISPONIBLE',
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI',
            num_doc='87654321',
            nombres='Luis',
            apellidos='Ramos',
            nacionalidad='Peruana',
        )

    def test_plano_muestra_reserva_del_dia_como_reservada(self):
        hoy = timezone.localdate()
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=hoy,
            fecha_salida=hoy + timedelta(days=1),
            num_adultos=1,
            estado='CONFIRMADA',
            precio_total=Decimal('100.00'),
        )

        response = self.client.get(reverse('estado_habitaciones_datos'))

        self.assertEqual(response.status_code, 200)
        habitacion = response.json()['habitaciones'][0]
        self.assertEqual(habitacion['estado'], 'RESERVADA')
        self.assertEqual(habitacion['reserva_id'], reserva.id)
        self.assertEqual(response.json()['resumen']['RESERVADA'], 1)

    def test_plano_web_contiene_filtros_y_actualizacion(self):
        response = self.client.get(reverse('estado_habitaciones'))

        self.assertContains(response, 'Plano del hotel')
        self.assertContains(response, 'filter-piso')
        self.assertContains(response, reverse('estado_habitaciones_datos'))

    def test_usuario_sin_autenticar_es_redirigido(self):
        self.client.logout()

        response = self.client.get(reverse('estado_habitaciones_datos'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_calendario_no_repite_mantenimiento_en_todo_el_mes(self):
        self.habitacion.numero = '308'
        self.habitacion.estado = 'MANTENIMIENTO'
        self.habitacion.save(update_fields=['numero', 'estado'])
        hoy = timezone.localdate()

        response = self.client.get(reverse('calendario_ocupacion'), {
            'anio': hoy.year,
            'mes': hoy.month,
        })

        self.assertEqual(response.status_code, 200)
        fila = next(
            item for item in response.context['filas']
            if item['habitacion'].id == self.habitacion.id
        )
        dias_mantenimiento = [
            celda['dia'] for celda in fila['celdas']
            if celda['estado'] == 'MANTENIMIENTO'
        ]
        self.assertEqual(dias_mantenimiento, [hoy])

    def test_calendario_conserva_ocupacion_y_huesped_despues_del_checkout(self):
        hoy = timezone.localdate()
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=hoy,
            fecha_salida=hoy + timedelta(days=1),
            num_adultos=1,
            estado='CHECKOUT',
            precio_total=Decimal('100.00'),
        )

        response = self.client.get(reverse('calendario_ocupacion'), {
            'anio': hoy.year,
            'mes': hoy.month,
        })

        fila = next(
            item for item in response.context['filas']
            if item['habitacion'].id == self.habitacion.id
        )
        celda = next(item for item in fila['celdas'] if item['dia'] == hoy)
        self.assertEqual(celda['estado'], 'OCUPADA')
        self.assertEqual(celda['reserva_id'], reserva.id)
        self.assertEqual(celda['detalle'], 'Luis Ramos')

    def test_historial_conserva_checkout_limpieza_y_mantenimiento(self):
        cambiar_estado_habitacion(
            self.habitacion,
            'OCUPADA',
            usuario=self.usuario,
            motivo='Check-in de prueba.',
        )
        cambiar_estado_habitacion(
            self.habitacion,
            'LIMPIEZA',
            usuario=self.usuario,
            motivo='Checkout de prueba.',
        )
        cambiar_estado_habitacion(
            self.habitacion,
            'MANTENIMIENTO',
            usuario=self.usuario,
            motivo='Falla detectada por housekeeping.',
        )

        cambios = list(
            HabitacionEstadoHistorial.objects.filter(habitacion=self.habitacion)
            .order_by('cambiado_en', 'id')
            .values_list('estado_anterior', 'estado_nuevo')
        )

        self.assertEqual(cambios[-3:], [
            ('DISPONIBLE', 'OCUPADA'),
            ('OCUPADA', 'LIMPIEZA'),
            ('LIMPIEZA', 'MANTENIMIENTO'),
        ])
        response = self.client.get(reverse('estado_habitaciones_datos'))
        historial = response.json()['habitaciones'][0]['historial']
        self.assertEqual(historial[0]['estado_nuevo'], 'MANTENIMIENTO')
        self.assertEqual(historial[0]['usuario'], self.usuario.username)

    def test_dashboard_integra_el_plano_actualizado(self):
        response = self.client.get(reverse('recepcion_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dashboard-room-grid')
        self.assertContains(response, reverse('estado_habitaciones_datos'))
        self.assertContains(response, 'Ver plano completo e historial')

    def test_calendario_usa_fechas_reales_de_estancia_finalizada(self):
        hoy = timezone.localdate()
        entrada_real = hoy.replace(day=1)
        salida_real = entrada_real + timedelta(days=1)
        reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=entrada_real,
            fecha_salida=entrada_real + timedelta(days=5),
            num_adultos=1,
            estado='CHECKOUT',
            precio_total=Decimal('500.00'),
        )
        Estancia.objects.create(
            reserva=reserva,
            habitacion=self.habitacion,
            fecha_checkin=timezone.make_aware(datetime.combine(entrada_real, time(15, 0))),
            fecha_checkout=timezone.make_aware(datetime.combine(salida_real, time(10, 0))),
            precio_final=Decimal('100.00'),
            estado='FINALIZADA',
        )

        response = self.client.get(reverse('calendario_ocupacion'), {
            'fecha': entrada_real.isoformat(),
        })
        fila = next(item for item in response.context['filas'] if item['habitacion'].id == self.habitacion.id)
        por_dia = {item['dia']: item for item in fila['celdas']}

        self.assertEqual(por_dia[entrada_real]['estado'], 'OCUPADA')
        self.assertEqual(por_dia[salida_real]['estado'], 'DISPONIBLE')

    def test_acceso_calendario_segun_rol(self):
        self.assertEqual(self.client.get(reverse('calendario_ocupacion')).status_code, 200)

        for nombre_rol in ['Gerencia', 'Administrador']:
            usuario = User.objects.create_user(
                username=f'usuario-{nombre_rol.lower()}',
                password='clave12345',
            )
            grupo, _ = Group.objects.get_or_create(name=nombre_rol)
            usuario.groups.add(grupo)
            self.client.force_login(usuario)
            self.assertEqual(
                self.client.get(reverse('calendario_ocupacion')).status_code,
                200,
                nombre_rol,
            )

        limpieza = User.objects.create_user(username='usuario-limpieza-cal', password='clave12345')
        grupo_limpieza, _ = Group.objects.get_or_create(name='Limpieza')
        limpieza.groups.add(grupo_limpieza)
        self.client.force_login(limpieza)
        response = self.client.get(reverse('calendario_ocupacion'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('inicio'))

    def test_calendario_respeta_transiciones_historicas_por_dia(self):
        hoy = timezone.localdate()
        dia_uno = hoy.replace(day=1)
        dia_dos = dia_uno + timedelta(days=1)
        dia_tres = dia_uno + timedelta(days=2)
        self.habitacion.historial_estados.all().delete()
        eventos = [
            ('DISPONIBLE', 'MANTENIMIENTO', dia_uno),
            ('MANTENIMIENTO', 'DISPONIBLE', dia_dos),
            ('DISPONIBLE', 'MANTENIMIENTO', dia_tres),
        ]
        for anterior, nuevo, fecha_evento in eventos:
            HabitacionEstadoHistorial.objects.create(
                habitacion=self.habitacion,
                estado_anterior=anterior,
                estado_nuevo=nuevo,
                motivo='Prueba de historial diario.',
                cambiado_en=timezone.make_aware(datetime.combine(fecha_evento, time(8, 0))),
            )
        Habitacion.objects.filter(pk=self.habitacion.pk).update(estado='MANTENIMIENTO')

        response = self.client.get(reverse('calendario_ocupacion'), {
            'fecha': dia_uno.isoformat(),
        })
        fila = next(item for item in response.context['filas'] if item['habitacion'].id == self.habitacion.id)
        por_dia = {item['dia']: item['estado'] for item in fila['celdas']}

        self.assertEqual(por_dia[dia_uno], 'MANTENIMIENTO')
        self.assertEqual(por_dia[dia_dos], 'DISPONIBLE')
        self.assertEqual(por_dia[dia_tres], 'MANTENIMIENTO')
