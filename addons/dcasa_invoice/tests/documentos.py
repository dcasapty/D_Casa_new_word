"""Documentos de prueba con datos FIJOS y el normalizador del HTML que protege «la bonita factura» de la dueña.

La factura, la cotización y la nota de entrega impresas NO pueden cambiar mientras los interruptores de la empresa
(«Mostrar el código QR…» y «Mostrar el código público…») estén apagados. Los tests ``test_documentos_intactos.py`` lo
vigilan así: arman los documentos con los datos de aquí, los pintan (el mismo HTML que luego wkhtmltopdf vuelve PDF) y
los comparan con el HTML aprobado que está guardado en ``tests/aprobado/``.

Cómo se hace estable el HTML (nada depende de la fecha, de los ids ni del número del documento):

* Todo lo que se pinta sale de datos fijos que arma ``DocumentosDePrueba`` (cliente, productos, fechas, importes).
* ``normalizar_html`` se queda con el ``<body>``, cambia los ids de base de datos, los números de documento y las
  imágenes incrustadas por marcas fijas, junta los espacios y quita los bloques que agregan OTROS módulos
  (Socios, factura electrónica): así el mismo archivo vale con uno o con todos los módulos instalados.

Si cambias una plantilla A PROPÓSITO (por ejemplo, el QR de la factura ya aprobado por la dueña), actualiza los
archivos aprobados con ``DCASA_ESCRIBIR_APROBADO=1`` y deja en el commit la imagen del antes y el después que ella vio.
"""
import os
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.tests import TransactionCase

from ..models.res_company import ResCompany

CARPETA_APROBADA = Path(__file__).parent / 'aprobado'

# Los bloques que otros módulos le suman a la factura (name="…" del <div>): no son de dcasa_invoice.
BLOQUES_DE_OTROS_MODULOS = ('dcasa_socios', 'dcasa_fe')

_NUMEROS = [
    (re.compile(r'\b[A-Z]*INV/\d{4}/\d{5}\b'), 'INV/AAAA/NNNNN'),
    (re.compile(r'\b[A-Z0-9]+/(?:OUT|IN|INT|PICK|PACK)/\d{5}\b'), 'ALM/TIPO/NNNNN'),
    (re.compile(r'\bS\d{5}\b'), 'SNNNNN'),
    (re.compile(r'\bP\d{5}\b'), 'PNNNNN'),
]


def normalizar_html(texto, quitar=()):
    """El ``<body>`` del HTML de un informe, estable entre corridas y entre bases de datos.

    ``quitar``: nombres (``name="…"``) de bloques que además se descartan; así un test puede decir «con el interruptor
    encendido, salvo el bloque del QR, el documento es idéntico».
    """
    arbol = lxml_html.document_fromstring(texto)
    cuerpo = arbol.find('body')
    for elemento in list(cuerpo.iter()):
        if elemento.get('name') in BLOQUES_DE_OTROS_MODULOS + tuple(quitar) and elemento.getparent() is not None:
            elemento.drop_tree()
    for elemento in cuerpo.iter():
        if 'data-oe-id' in elemento.attrib:
            elemento.set('data-oe-id', 'N')
        origen = elemento.get('src')
        if origen and origen.startswith('data:'):
            elemento.set('src', 'data:IMAGEN')
    salida = lxml_html.tostring(cuerpo, encoding='unicode', method='html')
    salida = re.sub(r'\s+', ' ', salida)
    salida = re.sub(r'>\s+<', '><', salida).strip()
    for patron, marca in _NUMEROS:
        salida = patron.sub(marca, salida)
    return salida.replace('><', '>\n<') + '\n'


