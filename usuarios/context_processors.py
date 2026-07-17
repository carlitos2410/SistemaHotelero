from .auth import ROLES, usuario_en_rol, obtener_rol_principal


def roles_usuario(request):
    user = request.user
    es_superusuario = user.is_authenticated and user.is_superuser

    return {
        'rol_principal': obtener_rol_principal(user),
        'es_superusuario': es_superusuario,
        # Estas banderas controlan la presentacion del menu. Los permisos reales
        # del superusuario siguen siendo globales mediante usuario_en_rol().
        'es_gerencia': not es_superusuario and usuario_en_rol(user, [ROLES['GERENCIA']]),
        'es_administrador': not es_superusuario and usuario_en_rol(user, [ROLES['ADMINISTRADOR']]),
        'es_recepcionista': not es_superusuario and usuario_en_rol(user, [ROLES['RECEPCIONISTA']]),
        'es_limpieza': not es_superusuario and usuario_en_rol(user, [ROLES['LIMPIEZA']]),
    }
