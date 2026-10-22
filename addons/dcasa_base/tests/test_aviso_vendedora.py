"""El aviso a la vendedora al facturar y al cobrar su venta (decisión de la dueña, 2026-10-22; aviso_vendedora.py).

Antes, cuando Caja facturaba el pedido de una vendedora, a ella le llegaba «Te asignaron Asiento contable Borrador de
factura». Ahora le llega «Se facturó tu venta S00139 (INV/2026/01117)» al publicarla y «Tu venta S00139 ya está
cobrada» cuando queda pagada; una sola vez y nunca por lo que ella misma hizo."""
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import html2plaintext

from .test_reglas_gerencia import ReglasGerenciaComun


@tagged('post_install', '-at_install')
class TestAvisoALaVendedora(ReglasGerenciaComun):

    def _pedido(self, monto=100.0):
        pedido = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1,
                                           'price_unit': monto, 'tax_ids': [Command.clear()]})]})
        pedido.action_confirm()
        return pedido

    def _facturar(self, usuario, pedido, **valores):
        """El asistente «Crear factura» del pedido, como lo usa ``usuario`` (normal o anticipo)."""
        asistente = self.env['sale.advance.payment.inv'].with_user(usuario).with_context(
            active_model='sale.order', active_ids=pedido.ids, active_id=pedido.id).create(
            valores or {'advance_payment_method': 'delivered'})
        asistente.create_invoices()
        return pedido.sudo().invoice_ids.sorted('id')[-1:].with_user(usuario)

    def _avisos(self, usuario):
        """Los avisos de la bandeja de ``usuario``: ``[(modelo, id, texto)]``."""
        mensajes = self.env['mail.message'].sudo().search([
            ('message_type', '=', 'user_notification'), ('partner_ids', 'in', usuario.partner_id.ids)], order='id')
        return [(m.model, m.res_id, html2plaintext(m.body).strip()) for m in mensajes]

    def test_caja_factura_y_a_la_vendedora_le_llega_el_aviso_nuevo(self):
        pedido = self._pedido()
        factura = self._facturar(self.caja, pedido)
        self.assertEqual(self._avisos(self.vendedora), [], 'nada de «Te asignaron Asiento contable Borrador…»')
        self.assertIn(self.vendedora.partner_id, factura.sudo().message_partner_ids,
                      'sigue siguiendo la factura, como antes')
        factura.action_post()
        self.assertEqual(self._avisos(self.vendedora), [
            ('sale.order', pedido.id, f'Se facturó tu venta {pedido.name} ({factura.name})')])
        mensaje = self.env['mail.message'].sudo().search([('model', '=', 'sale.order'), ('res_id', '=', pedido.id),
                                                          ('message_type', '=', 'user_notification')])
        self.assertFalse(mensaje.subject, 'sin asunto: en la bandeja saldría repetido')
        self.assertEqual(mensaje.author_id, self.caja.partner_id)
        self.assertEqual(mensaje.notification_ids.res_partner_id, self.vendedora.partner_id)
        self.assertFalse(self._avisos(self.caja), 'a Caja, que hizo la acción, no le llega nada')

    def test_pasar_a_borrador_y_volver_a_publicar_no_repite(self):
        pedido = self._pedido()
        factura = self._facturar(self.caja, pedido)
        factura.action_post()
        factura.with_user(self.gerencia).button_draft()
        factura.with_user(self.gerencia).action_post()
        self.assertEqual(len(self._avisos(self.vendedora)), 1)

    def test_cobrada_cuando_queda_pagada_y_no_con_un_abono(self):
        pedido = self._pedido()
        factura = self._facturar(self.caja, pedido)
        factura.action_post()
        self._cobrar(self.caja, factura, amount=60.0)
        self.assertEqual(factura.payment_state, 'partial')
        self.assertEqual(len(self._avisos(self.vendedora)), 1, 'un abono no la deja cobrada')
        self._cobrar(self.caja, factura, amount=40.0)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertEqual(self._avisos(self.vendedora)[-1],
                         ('sale.order', pedido.id, f'Tu venta {pedido.name} ya está cobrada'))
        self.assertEqual(len(self._avisos(self.vendedora)), 2)

    def test_la_vendedora_que_factura_su_venta_no_se_avisa_a_si_misma(self):
        pedido = self._pedido()
        factura = self._facturar(self.vendedora, pedido)
        factura.action_post()
        self.assertEqual(self._avisos(self.vendedora), [])
        self._cobrar(self.caja, factura)
        self.assertEqual(self._avisos(self.vendedora),
                         [('sale.order', pedido.id, f'Tu venta {pedido.name} ya está cobrada')])

    def test_un_anticipo_no_deja_la_venta_cobrada(self):
        pedido = self._pedido()
        anticipo = self._facturar(self.caja, pedido, advance_payment_method='percentage', amount=50)
        anticipo.action_post()
        self.assertEqual(self._avisos(self.vendedora), [
            ('sale.order', pedido.id, f'Se facturó un anticipo de tu venta {pedido.name} ({anticipo.name})')])
        self._cobrar(self.caja, anticipo)
        self.assertEqual(len(self._avisos(self.vendedora)), 1, 'falta facturar el resto: no está cobrada')
        final = self._facturar(self.caja, pedido)
        final.action_post()
        self._cobrar(self.caja, final)
        self.assertEqual(self._avisos(self.vendedora)[-2:], [
            ('sale.order', pedido.id, f'Se facturó tu venta {pedido.name} ({final.name})'),
            ('sale.order', pedido.id, f'Tu venta {pedido.name} ya está cobrada')])

    def test_una_factura_suelta_de_caja_con_vendedora(self):
        factura = self._factura(self.caja, vendedora=self.vendedora)
        self.assertEqual(self._avisos(self.vendedora),
                         [('account.move', factura.id, f'Se facturó tu venta {factura.name}')])

    def test_un_aviso_que_falla_no_frena_la_factura_ni_el_cobro(self):
        pedido = self._pedido()
        factura = self._facturar(self.caja, pedido)
        with patch.object(type(self.env['sale.order']), '_dcasa_avisar', side_effect=RuntimeError('sin bandeja')), \
                self.assertLogs('odoo.addons.dcasa_base.models.aviso_vendedora', level='ERROR') as registro:
            factura.action_post()
            self._cobrar(self.caja, factura)
        self.assertEqual(factura.state, 'posted')
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertIn('No se pudo avisar a la vendedora', registro.output[0])

    def test_las_facturas_del_sistema_anterior_no_avisan(self):
        factura = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_user_id': self.vendedora.id, 'dcasa_historica': True,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 10.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.with_user(self.caja).action_post()
        self.assertEqual(self._avisos(self.vendedora), [])