def comparar_con_lo_aprobado(prueba, nombre, html_actual):
    """Falla si el HTML (ya normalizado) no es IGUAL al aprobado ``tests/aprobado/<nombre>.html``."""
    archivo = CARPETA_APROBADA / f'{nombre}.html'
    if os.environ.get('DCASA_ESCRIBIR_APROBADO'):
        CARPETA_APROBADA.mkdir(exist_ok=True)
        archivo.write_text(html_actual, encoding='utf-8')
        return
    prueba.assertTrue(archivo.exists(), f'Falta el HTML aprobado {archivo.name}')
    aprobado = archivo.read_text(encoding='utf-8')
    if aprobado != html_actual:
        lineas_a, lineas_b = aprobado.splitlines(), html_actual.splitlines()
        distintas = [(i + 1, a, b) for i, (a, b) in enumerate(zip(lineas_a, lineas_b, strict=False)) if a != b][:6]
        detalle = '\n'.join(f'  línea {n}:\n    aprobado: {a[:300]}\n    ahora:    {b[:300]}' for n, a, b in distintas)
        if len(lineas_a) != len(lineas_b):
            detalle += f'\n  largo distinto: aprobado {len(lineas_a)} líneas, ahora {len(lineas_b)}'
        prueba.fail(
            f'«{nombre}» cambió con los interruptores APAGADOS. La factura, la cotización y la nota de entrega de '
            f'la dueña no pueden cambiar sin que ella apruebe una imagen del antes y el después. Si el cambio es a '
            f'propósito, actualiza tests/aprobado/{archivo.name} (DCASA_ESCRIBIR_APROBADO=1).\n{detalle}')


