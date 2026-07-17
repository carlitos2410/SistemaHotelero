from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from estancias.models import CargoEstancia, Comprobante, Estancia, Folio, MetodoPago, ProductoServicio
from estancias.services import registrar_adelanto_reserva, sincronizar_cargo_calculado
from habitaciones.models import Habitacion, TipoHabitacion
from habitaciones.services import actualizar_estado_housekeeping, cambiar_estado_habitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva
from reservas.services import (
    aplicar_cotizacion_reserva,
    calcular_tarifa_estadia,
    evaluar_checkin,
    obtener_habitaciones_disponibles,
    validar_ingreso_reserva,
)


class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = ['id', 'nombre', 'ruc', 'direccion', 'estrellas', 'telefono']


class TipoHabitacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoHabitacion
        fields = ['id', 'nombre', 'capacidad', 'precio_base', 'amenidades']


class HabitacionSerializer(serializers.ModelSerializer):
    hotel = HotelSerializer(read_only=True)
    tipo = TipoHabitacionSerializer(read_only=True)

    class Meta:
        model = Habitacion
        fields = ['id', 'hotel', 'tipo', 'numero', 'piso', 'estado']


class HuespedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Huesped
        fields = ['id', 'tipo_doc', 'num_doc', 'nombres', 'apellidos', 'email', 'telefono', 'nacionalidad']


class HuespedBusquedaResponseSerializer(serializers.Serializer):
    encontrado = serializers.BooleanField()
    huesped = HuespedSerializer(allow_null=True)


class PromocionAplicadaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    porcentaje_descuento = serializers.DecimalField(max_digits=5, decimal_places=2)


class PromocionDisponibleSerializer(PromocionAplicadaSerializer):
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    tipo_habitacion_id = serializers.IntegerField(allow_null=True)


class DesgloseCotizacionSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    tarifa_id = serializers.IntegerField(allow_null=True)
    tarifa_nombre = serializers.CharField()
    precio_original = serializers.DecimalField(max_digits=10, decimal_places=2)
    promocion_id = serializers.IntegerField(allow_null=True)
    promocion_nombre = serializers.CharField(allow_blank=True)
    porcentaje_descuento = serializers.DecimalField(max_digits=5, decimal_places=2)
    descuento = serializers.DecimalField(max_digits=10, decimal_places=2)
    precio_noche = serializers.DecimalField(max_digits=10, decimal_places=2)


class GarantiaCotizacionSerializer(serializers.Serializer):
    porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2)
    monto_requerido = serializers.DecimalField(max_digits=10, decimal_places=2)
    estado_inicial = serializers.CharField()
    plazo_pago_horas = serializers.IntegerField()
    adelanto_parcial_vencido = serializers.CharField()


class PoliticaCobroCotizacionSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    nombre = serializers.CharField()
    porcentaje_penalidad = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_igv = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_early_checkin = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_late_checkout = serializers.DecimalField(max_digits=5, decimal_places=2)


class CotizacionReservaResponseSerializer(serializers.Serializer):
    habitacion = HabitacionSerializer()
    noches = serializers.IntegerField()
    precio_sin_descuento = serializers.DecimalField(max_digits=10, decimal_places=2)
    descuento_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    precio_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    garantia_reserva = GarantiaCotizacionSerializer()
    promociones_aplicadas = PromocionAplicadaSerializer(many=True)
    promociones_disponibles = PromocionDisponibleSerializer(many=True)
    politica_cobro = PoliticaCobroCotizacionSerializer()
    desglose = DesgloseCotizacionSerializer(many=True)


class DisponibilidadQuerySerializer(serializers.Serializer):
    fecha_entrada = serializers.DateField()
    fecha_salida = serializers.DateField()
    tipo = serializers.IntegerField(required=False, min_value=1)
    num_personas = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if attrs['fecha_salida'] <= attrs['fecha_entrada']:
            raise serializers.ValidationError({
                'fecha_salida': 'La fecha de salida debe ser posterior a la fecha de entrada.'
            })
        return attrs


