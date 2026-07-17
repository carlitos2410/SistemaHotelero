from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from estancias.models import ConfiguracionCobro, Estancia, Folio
from estancias.services import agregar_cargo_estancia, recalcular_folio
from habitaciones.models import Habitacion, TipoHabitacion
from habitaciones.services import cambiar_estado_habitacion
from reservas.models import Huesped, Reserva
from reservas.services import (
    autorizar_prorroga_estancia,
    calcular_tarifa_estadia,
    cancelar_reserva,
    evaluar_checkout,
    obtener_habitaciones_disponibles,
)
from reportes.services import calcular_reporte_ocupacion

from .serializers import (
    AdelantoReservaCreateSerializer,
    CancelarReservaSerializer,
    CargoCreateSerializer,
    CargoEstanciaSerializer,
    CotizacionReservaQuerySerializer,
    CotizacionReservaResponseSerializer,
    DisponibilidadQuerySerializer,
    EstanciaSerializer,
    FolioSerializer,
    HabitacionSerializer,
    HousekeepingSerializer,
    HuespedSerializer,
    HuespedBusquedaResponseSerializer,
    ProrrogaCreateSerializer,
    ReservaCreateSerializer,
    ReservaSerializer,
    TipoHabitacionSerializer,
    actualizar_housekeeping,
    crear_estancia_desde_reserva,
    preparar_folio_api,
)
from .permissions import (
    EsGerenciaOAdministrador,
    EsLimpiezaOAdministrador,
    EsPersonalHotel,
    EsRecepcionGerenciaOAdministrador,
    EsRecepcionOAdministrador,
)


class TipoHabitacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoHabitacion.objects.all().order_by('nombre')
    serializer_class = TipoHabitacionSerializer
    permission_classes = [IsAuthenticated, EsPersonalHotel]


class HabitacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('piso', 'numero')
    serializer_class = HabitacionSerializer
    permission_classes = [IsAuthenticated, EsPersonalHotel]

    def get_permissions(self):
        permisos = [IsAuthenticated, EsLimpiezaOAdministrador] if self.action == 'housekeeping' else self.permission_classes
        return [permiso() for permiso in permisos]

    @extend_schema(
        request=HousekeepingSerializer,
        responses=HabitacionSerializer,
        description='Actualiza el estado operativo de limpieza de una habitacion.',
    )
    @action(detail=True, methods=['patch'], url_path='housekeeping')
    def housekeeping(self, request, pk=None):
        habitacion = self.get_object()
        serializer = HousekeepingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        habitacion = actualizar_housekeeping(
            habitacion,
            serializer.validated_data['estado'],
            serializer.validated_data.get('observacion', ''),
            request.user,
        )
        return Response(HabitacionSerializer(habitacion).data)


class HabitacionesDisponiblesAPIView(APIView):
    permission_classes = [IsAuthenticated, EsRecepcionGerenciaOAdministrador]

    @extend_schema(
        parameters=[
            OpenApiParameter('fecha_entrada', str, required=True),
            OpenApiParameter('fecha_salida', str, required=True),
            OpenApiParameter('tipo', int, required=False),
            OpenApiParameter('num_personas', int, required=False),
        ],
        responses=HabitacionSerializer(many=True),
    )
    def get(self, request):
        filtros = DisponibilidadQuerySerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        data = filtros.validated_data
        habitaciones = obtener_habitaciones_disponibles(
            data['fecha_entrada'],
            data['fecha_salida'],
            tipo_id=data.get('tipo'),
            num_personas=data.get('num_personas'),
        )
        return Response(HabitacionSerializer(habitaciones, many=True).data)


class BuscarHuespedAPIView(APIView):
    permission_classes = [IsAuthenticated, EsRecepcionOAdministrador]

    @extend_schema(
        parameters=[
            OpenApiParameter('num_doc', str, required=True, description='Número de documento exacto.'),
            OpenApiParameter('tipo_doc', str, required=False, description='DNI, PASAPORTE o CE.'),
        ],
        responses=HuespedBusquedaResponseSerializer,
    )
    def get(self, request):
        num_doc = request.query_params.get('num_doc', '').strip()
        tipo_doc = request.query_params.get('tipo_doc', '').strip()
        if not num_doc:
            return Response({'detail': 'Ingresa el numero de documento.'}, status=status.HTTP_400_BAD_REQUEST)

        huespedes = Huesped.objects.filter(num_doc=num_doc)
        if tipo_doc:
            huespedes = huespedes.filter(tipo_doc=tipo_doc)
        huesped = huespedes.first()
        if not huesped:
            return Response({'encontrado': False, 'huesped': None})
        return Response({'encontrado': True, 'huesped': HuespedSerializer(huesped).data})


