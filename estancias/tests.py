from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva

from .forms import CargoHabitacionForm
from .models import CargoEstancia, Comprobante, CorrelativoComprobante, Estancia, Folio, MetodoPago, MovimientoCaja, Pago, ProrrogaEstancia, ProductoServicio
from .services import agregar_cargo_estancia, recalcular_folio, registrar_adelanto_reserva, registrar_pago_folio, sincronizar_cargo_calculado
from reservas.services import cancelar_reserva, liberar_reservas_sin_garantia_vencidas
from reportes.services import calcular_reporte_ocupacion


class FolioCajaTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='cajarecepcion', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Caja', ruc='20555555551', direccion='Chiclayo', estrellas=4, telefono='955555551'
        )
        self.tipo = TipoHabitacion.objects.create(nombre='Habitacion Caja', capacidad=2, precio_base=Decimal('100.00'))
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='1001', piso=10, estado='OCUPADA'
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='50505050', nombres='Cliente', apellidos='Caja', nacionalidad='Peruana'
        )
        hoy = timezone.localdate()
        self.reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=hoy,
            fecha_salida=hoy + timedelta(days=1),
            num_adultos=1,
            estado='CHECKIN',
            precio_total=Decimal('100.00'),
        )
        self.estancia = Estancia.objects.create(
            reserva=self.reserva,
            habitacion=self.habitacion,
            fecha_checkin=timezone.make_aware(datetime.combine(hoy, time(15, 0))),
            fecha_entrada_programada=hoy,
            fecha_salida_programada=hoy + timedelta(days=1),
            precio_final=Decimal('100.00'),
            estado='ACTIVA',
        )
        self.folio = recalcular_folio(Folio.objects.create(estancia=self.estancia))
        self.efectivo = MetodoPago.objects.create(nombre='Efectivo pruebas caja', tipo='EFECTIVO')
        self.producto = ProductoServicio.objects.create(
            nombre='Lavanderia prueba', categoria='LAVANDERIA', precio=Decimal('20.00'), activo=True
        )

    def _pagar(self, monto, documento='50505050'):
        return registrar_pago_folio(
            self.folio,
            metodo_pago=self.efectivo,
            monto=monto,
            tipo_comprobante='BOLETA',
            cliente_documento=documento,
            cliente_nombre='Cliente Caja',
            usuario=self.usuario,
        )

    def test_folio_calcula_estadia_cargos_igv_y_saldo(self):
        cargo, folio = agregar_cargo_estancia(
            self.estancia,
            producto_servicio=self.producto,
            concepto=self.producto.nombre,
            cantidad=2,
            precio_unitario=self.producto.precio,
            tipo=self.producto.categoria,
        )

        self.assertEqual(cargo.monto, Decimal('40.00'))
        self.assertEqual(folio.subtotal, Decimal('118.64'))
        self.assertEqual(folio.igv, Decimal('21.36'))
        self.assertEqual(folio.total, Decimal('140.00'))
        self.assertEqual(folio.saldo_pendiente, Decimal('140.00'))

    def test_registros_financieros_impiden_borrado_en_cascada(self):
        pago, comprobante, _ = self._pagar(Decimal('100.00'))

        with self.assertRaises(ProtectedError):
            pago.delete()
        with self.assertRaises(ProtectedError):
            self.estancia.delete()
        with self.assertRaises(ProtectedError):
            self.reserva.delete()

        self.assertTrue(Pago.objects.filter(pk=pago.pk).exists())
        self.assertTrue(Comprobante.objects.filter(pk=comprobante.pk).exists())
        self.assertTrue(MovimientoCaja.objects.filter(pago=pago).exists())

    def test_pago_no_puede_quedar_sin_reserva_ni_folio(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Pago.objects.create(
                    metodo_pago=self.efectivo,
                    monto=Decimal('10.00'),
                )

    def test_movimiento_de_caja_exige_monto_positivo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MovimientoCaja.objects.create(
                    tipo='INGRESO',
                    concepto='AJUSTE',
                    monto=Decimal('0.00'),
                    metodo_pago=self.efectivo,
                )

    def test_admin_financiero_es_solo_lectura(self):
        modelos_protegidos = [
            Reserva,
            Estancia,
            CargoEstancia,
            ProrrogaEstancia,
            Folio,
            Pago,
            Comprobante,
            MovimientoCaja,
            CorrelativoComprobante,
        ]
        for modelo in modelos_protegidos:
            registro_admin = admin.site._registry[modelo]
            with self.subTest(modelo=modelo.__name__):
                self.assertFalse(registro_admin.has_add_permission(None))
                self.assertFalse(registro_admin.has_change_permission(None))
                self.assertFalse(registro_admin.has_delete_permission(None))

    def test_historial_pagos_y_reporte_caja_paginan_sin_alterar_totales(self):
        pagos = Pago.objects.bulk_create([
            Pago(
                folio=self.folio,
                metodo_pago=self.efectivo,
                monto=Decimal('1.00'),
                estado='APROBADO',
                usuario_responsable=self.usuario,
            )
            for _ in range(30)
        ])
        MovimientoCaja.objects.bulk_create([
            MovimientoCaja(
                pago=pago,
                tipo='INGRESO',
                concepto='PAGO_FOLIO',
                monto=Decimal('1.00'),
                metodo_pago=self.efectivo,
                usuario_responsable=self.usuario,
            )
            for pago in pagos
        ])

        historial = self.client.get(reverse('historial_pagos'), {'page': 2})
        caja = self.client.get(reverse('reporte_caja_diario'), {'page': 2})

        self.assertEqual(historial.context['pagina'].paginator.count, 30)
        self.assertEqual(len(historial.context['pagos']), 5)
        self.assertEqual(historial.context['total'], Decimal('30.00'))
        self.assertEqual(caja.context['pagina'].paginator.count, 30)
        self.assertEqual(len(caja.context['movimientos']), 5)
        self.assertEqual(caja.context['ingresos'], Decimal('30.00'))

    def test_formulario_excluye_productos_sin_precio(self):
        automatico = ProductoServicio.objects.create(
            nombre='Early check-in 5%', categoria='OTRO', precio=Decimal('0.00'), activo=False
        )

        formulario = CargoHabitacionForm()

        self.assertNotIn(automatico, formulario.fields['producto_servicio'].queryset)
        self.assertIn(self.producto, formulario.fields['producto_servicio'].queryset)

    def test_producto_activo_y_cargo_manual_exigen_precio_positivo(self):
        automatico = ProductoServicio(
            nombre='Late check-out 50%', categoria='OTRO', precio=Decimal('0.00'), activo=True
        )
        with self.assertRaises(ValidationError):
            automatico.full_clean()

        with self.assertRaises(ValidationError):
            agregar_cargo_estancia(
                self.estancia,
                concepto='Cargo manual cero',
                cantidad=1,
                precio_unitario=Decimal('0.00'),
                tipo='OTRO',
            )

    def test_cargo_nuevo_reabre_folio_que_ya_estaba_pagado(self):
        pago, comprobante, folio = self._pagar(Decimal('100.00'))
        self.assertEqual(folio.estado, 'PAGADO')

        cargo, folio = agregar_cargo_estancia(
            self.estancia,
            producto_servicio=self.producto,
            concepto=self.producto.nombre,
            cantidad=1,
            precio_unitario=self.producto.precio,
            tipo=self.producto.categoria,
        )

        self.assertEqual(folio.estado, 'PENDIENTE')
        self.assertEqual(folio.total, Decimal('120.00'))
        self.assertEqual(folio.saldo_pendiente, Decimal('20.00'))

    def test_servicio_revalida_saldo_y_bloquea_sobrepago(self):
        folio_desactualizado = Folio.objects.get(pk=self.folio.pk)
        self._pagar(Decimal('60.00'))

        with self.assertRaises(ValidationError):
            registrar_pago_folio(
                folio_desactualizado,
                metodo_pago=self.efectivo,
                monto=Decimal('100.00'),
                tipo_comprobante='BOLETA',
                cliente_documento='50505050',
                cliente_nombre='Cliente Caja',
                usuario=self.usuario,
            )

        self.assertEqual(folio_desactualizado.pagos_normalizados.count(), 1)

    def test_pagos_parciales_generan_correlativos_y_movimientos_unicos(self):
        primer_pago, primer_comprobante, folio = self._pagar(Decimal('50.00'))
        segundo_pago, segundo_comprobante, folio = self._pagar(Decimal('50.00'))

        self.assertEqual(primer_comprobante.correlativo, 'B001-000001')
        self.assertEqual(segundo_comprobante.correlativo, 'B001-000002')
        self.assertEqual(Comprobante.objects.count(), 2)
        self.assertEqual(MovimientoCaja.objects.count(), 2)
        self.assertEqual(CorrelativoComprobante.objects.get(tipo='BOLETA', serie='B001').ultimo_numero, 2)
        self.assertEqual(folio.estado, 'PAGADO')

    def test_caja_recalcula_folios_antiguos_con_estado_incorrecto(self):
        self.folio.estado = 'PAGADO'
        self.folio.save(update_fields=['estado'])

        response = self.client.get(reverse('caja_recepcion'))

        self.assertEqual(response.status_code, 200)
        self.folio.refresh_from_db()
        self.assertEqual(self.folio.estado, 'PENDIENTE')
        self.assertContains(response, f'#{self.folio.id}')

    def test_cargo_calculado_de_checkout_se_actualiza_sin_duplicarse(self):
        sincronizar_cargo_calculado(
            self.estancia,
            tipo='NOCHE_ADICIONAL',
            concepto='Noches adicionales no autorizadas previamente',
            monto=Decimal('100.00'),
            cantidad=1,
        )
        sincronizar_cargo_calculado(
            self.estancia,
            tipo='NOCHE_ADICIONAL',
            concepto='Noches adicionales no autorizadas previamente',
            monto=Decimal('200.00'),
            cantidad=2,
        )

        cargos = CargoEstancia.objects.filter(
            estancia=self.estancia, concepto='Noches adicionales no autorizadas previamente'
        )
        self.assertEqual(cargos.count(), 1)
        self.assertEqual(cargos.get().cantidad, 2)
        self.assertEqual(cargos.get().monto, Decimal('200.00'))

        sincronizar_cargo_calculado(
            self.estancia,
            tipo='NOCHE_ADICIONAL',
            concepto='Noches adicionales no autorizadas previamente',
            monto=Decimal('0.00'),
        )
        self.assertFalse(cargos.exists())


class AdelantoReservaTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username='adelantos', password='clave12345')
        grupo, _ = Group.objects.get_or_create(name='Recepcionista')
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)
        self.hotel = Hotel.objects.create(
            nombre='Hotel Garantias', ruc='20555555559', direccion='Chiclayo', estrellas=4, telefono='955555559'
        )
        self.tipo = TipoHabitacion.objects.create(nombre='Alta demanda', capacidad=2, precio_base=Decimal('200.00'))
        self.habitacion = Habitacion.objects.create(
            hotel=self.hotel, tipo=self.tipo, numero='1201', piso=12, estado='DISPONIBLE'
        )
        self.huesped = Huesped.objects.create(
            tipo_doc='DNI', num_doc='60606060', nombres='Cliente', apellidos='Garantia', nacionalidad='Peruana'
        )
        hoy = timezone.localdate()
        self.reserva = Reserva.objects.create(
            hotel=self.hotel,
            huesped=self.huesped,
            habitacion=self.habitacion,
            fecha_entrada=hoy + timedelta(days=2),
            fecha_salida=hoy + timedelta(days=4),
            num_adultos=1,
            estado='PENDIENTE',
            precio_total=Decimal('400.00'),
            porcentaje_adelanto=Decimal('50.00'),
            monto_adelanto_requerido=Decimal('200.00'),
        )
        self.efectivo = MetodoPago.objects.create(nombre='Efectivo garantia', tipo='EFECTIVO')

    def _adelantar(self, monto):
        return registrar_adelanto_reserva(
            self.reserva,
            metodo_pago=self.efectivo,
            monto=monto,
            tipo_comprobante='BOLETA',
            cliente_documento=self.huesped.num_doc,
            cliente_nombre='Cliente Garantia',
            usuario=self.usuario,
        )

    def test_confirma_solo_al_completar_cincuenta_por_ciento(self):
        historial_inicial = self.reserva.historial_estados.get()
        self.assertEqual(historial_inicial.estado_anterior, '')
        self.assertEqual(historial_inicial.estado_nuevo, 'PENDIENTE')

        pago, comprobante, reserva = self._adelantar(Decimal('80.00'))
        self.assertEqual(reserva.estado, 'PENDIENTE')
        self.assertEqual(reserva.saldo_adelanto, Decimal('120.00'))
        self.assertEqual(pago.movimientos_caja.get(tipo='INGRESO').concepto, 'ADELANTO_RESERVA')
        self.assertEqual(comprobante.estado, 'EMITIDO')

        pdf = self.client.get(reverse('exportar_comprobante', args=[comprobante.id]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        historial = self.client.get(reverse('historial_pagos'))
        self.assertContains(historial, f'Reserva #{self.reserva.id}')
        reporte = self.client.get(reverse('reporte_caja_diario'))
        self.assertContains(reporte, 'Cliente Garantia')

        _, _, reserva = self._adelantar(Decimal('120.00'))
        self.assertEqual(reserva.estado, 'CONFIRMADA')
        self.assertEqual(reserva.total_adelantado, Decimal('200.00'))
        cambio = reserva.historial_estados.first()
        self.assertEqual(cambio.estado_anterior, 'PENDIENTE')
        self.assertEqual(cambio.estado_nuevo, 'CONFIRMADA')
        self.assertEqual(cambio.cambiado_por, self.usuario)
        self.assertEqual(cambio.motivo, 'Garantia del 50% completada.')

        cantidad = reserva.historial_estados.count()
        reserva.origen = 'Recepcion'
        reserva.save(update_fields=['origen'])
        self.assertEqual(reserva.historial_estados.count(), cantidad)

    def test_adelanto_se_aplica_al_folio_sin_duplicar_pago(self):
        self._adelantar(Decimal('200.00'))
        self.reserva.refresh_from_db()
        self.reserva.estado = 'CHECKIN'
        self.reserva.save(update_fields=['estado'])
        hoy = timezone.localdate()
        estancia = Estancia.objects.create(
            reserva=self.reserva,
            habitacion=self.habitacion,
            fecha_checkin=timezone.make_aware(datetime.combine(hoy, time(15, 0))),
            fecha_entrada_programada=hoy,
            fecha_salida_programada=hoy + timedelta(days=2),
            precio_final=Decimal('400.00'),
            estado='ACTIVA',
        )
        folio = Folio.objects.create(estancia=estancia)
        from reservas.services import aplicar_adelantos_al_folio
        aplicar_adelantos_al_folio(self.reserva, folio)
        folio = recalcular_folio(folio)

        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(folio.total_pagado, Decimal('200.00'))
        self.assertEqual(folio.saldo_pendiente, Decimal('200.00'))
        self.assertEqual(Pago.objects.get().reserva, self.reserva)

    def test_no_show_conserva_el_adelanto(self):
        self._adelantar(Decimal('200.00'))
        ayer = timezone.localdate() - timedelta(days=1)
        Reserva.objects.filter(pk=self.reserva.pk).update(
            fecha_entrada=ayer - timedelta(days=2),
            fecha_salida=ayer,
        )
        response = self.client.post(reverse('marcar_no_show', args=[self.reserva.id]))
        self.assertEqual(response.status_code, 302)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'NO_SHOW')
        self.assertEqual(self.reserva.total_adelantado, Decimal('200.00'))

    def test_cancelacion_dentro_de_plazo_devuelve_adelanto_y_registra_egreso(self):
        pago, _, _ = self._adelantar(Decimal('200.00'))
        entrada = timezone.make_aware(datetime.combine(self.reserva.fecha_entrada, time(15, 0)))
        reserva, evaluacion = cancelar_reserva(
            self.reserva,
            motivo='Cambio de planes del huesped',
            usuario=self.usuario,
            momento=entrada - timedelta(hours=72),
        )

        self.assertEqual(reserva.estado, 'CANCELADA')
        self.assertEqual(reserva.tipo_cancelacion, 'GRATUITA')
        self.assertEqual(reserva.monto_reembolsado, Decimal('200.00'))
        self.assertEqual(reserva.monto_retenido, Decimal('0.00'))
        self.assertEqual(evaluacion['monto_reembolsar'], Decimal('200.00'))
        cambio = reserva.historial_estados.first()
        self.assertEqual(cambio.estado_anterior, 'CONFIRMADA')
        self.assertEqual(cambio.estado_nuevo, 'CANCELADA')
        self.assertEqual(cambio.cambiado_por, self.usuario)
        self.assertEqual(cambio.motivo, 'Cambio de planes del huesped')
        self.assertEqual(pago.movimientos_caja.filter(tipo='INGRESO').count(), 1)
        self.assertEqual(pago.movimientos_caja.filter(tipo='EGRESO').count(), 1)
        pago.refresh_from_db()
        self.assertEqual(pago.monto_neto, Decimal('0.00'))
        reporte = calcular_reporte_ocupacion(timezone.localdate(), timezone.localdate())
        self.assertEqual(reporte['revenue_cobrado'], Decimal('0.00'))

    def test_cancelacion_tardia_retiene_adelanto_sin_egreso(self):
        pago, _, _ = self._adelantar(Decimal('200.00'))
        entrada = timezone.make_aware(datetime.combine(self.reserva.fecha_entrada, time(15, 0)))
        reserva, evaluacion = cancelar_reserva(
            self.reserva,
            motivo='Cancelacion fuera de plazo',
            usuario=self.usuario,
            momento=entrada - timedelta(hours=12),
        )

        self.assertEqual(reserva.tipo_cancelacion, 'TARDIA')
        self.assertEqual(reserva.monto_reembolsado, Decimal('0.00'))
        self.assertEqual(reserva.monto_retenido, Decimal('200.00'))
        self.assertEqual(evaluacion['porcentaje_retencion'], Decimal('100.00'))
        self.assertFalse(pago.movimientos_caja.filter(tipo='EGRESO').exists())

    def test_pantalla_cancelacion_exige_confirmacion(self):
        self._adelantar(Decimal('200.00'))
        response = self.client.get(reverse('cancelar_reserva', args=[self.reserva.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resultado de la politica')

        response = self.client.post(reverse('cancelar_reserva', args=[self.reserva.id]), {
            'motivo': 'Solicitud expresa del huesped',
        })
        self.assertEqual(response.status_code, 200)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'CONFIRMADA')

    def test_vencimiento_de_garantia_cancela_y_audita_adelanto_parcial(self):
        self._adelantar(Decimal('80.00'))
        Reserva.objects.filter(pk=self.reserva.pk).update(
            fecha_limite_pago=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(liberar_reservas_sin_garantia_vencidas(), 1)

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'CANCELADA')
        self.assertEqual(self.reserva.tipo_cancelacion, 'VENCIMIENTO_PAGO')
        self.assertEqual(self.reserva.monto_retenido, Decimal('80.00'))
        self.assertEqual(self.reserva.monto_reembolsado, Decimal('0.00'))