class CotizacionReservaQuerySerializer(DisponibilidadQuerySerializer):
    habitacion = serializers.IntegerField(min_value=1)
    promocion = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        habitacion = Habitacion.objects.select_related('hotel', 'tipo').filter(
            pk=attrs['habitacion']
        ).first()
        if not habitacion:
            raise serializers.ValidationError({'habitacion': 'La habitacion no existe.'})
        if attrs.get('tipo') and attrs['tipo'] != habitacion.tipo_id:
            raise serializers.ValidationError({'tipo': 'El tipo no corresponde a la habitacion seleccionada.'})
        if attrs.get('num_personas') and attrs['num_personas'] > habitacion.tipo.capacidad:
            raise serializers.ValidationError({
                'num_personas': f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).'
            })
        if attrs.get('promocion'):
            try:
                calcular_tarifa_estadia(
                    habitacion.tipo,
                    attrs['fecha_entrada'],
                    attrs['fecha_salida'],
                    promocion_id=attrs['promocion'],
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'promocion': exc.messages[0]}) from exc
        attrs['habitacion_obj'] = habitacion
        return attrs


class ReservaSerializer(serializers.ModelSerializer):
    hotel = HotelSerializer(read_only=True)
    huesped = HuespedSerializer(read_only=True)
    habitacion = HabitacionSerializer(read_only=True)
    total_adelantado = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True, coerce_to_string=False,
    )
    saldo_adelanto = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True, coerce_to_string=False,
    )
    garantia_completa = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reserva
        fields = [
            'id',
            'hotel',
            'huesped',
            'habitacion',
            'fecha_entrada',
            'fecha_salida',
            'num_adultos',
            'estado',
            'precio_sin_descuento',
            'descuento_promocion',
            'precio_total',
            'porcentaje_adelanto',
            'monto_adelanto_requerido',
            'total_adelantado',
            'saldo_adelanto',
            'garantia_completa',
            'fecha_limite_pago',
            'horas_cancelacion_gratuita',
            'porcentaje_retencion_cancelacion_tardia',
            'tipo_cancelacion',
            'motivo_cancelacion',
            'cancelada_en',
            'monto_reembolsado',
            'monto_retenido',
            'detalle_tarifa',
            'politica_cobro_checkout',
            'porcentaje_penalidad_salida_anticipada',
            'porcentaje_igv',
            'porcentaje_early_checkin',
            'porcentaje_late_checkout',
            'origen',
            'creado_en',
        ]


