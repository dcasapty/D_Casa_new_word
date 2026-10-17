"""Lo pagado y lo que falta de una factura con abonos (_dcasa_estado_abono): una sola fuente para el papel y
para «Mi cuenta». Solo lee: los asientos de la factura y de los pagos quedan iguales."""
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from ..models.account_move import PARAMETRO_MESES_ABONO


@tagged('post_install', '-at_install')
class TestEstadoAbono(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE ABONO'})
        cls.mueble = cls.env['product.product'].create({
            'name': 'SOFÁ ABONO', 'type': 'consu', 'list_price': 200.0, 'taxes_id': [Command.clear()]})

    def _factura(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 200.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def _pagar(self, factura, monto, fecha):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'payment_date': fecha, 'amount': monto}).action_create_payments()

    def test_un_abono_dice_cuanto_falta_y_cuando_vence(self):
        factura = self._factura()
        inicio = fields.Date.today() - relativedelta(days=3)
        self._pagar(factura, 80.0, inicio)
        estado = factura._dcasa_estado_abono()
        self.assertTrue(estado['es_abono'])
        self.assertEqual((estado['total'], estado['pagado'], estado['saldo']), (200.0, 80.0, 120.0))
        self.assertEqual(estado['inicio'], inicio)
        self.assertEqual(estado['vence'], inicio + relativedelta(months=1), 'la dueña: un mes para terminar de pagar')
        self.assertFalse(estado['vencido'])
        self.assertEqual([a['monto'] for a in estado['abonos']], [80.0])

    def test_el_plazo_cuenta_desde_el_primer_abono_y_avisa_si_ya_paso(self):
        factura = self._factura()
        primero = fields.Date.today() - relativedelta(months=2)
        self._pagar(factura, 50.0, primero)
        self._pagar(factura, 50.0, fields.Date.today())
        estado = factura._dcasa_estado_abono()
        self.assertEqual(estado['inicio'], primero)
        self.assertEqual(estado['saldo'], 100.0)
        self.assertTrue(estado['vencido'])

    def test_pagada_por_completo_ya_no_es_abono_ni_vence(self):
        factura = self._factura()
        self._pagar(factura, 50.0, fields.Date.today())
        self._pagar(factura, 150.0, fields.Date.today())
        estado = factura._dcasa_estado_abono()
        self.assertFalse(estado['es_abono'])
        self.assertEqual(estado['saldo'], 0.0)
        self.assertFalse(estado['vence'])
        self.assertEqual(len(estado['abonos']), 2, 'los abonos siguen en la lista')

    def test_sin_pagos_no_es_abono(self):
        estado = self._factura()._dcasa_estado_abono()
        self.assertFalse(estado['es_abono'])
        self.assertEqual((estado['pagado'], estado['saldo']), (0.0, 200.0))
        self.assertFalse(estado['inicio'] or estado['vence'])

    def test_plazo_en_cero_no_muestra_vencimiento(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_MESES_ABONO, '0')
        factura = self._factura()
        self._pagar(factura, 20.0, fields.Date.today())
        self.assertFalse(factura._dcasa_estado_abono()['vence'])

    def test_no_toca_la_contabilidad(self):
        factura = self._factura()
        self._pagar(factura, 80.0, fields.Date.today())
        antes = [(linea.account_id.id, linea.debit, linea.credit, linea.amount_residual)
                 for linea in factura.line_ids.sorted('id')]
        factura._dcasa_estado_abono()
        despues = [(linea.account_id.id, linea.debit, linea.credit, linea.amount_residual)
                   for linea in factura.line_ids.sorted('id')]
        self.assertEqual(antes, despues)
