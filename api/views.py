from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from estancias.models import CargoEstancia, Estancia, Folio
from habitaciones.models import Habitacion, TipoHabitacion
from reservas.models import Reserva
from reservas.services import evaluar_checkout

from .serializers import (
    CargoCreateSerializer,
    CargoEstanciaSerializer,
    EstanciaSerializer,
    FolioSerializer,
    HabitacionSerializer,
    HousekeepingSerializer,
    ReservaCreateSerializer,
    ReservaSerializer,
    TipoHabitacionSerializer,
    actualizar_housekeeping,
    crear_estancia_desde_reserva,
    preparar_folio_api,
)


class TipoHabitacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoHabitacion.objects.all().order_by('nombre')
    serializer_class = TipoHabitacionSerializer
    permission_classes = [IsAuthenticated]


class HabitacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('piso', 'numero')
    serializer_class = HabitacionSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
        fecha_entrada = request.query_params.get('fecha_entrada')
        fecha_salida = request.query_params.get('fecha_salida')
        tipo = request.query_params.get('tipo')
        num_personas = request.query_params.get('num_personas')

        if not fecha_entrada or not fecha_salida:
            return Response({'detail': 'fecha_entrada y fecha_salida son obligatorias.'}, status=status.HTTP_400_BAD_REQUEST)

        habitaciones_ocupadas = Reserva.objects.filter(
            estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
            fecha_entrada__lt=fecha_salida,
            fecha_salida__gt=fecha_entrada,
        ).values_list('habitacion_id', flat=True)

        habitaciones = Habitacion.objects.select_related('hotel', 'tipo').filter(
            estado='DISPONIBLE',
        ).exclude(id__in=habitaciones_ocupadas)

        if tipo:
            habitaciones = habitaciones.filter(tipo_id=tipo)
        if num_personas:
            habitaciones = habitaciones.filter(tipo__capacidad__gte=num_personas)

        return Response(HabitacionSerializer(habitaciones.order_by('piso', 'numero'), many=True).data)


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.select_related('hotel', 'huesped', 'habitacion__hotel', 'habitacion__tipo').all().order_by('-creado_en')
    permission_classes = [IsAuthenticated]

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
        estancia = crear_estancia_desde_reserva(reserva)
        return Response(EstanciaSerializer(estancia).data, status=status.HTTP_201_CREATED)


class EstanciaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Estancia.objects.select_related(
        'reserva__hotel',
        'reserva__huesped',
        'habitacion__hotel',
        'habitacion__tipo',
        'folio',
    ).prefetch_related('cargos').all().order_by('-fecha_checkin')
    serializer_class = EstanciaSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CargoCreateSerializer, responses=CargoEstanciaSerializer)
    @action(detail=True, methods=['post'], url_path='cargos')
    def cargos(self, request, pk=None):
        estancia = self.get_object()
        if estancia.estado != 'ACTIVA':
            return Response({'detail': 'Solo se pueden agregar cargos a estancias activas.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CargoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        producto = data.get('producto_servicio')
        cantidad = data['cantidad']

        precio = producto.precio if producto else data['precio_unitario']
        concepto = producto.nombre if producto else data['concepto']
        tipo = producto.categoria if producto else data['tipo']

        cargo = CargoEstancia.objects.create(
            estancia=estancia,
            producto_servicio=producto,
            concepto=concepto,
            cantidad=cantidad,
            precio_unitario=precio,
            monto=precio * cantidad,
            tipo=tipo,
        )
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        folio.save()
        return Response(CargoEstanciaSerializer(cargo).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=FolioSerializer)
    @action(detail=True, methods=['get'], url_path='folio')
    def folio(self, request, pk=None):
        estancia = self.get_object()
        folio, _ = Folio.objects.get_or_create(estancia=estancia)
        folio.calcular_totales()
        folio.save()
        return Response(FolioSerializer(folio).data)

    @extend_schema(responses=EstanciaSerializer)
    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        estancia = self.get_object()
        if estancia.estado != 'ACTIVA':
            return Response({'detail': 'Solo se puede hacer check-out a estancias activas.'}, status=status.HTTP_400_BAD_REQUEST)

        evaluacion = evaluar_checkout(estancia.reserva, estancia=estancia)
        with transaction.atomic():
            folio = preparar_folio_api(estancia, evaluacion)
            if folio.saldo_pendiente > 0:
                return Response(
                    {'detail': 'El folio tiene saldo pendiente. Primero debe registrarse el pago en caja.', 'folio': FolioSerializer(folio).data},
                    status=status.HTTP_409_CONFLICT,
                )

            estancia.estado = 'FINALIZADA'
            estancia.save(update_fields=['estado'])
            estancia.reserva.estado = 'CHECKOUT'
            estancia.reserva.save(update_fields=['estado'])
            estancia.habitacion.estado = 'LIMPIEZA'
            estancia.habitacion.save(update_fields=['estado'])

        return Response(EstanciaSerializer(estancia).data)


@extend_schema(
    parameters=[OpenApiParameter('fecha', str, required=False)],
    responses=dict,
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_ocupacion(request):
    fecha_texto = request.query_params.get('fecha')
    fecha = timezone.datetime.strptime(fecha_texto, '%Y-%m-%d').date() if fecha_texto else timezone.localdate()
    total_habitaciones = Habitacion.objects.count()
    ocupadas = Habitacion.objects.filter(estado='OCUPADA').count()
    reservas_dia = Reserva.objects.filter(
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
        fecha_entrada__lte=fecha,
        fecha_salida__gt=fecha,
    )
    ingresos = Folio.objects.filter(estancia__fecha_checkin__date=fecha).aggregate(total=Sum('total'))['total'] or 0
    tasa = round((ocupadas / total_habitaciones) * 100, 2) if total_habitaciones else 0

    return Response({
        'fecha': fecha,
        'total_habitaciones': total_habitaciones,
        'habitaciones_ocupadas': ocupadas,
        'reservas_activas_dia': reservas_dia.count(),
        'tasa_ocupacion': tasa,
        'revenue_dia': ingresos,
    })
