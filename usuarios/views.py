from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django import forms
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from hoteles.models import Hotel
from habitaciones.models import Habitacion, ObservacionMantenimiento, TipoHabitacion
from estancias.models import Estancia, ProductoServicio
from reservas.models import Promocion, Reserva, Huesped, Tarifa
from reservas.forms import ReservaForm, HuespedForm
from reservas.services import (
    aplicar_cotizacion_reserva,
    calcular_tarifa_estadia,
    obtener_habitaciones_disponibles,
    obtener_panel_reservas_dia,
    liberar_reservas_sin_garantia_vencidas,
)
from .forms import DisponibilidadForm
from .auth import ROLES, obtener_rol_principal, role_required


MAESTROS_ADMIN = {
    'hotel': {
        'titulo': 'Datos del hotel',
        'modelo': Hotel,
        'fields': ['nombre', 'ruc', 'direccion', 'estrellas', 'telefono'],
        'list_display': [('nombre', 'Nombre'), ('ruc', 'RUC'), ('direccion', 'Direccion'), ('telefono', 'Telefono')],
    },
    'habitaciones': {
        'titulo': 'Habitaciones',
        'modelo': Habitacion,
        'fields': ['hotel', 'tipo', 'numero', 'piso', 'estado'],
        'list_display': [('numero', 'Numero'), ('hotel', 'Hotel'), ('tipo', 'Tipo'), ('piso', 'Piso'), ('estado', 'Estado')],
    },
    'tipos-habitacion': {
        'titulo': 'Tipos de habitacion',
        'modelo': TipoHabitacion,
        'fields': ['nombre', 'capacidad', 'precio_base', 'amenidades'],
        'list_display': [('nombre', 'Nombre'), ('capacidad', 'Capacidad'), ('precio_base', 'Precio base')],
    },
    'tarifas': {
        'titulo': 'Tarifas',
        'modelo': Tarifa,
        'fields': ['tipo_habitacion', 'nombre', 'precio_noche', 'fecha_inicio', 'fecha_fin'],
        'list_display': [('nombre', 'Nombre'), ('tipo_habitacion', 'Tipo'), ('precio_noche', 'Precio noche'), ('fecha_inicio', 'Desde'), ('fecha_fin', 'Hasta')],
    },
    'productos-servicios': {
        'titulo': 'Productos y servicios',
        'modelo': ProductoServicio,
        'fields': ['nombre', 'categoria', 'precio', 'activo'],
        'list_display': [('nombre', 'Nombre'), ('categoria', 'Categoria'), ('precio', 'Precio'), ('activo', 'Activo')],
    },
    'promociones': {
        'titulo': 'Promociones',
        'modelo': Promocion,
        'fields': ['nombre', 'descripcion', 'tipo_habitacion', 'porcentaje_descuento', 'fecha_inicio', 'fecha_fin', 'activo'],
        'list_display': [('nombre', 'Nombre'), ('tipo_habitacion', 'Tipo'), ('porcentaje_descuento', 'Descuento'), ('fecha_inicio', 'Desde'), ('fecha_fin', 'Hasta'), ('activo', 'Activo')],
    },
}


def obtener_config_maestro(tipo):
    return MAESTROS_ADMIN.get(tipo)


def construir_form_maestro(config):
    class FormularioMaestro(modelform_factory(config['modelo'], fields=config['fields'])):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for field in self.fields.values():
                widget = field.widget
                if isinstance(widget, forms.CheckboxInput):
                    widget.attrs.update({'class': 'form-check-input'})
                elif isinstance(widget, forms.Select):
                    widget.attrs.update({'class': 'form-select'})
                else:
                    widget.attrs.update({'class': 'form-control'})

                if isinstance(widget, forms.DateInput):
                    widget.input_type = 'date'

                if isinstance(widget, forms.Textarea):
                    widget.attrs.setdefault('rows', 3)

    return FormularioMaestro


@login_required(login_url='/login/')
def inicio(request):
    rol = obtener_rol_principal(request.user)

    if rol == ROLES['GERENCIA']:
        return redirect('gerencia_dashboard')
    if rol == ROLES['ADMINISTRADOR']:
        return redirect('administrador_dashboard')
    if rol == ROLES['LIMPIEZA']:
        return redirect('limpieza_dashboard')
    if rol is None:
        return redirect('/admin/')
    return redirect('recepcion_dashboard')


