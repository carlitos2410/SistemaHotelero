from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from estancias.models import CargoEstancia, Estancia, Folio
from habitaciones.models import Habitacion
from reservas.models import Huesped, Reserva
from usuarios.auth import ROLES, role_required

from .forms import ReporteFiltroForm
from .pdf import generar_reporte_hotel_pdf
from .services import calcular_reporte_ocupacion


def _obtener_contexto_reporte(request):
    form = ReporteFiltroForm(request.GET or None)
    if form.is_valid():
        fecha_desde, fecha_hasta = form.obtener_rango()
    else:
        hoy = timezone.localdate()
        fecha_desde, fecha_hasta = hoy.replace(day=1), hoy

    reservas = Reserva.objects.select_related('huesped', 'habitacion').filter(
        creado_en__date__gte=fecha_desde,
        creado_en__date__lte=fecha_hasta,
    )
    estancias = Estancia.objects.select_related('reserva__huesped', 'habitacion').filter(
        fecha_checkin__date__gte=fecha_desde,
        fecha_checkin__date__lte=fecha_hasta,
    )
    folios = Folio.objects.filter(estancia__in=estancias)
    cargos = CargoEstancia.objects.filter(estancia__in=estancias)
    reporte_ocupacion = calcular_reporte_ocupacion(fecha_desde, fecha_hasta)
    reporte_semana = calcular_reporte_ocupacion(
        fecha_hasta - timedelta(days=6),
        fecha_hasta,
        incluir_revenue=False,
    )

    total_habitaciones = Habitacion.objects.count()
    dia_referencia = reporte_ocupacion['serie_diaria'][-1]
    habitaciones_ocupadas = dia_referencia['habitaciones_ocupadas']
    ocupacion_actual = dia_referencia['tasa_ocupacion']

    ingresos_reservas = reservas.aggregate(
        total=Coalesce(
            Sum('precio_total'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )['total']
    ingresos_folios = folios.aggregate(
        total=Coalesce(
            Sum('total'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )['total']
    ingresos_consumos = cargos.aggregate(
        total=Coalesce(
            Sum('monto'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )['total']

    reservas_por_estado = reservas.values('estado').annotate(total=Count('id')).order_by('estado')
    cargos_por_tipo = cargos.values('tipo').annotate(total=Sum('monto'), cantidad=Count('id')).order_by('tipo')
    habitaciones_por_estado = Habitacion.objects.values('estado').annotate(total=Count('id')).order_by('estado')

    return {
        'form': form,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'total_reservas': reservas.count(),
        'total_huespedes': Huesped.objects.count(),
        'total_estancias': estancias.count(),
        'total_habitaciones': total_habitaciones,
        'habitaciones_ocupadas': habitaciones_ocupadas,
        'ocupacion_actual': ocupacion_actual,
        'ingresos_reservas': ingresos_reservas,
        'ingresos_folios': ingresos_folios,
        'ingresos_consumos': ingresos_consumos,
        'reservas_por_estado': reservas_por_estado,
        'cargos_por_tipo': cargos_por_tipo,
        'habitaciones_por_estado': habitaciones_por_estado,
        'ultimas_reservas': reservas.order_by('-creado_en')[:10],
        'ultimas_estancias': estancias.order_by('-fecha_checkin')[:10],
        'reporte_ocupacion': reporte_ocupacion,
        'ocupacion_semana': reporte_semana['tasa_ocupacion_periodo'],
        'serie_diaria': reporte_ocupacion['serie_diaria'],
        'desglose_tipos': reporte_ocupacion['desglose_tipos'],
        'revenue_facturado': reporte_ocupacion['revenue_facturado'],
        'revenue_cobrado': reporte_ocupacion['revenue_cobrado'],
        'revenue_cobrado_sin_tipo': reporte_ocupacion['revenue_cobrado_sin_tipo'],
    }


@role_required(ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def dashboard_reportes(request):
    return render(request, 'reportes/dashboard.html', _obtener_contexto_reporte(request))


@role_required(ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
def exportar_reporte_pdf(request):
    contexto = _obtener_contexto_reporte(request)
    pdf = generar_reporte_hotel_pdf(contexto)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_hotelero.pdf"'
    return response
