from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q

from usuarios.auth import ROLES, role_required
from usuarios.pagination import paginar_queryset

from .forms import HotelFiltroForm, HotelForm
from .models import Hotel


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def lista_hoteles(request):
    hoteles = Hotel.objects.all()
    form = HotelFiltroForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get('q')
        estrellas = form.cleaned_data.get('estrellas')
        if q:
            hoteles = hoteles.filter(
                Q(nombre__icontains=q) |
                Q(ruc__icontains=q) |
                Q(direccion__icontains=q)
            )
        if estrellas:
            hoteles = hoteles.filter(estrellas=estrellas)

    pagina, querystring = paginar_queryset(request, hoteles)
    return render(request, 'hoteles/lista.html', {
        'hoteles': pagina,
        'pagina': pagina,
        'querystring': querystring,
        'filtro_form': form,
    })


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def crear_hotel(request):
    if request.method == 'POST':
        form = HotelForm(request.POST)
        if form.is_valid():
            hotel = form.save()
            messages.success(request, f'Hotel "{hotel.nombre}" registrado correctamente.')
            return redirect('hoteles_lista')
    else:
        form = HotelForm()

    return render(request, 'hoteles/formulario.html', {
        'form': form,
        'titulo': 'Registrar hotel',
    })


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def editar_hotel(request, hotel_id):
    hotel = get_object_or_404(Hotel, pk=hotel_id)
    if request.method == 'POST':
        form = HotelForm(request.POST, instance=hotel)
        if form.is_valid():
            form.save()
            messages.success(request, f'Hotel "{hotel.nombre}" actualizado correctamente.')
            return redirect('hoteles_lista')
    else:
        form = HotelForm(instance=hotel)

    return render(request, 'hoteles/formulario.html', {
        'form': form,
        'hotel': hotel,
        'titulo': f'Editar {hotel.nombre}',
    })


@role_required(ROLES['ADMINISTRADOR'], ROLES['GERENCIA'])
def detalle_hotel(request, hotel_id):
    hotel = get_object_or_404(Hotel, pk=hotel_id)
    return render(request, 'hoteles/detalle.html', {
        'hotel': hotel,
    })


@role_required(ROLES['ADMINISTRADOR'])
def eliminar_hotel(request, hotel_id):
    hotel = get_object_or_404(Hotel, pk=hotel_id)
    if request.method == 'POST':
        nombre = hotel.nombre
        hotel.delete()
        messages.success(request, f'Hotel "{nombre}" eliminado correctamente.')
        return redirect('hoteles_lista')

    return render(request, 'hoteles/confirmar_eliminar.html', {
        'hotel': hotel,
    })