@role_required(ROLES['GERENCIA'])
def gerencia_dashboard(request):
    liberar_reservas_sin_garantia_vencidas()
    panel_reservas = obtener_panel_reservas_dia()
    total_habitaciones = Habitacion.objects.count()
    reservas_pendientes_checkin = Reserva.objects.filter(
        estado__in=['PENDIENTE', 'CONFIRMADA'],
        estancia__isnull=True,
    ).count()
    estados = Habitacion.objects.values('estado').annotate(total=Count('id'))
    habitaciones_por_estado = {item['estado']: item['total'] for item in estados}
    habitaciones_ocupadas = habitaciones_por_estado.get('OCUPADA', 0)
    ocupacion = round((habitaciones_ocupadas / total_habitaciones) * 100, 2) if total_habitaciones else 0

    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion').all().order_by('-creado_en')[:10]

    context = {
        'total_habitaciones': total_habitaciones,
        'total_reservas': reservas_pendientes_checkin,
        'total_huespedes': Huesped.objects.count(),
        'ingresos': Reserva.objects.filter(estado__in=['CONFIRMADA', 'CHECKIN', 'CHECKOUT']).aggregate(
            total=Coalesce(
                Sum('precio_total'),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )['total'],
        'ocupacion': ocupacion,
        'habitaciones_disponibles': habitaciones_por_estado.get('DISPONIBLE', 0),
        'habitaciones_ocupadas': habitaciones_ocupadas,
        'habitaciones_limpieza': habitaciones_por_estado.get('LIMPIEZA', 0),
        'habitaciones_mantenimiento': habitaciones_por_estado.get('MANTENIMIENTO', 0),
        'reservas': reservas,
        'panel_reservas': panel_reservas,
    }
    return render(request, 'usuarios/gerencia_dashboard.html', context)


@role_required(ROLES['ADMINISTRADOR'])
def administrador_dashboard(request):
    liberar_reservas_sin_garantia_vencidas()
    panel_reservas = obtener_panel_reservas_dia()
    hotel = Hotel.objects.first()
    habitaciones_por_estado = {
        item['estado']: item['total']
        for item in Habitacion.objects.values('estado').annotate(total=Count('id'))
    }
    reservas_pendientes = Reserva.objects.filter(
        estado__in=['PENDIENTE', 'CONFIRMADA'],
        estancia__isnull=True,
    ).count()
    salidas_pendientes = Reserva.objects.filter(
        estado='CHECKIN',
        estancia__estado='ACTIVA',
    ).count()

    context = {
        'hotel': hotel,
        'total_habitaciones': Habitacion.objects.count(),
        'total_tipos': Habitacion.objects.values('tipo').distinct().count(),
        'total_usuarios': User.objects.count(),
        'total_tarifas': Tarifa.objects.count(),
        'total_promociones': Promocion.objects.count(),
        'reservas_pendientes': reservas_pendientes,
        'salidas_pendientes': salidas_pendientes,
        'habitaciones_disponibles': habitaciones_por_estado.get('DISPONIBLE', 0),
        'habitaciones_ocupadas': habitaciones_por_estado.get('OCUPADA', 0),
        'habitaciones_limpieza': habitaciones_por_estado.get('LIMPIEZA', 0),
        'habitaciones_mantenimiento': habitaciones_por_estado.get('MANTENIMIENTO', 0),
        'panel_reservas': panel_reservas,
    }
    return render(request, 'usuarios/administrador_dashboard.html', context)


@role_required(ROLES['ADMINISTRADOR'])
def admin_maestro_lista(request, tipo):
    config = obtener_config_maestro(tipo)
    if not config:
        messages.error(request, 'Modulo administrativo no encontrado.')
        return redirect('administrador_dashboard')
    if tipo == 'habitaciones':
        return redirect('lista_habitaciones')

    objetos = config['modelo'].objects.all()
    campos = config['list_display']
    filas = []
    for objeto in objetos:
        filas.append({
            'objeto': objeto,
            'valores': [getattr(objeto, campo) for campo, etiqueta in campos],
        })

    return render(request, 'usuarios/admin_maestro_lista.html', {
        'tipo': tipo,
        'titulo': config['titulo'],
        'campos': [etiqueta for campo, etiqueta in campos],
        'filas': filas,
        'puede_crear': tipo != 'hotel' or not objetos.exists(),
        'habitaciones_seccion': tipo if tipo in {'habitaciones', 'tipos-habitacion', 'tarifas'} else '',
    })


@role_required(ROLES['ADMINISTRADOR'])
def admin_maestro_crear(request, tipo):
    config = obtener_config_maestro(tipo)
    if not config:
        messages.error(request, 'Modulo administrativo no encontrado.')
        return redirect('administrador_dashboard')

    if tipo == 'hotel' and config['modelo'].objects.exists():
        messages.info(request, 'El hotel ya existe. Puedes editar sus datos desde esta pantalla.')
        return redirect('admin_maestro_lista', tipo=tipo)

    Form = construir_form_maestro(config)
    if request.method == 'POST':
        form = Form(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'{config["titulo"]} creado correctamente.')
            return redirect('lista_habitaciones') if tipo == 'habitaciones' else redirect(
                'admin_maestro_lista', tipo=tipo
            )
    else:
        form = Form()

    return render(request, 'usuarios/admin_maestro_form.html', {
        'titulo': config['titulo'],
        'form': form,
        'modo': 'Crear',
        'tipo': tipo,
        'habitaciones_seccion': tipo if tipo in {'habitaciones', 'tipos-habitacion', 'tarifas'} else '',
    })


@role_required(ROLES['ADMINISTRADOR'])
def admin_maestro_editar(request, tipo, pk):
    config = obtener_config_maestro(tipo)
    if not config:
        messages.error(request, 'Modulo administrativo no encontrado.')
        return redirect('administrador_dashboard')

    objeto = get_object_or_404(config['modelo'], pk=pk)
    Form = construir_form_maestro(config)

    if request.method == 'POST':
        form = Form(request.POST, instance=objeto)
        if form.is_valid():
            form.save()
            messages.success(request, f'{config["titulo"]} actualizado correctamente.')
            return redirect('lista_habitaciones') if tipo == 'habitaciones' else redirect(
                'admin_maestro_lista', tipo=tipo
            )
    else:
        form = Form(instance=objeto)

    return render(request, 'usuarios/admin_maestro_form.html', {
        'titulo': config['titulo'],
        'form': form,
        'modo': 'Editar',
        'tipo': tipo,
        'habitaciones_seccion': tipo if tipo in {'habitaciones', 'tipos-habitacion', 'tarifas'} else '',
    })


@role_required(ROLES['RECEPCIONISTA'])
def recepcion_dashboard(request):
    liberar_reservas_sin_garantia_vencidas()
    total_hoteles = Hotel.objects.count()
    total_habitaciones = Habitacion.objects.count()
    total_reservas = Reserva.objects.filter(
        estado__in=['PENDIENTE', 'CONFIRMADA'],
        estancia__isnull=True,
    ).count()
    total_huespedes = Huesped.objects.count()
    hoy = timezone.localdate()
    panel_reservas = obtener_panel_reservas_dia(hoy)

    habitaciones = Habitacion.objects.select_related('hotel', 'tipo').all().order_by('piso', 'numero')
    reservas = Reserva.objects.select_related('hotel', 'huesped', 'habitacion').all().order_by('-creado_en')[:5]
    reservas_hoy = Reserva.objects.select_related('huesped', 'habitacion').filter(
        fecha_entrada__lte=hoy,
        fecha_salida__gte=hoy,
        estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
    ).order_by('fecha_entrada', 'habitacion__numero')

    context = {
        'total_hoteles': total_hoteles,
        'total_habitaciones': total_habitaciones,
        'total_reservas': total_reservas,
        'total_huespedes': total_huespedes,
        'habitaciones': habitaciones,
        'pisos_habitaciones': habitaciones.values_list('piso', flat=True).distinct().order_by('piso'),
        'reservas': reservas,
        'reservas_hoy': reservas_hoy,
        'panel_reservas': panel_reservas,
    }
    return render(request, 'usuarios/inicio.html', context)


@role_required(ROLES['LIMPIEZA'])
def limpieza_dashboard(request):
    pisos = list(Habitacion.objects.values_list('piso', flat=True).distinct().order_by('piso'))
    piso_solicitado = request.GET.get('piso', '').strip()
    piso_numero = int(piso_solicitado) if piso_solicitado.isdecimal() else None
    piso = str(piso_numero) if piso_numero in pisos else ''
    ultimo_checkout = Estancia.objects.filter(
        habitacion_id=OuterRef('pk'),
        fecha_checkout__isnull=False,
    ).order_by('-fecha_checkout').values('fecha_checkout')[:1]
    ultima_observacion = ObservacionMantenimiento.objects.filter(
        habitacion_id=OuterRef('pk'),
    ).order_by('-creado_en', '-pk')
    habitaciones_limpieza = Habitacion.objects.select_related('hotel', 'tipo').annotate(
        ultimo_checkout_fecha=Subquery(ultimo_checkout)
    ).filter(estado='LIMPIEZA').order_by('piso', 'numero')
    habitaciones_mantenimiento = Habitacion.objects.select_related('hotel', 'tipo').annotate(
        ultima_observacion=Subquery(ultima_observacion.values('observacion')[:1]),
        ultima_observacion_fecha=Subquery(ultima_observacion.values('creado_en')[:1]),
    ).filter(estado='MANTENIMIENTO').order_by('piso', 'numero')

    if piso:
        habitaciones_limpieza = habitaciones_limpieza.filter(piso=piso)
        habitaciones_mantenimiento = habitaciones_mantenimiento.filter(piso=piso)

    habitaciones_limpieza = list(habitaciones_limpieza)
    habitaciones_mantenimiento = list(habitaciones_mantenimiento)
    hoy = timezone.localdate()
    limpieza_hoy = []
    limpieza_atrasada = []
    limpieza_sin_checkout = []
    for habitacion in habitaciones_limpieza:
        if not habitacion.ultimo_checkout_fecha:
            limpieza_sin_checkout.append(habitacion)
            continue
        fecha_checkout = timezone.localtime(habitacion.ultimo_checkout_fecha).date()
        if fecha_checkout == hoy:
            limpieza_hoy.append(habitacion)
        elif fecha_checkout < hoy:
            limpieza_atrasada.append(habitacion)
        else:
            limpieza_sin_checkout.append(habitacion)

    return render(request, 'usuarios/limpieza_dashboard.html', {
        'habitaciones_limpieza': habitaciones_limpieza,
        'limpieza_hoy': limpieza_hoy,
        'limpieza_atrasada': limpieza_atrasada,
        'limpieza_sin_checkout': limpieza_sin_checkout,
        'habitaciones_mantenimiento': habitaciones_mantenimiento,
        'pisos': pisos,
        'piso_seleccionado': piso,
        'habitaciones_seccion': 'housekeeping',
        'hoy': hoy,
    })


@role_required(ROLES['RECEPCIONISTA'])
def buscar_disponibilidad(request):
    form = DisponibilidadForm(request.GET or None)
    habitaciones = []
    fecha_entrada = None
    fecha_salida = None
    num_personas = None

    if form.is_valid():
        fecha_entrada = form.cleaned_data['fecha_entrada']
        fecha_salida = form.cleaned_data['fecha_salida']
        num_personas = form.cleaned_data['num_personas']

        habitaciones = obtener_habitaciones_disponibles(
            fecha_entrada,
            fecha_salida,
            num_personas=num_personas,
        )

    return render(request, 'usuarios/disponibilidad.html', {
        'form': form,
        'habitaciones': habitaciones,
        'fecha_entrada': fecha_entrada,
        'fecha_salida': fecha_salida,
        'num_personas': num_personas,
    })


@role_required(ROLES['RECEPCIONISTA'])
def nueva_reserva(request):
    habitacion_id = request.GET.get('habitacion') or request.POST.get('habitacion')
    fecha_entrada = request.GET.get('fecha_entrada') or request.POST.get('fecha_entrada')
    fecha_salida = request.GET.get('fecha_salida') or request.POST.get('fecha_salida')
    num_personas = request.GET.get('num_personas') or request.POST.get('num_personas')

    habitacion_seleccionada = None
    if habitacion_id:
        habitacion_seleccionada = Habitacion.objects.select_related('hotel', 'tipo').filter(id=habitacion_id).first()

    if request.method == 'POST':
        huesped_form = HuespedForm(request.POST)
        reserva_form = ReservaForm(request.POST, habitacion_id=habitacion_id)

        if huesped_form.is_valid() and reserva_form.is_valid():
            reserva = reserva_form.save(commit=False)
            habitacion = reserva.habitacion
            fecha_entrada_obj = reserva.fecha_entrada
            fecha_salida_obj = reserva.fecha_salida

            hoy = timezone.localdate()
            if fecha_entrada_obj < hoy:
                reserva_form.add_error('fecha_entrada', 'No se puede reservar para una fecha anterior a hoy.')
            if fecha_salida_obj < hoy:
                reserva_form.add_error('fecha_salida', 'La fecha de salida no puede ser anterior a hoy.')
            if fecha_salida_obj <= fecha_entrada_obj:
                reserva_form.add_error('fecha_salida', 'La fecha de salida debe ser posterior a la fecha de entrada.')
            if habitacion and reserva.num_adultos > habitacion.tipo.capacidad:
                reserva_form.add_error('num_adultos', f'La habitacion permite maximo {habitacion.tipo.capacidad} persona(s).')

            reserva_existente = Reserva.objects.filter(
                habitacion=habitacion,
                estado__in=['PENDIENTE', 'CONFIRMADA', 'CHECKIN'],
                fecha_entrada__lt=fecha_salida_obj,
                fecha_salida__gt=fecha_entrada_obj
            ).exists()

            if reserva_existente:
                reserva_form.add_error('habitacion', 'La habitación seleccionada ya tiene una reserva en esas fechas.')

            if reserva_form.errors:
                return render(request, 'usuarios/nueva_reserva.html', {
                    'huesped_form': huesped_form,
                    'reserva_form': reserva_form,
                    'habitacion_seleccionada': habitacion_seleccionada,
                    'tipos_habitacion': TipoHabitacion.objects.all().order_by('nombre'),
                })

            try:
                with transaction.atomic():
                    habitacion = Habitacion.objects.select_for_update().select_related('hotel', 'tipo').get(
                        pk=habitacion.pk
                    )
                    disponible = obtener_habitaciones_disponibles(
                        fecha_entrada_obj,
                        fecha_salida_obj,
                        num_personas=reserva.num_adultos,
                        hotel_id=habitacion.hotel_id,
                    ).filter(pk=habitacion.pk).exists()
                    if not disponible:
                        reserva_form.add_error(
                            'habitacion',
                            'La habitacion dejo de estar disponible. Actualiza la busqueda.',
                        )
                        raise ValueError('habitacion_no_disponible')

                    datos_huesped = huesped_form.cleaned_data.copy()
                    num_doc = datos_huesped.pop('num_doc')
                    huesped, _ = Huesped.objects.update_or_create(
                        num_doc=num_doc,
                        defaults=datos_huesped,
                    )
                    cotizacion = calcular_tarifa_estadia(
                        habitacion.tipo,
                        fecha_entrada_obj,
                        fecha_salida_obj,
                        promocion_id=(
                            reserva_form.cleaned_data['promocion'].id
                            if reserva_form.cleaned_data.get('promocion') else None
                        ),
                    )
                    reserva.habitacion = habitacion
                    reserva.hotel = habitacion.hotel
                    reserva.huesped = huesped
                    reserva.estado = 'PENDIENTE'
                    reserva._estado_usuario = request.user
                    reserva._estado_motivo = 'Reserva creada desde recepcion.'
                    aplicar_cotizacion_reserva(reserva, cotizacion)
                    reserva.save()
                messages.success(
                    request,
                    f'Reserva #{reserva.id} creada. Registra el adelanto de S/ {reserva.monto_adelanto_requerido} para confirmarla.',
                )
                return redirect('pagar_reserva', reserva_id=reserva.id)
            except ValueError as exc:
                if str(exc) != 'habitacion_no_disponible':
                    raise
            except IntegrityError:
                reserva_form.add_error(
                    'habitacion',
                    'La habitacion acaba de ser reservada para esas fechas. Actualiza la busqueda.',
                )
    else:
        huesped_form = HuespedForm()
        reserva_form = ReservaForm(
            initial={
                'habitacion': int(habitacion_id) if habitacion_id else None,
                'fecha_entrada': fecha_entrada,
                'fecha_salida': fecha_salida,
                'num_adultos': int(num_personas) if num_personas else 1,
            },
            habitacion_id=habitacion_id
        )

    return render(request, 'usuarios/nueva_reserva.html', {
        'huesped_form': huesped_form,
        'reserva_form': reserva_form,
        'habitacion_seleccionada': habitacion_seleccionada,
        'tipos_habitacion': TipoHabitacion.objects.all().order_by('nombre'),
    })