class ReservaCreateSerializer(serializers.Serializer):
    habitacion_id = serializers.IntegerField()
    fecha_entrada = serializers.DateField()
    fecha_salida = serializers.DateField()
    num_adultos = serializers.IntegerField(min_value=1)
    origen = serializers.CharField(required=False, allow_blank=True, max_length=100)
    promocion_id = serializers.IntegerField(required=False, allow_null=True, min_value=1, write_only=True)
    huesped = HuespedSerializer()

    def validate(self, attrs):
        fecha_entrada = attrs['fecha_entrada']
        fecha_salida = attrs['fecha_salida']
        habitacion = Habitacion.objects.select_related('hotel', 'tipo').filter(id=attrs['habitacion_id']).first()

        if not habitacion:
            raise serializers.ValidationError({'habitacion_id': 'La habitacion no existe.'})
        if fecha_salida <= fecha_entrada:
            raise serializers.ValidationError({'fecha_salida': 'La fecha de salida debe ser posterior a la fecha de entrada.'})
        if fecha_entrada < timezone.localdate():
            raise serializers.ValidationError({'fecha_entrada': 'No se puede reservar para una fecha anterior a hoy.'})
        if attrs['num_adultos'] > habitacion.tipo.capacidad:
            raise serializers.ValidationError({'num_adultos': f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).'})

        disponible = obtener_habitaciones_disponibles(
            fecha_entrada,
            fecha_salida,
            num_personas=attrs['num_adultos'],
            hotel_id=habitacion.hotel_id,
        ).filter(id=habitacion.id).exists()
        if not disponible:
            raise serializers.ValidationError({'habitacion_id': 'La habitacion no esta disponible para esas fechas.'})

        if attrs.get('promocion_id'):
            try:
                calcular_tarifa_estadia(
                    habitacion.tipo,
                    fecha_entrada,
                    fecha_salida,
                    promocion_id=attrs['promocion_id'],
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'promocion_id': exc.messages[0]}) from exc

        attrs['habitacion'] = habitacion
        return attrs

    def create(self, validated_data):
        huesped_data = validated_data.pop('huesped')
        habitacion_validada = validated_data.pop('habitacion')
        validated_data.pop('habitacion_id')
        fecha_entrada = validated_data['fecha_entrada']
        fecha_salida = validated_data['fecha_salida']
        promocion_id = validated_data.pop('promocion_id', None)

        try:
            with transaction.atomic():
                habitacion = (
                    Habitacion.objects.select_for_update()
                    .select_related('hotel', 'tipo')
                    .get(pk=habitacion_validada.pk)
                )
                disponible = obtener_habitaciones_disponibles(
                    fecha_entrada,
                    fecha_salida,
                    num_personas=validated_data['num_adultos'],
                    hotel_id=habitacion.hotel_id,
                ).filter(id=habitacion.id).exists()
                if not disponible:
                    raise serializers.ValidationError({
                        'habitacion_id': 'La habitacion dejo de estar disponible. Actualiza la busqueda.'
                    })

                cotizacion = calcular_tarifa_estadia(
                    habitacion.tipo,
                    fecha_entrada,
                    fecha_salida,
                    promocion_id=promocion_id,
                )
                huesped, _ = Huesped.objects.update_or_create(
                    num_doc=huesped_data['num_doc'],
                    defaults=huesped_data,
                )
                reserva = Reserva(
                    hotel=habitacion.hotel,
                    huesped=huesped,
                    habitacion=habitacion,
                    estado='PENDIENTE',
                    **validated_data,
                )
                reserva._estado_usuario = self.context['request'].user
                reserva._estado_motivo = 'Reserva creada mediante API.'
                aplicar_cotizacion_reserva(reserva, cotizacion)
                reserva.save()
                return reserva
        except IntegrityError as exc:
            raise serializers.ValidationError({
                'habitacion_id': 'La habitacion acaba de ser reservada para esas fechas.'
            }) from exc


class AdelantoReservaCreateSerializer(serializers.Serializer):
    metodo_pago = serializers.PrimaryKeyRelatedField(
        queryset=MetodoPago.objects.filter(activo=True)
    )
    monto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    numero_operacion = serializers.CharField(required=False, allow_blank=True, max_length=100)
    tipo_comprobante = serializers.ChoiceField(choices=Comprobante.TIPO_CHOICES)
    cliente_documento = serializers.CharField(max_length=20)
    cliente_nombre = serializers.CharField(max_length=180)
    cliente_direccion = serializers.CharField(required=False, allow_blank=True, max_length=220)
    observacion = serializers.CharField(required=False, allow_blank=True, max_length=180)

    def create(self, validated_data):
        try:
            return registrar_adelanto_reserva(
                self.context['reserva'],
                usuario=self.context['request'].user,
                **validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'detail': exc.messages}) from exc


class CancelarReservaSerializer(serializers.Serializer):
    motivo = serializers.CharField(min_length=5, max_length=250)


class CargoEstanciaSerializer(serializers.ModelSerializer):
    producto_servicio_nombre = serializers.CharField(source='producto_servicio.nombre', read_only=True)

    class Meta:
        model = CargoEstancia
        fields = [
            'id',
            'producto_servicio',
            'producto_servicio_nombre',
            'concepto',
            'cantidad',
            'precio_unitario',
            'monto',
            'fecha',
            'tipo',
            'pagado',
        ]
        read_only_fields = ['precio_unitario', 'monto', 'fecha', 'pagado']


