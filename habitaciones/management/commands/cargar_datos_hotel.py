from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from estancias.models import ProductoServicio
from habitaciones.models import Habitacion, TipoHabitacion
from hoteles.models import Hotel


class Command(BaseCommand):
    help = 'Carga datos semilla realistas para tipos de habitacion, habitaciones y productos/servicios.'

    tipos_habitacion = [
        {
            'nombre': 'Simple Ejecutiva',
            'capacidad': 1,
            'precio_base': Decimal('120.00'),
            'amenidades': {
                'cama': '1 plaza y media',
                'incluye': ['wifi', 'smart tv', 'escritorio', 'ducha caliente', 'amenities basicos'],
                'vista': 'interior',
            },
        },
        {
            'nombre': 'Doble Superior',
            'capacidad': 2,
            'precio_base': Decimal('180.00'),
            'amenidades': {
                'cama': '1 queen o 2 twin',
                'incluye': ['wifi', 'smart tv', 'frigobar', 'secadora de cabello', 'amenities premium'],
                'vista': 'ciudad',
            },
        },
        {
            'nombre': 'Matrimonial Deluxe',
            'capacidad': 2,
            'precio_base': Decimal('220.00'),
            'amenidades': {
                'cama': '1 king',
                'incluye': ['wifi', 'smart tv', 'frigobar', 'bata', 'pantuflas', 'caja fuerte'],
                'vista': 'ciudad',
            },
        },
        {
            'nombre': 'Familiar',
            'capacidad': 4,
            'precio_base': Decimal('320.00'),
            'amenidades': {
                'cama': '1 queen y 2 twin',
                'incluye': ['wifi', 'smart tv', 'frigobar', 'mesa auxiliar', 'amenities familiares'],
                'vista': 'ciudad',
            },
        },
        {
            'nombre': 'Suite Premium',
            'capacidad': 3,
            'precio_base': Decimal('480.00'),
            'amenidades': {
                'cama': '1 king y sofa cama',
                'incluye': ['wifi', 'smart tv', 'sala privada', 'jacuzzi', 'minibar premium', 'caja fuerte'],
                'vista': 'panoramica',
            },
        },
    ]

    productos_servicios = [
        ('Desayuno buffet', 'RESTAURANTE', Decimal('38.00')),
        ('Almuerzo ejecutivo', 'RESTAURANTE', Decimal('48.00')),
        ('Cena a la carta', 'RESTAURANTE', Decimal('65.00')),
        ('Cafe americano', 'RESTAURANTE', Decimal('9.00')),
        ('Room service nocturno', 'RESTAURANTE', Decimal('25.00')),
        ('Agua mineral 625 ml', 'MINIBAR', Decimal('5.00')),
        ('Gaseosa personal', 'MINIBAR', Decimal('6.00')),
        ('Cerveza nacional', 'MINIBAR', Decimal('12.00')),
        ('Snack salado', 'MINIBAR', Decimal('8.00')),
        ('Chocolate premium', 'MINIBAR', Decimal('10.00')),
        ('Lavado de camisa', 'LAVANDERIA', Decimal('12.00')),
        ('Lavado de pantalon', 'LAVANDERIA', Decimal('15.00')),
        ('Lavado express por kilo', 'LAVANDERIA', Decimal('18.00')),
        ('Planchado de prenda', 'LAVANDERIA', Decimal('8.00')),
        ('Cochera por noche', 'OTRO', Decimal('20.00')),
        ('Traslado aeropuerto', 'OTRO', Decimal('75.00')),
        ('Penalidad por dano menor', 'OTRO', Decimal('80.00')),
        ('Reposicion de tarjeta de acceso', 'OTRO', Decimal('25.00')),
    ]

    def handle(self, *args, **options):
        hotel = Hotel.objects.order_by('id').first()
        if not hotel:
            raise CommandError('No existe un hotel registrado. Registra los datos del hotel antes de cargar la semilla.')

        with transaction.atomic():
            tipos = self.crear_tipos()
            habitaciones_creadas, habitaciones_actualizadas = self.crear_habitaciones(hotel, tipos)
            productos_creados, productos_actualizados = self.crear_productos()

        self.stdout.write(self.style.SUCCESS('Datos semilla cargados correctamente.'))
        self.stdout.write(f'Hotel usado: {hotel.nombre}')
        self.stdout.write(f'Tipos de habitacion: {len(tipos)}')
        self.stdout.write(f'Habitaciones creadas: {habitaciones_creadas}')
        self.stdout.write(f'Habitaciones actualizadas: {habitaciones_actualizadas}')
        self.stdout.write(f'Productos/servicios creados: {productos_creados}')
        self.stdout.write(f'Productos/servicios actualizados: {productos_actualizados}')

    def crear_tipos(self):
        tipos = {}
        for item in self.tipos_habitacion:
            tipo, _ = TipoHabitacion.objects.update_or_create(
                nombre=item['nombre'],
                defaults={
                    'capacidad': item['capacidad'],
                    'precio_base': item['precio_base'],
                    'amenidades': item['amenidades'],
                },
            )
            tipos[item['nombre']] = tipo
        return tipos

    def crear_habitaciones(self, hotel, tipos):
        distribucion_por_piso = {
            1: ['Simple Ejecutiva'] * 4 + ['Doble Superior'] * 4 + ['Matrimonial Deluxe'] * 2,
            2: ['Simple Ejecutiva'] * 3 + ['Doble Superior'] * 4 + ['Matrimonial Deluxe'] * 3,
            3: ['Doble Superior'] * 3 + ['Matrimonial Deluxe'] * 4 + ['Familiar'] * 3,
            4: ['Doble Superior'] * 2 + ['Matrimonial Deluxe'] * 3 + ['Familiar'] * 4 + ['Suite Premium'],
            5: ['Matrimonial Deluxe'] * 3 + ['Familiar'] * 4 + ['Suite Premium'] * 3,
            6: ['Matrimonial Deluxe'] * 2 + ['Familiar'] * 3 + ['Suite Premium'] * 5,
        }
        creadas = 0
        actualizadas = 0

        for piso, nombres_tipo in distribucion_por_piso.items():
            for indice, nombre_tipo in enumerate(nombres_tipo, start=1):
                numero = f'{piso}{indice:02d}'
                habitacion, creada = Habitacion.objects.update_or_create(
                    hotel=hotel,
                    numero=numero,
                    defaults={
                        'tipo': tipos[nombre_tipo],
                        'piso': piso,
                        'estado': 'DISPONIBLE',
                    },
                )
                if creada:
                    creadas += 1
                else:
                    actualizadas += 1

        return creadas, actualizadas

    def crear_productos(self):
        creados = 0
        actualizados = 0

        ProductoServicio.objects.filter(
            nombre__in=['Early check-in 5%', 'Late check-out 50%']
        ).update(activo=False)

        for nombre, categoria, precio in self.productos_servicios:
            _, creado = ProductoServicio.objects.update_or_create(
                nombre=nombre,
                defaults={
                    'categoria': categoria,
                    'precio': precio,
                    'activo': True,
                },
            )
            if creado:
                creados += 1
            else:
                actualizados += 1

        return creados, actualizados