class CotizacionReservaAPIView(APIView):
    permission_classes = [IsAuthenticated, EsRecepcionOAdministrador]

    @extend_schema(
        parameters=[CotizacionReservaQuerySerializer],
        responses=CotizacionReservaResponseSerializer,
    )
    def get(self, request):
        filtros = CotizacionReservaQuerySerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        data = filtros.validated_data
        habitacion = data['habitacion_obj']

        disponible = obtener_habitaciones_disponibles(
            data['fecha_entrada'],
            data['fecha_salida'],
            num_personas=data.get('num_personas'),
            hotel_id=habitacion.hotel_id,
        ).filter(pk=habitacion.pk).exists()
        if not disponible:
            return Response(
                {'detail': 'La habitacion no esta disponible para las fechas solicitadas.'},
                status=status.HTTP_409_CONFLICT,
            )

        cotizacion = calcular_tarifa_estadia(
            habitacion.tipo,
            data['fecha_entrada'],
            data['fecha_salida'],
            promocion_id=data.get('promocion'),
        )
        configuracion_cobro = ConfiguracionCobro.actual()
        return Response({
            'habitacion': HabitacionSerializer(habitacion).data,
            'noches': cotizacion['noches'],
            'precio_sin_descuento': cotizacion['precio_sin_descuento'],
            'descuento_total': cotizacion['descuento_total'],
            'precio_total': cotizacion['precio_total'],
            'garantia_reserva': {
                'porcentaje': configuracion_cobro.porcentaje_garantia_reserva,
                'monto_requerido': (
                    cotizacion['precio_total']
                    * configuracion_cobro.porcentaje_garantia_reserva
                    / Decimal('100')
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                'estado_inicial': 'PENDIENTE',
                'plazo_pago_horas': configuracion_cobro.horas_plazo_pago_garantia,
                'adelanto_parcial_vencido': 'RETENIDO',
            },
            'promociones_aplicadas': cotizacion['promociones_aplicadas'],
            'promociones_disponibles': cotizacion['promociones_disponibles'],
            'politica_cobro': {
                'codigo': configuracion_cobro.politica_checkout,
                'nombre': configuracion_cobro.get_politica_checkout_display(),
                'porcentaje_penalidad': configuracion_cobro.porcentaje_penalidad_salida_anticipada,
                'porcentaje_igv': configuracion_cobro.porcentaje_igv,
                'porcentaje_early_checkin': configuracion_cobro.porcentaje_early_checkin,
                'porcentaje_late_checkout': configuracion_cobro.porcentaje_late_checkout,
            },
            'desglose': cotizacion['desglose'],
        })


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__hotel', 'habitacion__tipo').all().order_by('-creado_en')
    permission_classes = [IsAuthenticated, EsRecepcionGerenciaOAdministrador]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        permisos = (
            [IsAuthenticated, EsRecepcionOAdministrador]
            if self.action in ['create', 'checkin', 'adelantos', 'cancelar']
            else self.permission_classes
        )
        return [permiso() for permiso in permisos]

    def get_serializer_class(self):
        if self.action == 'create':
            return ReservaCreateSerializer
        return ReservaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reserva = serializer.save()
        return Response(ReservaSerializer(reserva).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=EstanciaSerializer)
    @action(detail=True, methods=['post'], url_path='checkin')
    def checkin(self, request, pk=None):
        reserva = self.get_object()
        estancia = crear_estancia_desde_reserva(reserva, usuario=request.user)
        return Response(EstanciaSerializer(estancia).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=AdelantoReservaCreateSerializer, responses=ReservaSerializer)
    @action(detail=True, methods=['post'], url_path='adelantos')
    def adelantos(self, request, pk=None):
        reserva = self.get_object()
        serializer = AdelantoReservaCreateSerializer(
            data=request.data,
            context={'request': request, 'reserva': reserva},
        )
        serializer.is_valid(raise_exception=True)
        pago, comprobante, reserva = serializer.save()
        return Response({
            'pago_id': pago.id,
            'comprobante': comprobante.correlativo,
            'reserva': ReservaSerializer(reserva).data,
        }, status=status.HTTP_201_CREATED)

    @extend_schema(request=CancelarReservaSerializer, responses=ReservaSerializer)
    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        reserva = self.get_object()
        serializer = CancelarReservaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reserva, evaluacion = cancelar_reserva(
                reserva,
                motivo=serializer.validated_data['motivo'],
                usuario=request.user,
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'reserva': ReservaSerializer(reserva).data,
            'monto_reembolsado': evaluacion['monto_reembolsar'],
            'monto_retenido': evaluacion['monto_retenido'],
        })


class EstanciaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Estancia.objects.select_related(
        'reserva__hotel',
        'reserva__huesped',
        'habitacion__hotel',
        'habitacion__tipo',
        'folio',
    ).prefetch_related('cargos').all().order_by('-fecha_checkin')
    serializer_class = EstanciaSerializer
    permission_classes = [IsAuthenticated, EsRecepcionGerenciaOAdministrador]

    def get_permissions(self):
        permisos = (
            [IsAuthenticated, EsRecepcionOAdministrador]
            if self.action in ['cargos', 'checkout', 'prorroga']
            else self.permission_classes
        )
        return [permiso() for permiso in permisos]

    @extend_schema(request=CargoCreateSerializer, responses=CargoEstanciaSerializer)
    @action(detail=True, methods=['post'], url_path='cargos')
    def cargos(self, request, pk=None):
        estancia = self.get_object()
        serializer = CargoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        producto = data.get('producto_servicio')
        cantidad = data['cantidad']

        precio = producto.precio if producto else data['precio_unitario']
        concepto = producto.nombre if producto else data['concepto']
        tipo = producto.categoria if producto else data['tipo']

        try:
            cargo, folio = agregar_cargo_estancia(
                estancia,
                producto_servicio=producto,
                concepto=concepto,
                cantidad=cantidad,
                precio_unitario=precio,
                tipo=tipo,
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CargoEstanciaSerializer(cargo).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=FolioSerializer)
    @action(detail=True, methods=['get'], url_path='folio')
    def folio(self, request, pk=None):
        estancia = self.get_object()
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio = recalcular_folio(folio)
        return Response(FolioSerializer(folio).data)

    @extend_schema(request=ProrrogaCreateSerializer, responses=dict)
    @action(detail=True, methods=['post'], url_path='prorroga')
    def prorroga(self, request, pk=None):
        estancia = self.get_object()
        serializer = ProrrogaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prorroga = autorizar_prorroga_estancia(
                estancia,
                serializer.validated_data['fecha_salida_nueva'],
                usuario=request.user,
                motivo=serializer.validated_data.get('motivo', ''),
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages[0]}, status=status.HTTP_409_CONFLICT)
        return Response({
            'id': prorroga.id,
            'fecha_salida_anterior': prorroga.fecha_salida_anterior,
            'fecha_salida_nueva': prorroga.fecha_salida_nueva,
            'noches_adicionales': prorroga.noches_adicionales,
            'monto': prorroga.monto,
        }, status=status.HTTP_201_CREATED)

    @extend_schema(responses=EstanciaSerializer)
    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        estancia = self.get_object()
        with transaction.atomic():
            estancia = Estancia.objects.select_for_update().get(pk=estancia.pk)
            if estancia.estado != 'ACTIVA':
                return Response(
                    {'detail': 'Solo se puede hacer check-out a estancias activas.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            reserva = Reserva.objects.select_for_update().get(pk=estancia.reserva_id)
            habitacion = Habitacion.objects.select_for_update().get(pk=estancia.habitacion_id)
            evaluacion = evaluar_checkout(reserva, estancia=estancia)
            folio = preparar_folio_api(estancia, evaluacion)
            if folio.saldo_pendiente > 0:
                return Response(
                    {'detail': 'El folio tiene saldo pendiente. Primero debe registrarse el pago en caja.', 'folio': FolioSerializer(folio).data},
                    status=status.HTTP_409_CONFLICT,
                )

            estancia.fecha_checkout = evaluacion['momento']
            estancia.tipo_checkout = evaluacion['tipo']
            estancia.estado = 'FINALIZADA'
            estancia.save(update_fields=['fecha_checkout', 'tipo_checkout', 'estado'])
            reserva.estado = 'CHECKOUT'
            reserva._estado_usuario = request.user
            reserva._estado_motivo = 'Check-out completado mediante API.'
            reserva.save(update_fields=['estado'])
            cambiar_estado_habitacion(
                habitacion,
                'LIMPIEZA',
                usuario=request.user,
                motivo=f'Checkout API de reserva #{reserva.id}.',
            )

        estancia.refresh_from_db()
        return Response(EstanciaSerializer(estancia).data)


@extend_schema(
    parameters=[OpenApiParameter('fecha', str, required=False)],
    responses=dict,
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, EsGerenciaOAdministrador])
def reporte_ocupacion(request):
    fecha_texto = request.query_params.get('fecha')
    try:
        fecha = date.fromisoformat(fecha_texto) if fecha_texto else timezone.localdate()
    except ValueError:
        return Response(
            {'fecha': ['Use el formato YYYY-MM-DD con una fecha válida.']},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reporte_dia = calcular_reporte_ocupacion(fecha, fecha)
    reporte_semana = calcular_reporte_ocupacion(
        fecha - timedelta(days=6),
        fecha,
        incluir_revenue=False,
    )
    dia = reporte_dia['serie_diaria'][0]

    return Response({
        'fecha': fecha,
        'total_habitaciones': reporte_dia['total_habitaciones'],
        'habitaciones_ocupadas': dia['habitaciones_ocupadas'],
        'habitaciones_disponibles': dia['habitaciones_disponibles'],
        'tasa_ocupacion': dia['tasa_ocupacion'],
        'tasa_ocupacion_semana': reporte_semana['tasa_ocupacion_periodo'],
        'revenue_dia': reporte_dia['revenue_facturado'],
        'revenue_cobrado_dia': reporte_dia['revenue_cobrado'],
        'revenue_cobrado_sin_tipo_dia': reporte_dia['revenue_cobrado_sin_tipo'],
        'serie_semana': reporte_semana['serie_diaria'],
        'por_tipo_habitacion': reporte_dia['desglose_tipos'],
    })