class DocumentosDePrueba(TransactionCase):
    """Cliente, productos y un banco de prueba; ``factura_completa``, ``cotizacion`` y ``entrega`` con datos fijos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        pais = cls.env.ref('base.pa')
        cls.company.partner_id.write({'l10n_pa_dv': '7'})
        cls.company.write({
            'name': "D'CASA Panamá", 'street': 'Frente al Parque Libertadores',
            'street2': 'Diagonal a la Discoteca Seven', 'city': 'La Chorrera', 'country_id': pais.id,
            'vat': '155779346-2-2026', 'phone': '+507 6026-1919', 'email': 'info@dcasapty.com',
            'report_header': 'Tu casa, bien amueblada.',
            'dcasa_factura_garantia': 'Garantía de prueba.', 'dcasa_factura_cambios': 'Cambios de prueba.',
            'dcasa_factura_terminos': 'Términos de prueba.',
            'dcasa_mostrar_qr_documentos': False, 'dcasa_mostrar_codigo_publico': False,
        })
        # Lo que depende de la base de datos (el sitio web, el idioma instalado) se fija para que el HTML sea el mismo:
        # todo se pinta en inglés de Odoo con los formatos de fecha de una base nueva.
        cls.env['res.lang']._activate_lang('en_US').write({
            'date_format': '%m/%d/%Y', 'time_format': '%I:%M:%S %p', 'decimal_point': '.', 'thousands_sep': ',',
            'grouping': '[3,0]'})
        cls.enterClassContext(patch.object(ResCompany, '_dcasa_whatsapp', lambda self: '+507 6026-1919'))
        cls.enterClassContext(patch.object(ResCompany, '_dcasa_url_publica', lambda self: 'https://dcasapty.com'))
        cls.enterClassContext(patch.object(
            cls.registry['account.move'], '_dcasa_idioma_factura', lambda self: 'en_US'))
        cls.cliente = cls.env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA', 'vat': '8-000-0000', 'phone': '+507 61234567', 'email': 'cliente@example.com',
            'street': 'Calle 5, Barrio Balboa', 'city': 'La Chorrera', 'country_id': pais.id, 'lang': 'en_US'})
        cls.entrega_partner = cls.env['res.partner'].create({
            'name': 'Casa de Karen', 'type': 'delivery', 'parent_id': cls.cliente.id, 'street': 'Villa Lucre, casa 12',
            'city': 'Arraiján', 'country_id': pais.id, 'phone': '6999-0000', 'lang': 'en_US'})
        cls.vendedora = cls.env['res.users'].create({'name': 'Ana Vendedora', 'login': 'ana.vendedora.doc'})
        cls.colchon = cls.env['product.product'].create({
            'name': 'COLCHON IMPERIAL TWIN 3/4 BUEN SUEÑO', 'default_code': 'IM-2001', 'type': 'consu'})
        cls.cama = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES', 'default_code': '1062010735N', 'type': 'consu'})
        cls.flete = cls.env.ref('dcasa_invoice.product_flete')
        cls.condicion = cls.env['account.payment.term'].create({
            'name': 'Pago inmediato', 'line_ids': [Command.create({'value': 'percent', 'value_amount': 100.0,
                                                                   'nb_days': 0})]})
        cls.banco = cls.env['account.journal'].create({'name': 'Banco de prueba', 'type': 'bank', 'code': 'BPRU'})

    # --- Documentos -------------------------------------------------------------------------

    @classmethod
    def factura_completa(cls, abono=100.0):
        """Factura de dos muebles con descuento, flete, entrega a otra casa y un abono (la del antes y después)."""
        factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': '2026-10-14',
            'partner_shipping_id': cls.entrega_partner.id, 'invoice_user_id': cls.vendedora.id,
            'delivery_date': '2026-10-14', 'invoice_origin': 'S01004', 'invoice_payment_term_id': cls.condicion.id,
            'narration': False,   # con el sitio web instalado Odoo propone «Terms & Conditions: …/terms»: se fija vacío
            'invoice_line_ids': [
                Command.create({'product_id': cls.colchon.id, 'quantity': 2, 'price_unit': 81.99}),
                Command.create({'product_id': cls.cama.id, 'quantity': 1, 'price_unit': 158.02, 'discount': 10}),
                Command.create({'product_id': cls.flete.id, 'quantity': 1, 'price_unit': 25.0}),
            ]})
        factura.action_post()
        if abono:
            cls.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=factura.ids,
            ).create({'payment_date': '2026-10-14', 'amount': abono, 'journal_id': cls.banco.id})._create_payments()
        return factura

    @classmethod
    def cotizacion(cls, confirmar=False):
        pedido = cls.env['sale.order'].create({
            'partner_id': cls.cliente.id, 'partner_shipping_id': cls.entrega_partner.id,
            'user_id': cls.vendedora.id, 'date_order': datetime(2026, 10, 14, 15, 0, 0),
            'validity_date': fields.Date.to_date('2026-10-31'), 'payment_term_id': cls.condicion.id,
            'client_order_ref': 'REF-CLIENTE-1', 'note': False,
            'order_line': [
                Command.create({'product_id': cls.colchon.id, 'product_uom_qty': 2, 'price_unit': 81.99}),
                Command.create({'product_id': cls.cama.id, 'product_uom_qty': 1, 'price_unit': 158.02,
                                'discount': 10}),
                Command.create({'product_id': cls.flete.id, 'product_uom_qty': 1, 'price_unit': 25.0}),
            ]})
        if confirmar:
            pedido.action_confirm()
        return pedido

    @classmethod
    def entrega(cls):
        """La entrega (albarán de salida) de un pedido confirmado, con fecha fija."""
        pedido = cls.cotizacion(confirmar=True)
        entrega = pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
        entrega.scheduled_date = datetime(2026, 10, 14, 12, 0, 0)
        return entrega

    # --- Cómo se pintan ---------------------------------------------------------------------

    def html(self, informe, registros, normalizado=True, quitar=()):
        contenido, _tipo = self.env['ir.actions.report']._render_qweb_html(informe, registros.ids)
        contenido = contenido.decode()
        return normalizar_html(contenido, quitar) if normalizado else contenido

    def interruptores(self, qr=None, codigo_publico=None):
        """Enciende o apaga los interruptores de la empresa (lo que no se nombra, no cambia)."""
        if qr is not None:
            self.company.dcasa_mostrar_qr_documentos = qr
        if codigo_publico is not None:
            self.company.dcasa_mostrar_codigo_publico = codigo_publico
