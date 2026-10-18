"""La conciliación bancaria no se frena por el primer abono mínimo (decisión de la gerencia A3, 17 oct 2026): el dinero
ya entró. Si así entra un primer abono menor a la mitad, queda una nota en la factura para que Gerencia lo revise."""
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.tests import tagged

from .test_contabilidad import ContabilidadCommon


@tagged('post_install', '-at_install')
class TestPrimerAbonoPorElBanco(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contador = crear_usuario(cls.env, 'pab_contador', 'account.group_account_user')
        cls.cliente.write({'phone': '+507 6555-0501', 'email': 'cliente.contable@example.com'})

    def _notas(self, factura):
        return factura.message_ids.filtered(lambda m: 'Primer abono' in (m.body or ''))

    def test_la_conciliacion_bancaria_no_se_bloquea_y_deja_el_aviso(self):
        factura = self._factura(100.0)   # 107.00 con ITBMS: la mitad es 53.50
        movimiento = self._movimiento(30.0, 'ABONO', partner=self.cliente)
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        resultado = self.env['dcasa.conciliacion'].with_user(self.contador).conciliar(
            movimiento.id, apunte_ids=apunte.ids)
        self.assertTrue(resultado['conciliado'])
        self.assertEqual(factura.payment_state, 'partial')
        self.assertAlmostEqual(factura.amount_residual, 77.0)
        nota = self._notas(factura)
        self.assertEqual(len(nota), 1)
        self.assertIn('Primer abono de $30.00: es menos de la mitad del total ($107.00).', nota.body)
        self.assertIn('Que Gerencia lo revise', nota.body)
        # Lo que entra después por el banco ya no es el primero: sin otra nota.
        segundo = self._movimiento(10.0, 'ABONO 2', partner=self.cliente)
        self.env['dcasa.conciliacion'].with_user(self.contador).conciliar(segundo.id, apunte_ids=apunte.ids)
        self.assertAlmostEqual(factura.amount_residual, 67.0)
        self.assertEqual(len(self._notas(factura)), 1)

    def test_por_el_banco_la_mitad_o_mas_no_deja_nota(self):
        factura = self._factura(100.0)
        movimiento = self._movimiento(60.0, 'ABONO', partner=self.cliente)
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        self.env['dcasa.conciliacion'].with_user(self.contador).conciliar(movimiento.id, apunte_ids=apunte.ids)
        self.assertEqual(factura.payment_state, 'partial')
        self.assertFalse(self._notas(factura))
