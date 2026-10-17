"""Datos comunes de las pruebas de Mi cuenta: una socia con un pedido pagado a medias (abono), un apartado, un pedido
anulado por apartado vencido, un carrito de la web (que nunca se enseña), una factura suelta y otro cliente."""
import os
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import new_test_user

PIN = '482915'
CLAVE = 'clave-mi-cuenta-123'
CELULAR = '6100-1001'
CORREO = 'ana.micuenta@example.com'
CALLE = 'Calle Secreta 123'


class MiCuentaComun:

    def preparar(self):
        self.startPatcher(patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'}))
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))
        self.website = self.env.ref('website.default_website')
        itbms = self.env.ref('base.main_company').account_sale_tax_id
        self.sofa = self.env['product.product'].create({
            'name': 'SOFÁ MILÁN DE PRUEBA', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 1000.0,
            'taxes_id': [Command.set(itbms.ids)], 'is_published': True,
        })
        self.cojin = self.env['product.product'].create({
            'name': 'COJÍN DE PRUEBA', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 50.0,
            'taxes_id': [Command.set(itbms.ids)],
        })
        self.socia = self.env['res.partner'].create({
            'name': 'ANA MICUENTA PÉREZ', 'phone': CELULAR, 'email': CORREO, 'street': CALLE})
        self.socia._dcasa_asegurar_ficha()
        self.socia._dcasa_guardar_pin(PIN)

        hoy = fields.Date.today()
        self.inicio_abono = hoy - timedelta(days=3)
        self.pedido = self._pedido(self.socia, [(self.sofa, 1), (self.cojin, 2)])
        self.pedido.action_confirm()
        self.factura = self.pedido._create_invoices()
        self.factura.action_post()
        self._pagar(self.factura, 300.0, self.inicio_abono)

        self.carrito = self._pedido(self.socia, [(self.cojin, 1)], website_id=self.website.id)
        self.apartado = self._pedido(self.socia, [(self.sofa, 1)])
        self.apartado.write({'state': 'sent', 'dcasa_apartado_vence': hoy + timedelta(days=3)})
        self.anulado = self._pedido(self.socia, [(self.cojin, 3)])
        self.anulado.write({'state': 'sent', 'dcasa_apartado_vence': hoy - timedelta(days=2)})
        self.anulado._action_cancel()
        self.suelta = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.socia.id, 'invoice_date': hoy,
            'invoice_line_ids': [Command.create({'product_id': self.cojin.id, 'quantity': 1, 'price_unit': 50.0})]})
        self.suelta.action_post()

        self.otro = self.env['res.partner'].create({'name': 'OTRO CLIENTE AJENO', 'phone': '6100-2002'})
        self.ajeno = self._pedido(self.otro, [(self.sofa, 1)])
        self.ajeno.action_confirm()
        self.factura_ajena = self.ajeno._create_invoices()
        self.factura_ajena.action_post()
        self.suelta_ajena = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.otro.id, 'invoice_date': hoy,
            'invoice_line_ids': [Command.create({'product_id': self.cojin.id, 'quantity': 1, 'price_unit': 50.0})]})
        self.suelta_ajena.action_post()

    def _pedido(self, cliente, lineas, **extra):
        return self.env['sale.order'].create(dict(extra, partner_id=cliente.id, order_line=[
            Command.create({'product_id': producto.id, 'product_uom_qty': cantidad}) for producto, cantidad in lineas]))

    def _pagar(self, factura, monto, fecha):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'payment_date': fecha, 'amount': monto}).action_create_payments()

    def usuario_de_la_tienda(self, login='mc_tienda'):
        usuario = new_test_user(self.env, login=login, password=CLAVE, groups='base.group_portal',
                                name='TIENDA MICUENTA')
        return usuario

    # --- Como el navegador ----------------------------------------------------------------------

    def csrf(self):
        return re.search(r'csrf_token: "([^"]+)"', self.url_open('/socios/terminos').text).group(1)

    def post(self, url, **datos):
        datos['csrf_token'] = self.csrf()
        return self.url_open(url, data=datos)

    def entrar(self, celular=CELULAR, pin=PIN, **extra):
        return self.post('/socios/entrar', celular=celular, pin=pin, **extra)

    @staticmethod
    def ruta(respuesta):
        """La ruta final (sin dominio ni parámetros) a la que llegó el navegador."""
        return '/' + respuesta.url.split('://', 1)[-1].split('/', 1)[-1].split('?')[0].rstrip('/')
