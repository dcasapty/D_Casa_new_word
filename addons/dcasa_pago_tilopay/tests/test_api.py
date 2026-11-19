from odoo.tests import BaseCase, tagged

from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api


@tagged('post_install', '-at_install')
class TestHumoApi(BaseCase):
    def test_orden(self):
        self.assertTrue(api.orden_valida('S00012-1-3fa9c2e1'))
