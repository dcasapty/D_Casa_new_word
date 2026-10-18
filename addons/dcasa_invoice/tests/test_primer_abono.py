"""El primer abono: al menos la mitad del total (decisión de la gerencia A3, 17 oct 2026; docs/DECISIONES_CONTABLES.md).

Si es menos, solo Gerencia (o un administrador) lo registra; a Caja le sale el mensaje claro y el asistente «Pagar» lo
avisa antes. Los abonos siguientes y el pago completo son libres. La conciliación bancaria no se frena (test en
dcasa_contabilidad) y Brian usa el mismo asistente (test en dcasa_brian).
"""
from contextlib import contextmanager

from odoo import Command, fields
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@contextmanager
def negado(prueba, excepcion, texto):
    """``assertRaisesRegex`` con el savepoint de Odoo (``assertRaises``): lo que se escribió antes del error se deshace,
    como en una llamada real."""
    with prueba.assertRaises(excepcion) as contexto:
        yield contexto
    prueba.assertRegex(str(contexto.exception), texto)


MENSAJE = 'El primer abono debe ser de al menos la mitad: $100.00. Si es menos, lo registra Gerencia.'


@tagged('post_install', '-at_install')
class TestPrimerAbono(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.caja = crear_usuario(env, 'pa_caja', 'dcasa_base.group_caja')
        cls.gerencia = crear_usuario(env, 'pa_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(env, 'pa_contador', 'account.group_account_user')
        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE PRIMER ABONO', 'phone': '+507 6555-0301', 'email': 'primer.abono@example.com'})
        cls.mueble = env['product.product'].create({
            'name': 'CAMA PRIMER ABONO', 'type': 'consu', 'list_price': 200.0, 'taxes_id': [Command.clear()]})
        cls.efectivo = env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', env.company.id)], limit=1)

    def _factura(self, monto=200.0):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': monto,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def _asistente(self, usuario, facturas, monto=None, **valores):
        if monto is not None:
            valores['amount'] = monto
        return self.env['account.payment.register'].with_user(usuario).with_context(
            active_model='account.move', active_ids=facturas.ids).create(
            {'payment_date': fields.Date.today(), 'journal_id': self.efectivo.id, **valores})

    def _pagar(self, usuario, factura, monto=None):
        return self._asistente(usuario, factura, monto)._create_payments()

    def _notas(self, factura):
        return factura.message_ids.filtered(lambda m: 'Primer abono' in (m.body or ''))

    # --- Menos de la mitad --------------------------------------------------------------------------------------
    def test_primer_abono_de_49_por_ciento_negado_a_caja(self):
        factura = self._factura()
        for monto in (98.0, 99.99, 1.0):
            with self.subTest(monto=monto):
                with self.assertRaises(UserError) as error:
                    self._pagar(self.caja, factura, monto)
                self.assertEqual(str(error.exception.args[0]), MENSAJE)
                with negado(self, UserError, 'al menos la mitad'):
                    self._asistente(self.caja, factura, monto).action_create_payments()
        self.assertEqual(factura.payment_state, 'not_paid')
        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', self.cliente.id)]))

    def test_tampoco_al_contador(self):
        """«Solo Gerencia (o un administrador)»: contabilidad cobra, pero un primer abono bajo no."""
        factura = self._factura()
        with negado(self, UserError, 'al menos la mitad'):
            self._pagar(self.contador, factura, 98.0)

    def test_el_asistente_lo_avisa_antes(self):
        factura = self._factura()
        self.assertEqual(self._asistente(self.caja, factura, 98.0).dcasa_aviso_primer_abono, MENSAJE)
        self.assertFalse(self._asistente(self.caja, factura, 100.0).dcasa_aviso_primer_abono, 'la mitad justa pasa')
        self.assertFalse(self._asistente(self.caja, factura).dcasa_aviso_primer_abono, 'completo: sin aviso')
        aviso = self._asistente(self.gerencia, factura, 98.0).dcasa_aviso_primer_abono
        self.assertIn('Como eres Gerencia, puedes registrarlo', aviso)
        vista = self.env['account.payment.register'].with_user(self.caja).get_views(
            [(False, 'form')])['views']['form']['arch']
        self.assertIn('dcasa_aviso_primer_abono', vista)

    def test_gerencia_registra_el_49_por_ciento_y_queda_la_nota(self):
        factura = self._factura()
        pago = self._pagar(self.gerencia, factura, 98.0)
        self.assertEqual((pago.amount, factura.payment_state), (98.0, 'partial'))
        nota = self._notas(factura)
        self.assertEqual(len(nota), 1)
        self.assertIn('Primer abono de $98.00: es menos de la mitad del total ($200.00).', nota.body)
        self.assertIn('Gerencia', nota.body)
        self.assertEqual(nota.author_id, self.gerencia.partner_id)
        # Lo siguiente lo cobra Caja sin trabas.
        self._pagar(self.caja, factura, 10.0)
        self.assertEqual(factura.amount_residual, 92.0)

    # --- Lo que nunca se frena ---------------------------------------------------------------------------------
    def test_la_mitad_justa_pasa_sin_nota(self):
        factura = self._factura()
        self._pagar(self.caja, factura, 100.0)
        self.assertEqual(factura.payment_state, 'partial')
        self.assertFalse(self._notas(factura))

    def test_los_pagos_siguientes_son_libres(self):
        factura = self._factura()
        self._pagar(self.caja, factura, 120.0)
        for monto in (1.0, 20.0, 9.0):
            self._pagar(self.caja, factura, monto)
        self.assertEqual(factura.amount_residual, 50.0)
        self._pagar(self.caja, factura)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    def test_el_pago_completo_es_libre(self):
        factura = self._factura()
        self._pagar(self.caja, factura)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        # También cuando una nota de crédito ya bajó lo que falta a menos de la mitad: pagarlo todo pasa.
        otra = self._factura()
        nota = self.env['account.move'].with_user(self.gerencia).create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 150.0,
                                                 'tax_ids': [Command.clear()]})]})
        nota.action_post()
        credito = nota.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        otra.with_user(self.gerencia).js_assign_outstanding_line(credito.id)
        self.assertEqual(otra.amount_residual, 50.0)
        self.assertFalse(otra._dcasa_tiene_pagos(), 'una nota de crédito no es un pago')
        with negado(self, UserError, 'al menos la mitad'):
            self._pagar(self.caja, otra, 30.0)
        self._pagar(self.caja, otra, 50.0)
        self.assertIn(otra.payment_state, ('paid', 'in_payment'))

    def test_varias_facturas_en_un_solo_pago(self):
        """Un pago agrupado que deja una factura con un primer abono bajo se deshace entero."""
        primera, segunda = self._factura(100.0), self._factura(100.0)
        asistente = self._asistente(self.caja, primera | segunda, 40.0, group_payment=True)
        with negado(self, UserError, 'al menos la mitad: \\$50.00'):
            asistente._create_payments()
        self.env.invalidate_all()
        self.assertEqual((primera.payment_state, segunda.payment_state), ('not_paid', 'not_paid'))
        self.assertFalse(self.env['account.payment'].search([('partner_id', '=', self.cliente.id)]), 'no quedó pago')
        self._asistente(self.caja, primera | segunda, 150.0, group_payment=True)._create_payments()
        self.assertEqual(primera.amount_residual + segunda.amount_residual, 50.0)
