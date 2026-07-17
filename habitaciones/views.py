from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.auth import ROLES, role_required, usuario_en_rol

from django.core.exceptions import ValidationError

from .models import Habitacion
from .services import actualizar_estado_housekeeping, obtener_transiciones_housekeeping


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'], ROLES['RECEPCIONISTA'], ROLES['LIMPIEZA'])
def modulo_habitaciones(request):
    if request.user.is_superuser or usuario_en_rol(request.user, [ROLES['ADMINISTRADOR']]):
        return redirect('lista_habitaciones')
    if usuario_en_rol(request.user, [ROLES['LIMPIEZA']]):
        return redirect('limpieza_dashboard')
    return redirect('estado_habitaciones')


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'], ROLES['RECEPCIONISTA'])
def lista_habitaciones(request):
    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('hotel__nombre', 'numero')

    return render(request, 'habitaciones/lista_habitaciones.html', {
        'habitaciones': habitaciones,
        'habitaciones_seccion': 'inventario',
        'puede_cambiar_estado': usuario_en_rol(
            request.user, [ROLES['ADMINISTRADOR']]
        ),
        'puede_administrar_inventario': usuario_en_rol(request.user, [ROLES['ADMINISTRADOR']]),
    })


@role_required(ROLES['ADMINISTRADOR'], ROLES['LIMPIEZA'])
def cambiar_estado_habitacion(request, habitacion_id):
    habitacion = get_object_or_404(Habitacion, id=habitacion_id)
    modo_limpieza = usuario_en_rol(request.user, [ROLES['LIMPIEZA']]) and not usuario_en_rol(
        request.user, [ROLES['ADMINISTRADOR']]
    )

    if request.method == 'POST':
        nuevo_estado = request.POST.get('estado')
        observacion = (request.POST.get('observacion_mantenimiento') or '').strip()
        try:
            actualizar_estado_housekeeping(
                habitacion,
                nuevo_estado,
                usuario=request.user,
                observacion=observacion,
            )
            messages.success(request, 'Estado de habitacion actualizado correctamente.')
            if modo_limpieza:
                piso = request.GET.get('piso', '').strip()
                destino = '/limpieza/' + (f'?piso={piso}' if piso else '')
                return redirect(destino)
            return redirect('lista_habitaciones')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])

    return render(request, 'habitaciones/cambiar_estado.html', {
        'habitacion': habitacion,
        'modo_limpieza': modo_limpieza,
        'observaciones_mantenimiento': habitacion.observaciones_mantenimiento.select_related('creado_por')[:5],
        'transiciones_permitidas': obtener_transiciones_housekeeping(habitacion, request.user),
        'observacion_mantenimiento': (request.POST.get('observacion_mantenimiento') or '') if request.method == 'POST' else '',
        'habitaciones_seccion': 'housekeeping' if modo_limpieza else 'inventario',
    })
