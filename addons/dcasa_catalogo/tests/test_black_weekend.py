import json
import re

from odoo.addons.dcasa_catalogo.catalogo import (
    BLACK_WEEKEND,
    atributo_tamano,
    corregir_nombres,
    leer_catalogo,
    marcar_black_weekend,
)
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_open


@tagged('post_install', '-at_install')
class TestBlackWeekendCatalogo(TransactionCase):
    """La carga marca los 12 productos de Black Weekend por su código, sin tocar precios."""

    def _producto(self, codigo):
        variante = self.env['product.product'].with_context(active_test=False).search(
            [('default_code', '=', codigo)], limit=1)
        self.assertTrue(variante, f'{codigo} debe estar en el catálogo')
        return variante

    def test_doce_codigos_marcados_en_su_orden(self):
        self.assertEqual(len(BLACK_WEEKEND), 12)
        marcar_black_weekend(self.env)
        for orden, (codigo, _grafica) in enumerate(BLACK_WEEKEND, start=1):
            producto = self._producto(codigo).product_tmpl_id
            self.assertTrue(producto.dcasa_black_weekend, codigo)
            self.assertEqual(producto.dcasa_bw_orden, orden * 10, codigo)

    def test_908k_con_la_variante_negra_destacada(self):
        marcar_black_weekend(self.env)
        negra = self._producto('908K-NEGRO')
        self.assertEqual(negra.product_tmpl_id.dcasa_bw_variante_id, negra)
        self.assertFalse(self._producto('888K').product_tmpl_id.dcasa_bw_variante_id,
                         'Sin colores no hace falta variante destacada')

    def test_y0300300_es_el_del_pedido_no_el_anterior(self):
        marcar_black_weekend(self.env)
        self.assertTrue(self._producto('Y0300300-LTSC07').product_tmpl_id.dcasa_black_weekend)
        self.assertFalse(self._producto('Y0300300').product_tmpl_id.dcasa_black_weekend,
                         'El Y0300300 de $159.99 no es el de la promoción')

    def test_hk_bf_022_k_es_queen(self):
        """La dueña (2026-10-02): la «Base Queen» de 153.png es Queen aunque el Excel dijera King."""
        variante = self._producto('HK-BF-022-N-K-1-W')
        producto = variante.product_tmpl_id
        self.assertEqual(producto.name, 'Cama tapizada Queen – blanco')
        self.assertEqual(variante.product_template_attribute_value_ids.name, 'Queen')
        self.assertTrue(variante.active)

    def test_corregir_nombres_lleva_lo_cargado_como_king_a_queen(self):
        _atributo, valores = atributo_tamano(self.env)
        producto = self._producto('HK-BF-022-N-K-1-W').product_tmpl_id
        # Como lo dejó la carga anterior (19.0.1.3.0): King.
        producto.name = 'Cama tapizada King – blanco'
        linea = producto.attribute_line_ids.filtered(lambda lin: lin.attribute_id.name == 'Tamaño')
        linea.value_ids = [(6, 0, valores['King'].ids)]
        producto.product_variant_ids.default_code = 'HK-BF-022-N-K-1-W'
        precio = producto.list_price

        self.assertEqual(corregir_nombres(self.env), 1)
        self.assertEqual(corregir_nombres(self.env), 0, 'Idempotente')
        self.assertEqual(producto.name, 'Cama tapizada Queen – blanco')
        activa = producto.product_variant_ids
        self.assertEqual(len(activa), 1)
        self.assertEqual(activa.product_template_attribute_value_ids.name, 'Queen')
        self.assertEqual(activa.default_code, 'HK-BF-022-N-K-1-W')
        self.assertEqual(producto.list_price, precio)

    def test_corregir_nombres_respeta_lo_que_edito_la_duena(self):
        producto = self._producto('HK-BF-022-N-K-1-W').product_tmpl_id
        producto.name = 'Base Queen blanca'
        corregir_nombres(self.env)
        self.assertEqual(producto.name, 'Base Queen blanca')

    def test_idempotente_y_sin_tocar_precios(self):
        marcar_black_weekend(self.env)
        Plantilla = self.env['product.template']
        marcados = Plantilla.search([('dcasa_black_weekend', '=', True)])
        antes = {p.id: (p.list_price, p.write_date, p.dcasa_bw_orden) for p in marcados}
        self.assertEqual(marcar_black_weekend(self.env), 12)
        self.assertEqual(Plantilla.search([('dcasa_black_weekend', '=', True)]), marcados)
        self.assertEqual({p.id: (p.list_price, p.write_date, p.dcasa_bw_orden) for p in marcados}, antes,
                         'La segunda vez no escribe nada')

    def test_precio_del_catalogo_igual_a_la_grafica(self):
        """Las gráficas de la dueña traen el mismo precio que el Excel LTSC-07 (cama sola y combo)."""
        graficas = {  # cifras leídas de up media/<gráfica> (revisión del 2026-10-02)
            '888K': (259.99, 469.99), '908K-NEGRO': (229.99, 439.99), '803K': (179.99, 389.99),
            '809Q': (139.99, 298.99), '822F': (99.99, 186.99), '825K': (159.99, 369.99),
            '6220Q': (129.99, 288.99), '6877F': (99.99, 186.99), 'Y0200100': (129.99, 288.99),
            'Y0300300-LTSC07': (129.99, 288.99), 'HK-BF-022-N-K-1-W': (159.99, 369.99),
            'N-F10018-Q-BK': (69.99, 228.99),
        }
        catalogo = {i['codigo']: i for i in leer_catalogo()}
        for codigo, (cama, combo) in graficas.items():
            item = catalogo[codigo.removesuffix('-NEGRO')]
            self.assertEqual(min(item['precios'].values()), cama, codigo)
            self.assertTrue(item['combo'].endswith(f'${combo:.2f}'), codigo)
            self.assertEqual(self._producto(codigo).lst_price, cama, codigo)

    def test_las_graficas_no_van_en_la_imagen(self):
        """Las gráficas originales se quedan en «up media» (fuente): .dockerignore la excluye."""
        with file_open('dcasa_catalogo/data/catalogo.json', 'rb') as archivo:
            fotos = {f for i in json.load(archivo) for f in i['fotos']}
        for _codigo, grafica in BLACK_WEEKEND:
            self.assertNotIn(grafica, fotos)


