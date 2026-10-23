"""D1: los saldos de 1 a 5 centavos (redondeo) se ven con vista previa y se cierran con su ajuste contable."""
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..wizard.saldos_centavos import MAX_CENTAVOS
from .test_contabilidad import ContabilidadCommon


@tagged('post_install', '-at_install')
class TestSaldosDeCentavos(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contador = crear_usuario(cls.env, 'cent_contador', 'account.group_account_user')
        cls.gerente = crear_usuario(cls.env, 'cent_gerente', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'cent_vendedora', 'dcasa_base.group_vendedora')
        cls.cliente.write({'phone': '+507 6555-0601', 'email': 'cliente.centavos@example.com'})
        cls.efectivo = cls.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', cls.company.id)], limit=1)

    def _pagar(self, factura, monto):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'amount': monto, 'journal_id': self.efectivo.id, 'payment_difference_handling': 'open',
            })._create_payments()

    def _asistente(self, usuario):
        Asistente = self.env['dcasa.saldos.centavos'].with_user(usuario)
        return Asistente.create(Asistente.default_get(['linea_ids', 'company_id']))

    def test_vista_previa_y_cierre(self):
        redondeo = self._factura(100.0)            # 107.00 con ITBMS
        self._pagar(redondeo, 106.98)              # quedan 2 centavos
        de_verdad = self._factura(100.0)
        self._pagar(de_verdad, 106.90)             # 10 centavos: no es redondeo
        sin_pago = self._factura(0.03)             # una factura de centavos sin ningún pago: no es redondeo
        de_mas = self._factura(100.0)
        self._pagar(de_mas, 107.03)                # al cliente le sobran 3 centavos en su cobro
        self.assertEqual(redondeo.payment_state, 'partial')
        self.assertAlmostEqual(redondeo.amount_residual, 0.02)

        asistente = self._asistente(self.contador)
        documentos = {linea.move_line_id.move_id: linea for linea in asistente.linea_ids}
        self.assertIn(redondeo, documentos)
        self.assertEqual(documentos[redondeo].tipo, 'factura')
        self.assertNotIn(de_verdad, documentos)
        self.assertNotIn(sin_pago, documentos)
        # Solo las de este cliente: la base puede traer otros saldos de centavos.
        mias = asistente.linea_ids.filtered(lambda linea: linea.partner_id == self.cliente)
        cobro = mias.filtered(lambda linea: linea.tipo == 'cobro')
        self.assertEqual(len(cobro), 1)
        self.assertAlmostEqual(cobro.saldo, -0.03)
        self.assertAlmostEqual(sum(s for s in mias.mapped('saldo') if s > 0), 0.02)
        self.assertGreaterEqual(asistente.pierde, 0.02)
        self.assertGreaterEqual(asistente.gana, 0.03)
        self.assertTrue(all(abs(linea.saldo) <= MAX_CENTAVOS for linea in asistente.linea_ids))

        asistente.action_cerrar()
        self.assertIn(redondeo.payment_state, ('paid', 'in_payment'))
        self.assertAlmostEqual(redondeo.amount_residual, 0.0)
        self.assertTrue(cobro.move_line_id.reconciled)
        self.assertAlmostEqual(de_verdad.amount_residual, 0.10)
        self.assertIn('por redondeo', redondeo.message_ids[0].body)
        perdida = self.company.default_cash_difference_expense_account_id
        ganancia = self.company.default_cash_difference_income_account_id
        ajustes = self.env['account.move.line'].search([('name', 'like', 'Ajuste por redondeo%'),
                                                        ('partner_id', '=', self.cliente.id)])
        self.assertAlmostEqual(sum(ajustes.filtered(lambda a: a.account_id == perdida).mapped('debit')), 0.02)
        self.assertAlmostEqual(sum(ajustes.filtered(lambda a: a.account_id == ganancia).mapped('credit')), 0.03)
        # Ya no queda nada que cerrar de esas dos.
        self.assertNotIn(redondeo, self._asistente(self.gerente).linea_ids.move_line_id.move_id)

    def test_lo_que_cambio_despues_de_la_vista_previa_no_se_toca(self):
        factura = self._factura(100.0)
        self._pagar(factura, 106.98)
        asistente = self._asistente(self.gerente)
        self._pagar(factura, 0.02)                 # alguien cobró los 2 centavos mientras tanto
        asistente.action_cerrar()
        self.assertFalse(self.env['account.move.line'].search_count(
            [('name', '=', f'Ajuste por redondeo {factura.name}')]))

    def test_la_vendedora_no_cierra_saldos(self):
        with self.assertRaises(AccessError):
            self._asistente(self.vendedora)
        with self.assertRaises(AccessError):
            self.env['dcasa.saldos.centavos'].with_user(self.vendedora)._dcasa_buscar()
