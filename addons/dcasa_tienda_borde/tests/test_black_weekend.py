import os
from unittest.mock import patch

from odoo.addons.dcasa_tienda_borde.models.pendiente import PARAM_BW_PUBLICADO, TODO
from odoo.tests import HttpCase, TransactionCase, tagged

TOKEN = 'z' * 40


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


@tagged('post_install', '-at_install')
class TestBlackWeekendFeed(HttpCase):

    def setUp(self):
        super().setUp()
        recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        self.cama = self.env['product.template'].create({
            'name': 'Cama BW feed prueba', 'list_price': 143.99, 'is_published': True, 'default_code': 'BW-FEED-1',
            'public_categ_ids': [(6, 0, recamaras.ids)], 'dcasa_black_weekend': True, 'dcasa_bw_orden': -1000,
        })

    def _feed(self):
        with patch.dict(os.environ, {'TIENDA_FEED_TOKEN': TOKEN}):
            respuesta = self.url_open('/dcasa/tienda/feed', headers={'X-Dcasa-Tienda-Token': TOKEN})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_feed_con_la_campana_activa(self):
        _ventana(self.env, '1', '2026-10-05', '2026-10-11')
        feed = self._feed()
        bw = feed['black_weekend']
        self.assertTrue(bw['activo'])
        self.assertEqual((bw['inicio'], bw['fin'], bw['zona']), ('2026-10-05', '2026-10-11', 'America/Panama'))
        self.assertEqual(bw['ruta'], '/black-weekend')
        self.assertTrue(bw['og_imagen'].endswith('/website_dcasa/static/src/img/black_weekend/og.jpg'))
        item = next(p for p in bw['productos'] if p['id'] == self.cama.id)
        self.assertEqual(item['precio'], 143.99)
        self.assertEqual(item['codigo'], 'BW-FEED-1')
        self.assertIn('BW-FEED-1', item['whatsapp'])
        self.assertEqual(item['compra'], 'directa')
        self.assertEqual(bw['json_ld']['@type'], 'ItemList')
        producto = next(p for p in feed['productos'] if p['id'] == self.cama.id)
        self.assertTrue(producto['black_weekend'])

    def test_feed_con_la_campana_apagada(self):
        _ventana(self.env, '0', '2020-01-01', '2020-01-02')
        self.assertFalse(self._feed()['black_weekend']['activo'])
