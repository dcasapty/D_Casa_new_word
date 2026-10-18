"""Datos técnicos del navegador en el pedido web, para el Purchase de la Conversions API.

Solo se llenan en el checkout y la confirmación (``controllers/main.py``) y SOLO con consentimiento: el aviso de
cookies aceptado (A) o la casilla de la compra marcada (B). Se borran al encolar la compra o, si el pedido nunca se
paga, a los 30 días (cron de retención). Son técnicos: solo los ve un administrador y no tienen vista.
"""
from odoo import fields, models

from . import meta_api

CAMPOS_NAVEGADOR = ('dcasa_meta_fbp', 'dcasa_meta_fbc', 'dcasa_meta_ua', 'dcasa_meta_ip', 'dcasa_meta_url',
                    'dcasa_meta_consentimiento_navegador')
TIPOS_PRODUCTO = ('consu', 'combo')  # sin servicios, descuentos, anticipos ni envíos
LARGO_UA = 512


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_meta_fbp = fields.Char('Meta: _fbp', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_fbc = fields.Char('Meta: _fbc', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_ua = fields.Char('Meta: navegador', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_ip = fields.Char('Meta: IP', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_url = fields.Char('Meta: página', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_consentimiento_navegador = fields.Datetime(
        'Meta: datos del navegador tomados', groups='base.group_system', copy=False, readonly=True)
    dcasa_meta_consentimiento_compra = fields.Datetime(
        'Meta: aceptó compartir esta compra', groups='base.group_system', copy=False, readonly=True,
        help='La casilla del checkout: vale para esta compra (y para la ficha, si la ficha es de este carrito).')

    def _dcasa_meta_guardar_navegador(self, fbp, fbc, ua, ip, url):
        """Guarda (sudo, desde el controlador) lo que el navegador manda; los valores raros no se guardan."""
        self.ensure_one()
        pedido = self.sudo()
        pedido.write({
            'dcasa_meta_fbp': meta_api.fbp_valida(fbp) or pedido.dcasa_meta_fbp or False,
            'dcasa_meta_fbc': meta_api.fbc_valida(fbc) or pedido.dcasa_meta_fbc or False,
            'dcasa_meta_ua': (ua or '').strip()[:LARGO_UA] or False,
            'dcasa_meta_ip': (ip or '').strip()[:64] or False,
            'dcasa_meta_url': (url or '').strip()[:512] or False,
            'dcasa_meta_consentimiento_navegador': fields.Datetime.now(),
        })

    def _dcasa_meta_navegador(self):
        """``{fbp, fbc, ua, ip, url}`` del navegador, o ``{}`` si no se tomó (sin consentimiento o ya borrado)."""
        self.ensure_one()
        pedido = self.sudo()
        if not (pedido.dcasa_meta_consentimiento_navegador and pedido.dcasa_meta_ua):
            return {}
        return {
            'fbp': pedido.dcasa_meta_fbp or None,
            'fbc': pedido.dcasa_meta_fbc or None,
            'ua': pedido.dcasa_meta_ua,
            'ip': pedido.dcasa_meta_ip or None,
            'url': pedido.dcasa_meta_url or None,
        }

    def _dcasa_meta_limpiar_navegador(self):
        self.sudo().write(dict.fromkeys(CAMPOS_NAVEGADOR, False))

    def _dcasa_meta_limpiar_navegador_viejo(self, antes_de):
        """Pedidos que nunca se pagaron: sus datos del navegador se borran a los 30 días."""
        pedidos = self.sudo().search([('dcasa_meta_consentimiento_navegador', '!=', False),
                                      ('dcasa_meta_consentimiento_navegador', '<', antes_de)])
        pedidos._dcasa_meta_limpiar_navegador()
        return pedidos

    def _dcasa_meta_datos_pagina(self, evento):
        """Lo que el píxel manda en el checkout y la confirmación (InitiateCheckout, AddPaymentInfo).

        Mismos ids que el feed y la Conversions API (la variante, contrato 2.1); valor SIN ITBMS. Nunca ``Purchase``:
        la compra la reporta el servidor cuando queda pagada.
        """
        self.ensure_one()
        cantidades = {}
        for linea in self.sudo().order_line:
            producto = linea.product_id
            if (linea.display_type or not producto or producto.type not in TIPOS_PRODUCTO or linea.is_downpayment
                    or getattr(linea, 'is_delivery', False) or linea.product_uom_qty <= 0):
                continue
            cantidades[producto.id] = cantidades.get(producto.id, 0.0) + linea.product_uom_qty
        contents = [{'id': str(pid), 'quantity': int(c) if float(c).is_integer() else c}
                    for pid, c in cantidades.items()]
        return {
            'evento': evento,
            'datos': {
                'content_type': 'product',
                'content_ids': [c['id'] for c in contents],
                'contents': contents,
                'num_items': int(sum(cantidades.values())),
                'value': self.currency_id.round(self.amount_untaxed),
                'currency': self.currency_id.name,
            },
        }
