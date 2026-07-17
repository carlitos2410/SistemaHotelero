from datetime import date
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reservas.models import Reserva
from reservas.services import (
    liberar_reservas_sin_garantia_vencidas,
    marcar_reservas_no_show_vencidas,
)
from usuarios.auditoria import registrar_evento


class Command(BaseCommand):
    help = 'Cancela garantias vencidas y marca no-show sin depender de abrir el dashboard.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fecha',
            help='Fecha operativa en formato YYYY-MM-DD. Por defecto usa la fecha local.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuantas reservas procesaria sin modificar datos.',
        )
        parser.add_argument(
            '--continuo',
            action='store_true',
            help='Mantiene el proceso activo y revisa las reservas periodicamente.',
        )
        parser.add_argument(
            '--intervalo',
            type=int,
            default=300,
            help='Segundos entre revisiones en modo continuo (minimo 10).',
        )

    def handle(self, *args, **options):
        if options['continuo'] and options['dry_run']:
            raise CommandError('--continuo y --dry-run no pueden usarse juntos.')
        intervalo = max(options['intervalo'], 10)
        if not options['continuo']:
            self._procesar(options.get('fecha'), dry_run=options['dry_run'])
            return
        self.stdout.write(self.style.SUCCESS(
            f'Automatizacion operativa activa. Intervalo: {intervalo} segundos.'
        ))
        try:
            while True:
                self._procesar(options.get('fecha'), dry_run=False)
                time.sleep(intervalo)
        except KeyboardInterrupt:
            self.stdout.write('Automatizacion detenida.')

    def _procesar(self, fecha_texto, *, dry_run):
        fecha = self._obtener_fecha(fecha_texto)
        momento = timezone.now()

        if dry_run:
            garantias = Reserva.objects.filter(
                estado='PENDIENTE',
                fecha_limite_pago__isnull=False,
                fecha_limite_pago__lt=momento,
            )
            no_show = Reserva.objects.filter(
                estado__in=['PENDIENTE', 'CONFIRMADA'],
                estancia__isnull=True,
                fecha_salida__lte=fecha,
            ).exclude(pk__in=garantias.values('pk'))
            self.stdout.write(
                f'Simulacion: {garantias.count()} garantia(s) vencida(s) y '
                f'{no_show.count()} no-show(s).'
            )
            return

        garantias = liberar_reservas_sin_garantia_vencidas(momento=momento)
        no_show = marcar_reservas_no_show_vencidas(fecha=fecha)
        registrar_evento(
            'procesamiento_reservas_operativas',
            cantidad=garantias + no_show,
            resultado='completado',
        )
        self.stdout.write(self.style.SUCCESS(
            f'Proceso completado: {garantias} garantia(s) cancelada(s) y '
            f'{no_show} reserva(s) marcada(s) no-show.'
        ))

    @staticmethod
    def _obtener_fecha(valor):
        if not valor:
            return timezone.localdate()
        try:
            return date.fromisoformat(valor)
        except ValueError as exc:
            raise CommandError('Usa --fecha con formato YYYY-MM-DD.') from exc
