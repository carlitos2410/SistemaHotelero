from rest_framework.permissions import BasePermission

from usuarios.auth import ROLES, usuario_en_rol


class PermisoPorRoles(BasePermission):
    roles = ()
    message = 'No tienes el rol necesario para realizar esta operacion.'

    def has_permission(self, request, view):
        return usuario_en_rol(request.user, self.roles)


class EsPersonalHotel(PermisoPorRoles):
    roles = (
        ROLES['ADMINISTRADOR'],
        ROLES['GERENCIA'],
        ROLES['RECEPCIONISTA'],
        ROLES['LIMPIEZA'],
    )


class EsRecepcionOAdministrador(PermisoPorRoles):
    roles = (ROLES['RECEPCIONISTA'], ROLES['ADMINISTRADOR'])


class EsRecepcionGerenciaOAdministrador(PermisoPorRoles):
    roles = (ROLES['RECEPCIONISTA'], ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])


class EsLimpiezaOAdministrador(PermisoPorRoles):
    roles = (ROLES['LIMPIEZA'], ROLES['ADMINISTRADOR'])


class EsGerenciaOAdministrador(PermisoPorRoles):
    roles = (ROLES['GERENCIA'], ROLES['ADMINISTRADOR'])
