"""Revisión adversarial de «los combos son inamovibles» (rama local/combos). Datos inventados.

Cada prueba que falla demuestra un hallazgo; las que pasan, lo que se intentó romper y aguantó.
"""
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_catalogo.models.combo_armable import SIN_RECALCULAR
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_combos_armables import COMBO_KING, CombosCommon


@tagged('post_install', '-at_install', 'rv_combos')
class TestRvCombosCampana(CombosCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.group_user').write({
            'implied_ids': [Command.link(cls.env.ref('product.group_product_pricelist').id)]})
        Campana = cls.env['dcasa.campana']
        Campana._dcasa_tarifa_del_sitio()
        sitio = cls.env.ref('website.default_website')
        cls.tarifa = cls.env['product.template']._dcasa_campana_tarifas(sitio)[:1]
        cls.cliente.property_product_pricelist = cls.tarifa
        cls.campana = Campana.search([('website_id', '=', sitio.id)]) or Campana.create({'website_id': sitio.id})
        hoy = fields.Date.context_today(cls.campana)
        cls.campana.write({'fecha_inicio': hoy - timedelta(days=1), 'fecha_fin': hoy + timedelta(days=1),
                           'dcasa_rebaja_combos': False})
        # La cama king 400 → 385 en campaña. El colchón king NO está en la campaña: va a 300 solo, 260 en combo.
        # (El 385 no es casual: la cama pierde 15 al entrar al combo y el colchón gana 40, así que el combo sigue
        # siendo el más barato y se queda tal cual. Con la regla del par, del 2026-11-16, un 350 lo desharía: la cama
        # perdería 50 y el par saldría más caro que comprar suelto. Ese caso tiene sus pruebas en
        # test_rv2_combos_campana.py.)
        cls.cama_king.product_tmpl_id.write({'dcasa_black_weekend': True, 'dcasa_campana_precio': 385.0})

    # --- Hallazgos -------------------------------------------------------------------

    def test_rv_dos_camas_en_lineas_y_un_colchon_por_dos_la_segunda_cama_toma_la_campana(self):
        """Dos camas king (dos líneas) y una línea de 2 colchones king: son dos combos con precio en combo (el colchón
        ocupa las dos camas), pero solo la «cama principal» queda sin campaña. La otra cama va a 385 y su colchón a
        260: campaña + combo juntos."""
        orden = self.orden(productos=[self.cama_king, self.cama_king])
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon_king.id, 'product_uom_qty': 2})
        colchon = self.linea(orden, self.colchon_king)
        self.assertEqual((colchon.price_unit, colchon.product_uom_qty), (COMBO_KING, 2), 'dos colchones en combo')
        camas = self.linea(orden, self.cama_king)
        self.assertEqual(camas.mapped('price_unit'), [400.0, 400.0],
                         'las dos camas van en combo: ninguna con precio de campaña')

    def test_rv_contexto_sin_recalcular_por_rpc_deja_campana_y_combo_juntos(self):
        """Una vendedora manda por RPC el contexto interno ``dcasa_combo_sin_recalcular``: borra la marca de la cama
        del combo (campo «readonly» solo en pantalla) y le pone el precio de campaña. El tope la mide contra la
        campaña (sin marca) y el emparejamiento, que la volvería a marcar, no corre: cama 385 + colchón 260."""
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        self.assertEqual((cama.price_unit, colchon.price_unit), (400.0, COMBO_KING))
        rpc = cama.with_user(self.vendedora).with_context(**{SIN_RECALCULAR: True})
        rpc.write({'dcasa_combo_sin_campana': False})
        # Arreglado, la marca no se borra: el emparejamiento la vuelve a poner al medir el tope.
        # (El tope mide la rebaja contra lo que la cama costaría suelta, 385: poner 350 a mano es un 9,1 % y entra en
        # su tope del 10 %, como en cualquier otra línea. Lo que no puede hacer es sacarle la marca al combo.)
        rpc.write({'price_unit': 350.0})
        self.assertEqual(colchon.price_unit, COMBO_KING)
        self.assertTrue(cama.dcasa_combo_sin_campana, 'la cama sigue marcada como pieza del combo')
        with self.assertRaises(ValidationError):
            rpc.write({'price_unit': 300.0})   # un 22 %: muy por encima de su tope

    def test_rv_contexto_sin_recalcular_al_quitar_la_cama_el_colchon_conserva_el_combo(self):
        """Misma raíz (ya existía antes de esta rama): quitar la cama con ``dcasa_combo_sin_recalcular`` deja el
        colchón a precio en combo sin cama."""
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        self.linea(orden, self.cama_king).with_user(self.vendedora).with_context(**{SIN_RECALCULAR: True}).unlink()
        self.assertEqual(orden.order_line.price_unit, 300.0, 'sin cama, el colchón vuelve a su precio normal')

    def test_rv_tarifa_encadenada_a_la_del_sitio_le_da_la_campana_a_la_cama_del_combo(self):
        """Latente: una tarifa basada en la del sitio («Otra tarifa»): la regla de la línea se busca con la bandera,
        pero su precio base se calcula sin ella (``pricelist_item_id`` se usa en el entorno de la línea)."""
        mayorista = self.env['product.pricelist'].create({'name': 'Tarifa encadenada de prueba', 'item_ids': [
            Command.create({'applied_on': '3_global', 'compute_price': 'formula', 'base': 'pricelist',
                            'base_pricelist_id': self.tarifa.id, 'price_discount': 0.0})]})
        self.cliente.property_product_pricelist = mayorista
        solo = self.orden(productos=[self.cama_king])
        self.assertEqual(solo.order_line.price_unit, 385.0, 'la cama sola hereda la campaña de la tarifa base')
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama = self.linea(orden, self.cama_king)
        self.assertTrue(cama.dcasa_combo_sin_campana)
        panel = orden.with_user(self.vendedora).dcasa_combo_panel()['combos'][0]['cama']
        self.assertEqual(panel['precio'], 400.0, 'el panel dice 400')
        self.assertEqual(cama.price_unit, 400.0, 'y la línea también debería')

    def test_rv_colchon_sin_descuento_real_le_quita_la_campana_a_la_cama(self):
        """El precio normal del colchón bajó por debajo de su precio en combo («Revisar: ya no es menor»): el combo no
        da ningún descuento, pero la cama igual pierde su precio de campaña."""
        self.colchon_king.product_tmpl_id.list_price = 200.0   # king: 200 + 50 = 250 < 260 (precio en combo)
        self.assertEqual(self.colchon_king.dcasa_combo_estado, 'no_menor')
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama, colchon = self.linea(orden, self.cama_king), self.linea(orden, self.colchon_king)
        self.assertEqual(colchon.price_unit, 250.0, 'el colchón va a su normal: el combo no rebaja nada')
        self.assertEqual(cama.price_unit, 385.0, 'sin descuento de combo, la cama conserva la campaña')

    def test_rv_cama_por_dos_con_un_colchon_cobra_la_cama_sola_sin_campana(self):
        """Una línea de 2 camas king con 1 colchón: un combo y una cama sola. Toda la línea queda sin campaña: la cama
        sola se cobra a 400 y no a 385."""
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama = self.linea(orden, self.cama_king)
        cama.with_user(self.vendedora).product_uom_qty = 2
        self.assertLessEqual(cama.price_subtotal, 400.0 + 385.0, 'una cama en combo (400) y una sola (385)')

    def test_rv_textos_promo_y_expo_en_femenino(self):
        from odoo.addons.website_dcasa.models.black_weekend import articulo_y_nombre
        self.assertEqual(articulo_y_nombre('Promo Navideña')[0], 'la', '«Ver toda la Promo Navideña»')
        self.assertEqual(articulo_y_nombre('Expo Muebles')[0], 'la', '«Ver toda la Expo Muebles»')

    # --- Lo que aguantó ----------------------------------------------------------------

    def test_rv_duplicar_cambiar_cantidad_y_variante(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        copia = orden.with_user(self.vendedora).copy()
        self.assertEqual(sorted(copia.order_line.mapped('price_unit')), [COMBO_KING, 400.0])
        self.assertTrue(all(copia.order_line.mapped('dcasa_combo_sin_campana')))
        cama = self.linea(copia, self.cama_king)
        colchon = self.linea(copia, self.colchon_king)
        colchon.with_user(self.vendedora).product_uom_qty = 2   # dos colchones, una cama: sale del combo
        self.assertEqual((cama.price_unit, colchon.price_unit), (385.0, 300.0))
        cama.with_user(self.vendedora).product_uom_qty = 2      # dos camas: dos combos
        self.assertEqual((cama.price_unit, colchon.price_unit), (400.0, COMBO_KING))
        (colchon | cama).with_user(self.vendedora).write({'product_uom_qty': 1})
        colchon.with_user(self.vendedora).product_id = self.colchon_queen   # otra medida: sale del combo
        self.assertEqual(cama.price_unit, 385.0)
        self.assertFalse(cama.dcasa_combo_sin_campana)
        colchon.with_user(self.vendedora).product_id = self.colchon_king    # vuelve
        self.assertEqual((cama.price_unit, colchon.price_unit), (400.0, COMBO_KING))

    def test_rv_escribir_la_marca_a_mano_no_sirve(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        cama = self.linea(orden, self.cama_king)
        cama.with_user(self.vendedora).write({'dcasa_combo_sin_campana': False})
        self.assertTrue(cama.dcasa_combo_sin_campana)
        self.assertEqual(cama.price_unit, 400.0)

    def test_rv_actualizar_precios_no_le_da_la_campana_al_combo(self):
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        orden.with_user(self.vendedora).action_update_prices()
        self.assertEqual(sorted(orden.order_line.mapped('price_unit')), [COMBO_KING, 400.0])

    def test_rv_la_bandera_no_se_filtra_a_otra_linea_ni_a_otro_pedido(self):
        combo = self.orden(productos=[self.cama_king, self.colchon_king])
        sola = self.orden(productos=[self.cama_king])
        (combo | sola).order_line.invalidate_recordset()
        lineas = (combo | sola).order_line
        lineas._compute_pricelist_item_id()   # todas juntas en un solo cómputo
        self.assertEqual(sola.order_line.price_unit, 385.0)
        self.assertTrue(sola.order_line.pricelist_item_id.dcasa_campana)
        self.assertFalse(self.linea(combo, self.cama_king).pricelist_item_id.dcasa_campana)

    def test_rv_la_vendedora_no_fecha_una_linea_en_la_campana_por_otros_caminos(self):
        """I-B: la campaña terminó hace 5 días (sus reglas siguen 30 días). Ni con un valor por defecto en el
        contexto, ni al duplicar con ``default``, ni importando, la vendedora fecha una línea dentro de la campaña."""
        hoy = fields.Date.context_today(self.campana)
        self.campana.write({'fecha_inicio': hoy - timedelta(days=10), 'fecha_fin': hoy - timedelta(days=5)})
        adentro = fields.Datetime.now() - timedelta(days=7)
        orden = self.orden(productos=[self.mesa])
        Linea = self.env['sale.order.line'].with_user(self.vendedora)
        por_defecto = Linea.with_context(default_dcasa_fecha_precio=adentro).create(
            {'order_id': orden.id, 'product_id': self.cama_king.id})
        self.assertEqual(por_defecto.price_unit, 400.0)
        copia = por_defecto.copy({'dcasa_fecha_precio': adentro, 'order_id': orden.id})
        self.assertEqual(copia.price_unit, 400.0)
        Linea.load(['order_id/.id', 'product_id/.id', 'dcasa_fecha_precio'],
                   [[str(orden.id), str(self.cama_king.id), fields.Datetime.to_string(adentro)]])
        self.assertEqual(self.linea(orden, self.cama_king).mapped('price_unit'), [400.0] * 3)

    def test_rv_combo_de_antes_del_cambio_se_cura_al_actualizar_precios(self):
        """Un combo armado antes de subir esto (sin la marca) en una cotización abierta durante la campaña."""
        orden = self.orden(productos=[self.cama_king, self.colchon_king])
        orden.order_line.sudo().with_context(**{SIN_RECALCULAR: True}).write({'dcasa_combo_sin_campana': False})
        orden.with_user(self.vendedora).action_update_prices()
        self.assertEqual(sorted(orden.order_line.mapped('price_unit')), [COMBO_KING, 400.0])
        self.assertTrue(all(orden.order_line.mapped('dcasa_combo_sin_campana')))
