"""C-07: reportes y conciliación exigen el grupo contable en el servidor, no solo en el menú.

La vendedora puede leer apuntes por el ACL de ``sale`` (``account.move.line``); por RPC
directo llegaba al balance completo. Se llama por ``odoo.service.model.call_kw``, la misma
puerta que ``/web/dataset/call_kw``.
"""
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .test_contabilidad import DESDE, HASTA, ContabilidadCommon


@tagged('post_install', '-at_install')
class TestSeguridadRpcContabilidad(ContabilidadCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='rpc_conta_ventas', name='Ventas sin contabilidad',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.contador = new_test_user(cls.env, login='rpc_conta_contador', name='Contador',
                                     groups='base.group_user,account.group_account_user')

    def rpc(self, usuario, modelo, metodo, args=(), kwargs=None):
        return call_kw(self.env(user=usuario)[modelo], metodo, list(args), kwargs or {})

    def test_vendedora_no_llega_a_los_reportes(self):
        self._factura(100.0)
        for reporte in self.reportes.REPORTES:
            with self.subTest(reporte=reporte):
                with self.assertRaises(AccessError):  # el motor ya no es público
                    self.rpc(self.vendedora, 'dcasa.reporte.contable', reporte, [], {'desde': DESDE, 'hasta': HASTA})
                with self.assertRaises(AccessError):  # y la puerta pública pide el grupo
                    self.rpc(self.vendedora, 'dcasa.reporte.contable', 'obtener', [reporte])

    def test_contador_ve_los_reportes(self):
        self._factura(100.0)
        datos = self.rpc(self.contador, 'dcasa.reporte.contable', 'obtener', ['balance_general'],
                         {'desde': DESDE, 'hasta': HASTA})
        self.assertTrue(datos['cuadra'])

    def test_vendedora_no_concilia(self):
        factura = self._factura(100.0)
        movimiento = self._movimiento(107.0, f'TRANSFERENCIA {factura.name}')
        apunte = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        llamadas = [
            ('diarios', []), ('pendientes', [self.banco.id]), ('candidatos', [movimiento.id]),
            ('cuentas_rapidas', []), ('conciliar', [movimiento.id, apunte.ids]), ('automatico', [self.banco.id]),
            ('deshacer', [movimiento.id]),
        ]
        for metodo, args in llamadas:
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                self.rpc(self.vendedora, 'dcasa.conciliacion', metodo, args)
        for metodo, args in (('dcasa_candidatos', []), ('dcasa_conciliar', [apunte.ids]),
                             ('dcasa_conciliar_automatico', [])):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                self.rpc(self.vendedora, 'account.bank.statement.line', metodo, [movimiento.ids, *args])
        # Aunque la llamen desde Python con su usuario, el grupo se comprueba.
        with self.assertRaises(AccessError):
            movimiento.with_user(self.vendedora).dcasa_conciliar(apunte.ids)
        self.assertFalse(movimiento.is_reconciled)

    def test_contador_concilia(self):
        factura = self._factura(100.0)
        movimiento = self._movimiento(107.0, f'TRANSFERENCIA {factura.name}')
        self.assertTrue(self.rpc(self.contador, 'dcasa.conciliacion', 'pendientes', [self.banco.id]))
        self.assertEqual(self.rpc(self.contador, 'dcasa.conciliacion', 'automatico', [self.banco.id]), 1)
        self.assertTrue(movimiento.is_reconciled)