@tagged('post_install', '-at_install')
class TestBlackWeekendWeb(HttpCase):
    """/black-weekend con los productos reales: precio y combo del catálogo, código en WhatsApp."""

    def setUp(self):
        super().setUp()
        marcar_black_weekend(self.env)
        self.env['ir.config_parameter'].sudo().set_param('dcasa_black_weekend.activo', '1')

    def test_pagina_con_precio_y_combo_del_catalogo(self):
        html = self.url_open('/black-weekend').text
        self.assertRegex(html, r'259[.,]99')
        self.assertIn('Combo con colchón First Class', html)
        self.assertRegex(html, r'469[.,]99')
        self.assertIn('908K-NEGRO', html, 'La 908K sale en negro')
        self.assertIn('c%C3%B3digo%20888K', html)
        self.assertIn('Y0300300-LTSC07', html)
        self.assertNotIn('Código Y0300300<', html, 'No el Y0300300 anterior de $159.99')
        visible = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S).lower()
        for palabra in ('tafi', 'tiempo limitado', 'remate', 'cuotas'):
            self.assertNotIn(palabra, visible)

    def test_cambio_de_precio_se_ve(self):
        cama = self.env['product.product'].search([('default_code', '=', '888K')]).product_tmpl_id
        cama.list_price = 249.5
        html = self.url_open('/black-weekend').text
        self.assertRegex(html, r'249[.,]50')
        self.assertNotRegex(html, r'259[.,]99')
