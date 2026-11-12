"""El envío dentro de una cotización: la línea del envío y, si aplica, la de la promoción (para Juan y, mañana, otros).

Cómo agregan hoy el envío las vendedoras: el botón «Agregar envío» de la cotización (Odoo, ``delivery``) abre el
asistente de transportistas, eligen «Entrega a domicilio: te cotizamos por WhatsApp» (el transportista que crea
website_dcasa, de precio fijo $0 y marcado «Costo por cotizar») y Odoo pone una línea de envío
(``set_delivery_line``: ``is_delivery``, el producto del transportista con SUS impuestos y el método de entrega del
pedido, que es lo que Bodega mira para saber si es envío o retiro). Aquí se hace lo mismo, por el mismo camino de Odoo,
con el precio de la calculadora:

* **La línea del envío** = ``set_delivery_line(transportista, precio normal)``. El ITBMS es el que tenga configurado el
  producto del transportista (Odoo lo pone, aquí no se elige ningún impuesto).
* **La línea de la promoción** (si aplica): el mismo producto y los mismos impuestos que la línea del envío, en
  negativo, también como línea de envío (así «Actualizar costo de envío» de Odoo quita las dos juntas). La paga la
  promoción, no la vendedora: no cuenta contra su tope de descuento (``_dcasa_pagada_por_el_programa``). Solo el
  servidor (o Gerencia) la marca.
* Lo puesto por el sistema queda marcado (``dcasa_envio_lugar_id`` / ``dcasa_promocion_envio_id``). Si una persona le
  cambia el precio, la cantidad o el producto, deja de ser del sistema (y la promoción pasa a contar como cualquier
  rebaja). Un envío que puso una persona nunca se reemplaza solo: se le deja a ella.
"""
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.addons.dcasa_catalogo import reglas as reglas_catalogo
from odoo.addons.dcasa_invoice.models import lineas
from odoo.exceptions import AccessError

from ..motor import tarjeta as motor_tarjeta
from ..motor.promocion import GRATIS
from ..motor.texto import dinero

