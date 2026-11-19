from odoo.tests import TransactionCase, tagged

from .common import PreparaPedido


@tagged('post_install', '-at_install')
class TestHumo(PreparaPedido, TransactionCase):
    def test_existe_el_proveedor_apagado(self):
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        self.assertEqual(proveedor.state, 'disabled')
