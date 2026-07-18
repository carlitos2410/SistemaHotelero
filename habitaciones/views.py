from django.shortcuts import render

from usuarios.auth import ROLES, role_required

from .models import Habitacion


@role_required(ROLES['ADMINISTRADOR'])
def lista_habitaciones(request):
    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('piso', 'numero')
    return render(request, 'usuarios/lista_habitaciones.html', {
        'habitaciones': habitaciones,
    })
