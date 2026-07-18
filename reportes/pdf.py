import io
from datetime import date


class PDFGenerator:
    def __init__(self, titulo='Reporte', subtitulo=''):
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.buffer = io.BytesIO()
        self._lineas = []

    def _texto_a_bytes(self, texto):
        return texto.encode('latin-1', 'replace')

    def agregar_titulo(self, texto):
        self._lineas.append(('T', texto))

    def agregar_subtitulo(self, texto):
        self._lineas.append(('S', texto))

    def agregar_parrafo(self, texto):
        self._lineas.append(('P', texto))

    def agregar_linea_vacia(self):
        self._lineas.append(('P', ''))

    def agregar_tabla(self, encabezados, filas):
        self._lineas.append(('TABLA', encabezados, filas))

    def _renderizar_lineas(self):
        lineas_pdf = []
        y = 750

        lineas_pdf.append(self._texto_a_bytes(f'/Helvetica-Bold 20 0 0 72 {720 - 160} {y} Td'))
        lineas_pdf.append(self._texto_a_bytes(f'({self.titulo}) Tj'))
        y -= 25

        if self.subtitulo:
            lineas_pdf.append(self._texto_a_bytes(f'/Helvetica 11 0 0 72 {720 - 160} {y} Td'))
            lineas_pdf.append(self._texto_a_bytes(f'({self.subtitulo}) Tj'))
            y -= 20

        fecha_texto = f'Generado: {date.today().strftime("%d/%m/%Y")}'
        lineas_pdf.append(self._texto_a_bytes(f'/Helvetica 9 0 0 72 {720 - 160} {y} Td'))
        lineas_pdf.append(self._texto_a_bytes(f'({fecha_texto}) Tj'))
        y -= 25

        for item in self._lineas:
            if y < 60:
                lineas_pdf.append(b'BT /Helvetica 10 0 0 72 72 30 Td (Pagina siguiente...) Tj ET')
                break

            if item[0] == 'T':
                lineas_pdf.append(self._texto_a_bytes(f'/Helvetica-Bold 14 0 0 72 {720 - 160} {y} Td'))
                lineas_pdf.append(self._texto_a_bytes(f'({item[1]}) Tj'))
                y -= 22

            elif item[0] == 'S':
                lineas_pdf.append(self._texto_a_bytes(f'/Helvetica 11 0 0 72 {720 - 160} {y} Td'))
                lineas_pdf.append(self._texto_a_bytes(f'({item[1]}) Tj'))
                y -= 18

            elif item[0] == 'P':
                texto = item[1] if item[1] else ''
                lineas_pdf.append(self._texto_a_bytes(f'/Helvetica 10 0 0 72 {720 - 160} {y} Td'))
                lineas_pdf.append(self._texto_a_bytes(f'({texto}) Tj'))
                y -= 16

            elif item[0] == 'TABLA':
                encabezados = item[1]
                filas = item[2]
                col_width = 500 // max(len(encabezados), 1)

                header_text = '  |  '.join(encabezados)
                lineas_pdf.append(self._texto_a_bytes(f'/Helvetica-Bold 9 0 0 72 {720 - 160} {y} Td'))
                lineas_pdf.append(self._texto_a_bytes(f'({header_text}) Tj'))
                y -= 14

                for fila in filas:
                    if y < 60:
                        break
                    fila_text = '  |  '.join(str(c) for c in fila)
                    lineas_pdf.append(self._texto_a_bytes(f'/Helvetica 9 0 0 72 {720 - 160} {y} Td'))
                    lineas_pdf.append(self._texto_a_bytes(f'({fila_text}) Tj'))
                    y -= 13

                y -= 8

        return lineas_pdf

    def generar(self):
        lineas = self._renderizar_lineas()

        pdf = b'%PDF-1.4\n'
        pdf += b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
        pdf += b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
        pdf += b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n'

        contenido = b'BT\n'
        for linea in lineas:
            contenido += linea + b'\n'
        contenido += b'ET\n'

        stream_bytes = contenido
        pdf += f'4 0 obj<</Length {len(stream_bytes)}>>stream\n'.encode()
        pdf += stream_bytes
        pdf += b'\nendstream\nendobj\n'

        pdf += b'5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n'

        pdf += b'xref\n0 6\n'
        pdf += b'0000000000 65535 f \n'
        pdf += b'0000000009 00000 n \n'
        pdf += b'0000000058 00000 n \n'
        pdf += b'0000000115 00000 n \n'
        pdf += b'0000000266 00000 n \n'
        pdf += b'0000000000 00000 n \n'

        pdf += b'trailer<</Size 6/Root 1 0 R>>\n'
        pdf += b'startxref\n0\n%%EOF\n'

        self.buffer.write(pdf)
        self.buffer.seek(0)
        return self.buffer


def construir_reporte_pdf(datos):
    pdf = PDFGenerator(
        titulo=datos.get('titulo', 'Reporte Hotelero'),
        subtitulo=datos.get('subtitulo', f'Periodo: {datos.get("periodo", "")}'),
    )

    if 'hotel' in datos:
        pdf.agregar_parrafo(f'Hotel: {datos["hotel"]}')
        pdf.agregar_linea_vacia()

    if 'ocupacion' in datos:
        oc = datos['ocupacion']
        pdf.agregar_titulo('Ocupacion')
        pdf.agregar_parrafo(f'Porcentaje: {oc.get("porcentaje_ocupacion", 0)}%')
        pdf.agregar_parrafo(f'Habitaciones ocupadas promedio: {oc.get("ocupadas_promedio", 0)} de {oc.get("total_habitaciones", 0)}')
        pdf.agregar_linea_vacia()

    if 'ingresos' in datos:
        ing = datos['ingresos']
        pdf.agregar_titulo('Ingresos')
        pdf.agregar_parrafo(f'Total pagos: S/ {ing.get("total_pagos", 0)}')
        pdf.agregar_parrafo(f'Cantidad de pagos: {ing.get("cantidad_pagos", 0)}')
        pdf.agregar_parrafo(f'Flujo neto caja: S/ {ing.get("flujo_neto", 0)}')
        pdf.agregar_linea_vacia()

    if 'reservas' in datos:
        res = datos['reservas']
        pdf.agregar_titulo('Reservas')
        encabezados = ['Estado', 'Cantidad']
        filas = [
            ['Pendientes', str(res.get('pendientes', 0))],
            ['Confirmadas', str(res.get('confirmadas', 0))],
            ['En casa', str(res.get('en_casa', 0))],
            ['Finalizadas', str(res.get('finalizadas', 0))],
            ['Canceladas', str(res.get('canceladas', 0))],
            ['No-show', str(res.get('no_show', 0))],
        ]
        pdf.agregar_tabla(encabezados, filas)
        pdf.agregar_linea_vacia()

    if 'habitaciones' in datos:
        hab = datos['habitaciones']
        pdf.agregar_titulo('Habitaciones por estado')
        encabezados = ['Estado', 'Cantidad']
        filas = [[estado, str(cantidad)] for estado, cantidad in hab.items()]
        pdf.agregar_tabla(encabezados, filas)

    return pdf.generar()