ESTADOS_EDITABLES = ('draft', 'sent')
# Cambiar esto en una línea puesta por el sistema la vuelve de la persona que la cambió.
CAMPOS_DE_LA_PERSONA = {'price_unit', 'discount', 'product_id', 'product_uom_qty', 'product_uom_id', 'tax_ids'}


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_envio_lugar_id = fields.Many2one(
        'dcasa.envio.lugar', 'Lugar del envío', readonly=True, copy=False, index='btree_not_null', ondelete='set null',
        help='El envío lo puso el sistema con el precio de la calculadora para este lugar.')
    dcasa_promocion_envio_id = fields.Many2one(
        'dcasa.envio.promocion', 'Promoción de envío', readonly=True, copy=False, index='btree_not_null',
        ondelete='restrict', help='Lo que la promoción de envío le rebaja al envío. La paga la promoción.')

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('dcasa_promocion_envio_id') for vals in vals_list):
            self._dcasa_exigir_servidor_para_la_promocion()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('dcasa_promocion_envio_id'):
            self._dcasa_exigir_servidor_para_la_promocion()
        if not self.env.su and CAMPOS_DE_LA_PERSONA & set(vals):
            del_sistema = self.filtered(lambda linea: linea.dcasa_envio_lugar_id or linea.dcasa_promocion_envio_id)
            if del_sistema:
                super(SaleOrderLine, del_sistema).write({'dcasa_envio_lugar_id': False,
                                                         'dcasa_promocion_envio_id': False})
        return super().write(vals)

    @api.model
    def _dcasa_exigir_servidor_para_la_promocion(self):
        """La marca «promoción de envío» exime a la línea del tope de descuento: solo la pone el servidor (al sumar el
        envío) o Gerencia. Si la vendedora pudiera escribirla, bastaría con marcar cualquier rebaja."""
        if self.env.su or self.env.user._dcasa_es_gerencia():
            return
        raise AccessError(self.env._('La promoción de envío la pone el sistema al sumar el envío, no se escribe a '
                                     'mano.'))

    def _dcasa_exenta_tope_descuento(self):
        return super()._dcasa_exenta_tope_descuento() or bool(self.dcasa_promocion_envio_id)

    def _dcasa_pagada_por_el_programa(self):
        return super()._dcasa_pagada_por_el_programa() or bool(self.dcasa_promocion_envio_id)

    def _dcasa_es_envio(self):
        """¿Es una línea de envío o flete (del transportista, el producto de flete, o la promoción del envío)?"""
        self.ensure_one()
        return bool(self.is_delivery or self.dcasa_envio_lugar_id or self.dcasa_promocion_envio_id
                    or lineas.es_flete(self.product_id))

    def _dcasa_envio_del_sistema(self):
        self.ensure_one()
        return bool(self.dcasa_envio_lugar_id or self.dcasa_promocion_envio_id)

    def _dcasa_lleva_colchon(self):
        """Un colchón (``dcasa_tipo_combo == 'colchon'``) o un combo «… + COLCHÓN» (de los de antes o de Odoo)."""
        self.ensure_one()
        plantilla = self.product_id.product_tmpl_id
        if not plantilla:
            return False
        return bool(plantilla.dcasa_tipo_combo == 'colchon'
                    or reglas_catalogo.clase_de_fila_inventario(plantilla.name) == 'combo')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dcasa_envio_lineas(self):
        self.ensure_one()
        return self.order_line.filtered(lambda linea: not linea.display_type and linea._dcasa_es_envio())

    def _dcasa_envio_compra(self):
        """La compra de la cotización SIN el envío: ``{subtotal_sin_itbms, subtotal_con_itbms, colchon}``. Cuentan
        los productos y sus rebajas (las líneas que Odoo suma en el subtotal), no el envío ni la promoción del envío."""
        self.ensure_one()
        productos = self.order_line.filtered(
            lambda linea: not linea.display_type and not linea.is_downpayment and not linea._dcasa_es_envio())
        moneda = self.currency_id or self.company_id.currency_id
        return {
            'subtotal_sin_itbms': moneda.round(sum(productos.mapped('price_subtotal'))),
            'subtotal_con_itbms': moneda.round(sum(productos.mapped('price_total'))),
            'colchon': any(linea._dcasa_lleva_colchon() for linea in productos),
        }

    @api.model
    def _dcasa_envio_transportista(self):
        """El de «Agregar envío» para un envío a domicilio: el transportista activo marcado «Costo por cotizar»
        (website_dcasa: «Entrega a domicilio: te cotizamos por WhatsApp»)."""
        return self.env['delivery.carrier'].sudo().search(
            [('dcasa_por_cotizar', '=', True), ('product_id', '!=', False)], order='sequence, id', limit=1)

    def _dcasa_envio_lleva_itbms(self):
        transportista = self._dcasa_envio_transportista()
        return bool(transportista and transportista.product_id.taxes_id._filter_taxes_by_company(
            self.company_id or self.env.company))

    def _dcasa_envio_poner(self, lugar, precio, resultado, promocion):
        """Pone (o reemplaza) el envío de esta cotización con el precio normal de la calculadora y, si la promoción
        aplica (``resultado`` del motor), la línea de la promoción. Corre con ``sudo`` (lo llama el servidor).

        Devuelve ``{'puesto': True, 'linea_envio', 'linea_promocion'}`` o ``{'puesto': False, 'motivo'}`` con
        motivo ``confirmada`` (no es borrador ni enviada), ``ajeno`` (ya tiene un envío que puso una persona) o
        ``sin_transportista``."""
        self.ensure_one()
        if self.state not in ESTADOS_EDITABLES or self.locked:
            return {'puesto': False, 'motivo': 'confirmada'}
        if self._dcasa_envio_lineas().filtered(lambda linea: not linea._dcasa_envio_del_sistema()):
            return {'puesto': False, 'motivo': 'ajeno'}
        transportista = self._dcasa_envio_transportista()
        if not transportista:
            return {'puesto': False, 'motivo': 'sin_transportista'}
        orden = self.sudo()
        # El mismo camino que «Agregar envío»: quita las líneas de envío de antes (las del sistema: otro lugar u otra
        # promoción) y pone la nueva con el método de entrega del pedido.
        orden.set_delivery_line(transportista, precio)
        envio = orden.order_line.filtered('is_delivery')[-1:]
        envio.write({'name': self.env._('Envío a domicilio: %s', motor_tarjeta.lugar_con_zona(lugar._como_motor())),
                     'dcasa_envio_lugar_id': lugar.id})
        promocion_linea = orden.env['sale.order.line']
        if resultado.get('aplica') and resultado.get('ahorro'):
            promocion_linea = orden.env['sale.order.line'].create({
                'order_id': orden.id, 'product_id': transportista.product_id.id, 'product_uom_qty': 1,
                'name': self._dcasa_envio_nombre_promocion(resultado, promocion),
                'price_unit': -resultado['ahorro'], 'tax_ids': [fields.Command.set(envio.tax_ids.ids)],
                'is_delivery': True, 'sequence': envio.sequence + 1, 'dcasa_promocion_envio_id': promocion.id,
            })
        orden.message_post(body=self._dcasa_envio_nota(lugar, precio, resultado), subtype_xmlid='mail.mt_note')
        return {'puesto': True, 'linea_envio': envio, 'linea_promocion': promocion_linea}

    def _dcasa_envio_nombre_promocion(self, resultado, promocion):
        """«Promoción Envío Gratis Todo Noviembre: envío gratis» o «Promoción de envío (del 1 al 30 de noviembre):
        abono de $20» (en una zona con abono no se nombra una promoción que diga «gratis»)."""
        if resultado['motivo'] == GRATIS:
            nombre = promocion.name if resultado['zona'] == GRATIS else self.env._('de envío')
            return self.env._('Promoción %s: envío gratis', nombre)
        return self.env._('Promoción de envío: abono de %s', dinero(resultado['ahorro']))

    def _dcasa_envio_nota(self, lugar, precio, resultado):
        texto = self.env._('Envío a %(lugar)s sumado con el precio de la calculadora (%(precio)s).',
                           lugar=motor_tarjeta.lugar_con_zona(lugar._como_motor()), precio=dinero(precio))
        if resultado.get('aplica'):
            texto += ' ' + self.env._('Promoción de envío: −%s.', dinero(resultado['ahorro']))
        elif resultado.get('frase'):
            texto += ' ' + resultado['frase']
        return Markup('<p>%s</p>') % escape(texto)
