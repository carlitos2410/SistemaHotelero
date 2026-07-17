from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 42


def _pdf_escape(text):
    return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _money(value):
    return f'S/ {value}'


class SimplePDF:
    def __init__(self, titulo, subtitulo=''):
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.pages = [[]]
        self.y = 792

    @property
    def content(self):
        return self.pages[-1]

    def new_page(self):
        self.pages.append([])
        self.y = 792
        self.header()

    def ensure_space(self, needed=24):
        if self.y - needed < 50:
            self.new_page()

    def text(self, x, y, text, size=10, font='F1'):
        self.content.append(f'BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({_pdf_escape(text)}) Tj ET')

    def line(self, x1, y1, x2, y2):
        self.content.append(f'{x1} {y1} m {x2} {y2} l S')

    def rect(self, x, y, w, h):
        self.content.append(f'{x} {y} {w} {h} re S')

    def header(self):
        self.text(MARGIN_X, 806, self.titulo, size=17, font='F2')
        if self.subtitulo:
            self.text(MARGIN_X, 788, self.subtitulo, size=9)
            self.y = 762
        else:
            self.y = 772
        self.line(MARGIN_X, self.y + 12, PAGE_WIDTH - MARGIN_X, self.y + 12)

    def section(self, title):
        self.ensure_space(34)
        self.y -= 12
        self.text(MARGIN_X, self.y, title.upper(), size=11, font='F2')
        self.line(MARGIN_X, self.y - 5, PAGE_WIDTH - MARGIN_X, self.y - 5)
        self.y -= 24

    def paragraph_line(self, label, value, x=MARGIN_X):
        self.ensure_space(18)
        self.text(x, self.y, f'{label}:', size=9, font='F2')
        self.text(x + 118, self.y, value, size=9)
        self.y -= 16

    def table(self, headers, rows, widths):
        row_height = 20
        total_width = sum(widths)
        self.ensure_space(row_height * (len(rows) + 2))
        x = MARGIN_X

        self.rect(x, self.y - 5, total_width, row_height)
        cursor = x + 6
        for header, width in zip(headers, widths):
            self.text(cursor, self.y + 2, header, size=8, font='F2')
            cursor += width
        self.y -= row_height

        for row in rows:
            self.ensure_space(row_height + 4)
            self.rect(x, self.y - 5, total_width, row_height)
            cursor = x + 6
            for value, width in zip(row, widths):
                text = str(value)
                if len(text) > 42:
                    text = text[:39] + '...'
                self.text(cursor, self.y + 2, text, size=8)
                cursor += width
            self.y -= row_height

        self.y -= 8

    def totals(self, items):
        self.ensure_space(22 * len(items) + 10)
        x = 360
        for label, value in items:
            self.text(x, self.y, label, size=9, font='F2')
            self.text(x + 100, self.y, str(value), size=9)
            self.y -= 17

    def render(self):
        if not self.pages[0]:
            self.header()

        objects = [
            b'<< /Type /Catalog /Pages 2 0 R >>',
            None,
        ]

        page_object_ids = []
        content_object_ids = []
        next_id = 3
        for page in self.pages:
            page_object_ids.append(next_id)
            content_object_ids.append(next_id + 1)
            next_id += 2

        font_regular_id = next_id
        font_bold_id = next_id + 1

        kids = ' '.join(f'{page_id} 0 R' for page_id in page_object_ids)
        objects[1] = f'<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>'.encode()

        for page_id, content_id, commands in zip(page_object_ids, content_object_ids, self.pages):
            stream = '\n'.join(['0.2 w'] + commands).encode('latin-1', errors='replace')
            objects.append(
                f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] '
                f'/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> '
                f'/Contents {content_id} 0 R >>'.encode()
            )
            objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')

        objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
        objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>')

        buffer = BytesIO()
        buffer.write(b'%PDF-1.4\n')
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(buffer.tell())
            buffer.write(f'{index} 0 obj\n'.encode())
            buffer.write(obj)
            buffer.write(b'\nendobj\n')

        xref = buffer.tell()
        buffer.write(f'xref\n0 {len(objects) + 1}\n'.encode())
        buffer.write(b'0000000000 65535 f \n')
        for offset in offsets[1:]:
            buffer.write(f'{offset:010d} 00000 n \n'.encode())
        buffer.write(f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n'.encode())
        buffer.write(f'startxref\n{xref}\n%%EOF'.encode())
        return buffer.getvalue()


def generar_reporte_hotel_pdf(contexto):
    pdf = SimplePDF(
        'Reporte hotelero',
        f"Periodo: {contexto['fecha_desde']} a {contexto['fecha_hasta']}",
    )
    pdf.header()
    pdf.section('Resumen ejecutivo')
    resumen = [
        ('Reservas', contexto['total_reservas']),
        ('Estancias', contexto['total_estancias']),
        ('Huespedes registrados', contexto['total_huespedes']),
        ('Habitaciones', contexto['total_habitaciones']),
        ('Habitaciones ocupadas', contexto['habitaciones_ocupadas']),
        ('Ocupacion fecha final', f"{contexto['ocupacion_actual']}%"),
        ('Ocupacion del periodo', f"{contexto['reporte_ocupacion']['tasa_ocupacion_periodo']}%"),
        ('Ocupacion ultimos 7 dias', f"{contexto['ocupacion_semana']}%"),
    ]
    for label, value in resumen:
        pdf.paragraph_line(label, value)

    pdf.section('Ingresos')
    pdf.totals([
        ('Folios facturados', _money(contexto['revenue_facturado'])),
        ('Flujo neto cobrado', _money(contexto['revenue_cobrado'])),
        ('Flujo sin tipo asignado', _money(contexto['revenue_cobrado_sin_tipo'])),
    ])

    pdf.section('Ocupacion y revenue por tipo de habitacion')
    pdf.table(
        ['Tipo', 'Ocupacion', 'Hab.-noche', 'Facturado', 'Cobrado'],
        [
            [
                item['tipo'],
                f"{item['tasa_ocupacion']}%",
                item['habitaciones_noche_ocupadas'],
                _money(item['revenue_facturado']),
                _money(item['revenue_cobrado']),
            ]
            for item in contexto['desglose_tipos']
        ],
        [130, 75, 75, 105, 105],
    )

    pdf.section('Reservas por estado')
    pdf.table(
        ['Estado', 'Cantidad'],
        [[item['estado'], item['total']] for item in contexto['reservas_por_estado']],
        [250, 120],
    )

    pdf.section('Cargos por tipo')
    pdf.table(
        ['Tipo', 'Cantidad', 'Total'],
        [[item['tipo'], item['cantidad'], _money(item['total'])] for item in contexto['cargos_por_tipo']],
        [200, 100, 140],
    )

    pdf.section('Ultimas reservas')
    pdf.table(
        ['Fecha', 'Huesped', 'Habitacion', 'Estado', 'Total'],
        [
            [
                reserva.creado_en.strftime('%d/%m/%Y'),
                f'{reserva.huesped.nombres} {reserva.huesped.apellidos}',
                reserva.habitacion.numero if reserva.habitacion else '-',
                reserva.estado,
                _money(reserva.precio_total),
            ]
            for reserva in contexto['ultimas_reservas']
        ],
        [70, 170, 70, 90, 90],
    )
    return pdf.render()


def generar_comprobante_pdf(comprobante, folio, estancia, reserva, huesped, hotel, cargos):
    pago = comprobante.pago
    pdf = SimplePDF(
        f'{comprobante.get_tipo_display()} electronica simulada',
        f'Comprobante {comprobante.correlativo} - Emitido: {comprobante.fecha_emision:%d/%m/%Y %H:%M}',
    )
    pdf.header()

    pdf.section('Datos del hotel')
    pdf.paragraph_line('Nombre comercial', hotel.nombre)
    pdf.paragraph_line('RUC', hotel.ruc)
    pdf.paragraph_line('Direccion', hotel.direccion)
    pdf.paragraph_line('Telefono', hotel.telefono)

    pdf.section('Datos del cliente')
    pdf.paragraph_line('Cliente', comprobante.cliente_nombre)
    pdf.paragraph_line('Documento', comprobante.cliente_documento)
    pdf.paragraph_line('Direccion', comprobante.cliente_direccion or '-')
    pdf.paragraph_line('Huesped', f'{huesped.nombres} {huesped.apellidos}')

    pdf.section('Detalle de estancia')
    pdf.paragraph_line('Habitacion', f'{estancia.habitacion.numero} - {estancia.habitacion.tipo.nombre}')
    pdf.paragraph_line('Check-in', estancia.fecha_checkin.strftime('%d/%m/%Y %H:%M'))
    checkout = estancia.fecha_checkout.strftime('%d/%m/%Y %H:%M') if estancia.fecha_checkout else 'Pendiente'
    pdf.paragraph_line('Check-out', checkout)
    pdf.paragraph_line('Noches reales', estancia.noches_reales)

    rows = [['Habitacion / estadia', 'HABITACION', 1, _money(estancia.precio_final)]]
    for cargo in cargos:
        rows.append([cargo.concepto, cargo.tipo, cargo.cantidad, _money(cargo.monto)])

    pdf.section('Cargos facturados')
    pdf.table(['Concepto', 'Tipo', 'Cant.', 'Total'], rows, [230, 95, 55, 95])

    pdf.section('Resumen de pago')
    pdf.totals([
        ('Subtotal', _money(folio.subtotal)),
        (f'IGV {folio.porcentaje_igv}%', _money(folio.igv)),
        ('Total folio', _money(folio.total)),
        ('Total pagado', _money(folio.total_pagado)),
        ('Pago actual', _money(pago.monto)),
    ])
    pdf.paragraph_line('Metodo de pago', pago.metodo_pago.nombre)
    pdf.paragraph_line('Operacion', pago.numero_operacion or 'Efectivo / Simulado')
    pdf.paragraph_line('Responsable', pago.usuario_responsable.username if pago.usuario_responsable else '-')
    pdf.paragraph_line('Estado', comprobante.get_estado_display())

    return pdf.render()


def generar_comprobante_adelanto_pdf(comprobante, reserva, huesped, hotel):
    pago = comprobante.pago
    factor_igv = Decimal('1.00') + Decimal(reserva.porcentaje_igv or 0) / Decimal('100')
    subtotal = (pago.monto / factor_igv).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    igv = pago.monto - subtotal
    pdf = SimplePDF(
        f'{comprobante.get_tipo_display()} electronica simulada',
        f'Comprobante {comprobante.correlativo} - Emitido: {comprobante.fecha_emision:%d/%m/%Y %H:%M}',
    )
    pdf.header()
    pdf.section('Datos del hotel')
    pdf.paragraph_line('Nombre comercial', hotel.nombre)
    pdf.paragraph_line('RUC', hotel.ruc)
    pdf.paragraph_line('Direccion', hotel.direccion)
    pdf.paragraph_line('Telefono', hotel.telefono)
    pdf.section('Datos del cliente')
    pdf.paragraph_line('Cliente', comprobante.cliente_nombre)
    pdf.paragraph_line('Documento', comprobante.cliente_documento)
    pdf.paragraph_line('Direccion', comprobante.cliente_direccion or '-')
    pdf.paragraph_line('Huesped', f'{huesped.nombres} {huesped.apellidos}')
    pdf.section('Garantia de reserva')
    pdf.paragraph_line('Reserva', f'#{reserva.id}')
    pdf.paragraph_line('Habitacion', f'{reserva.habitacion.numero} - {reserva.habitacion.tipo.nombre}')
    pdf.paragraph_line('Entrada', reserva.fecha_entrada.strftime('%d/%m/%Y'))
    pdf.paragraph_line('Salida', reserva.fecha_salida.strftime('%d/%m/%Y'))
    pdf.paragraph_line('Total reservado', _money(reserva.precio_total))
    pdf.paragraph_line('Garantia requerida', _money(reserva.monto_adelanto_requerido))
    pdf.section('Resumen de pago')
    pdf.totals([
        ('Subtotal', _money(subtotal)),
        ('IGV incluido', _money(igv)),
        ('Pago actual', _money(pago.monto)),
        ('Total adelantado', _money(reserva.total_adelantado)),
        ('Saldo garantia', _money(reserva.saldo_adelanto)),
    ])
    pdf.paragraph_line('Metodo de pago', pago.metodo_pago.nombre)
    pdf.paragraph_line('Operacion', pago.numero_operacion or 'Efectivo / Simulado')
    pdf.paragraph_line('Responsable', pago.usuario_responsable.username if pago.usuario_responsable else '-')
    pdf.paragraph_line('Estado reserva', reserva.get_estado_display())
    return pdf.render()