class CargoCreateSerializer(serializers.Serializer):
    producto_servicio_id = serializers.IntegerField(required=False)
    concepto = serializers.CharField(required=False, allow_blank=True, max_length=150)
    cantidad = serializers.IntegerField(min_value=1, default=1)
    precio_unitario = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    tipo = serializers.ChoiceField(
        choices=[
            choice for choice in CargoEstancia.TIPO_CHOICES
            if choice[0] in CargoEstancia.TIPOS_MANUALES
        ],
        default='OTRO',
    )

    def validate(self, attrs):
        producto_id = attrs.get('producto_servicio_id')
        producto = None
        if producto_id:
            producto = ProductoServicio.objects.filter(id=producto_id, activo=True, precio__gt=0).first()
            if not producto:
                raise serializers.ValidationError({'producto_servicio_id': 'El producto o servicio no existe o no esta activo.'})
        elif not attrs.get('concepto') or attrs.get('precio_unitario') is None:
            raise serializers.ValidationError('Ingresa producto_servicio_id o concepto con precio_unitario.')

        attrs['producto_servicio'] = producto
        return attrs


class FolioSerializer(serializers.ModelSerializer):
    saldo_pendiente = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_pagado = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    cargos = CargoEstanciaSerializer(source='estancia.cargos', many=True, read_only=True)

    class Meta:
        model = Folio
        fields = [
            'id', 'subtotal', 'porcentaje_igv', 'igv', 'total',
            'total_pagado', 'saldo_pendiente', 'estado', 'cargos',
        ]


class EstanciaSerializer(serializers.ModelSerializer):
    reserva = ReservaSerializer(read_only=True)
    habitacion = HabitacionSerializer(read_only=True)
    folio = FolioSerializer(read_only=True)

    class Meta:
        model = Estancia
        fields = [
            'id',
            'reserva',
            'habitacion',
            'fecha_checkin',
            'fecha_checkout',
            'fecha_entrada_programada',
            'fecha_salida_programada',
            'precio_final',
            'tipo_checkin',
            'tipo_checkout',
            'cargo_early_checkin',
            'cargo_late_checkout',
            'politica_cobro_checkout',
            'noches_reservadas',
            'noches_reales',
            'monto_estadia_real',
            'cargo_penalidad_salida_anticipada',
            'estado',
            'folio',
        ]


class HousekeepingSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=['DISPONIBLE', 'LIMPIEZA', 'MANTENIMIENTO'])
    observacion = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['estado'] == 'MANTENIMIENTO' and not attrs.get('observacion'):
            raise serializers.ValidationError({'observacion': 'Ingresa una observacion para enviar a mantenimiento.'})
        return attrs


class ProrrogaCreateSerializer(serializers.Serializer):
    fecha_salida_nueva = serializers.DateField()
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=180)


