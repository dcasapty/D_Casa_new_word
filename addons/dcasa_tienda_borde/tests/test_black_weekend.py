from odoo.addons.dcasa_tienda_borde.models.pendiente import PARAM_BW_PUBLICADO, TODO
from odoo.tests import TransactionCase, tagged


def _ventana(env, activo='0', inicio='', fin=''):
    param = env['ir.config_parameter'].sudo()
    param.set_param('dcasa_black_weekend.activo', activo)
    param.set_param('dcasa_black_weekend.inicio', inicio)
    param.set_param('dcasa_black_weekend.fin', fin)


@tagged('post_install', '-at_install')
class TestBlackWeekendAviso(TransactionCase):
    """La marca, el orden y la ventana de Black Weekend regeneran la tienda del borde."""

    def setUp(self):
        super().setUp()
        self.Pendiente = self.env['dcasa.tienda.pendiente'].sudo()
        self.producto = self.env['product.template'].create({
            'name': 'Cama BW marcas prueba', 'list_price': 99.99, 'is_published': True})
        self._marcados()
        self.Pendiente.search([]).unlink()

    def _marcados(self):
        self.env.flush_all()
        self.env.cr.flush()
        return set(self.Pendiente.search([]).mapped('producto_id'))

    def test_marcar_el_producto_regenera(self):
        self.producto.dcasa_black_weekend = True
        self.assertIn(self.producto.id, self._marcados())

    def test_cambiar_la_ventana_regenera_todo(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_black_weekend.fin', '2026-10-10')
        self.assertIn(TODO, self._marcados())

    def test_otro_parametro_no_regenera(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa.prueba_cualquiera', 'x')
        self.assertNotIn(TODO, self._marcados())

    def test_vigilante_avisa_solo_cuando_cambia(self):
        _ventana(self.env, '1')
        self.env['ir.config_parameter'].sudo().set_param(PARAM_BW_PUBLICADO, '0')
        self._marcados()
        self.Pendiente.search([]).unlink()
        self.assertTrue(self.Pendiente._dcasa_vigilar_black_weekend())
        self.assertIn(TODO, self._marcados())
        self.Pendiente.search([]).unlink()
        self.assertFalse(self.Pendiente._dcasa_vigilar_black_weekend(), 'Sin cambio, no hay aviso')
        self.assertNotIn(TODO, self._marcados())
        _ventana(self.env, '0', '2020-01-01', '2020-01-02')  # la ventana ya pasó: se apaga
        self.assertTrue(self.Pendiente._dcasa_vigilar_black_weekend())
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param(PARAM_BW_PUBLICADO), '0')

    def test_vigilante_programado(self):
        cron = self.env.ref('dcasa_tienda_borde.cron_vigilar_black_weekend')
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'hours'))

