"""Piezas del «paquete de impresión» que no dependen de la base de datos: sellar la copia y unir PDF.

Usan las mismas herramientas de PDF que Odoo (``odoo.tools.pdf``), así que funcionan igual con la versión de
PyPDF2/pypdf que traiga cada imagen. No se agrega ninguna librería.
"""
import io

from odoo.tools import pdf

# Un paquete nunca pasa de este número de facturas (cada una trae 2 o 3 documentos): wkhtmltopdf tarda unos
# segundos por documento y no queremos tener una petición colgada minutos.
MAX_FACTURAS = 20

TEXTO_COPIA = 'COPIA EMPRESA'

# Azul de la marca (#1340B1) con letra blanca: el amarillo nunca toca el blanco.
_AZUL = (0x13 / 255, 0x40 / 255, 0xB1 / 255)
_MM = 72 / 25.4  # puntos por milímetro


def paginas(contenido):
    """Cuántas páginas tiene un PDF (bytes)."""
    return pdf.PdfFileReader(io.BytesIO(contenido), strict=False).getNumPages()


def unir(pdfs):
    """Un solo PDF con los de la lista, en ese orden."""
    return pdf.merge_pdf([contenido for contenido in pdfs if contenido])


def sellar_copia(contenido, texto=TEXTO_COPIA):
    """El mismo PDF con una cinta azul «COPIA EMPRESA» en la esquina de arriba a la derecha de cada página.

    La copia de la empresa es la misma factura que recibe el cliente: no es otra plantilla, solo lleva la cinta.
    Así lo que cambie en la factura (QR, textos) cambia también en la copia sin tocar nada más.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.pdfgen import canvas  # noqa: PLC0415

    entrada = pdf.PdfFileReader(io.BytesIO(contenido), strict=False, overwriteWarnings=False)
    sello = io.BytesIO()
    lienzo = canvas.Canvas(sello)
    for n in range(entrada.getNumPages()):
        pagina = entrada.getPage(n)
        ancho = float(abs(pagina.mediaBox.getWidth()))
        alto = float(abs(pagina.mediaBox.getHeight()))
        lienzo.setPageSize((ancho, alto))
        # Cinta en el margen de arriba, a la derecha, sin tapar el encabezado ni el cuerpo.
        caja_ancho, caja_alto = 44 * _MM, 7 * _MM
        x = ancho - 12 * _MM - caja_ancho
        y = alto - 8 * _MM - caja_alto
        lienzo.setFillColorRGB(*_AZUL)
        lienzo.rect(x, y, caja_ancho, caja_alto, fill=1, stroke=0)
        lienzo.setFillColor(colors.white)
        lienzo.setFont('Helvetica-Bold', 10)
        lienzo.drawCentredString(x + caja_ancho / 2, y + caja_alto / 2 - 3.5, texto)
        lienzo.showPage()
    lienzo.save()

    marcas = pdf.PdfFileReader(sello, overwriteWarnings=False)
    salida = pdf.PdfFileWriter()
    for n in range(entrada.getNumPages()):
        salida.addPage(entrada.getPage(n))
        nueva = salida.getPage(-1)
        if '/Annots' in nueva:  # PyPDF2 se queja de las anotaciones al fusionar
            del nueva['/Annots']
        nueva.mergePage(marcas.getPage(n))
        nueva.compressContentStreams()
    resultado = io.BytesIO()
    salida.write(resultado)
    return resultado.getvalue()
