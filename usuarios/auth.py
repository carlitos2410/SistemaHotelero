from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


ROLES = {
    'GERENCIA': 'Gerencia',
    'ADMINISTRADOR': 'Administrador',
    'RECEPCIONISTA': 'Recepcionista',
    'LIMPIEZA': 'Limpieza',
}

def usuario_en_rol(user, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()


def role_required(*roles):
    def decorator(view_func):
        @login_required(login_url='/login/')
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if usuario_en_rol(request.user, roles):
                return view_func(request, *args, **kwargs)

            messages.error(request, 'No tienes permiso para acceder a esta seccion.')
            return redirect('inicio')

        return wrapper

    return decorator


def obtener_rol_principal(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLES['ADMINISTRADOR']

    for rol in ROLES.values():
        if user.groups.filter(name=rol).exists():
            return rol

    return None
