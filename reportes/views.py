from django.shortcuts import render
from django.utils import timezone

from hoteles.models import Hotel
from usuarios.auth import ROLES, role_required

from .forms import ReporteFiltroForm
from .services import calcular_ocupacion, calcular_ingresos, resumen_reservas, resumen_habitaciones


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def dashboard_reportes(request):
    form = ReporteFiltroForm(request.GET or None)
    fecha_desde = None
    fecha_hasta = None
    hotel_id = None

    if form.is_valid():
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        hotel = form.cleaned_data.get('hotel')
        if hotel:
            hotel_id = hotel.id

    ocupacion = calcular_ocupacion(fecha_desde, fecha_hasta, hotel_id)
    ingresos = calcular_ingresos(fecha_desde, fecha_hasta, hotel_id)
    reservas = resumen_reservas(fecha_desde, fecha_hasta, hotel_id)
    habitaciones = resumen_habitaciones(hotel_id)

    total_habitaciones = sum(habitaciones.values())
    hoteles = Hotel.objects.filter(activo=True).order_by('nombre')

    return render(request, 'reportes/dashboard.html', {
        'form': form,
        'ocupacion': ocupacion,
        'ingresos': ingresos,
        'reservas': reservas,
        'habitaciones': habitaciones,
        'total_habitaciones': total_habitaciones,
        'hoteles': hoteles,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
    })
