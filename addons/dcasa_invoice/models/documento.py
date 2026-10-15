"""El código QR de los documentos (uso INTERNO) y cómo se abre el documento que apunta.

El QR contiene una dirección corta y estable, sin un solo dato del cliente::

    <web.base.url>/dcasa/doc/<TIPO>/<REFERENCIA>
    https://…/dcasa/doc/FAC/INV/2026/00001      FAC: factura y nota de crédito de cliente
    https://…/dcasa/doc/COT/S00007               COT: cotización / pedido de venta
    https://…/dcasa/doc/COM/P00012               COM: pedido de compra
    https://…/dcasa/doc/ENT/WH/OUT/00005         ENT: entrega (albarán)

El equipo lo escanea con el Escáner (``dcasa_barras``) o con la cámara del teléfono y se abre ESE documento en el
sistema (la ruta ``/dcasa/doc/…`` está en ``controllers/documento.py``: pide sesión y comprueba el permiso de quien
escanea). Si el QR llega a manos de un cliente solo le lleva a la pantalla de entrada del sistema.

Todo el código de este archivo es de uso interno de los módulos de D'CASA: ningún método es público (nada se llama por
RPC), y lo que abre un documento siempre se comprueba con los permisos de quien lo pide.
"""
import base64
import re
from urllib.parse import quote, unquote, urlsplit

from odoo import models

RUTA = '/dcasa/doc'
LARGO_MAXIMO_REFERENCIA = 64

# tipo → (modelo, nombre para la persona)
TIPOS = {
    'FAC': ('account.move', 'factura'),
    'COT': ('sale.order', 'cotización o pedido'),
    'COM': ('purchase.order', 'pedido de compra'),
    'ENT': ('stock.picking', 'entrega'),
}

# El tamaño del PNG que se incrusta (se muestra a ~2 cm: de sobra para que la cámara lo lea impreso) y el nivel de
# corrección de errores: «M» aguanta ~15 % de daño (un doblez, una mancha) sin hacer el cuadro mucho más grande.
QR_PIXELES = 600
QR_NIVEL = 'M'

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_FORMA = re.compile(rf'(?:[\w.\-:@]+)?{RUTA}/(?P<tipo>[A-Za-z]{{3}})/(?P<referencia>.+)', re.IGNORECASE)


def url_del_documento(base, tipo, referencia):
    """``https://…/dcasa/doc/FAC/INV/2026/00001``; vacío si falta la dirección del sistema o la referencia.

    Las barras de la referencia se dejan tal cual (la ruta las acepta); lo demás raro se escapa.
    """
    base = (base or '').strip().rstrip('/')
    referencia = (referencia or '').strip()
    if not base or not referencia or tipo not in TIPOS:
        return ''
    return f'{base}{RUTA}/{tipo}/{quote(referencia, safe="/")}'


def leer_url(texto):
    """``(tipo, referencia)`` si el texto es la dirección de un documento de D'CASA; si no, ``None``.

    Acepta la dirección completa (cualquier dominio: el QR impreso puede ser de antes de un cambio de dominio), con o
    sin ``https://``, o solo la ruta; el tipo puede venir en minúsculas; lo que venga después de ``?`` o ``#`` se
    descarta. No toca la base de datos: solo reconoce la forma.
    """
    if not isinstance(texto, str):
        return None
    limpio = _CONTROL.sub('', texto).strip()
    if not limpio or len(limpio) > 400:
        return None
    ruta = urlsplit(limpio).path if '://' in limpio else limpio.split('?', 1)[0].split('#', 1)[0]
    reconocido = _FORMA.fullmatch(unquote(ruta))
    if not reconocido or reconocido.group('tipo').upper() not in TIPOS:
        return None
    referencia = reconocido.group('referencia').strip('/ ')
    if not referencia or len(referencia) > LARGO_MAXIMO_REFERENCIA or _CONTROL.search(referencia):
        return None
    return reconocido.group('tipo').upper(), referencia


def nombre_del_tipo(tipo):
    return TIPOS[tipo][1] if tipo in TIPOS else 'documento'


class DcasaQrMixin(models.AbstractModel):
    """Lo que necesita un documento (factura, cotización, compra, entrega) para llevar su QR de uso interno."""
    _name = 'dcasa.qr.mixin'
    _description = "Documento con código QR de uso interno"

    def _dcasa_qr_tipo(self):
        raise NotImplementedError

    def _dcasa_qr_referencia(self):
        """El número del documento tal como está impreso (INV/2026/00001, S00007, P00012, WH/OUT/00005)."""
        self.ensure_one()
        return self.name

    def _dcasa_qr_mostrar(self):
        """¿Va el QR en el documento? Lo decide el interruptor de la empresa; el pedido de compra lo ignora."""
        self.ensure_one()
        return bool(self.company_id.dcasa_mostrar_qr_documentos)

    def _dcasa_qr_url(self):
        """La dirección que lleva el QR (vacía si el documento aún no tiene número, p. ej. una factura en borrador)."""
        self.ensure_one()
        if not self._dcasa_qr_referencia() or self._dcasa_qr_referencia() == '/':
            return ''
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return url_del_documento(base, self._dcasa_qr_tipo(), self._dcasa_qr_referencia())

    def _dcasa_qr_src(self):
        """El QR como imagen incrustada (``data:image/png;base64,…``), o '' si no debe imprimirse.

        Se genera con el generador estándar de Odoo (el mismo de ``/report/barcode``) y se incrusta en el propio
        HTML: wkhtmltopdf no tiene que pedir nada más al servidor, así que el QR sale igual en el PDF, en la vista
        previa y en cualquier prueba, y no depende de ninguna dirección.
        """
        self.ensure_one()
        if not self._dcasa_qr_mostrar():
            return ''
        url = self._dcasa_qr_url()
        if not url:
            return ''
        png = self.env['ir.actions.report'].barcode(
            'QR', url, width=QR_PIXELES, height=QR_PIXELES, quiet=0, barLevel=QR_NIVEL)
        return 'data:image/png;base64,' + base64.b64encode(png).decode()


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'dcasa.qr.mixin']

    def _dcasa_qr_tipo(self):
        return 'FAC'


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'dcasa.qr.mixin']

    def _dcasa_qr_tipo(self):
        return 'COT'


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'dcasa.qr.mixin']

    def _dcasa_qr_tipo(self):
        return 'COM'

    def _dcasa_qr_mostrar(self):
        """El pedido de compra es de uso interno (y del proveedor): siempre lleva su QR, no depende del interruptor."""
        return True


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'dcasa.qr.mixin']

    def _dcasa_qr_tipo(self):
        return 'ENT'
