"""Checkout de la tienda: cómo paga y recibe un cliente de D'CASA.

Sin pasarela de tarjeta todavía: se cobra con Yappy o transferencia (los datos se mandan
por WhatsApp; nunca se escriben aquí números de cuenta) o al recibir / en la tienda.
La entrega a domicilio se cotiza por WhatsApp, como promete el sitio; no hay «envío gratis».
"""
from markupsafe import Markup

from odoo import api, fields, models
from odoo.addons.dcasa_base import _nombrar

IDIOMA = 'es_419'

# (xmlid o None, nombre, modo, mensaje al terminar el pedido)
PAGOS = [
    ('payment.payment_provider_transfer', 'Transferencia bancaria', 'wire_transfer',
     'Te escribimos por WhatsApp con los datos de la cuenta para que transfieras. '
     'Apenas veamos el pago, confirmamos tu pedido y coordinamos la entrega.'),
    (None, 'Yappy', 'wire_transfer',
     'Te escribimos por WhatsApp con el número de Yappy para que pagues. '
     'Apenas veamos el pago, confirmamos tu pedido y coordinamos la entrega.'),
    ('delivery.payment_provider_cod', 'Pago al recibir o en tienda', 'cash_on_delivery',
     'Pagas al recibir o en la tienda: efectivo, Yappy o tarjeta. '
     'Te escribimos por WhatsApp para confirmar la fecha.'),
]

ENTREGAS = [
    # (nombre, por cotizar)
    ("Retiro en tienda (La Chorrera)", False),
    ('Entrega a domicilio: te cotizamos por WhatsApp', True),
]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    dcasa_por_cotizar = fields.Boolean(
        string='Costo por cotizar',
        help='El costo se cotiza por WhatsApp: en la tienda sale «Por cotizar» en vez de «Gratis».')


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _dcasa_configurar_tienda(self):
        """Idioma, pagos, entregas y dirección para Panamá. Se corre al instalar o migrar."""
        self._dcasa_sitio_en_espanol()
        pa = self.env.ref('base.pa')
        pa.zip_required = False
        b2b = self.env.ref('website_sale.address_b2b', raise_if_not_found=False)
        if b2b:
            b2b.active = False  # sin «Empresa» ni «VAT» para el cliente final
        self._dcasa_pagos()
        self._dcasa_entregas()

    @api.model
    def _dcasa_sitio_en_espanol(self):
        lang = self.env['res.lang']._activate_lang(IDIOMA)
        if not lang:
            return
        self.env['ir.module.module'].search([('state', '=', 'installed')])._update_translations([IDIOMA])
        for website in self.search([]):
            website.write({'language_ids': [(6, 0, lang.ids)], 'default_lang_id': lang.id})

    @api.model
    def _dcasa_pagos(self):
        Provider = self.env['payment.provider'].sudo().with_context(active_test=False)
        transferencia = self.env.ref('payment.payment_provider_transfer')
        idiomas = [codigo for codigo, _n in self.env['res.lang'].get_installed()]
        for xmlid, nombre, modo, mensaje in PAGOS:
            proveedor = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else Provider.search(
                [('code', '=', 'custom'), ('custom_mode', '=', modo), ('name', '=', nombre)], limit=1)
            if not proveedor:
                proveedor = transferencia.copy({
                    'name': nombre, 'payment_method_ids': [(6, 0, transferencia.payment_method_ids.ids)]})
            proveedor.write({'state': 'enabled', 'is_published': True})
            _nombrar(proveedor, nombre)
            # La tienda muestra MÉTODOS (no proveedores): Yappy necesita el suyo, si no se
            # juntaría con la transferencia en una sola opción.
            metodo = self._dcasa_metodo_de_pago(proveedor, nombre, modo)
            if metodo:
                proveedor.payment_method_ids = [(6, 0, metodo.ids)]
                _nombrar(metodo, nombre)
            for idioma in idiomas:
                proveedor.with_context(lang=idioma).pending_msg = Markup('<p>%s</p>') % mensaje

    @api.model
    def _dcasa_metodo_de_pago(self, proveedor, nombre, modo):
        Method = self.env['payment.method'].sudo().with_context(active_test=False)
        if modo == 'cash_on_delivery':
            return self.env.ref('delivery.payment_method_cash_on_delivery', raise_if_not_found=False)
        transferencia = self.env.ref('payment_custom.payment_method_wire_transfer')
        if nombre != 'Yappy':
            return transferencia
        yappy = Method.search([('code', '=', 'yappy')], limit=1) or transferencia.copy({
            'name': 'Yappy', 'code': 'yappy', 'sequence': transferencia.sequence - 1, 'provider_ids': [(5, 0, 0)]})
        yappy.active = True
        return yappy

    @api.model
    def _dcasa_entregas(self):
        Carrier = self.env['delivery.carrier'].sudo().with_context(active_test=False)
        estandar = self.env.ref('delivery.free_delivery_carrier', raise_if_not_found=False)
        if estandar:
            estandar.write({'active': False, 'is_published': False})
        producto = self.env['product.product'].sudo().search([('default_code', '=', 'DCASA-ENTREGA')], limit=1) \
            or self.env['product.product'].sudo().create({
                'name': 'Entrega', 'default_code': 'DCASA-ENTREGA', 'type': 'service',
                'list_price': 0, 'sale_ok': False, 'purchase_ok': False, 'taxes_id': [(5, 0, 0)],
            })
        for orden, (nombre, por_cotizar) in enumerate(ENTREGAS, start=1):
            carrier = Carrier.search([('name', '=', nombre)], limit=1) or Carrier.create({
                'name': nombre, 'delivery_type': 'fixed', 'fixed_price': 0, 'product_id': producto.id,
            })
            carrier.write({
                'active': True, 'is_published': True, 'sequence': orden,
                'allow_cash_on_delivery': True, 'dcasa_por_cotizar': por_cotizar,
            })
            _nombrar(carrier, nombre)
