"""Piezas del «paquete de impresión» que no dependen de la base de datos: sellar la copia y unir PDF.

Usan las herramientas de PDF que ya trae Odoo (``odoo.tools.pdf``); no se agrega ninguna librería. El código
funciona igual con PyPDF2 1.26 / 2.12 (la imagen de producción) y con 3.x / pypdf: los nombres de los métodos de
página cambiaron entre versiones, por eso se pide cada uno con su nombre nuevo y, si no existe, con el viejo.
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


def _leer(contenido):
    return pdf.PdfFileReader(io.BytesIO(contenido), strict=False)


def _paginas(lector):
    return list(lector.pages)


def _agregar(escritor, pagina):
    """Agrega la página y devuelve la página ya dentro del escritor."""
    agregar = getattr(escritor, 'add_page', None) or escritor.addPage
    agregar(pagina)
    return _paginas(escritor)[-1] if hasattr(escritor, 'pages') else escritor.getPage(-1)


def _tamano(pagina):
    caja = getattr(pagina, 'mediabox', None) or pagina.mediaBox
    ancho = caja.width if hasattr(caja, 'width') else caja.getWidth()
    alto = caja.height if hasattr(caja, 'height') else caja.getHeight()
    return float(abs(ancho)), float(abs(alto))


def paginas(contenido):
    """Cuántas páginas tiene un PDF (bytes)."""
    return len(_paginas(_leer(contenido)))


def unir(pdfs):
    """Un solo PDF con los de la lista, en ese orden."""
    escritor = pdf.PdfFileWriter()
    for contenido in pdfs:
        if contenido:
            for pagina in _paginas(_leer(contenido)):
                _agregar(escritor, pagina)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def sellar_copia(contenido, texto=TEXTO_COPIA):
    """El mismo PDF con una cinta azul «COPIA EMPRESA» en cada página, a la derecha del título.

    La copia de la empresa es la misma factura que recibe el cliente: no es otra plantilla, solo lleva la cinta.
    Así lo que cambie en la factura (QR, textos) cambia también en la copia sin tocar nada más.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.pdfgen import canvas  # noqa: PLC0415

    originales = _paginas(_leer(contenido))
    sello = io.BytesIO()
    lienzo = canvas.Canvas(sello)
    for pagina in originales:
        ancho, alto = _tamano(pagina)
        lienzo.setPageSize((ancho, alto))
        # Cinta a la derecha, a la altura del título «Factura INV/…» (bajo la banda del encabezado, donde la
        # hoja de D'CASA tiene el margen derecho libre): no tapa la dirección de la empresa ni los datos.
        caja_ancho, caja_alto = 44 * _MM, 7 * _MM
        x = ancho - 12 * _MM - caja_ancho
        y = alto - 37 * _MM - caja_alto
        lienzo.setFillColorRGB(*_AZUL)
        lienzo.rect(x, y, caja_ancho, caja_alto, fill=1, stroke=0)
        lienzo.setFillColor(colors.white)
        lienzo.setFont('Helvetica-Bold', 10)
        lienzo.drawCentredString(x + caja_ancho / 2, y + caja_alto / 2 - 3.5, texto)
        lienzo.showPage()
    lienzo.save()

    marcas = _paginas(_leer(sello.getvalue()))
    salida = pdf.PdfFileWriter()
    for pagina, marca in zip(originales, marcas):
        nueva = _agregar(salida, pagina)
        if '/Annots' in nueva:  # PyPDF2 se queja de las anotaciones al fusionar
            del nueva['/Annots']
        (getattr(nueva, 'merge_page', None) or nueva.mergePage)(marca)
    resultado = io.BytesIO()
    salida.write(resultado)
    return resultado.getvalue()