def crear_estancia_desde_reserva(reserva, usuario=None):
    with transaction.atomic():
        reserva = Reserva.objects.select_for_update().get(pk=reserva.pk)
        if reserva.estado != 'CONFIRMADA':
            raise serializers.ValidationError(
                'La reserva debe estar confirmada con el adelanto completo antes del check-in.'
            )
        if not reserva.habitacion_id:
            raise serializers.ValidationError('La reserva no tiene habitacion asignada.')
        if Estancia.objects.filter(reserva=reserva).exists():
            raise serializers.ValidationError('Esta reserva ya tiene una estancia registrada.')

        habitacion = (
            Habitacion.objects.select_for_update()
            .select_related('tipo')
            .get(pk=reserva.habitacion_id)
        )
        if habitacion.estado != 'DISPONIBLE':
            raise serializers.ValidationError(
                f'No se puede hacer check-in: la habitacion esta {habitacion.get_estado_display().lower()}.'
            )
        if Estancia.objects.filter(habitacion=habitacion, estado='ACTIVA').exists():
            raise serializers.ValidationError('La habitacion ya tiene una estancia activa.')

        evaluacion = evaluar_checkin(reserva)
        errores_ingreso = validar_ingreso_reserva(reserva, evaluacion)
        if errores_ingreso:
            raise serializers.ValidationError({'detail': errores_ingreso})
        reserva.estado = 'CHECKIN'
        reserva._estado_usuario = usuario
        reserva._estado_motivo = 'Check-in confirmado mediante API.'
        reserva.save(update_fields=['estado'])

        cambiar_estado_habitacion(
            habitacion,
            'OCUPADA',
            usuario=usuario,
            motivo=f'Check-in API de reserva #{reserva.id}.',
        )

        estancia = Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            fecha_checkin=evaluacion['momento'],
            fecha_entrada_programada=reserva.fecha_entrada,
            fecha_salida_programada=reserva.fecha_salida,
            precio_final=reserva.precio_total,
            tipo_checkin=evaluacion['tipo'],
            cargo_early_checkin=evaluacion['cargo'],
            estado='ACTIVA',
        )

        if evaluacion['cargo'] > 0:
            CargoEstancia.objects.create(
                estancia=estancia,
                concepto=(
                    f'Ingreso anticipado: {evaluacion["noches_anticipadas"]} noche(s) adicional(es)'
                    if evaluacion['tipo'] == 'ANTICIPADO_FECHA'
                    else evaluacion['concepto_cargo']
                ),
                cantidad=max(evaluacion['noches_anticipadas'], 1),
                precio_unitario=(
                    evaluacion['cargo'] / max(evaluacion['noches_anticipadas'], 1)
                ),
                monto=evaluacion['cargo'],
                tipo=('NOCHE_ADICIONAL' if evaluacion['tipo'] == 'ANTICIPADO_FECHA' else 'EARLY_CHECKIN'),
            )

        folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
        from reservas.services import aplicar_adelantos_al_folio
        aplicar_adelantos_al_folio(reserva, folio)
        folio.calcular_totales()
        folio.save()
    return estancia


def preparar_folio_api(estancia, evaluacion):
    estancia.cargo_late_checkout = evaluacion['cargo']
    estancia.politica_cobro_checkout = evaluacion['politica']
    estancia.noches_reservadas = evaluacion['noches_reservadas']
    estancia.noches_reales = evaluacion['noches_reales']
    estancia.monto_estadia_real = evaluacion['monto_estadia_real']
    estancia.precio_final = evaluacion['monto_habitacion']
    estancia.cargo_penalidad_salida_anticipada = evaluacion['penalidad_salida_anticipada']
    estancia.save()

    sincronizar_cargo_calculado(
        estancia,
        tipo='LATE_CHECKOUT',
        concepto=evaluacion['concepto_cargo'],
        monto=evaluacion['cargo'],
    )
    sincronizar_cargo_calculado(
        estancia,
        tipo='PENALIDAD',
        concepto='Penalidad por salida anticipada',
        monto=evaluacion['penalidad_salida_anticipada'],
    )
    sincronizar_cargo_calculado(
        estancia,
        tipo='NOCHE_ADICIONAL',
        concepto='Noches adicionales no autorizadas previamente',
        monto=evaluacion['monto_noches_adicionales'],
        cantidad=evaluacion['noches_adicionales'] or 1,
    )

    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    folio.estado = 'PAGADO' if folio.saldo_pendiente <= 0 else 'PENDIENTE'
    folio.save()
    return folio


def actualizar_housekeeping(habitacion, estado, observacion='', usuario=None):
    try:
        return actualizar_estado_housekeeping(
            habitacion,
            estado,
            usuario=usuario,
            observacion=observacion,
        )
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages[0]) from exc
