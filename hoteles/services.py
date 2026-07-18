from django.core.exceptions import ValidationError

from .models import Hotel


def validar_hotel_unico(nombre, ruc, exclude_id=None):
    qs = Hotel.objects.filter(ruc=ruc)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    if qs.exists():
        raise ValidationError('Ya existe un hotel registrado con ese RUC.')


def obtener_o_crear_hotel(datos):
    ruc = datos.get('ruc', '').strip()
    nombre = datos.get('nombre', '').strip()
    hotel, creado = Hotel.objects.get_or_create(
        ruc=ruc,
        defaults={
            'nombre': nombre,
            'direccion': datos.get('direccion', ''),
            'estrellas': datos.get('estrellas', 3),
            'telefono': datos.get('telefono', ''),
            'email': datos.get('email', ''),
        },
    )
    return hotel, creado


def hoteles_activos():
    return Hotel.objects.filter(activo=True).order_by('nombre')
