from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from estancias.models import CargoEstancia, Estancia, Folio, ProductoServicio
from habitaciones.models import Habitacion, ObservacionMantenimiento, TipoHabitacion
from hoteles.models import Hotel
from reservas.models import Huesped, Reserva, Tarifa
from reservas.services import evaluar_checkin


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


class ReservaSerializer(serializers.ModelSerializer):
    hotel = HotelSerializer(read_only=True)
    huesped = HuespedSerializer(read_only=True)
    habitacion = HabitacionSerializer(read_only=True)

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
            'precio_total',
            'origen',
            'creado_en',
        ]


class ReservaCreateSerializer(serializers.Serializer):
    habitacion_id = serializers.IntegerField()
    fecha_entrada = serializers.DateField()
    fecha_salida = serializers.DateField()
    num_adultos = serializers.IntegerField(min_value=1)
    origen = serializers.CharField(required=False, allow_blank=True, max_length=100)
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
        if habitacion.estado != 'DISPONIBLE':
            raise serializers.ValidationError({'habitacion_id': 'La habitacion debe estar disponible.'})
        if attrs['num_adultos'] > habitacion.tipo.capacidad:
            raise serializers.ValidationError({'num_adultos': f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).'})

        reserva_existente = Reserva.objects.filter(
            habitacion=habitacion,
            estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
            fecha_entrada__lt=fecha_salida,
            fecha_salida__gt=fecha_entrada,
        ).exists()
        if reserva_existente:
            raise serializers.ValidationError({'habitacion_id': 'La habitacion ya tiene una reserva activa en esas fechas.'})

        attrs['habitacion'] = habitacion
        return attrs

    def create(self, validated_data):
        huesped_data = validated_data.pop('huesped')
        habitacion = validated_data.pop('habitacion')
        validated_data.pop('habitacion_id')
        fecha_entrada = validated_data['fecha_entrada']
        fecha_salida = validated_data['fecha_salida']
        noches = max((fecha_salida - fecha_entrada).days, 1)

        tarifa = Tarifa.objects.filter(
            tipo_habitacion=habitacion.tipo,
            fecha_inicio__lte=fecha_entrada,
            fecha_fin__gte=fecha_salida,
        ).first()
        precio_noche = tarifa.precio_noche if tarifa else habitacion.tipo.precio_base

        huesped, _ = Huesped.objects.update_or_create(
            num_doc=huesped_data['num_doc'],
            defaults=huesped_data,
        )

        return Reserva.objects.create(
            hotel=habitacion.hotel,
            huesped=huesped,
            habitacion=habitacion,
            precio_total=Decimal(noches) * precio_noche,
            estado='CONFIRMADA',
            **validated_data,
        )


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
    tipo = serializers.ChoiceField(choices=CargoEstancia.TIPO_CHOICES, default='OTRO')

    def validate(self, attrs):
        producto_id = attrs.get('producto_servicio_id')
        producto = None
        if producto_id:
            producto = ProductoServicio.objects.filter(id=producto_id, activo=True).first()
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
        fields = ['id', 'subtotal', 'igv', 'total', 'total_pagado', 'saldo_pendiente', 'estado', 'cargos']


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


def crear_estancia_desde_reserva(reserva):
    if reserva.estado in ['CHECKIN', 'CHECKOUT', 'CANCELADA']:
        raise serializers.ValidationError('No se puede realizar check-in a esta reserva.')
    if not reserva.habitacion:
        raise serializers.ValidationError('La reserva no tiene habitacion asignada.')
    if hasattr(reserva, 'estancia'):
        raise serializers.ValidationError('Esta reserva ya tiene una estancia registrada.')
    if reserva.habitacion.estado in ['LIMPIEZA', 'MANTENIMIENTO']:
        raise serializers.ValidationError('No se puede hacer check-in en habitacion en limpieza o mantenimiento.')

    evaluacion = evaluar_checkin(reserva)
    with transaction.atomic():
        reserva.estado = 'CHECKIN'
        reserva.save(update_fields=['estado'])

        habitacion = reserva.habitacion
        habitacion.estado = 'OCUPADA'
        habitacion.save(update_fields=['estado'])

        estancia = Estancia.objects.create(
            reserva=reserva,
            habitacion=habitacion,
            fecha_checkin=evaluacion['momento'],
            precio_final=reserva.precio_total,
            tipo_checkin=evaluacion['tipo'],
            cargo_early_checkin=evaluacion['cargo'],
            estado='ACTIVA',
        )

        if evaluacion['cargo'] > 0:
            CargoEstancia.objects.create(
                estancia=estancia,
                concepto='Early check-in 5% de tarifa',
                monto=evaluacion['cargo'],
                tipo='EARLY_CHECKIN',
            )

        folio = Folio.objects.create(estancia=estancia, estado='PENDIENTE')
        folio.calcular_totales()
        folio.save()
    return estancia


def preparar_folio_api(estancia, evaluacion):
    estancia.fecha_checkout = evaluacion['momento']
    estancia.tipo_checkout = evaluacion['tipo']
    estancia.cargo_late_checkout = evaluacion['cargo']
    estancia.politica_cobro_checkout = evaluacion['politica']
    estancia.noches_reservadas = evaluacion['noches_reservadas']
    estancia.noches_reales = evaluacion['noches_reales']
    estancia.monto_estadia_real = evaluacion['monto_estadia_real']
    estancia.precio_final = evaluacion['monto_habitacion']
    estancia.cargo_penalidad_salida_anticipada = evaluacion['penalidad_salida_anticipada']
    estancia.save()

    if evaluacion['cargo'] > 0:
        CargoEstancia.objects.get_or_create(
            estancia=estancia,
            tipo='LATE_CHECKOUT',
            concepto='Late check-out 50% de tarifa',
            defaults={'monto': evaluacion['cargo']},
        )
    if evaluacion['penalidad_salida_anticipada'] > 0:
        CargoEstancia.objects.get_or_create(
            estancia=estancia,
            tipo='PENALIDAD',
            concepto='Penalidad por salida anticipada',
            defaults={'monto': evaluacion['penalidad_salida_anticipada']},
        )

    folio, _ = Folio.objects.get_or_create(estancia=estancia)
    folio.calcular_totales()
    folio.estado = 'PAGADO' if folio.saldo_pendiente <= 0 else 'PENDIENTE'
    folio.save()
    return folio


def actualizar_housekeeping(habitacion, estado, observacion='', usuario=None):
    if habitacion.estado == 'OCUPADA':
        raise serializers.ValidationError('No se puede cambiar housekeeping de una habitacion ocupada.')

    habitacion.estado = estado
    habitacion.save(update_fields=['estado'])

    if estado == 'MANTENIMIENTO':
        ObservacionMantenimiento.objects.create(
            habitacion=habitacion,
            observacion=observacion,
            creado_por=usuario if usuario and usuario.is_authenticated else None,
        )
    return habitacion
