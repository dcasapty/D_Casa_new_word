"""Juan y la caja de respuesta con un producto tipo «Combo» (cama + colchón): no arman una cotización en cero."""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_cotizacion_automatica import CotizarCase
from .test_panel_catalogo import CatalogoCase


def _combo_publicado(env, cama, colchon):
    impuesto = env['brian.herramientas']._b_itbms_venta()
    grupos = env['product.combo'].create([
        {'name': 'Cama', 'combo_item_ids': [(0, 0, {'product_id': cama.product_variant_id.id})]},
        {'name': 'Colchón', 'combo_item_ids': [(0, 0, {'product_id': colchon.product_variant_id.id})]}])
    return env['product.template'].create({
        'name': 'Zzcombo Cama y Colchón', 'default_code': 'ZZ-COMBO', 'type': 'combo', 'list_price': 700.0,
        'sale_ok': True, 'is_published': True, 'taxes_id': [Command.set(impuesto.ids)],
        'combo_ids': [Command.set(grupos.ids)]})


@tagged('post_install', '-at_install')
class TestJuanConCombos(CotizarCase):

    def test_un_combo_publicado_no_se_cotiza_solo_lo_arma_una_vendedora(self):
        _combo_publicado(self.env, self.cama, self.colchon)
        antes = self.env['sale.order'].search_count([])
        datos = self.cotizar({'codigo': 'ZZ-COMBO'})
        self.assertFalse(datos['creada'])
        self.assertEqual(datos['motivo'], 'es_combo')
        self.assertIn('pasar_a_vendedora', datos['mensaje'])
        self.assertEqual(self.env['sale.order'].search_count([]), antes, 'No deja una cotización en cero')

    def test_los_demas_productos_se_siguen_cotizando(self):
        _combo_publicado(self.env, self.cama, self.colchon)
        self.assertTrue(self.cotizar({'codigo': 'ZZ-SOFA'})['creada'])


@tagged('post_install', '-at_install')
class TestCajaDeRespuestaConCombos(CatalogoCase):

    def test_el_boton_cotizacion_no_deja_cotizar_un_combo_en_cero(self):
        combo = _combo_publicado(self.env, self.cama, self.colchon)
        antes = self.env['sale.order'].search_count([])
        with self.assertRaisesRegex(UserError, 'es un combo'):
            self.panel.crear_cotizacion(self.conv.id, [{'variante_id': combo.product_variant_id.id, 'cantidad': 1}])
        self.assertEqual(self.env['sale.order'].search_count([]), antes)
