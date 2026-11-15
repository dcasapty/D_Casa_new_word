"""Tarjetas de la portada (v3, aprobada por la dueña el 2026-11-15): «Quedan pocas» o «Agotado» sobre la foto, con la
misma regla y las mismas palabras que la ficha (``_dcasa_disponibilidad_ficha``), nunca el número. «Disponible» no se
pinta. La etiqueta va después del nombre en el HTML (el lector de pantalla dice primero qué es)."""
from lxml import html as lhtml

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestDisponibilidadEnLaPortada(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Plantilla = cls.env['product.template']
        base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
                'allow_out_of_stock_order': True, 'list_price': 89.99}
        # Primero en «Lo más buscado» (website_sequence más bajo que el catálogo).
        cls.muchas = Plantilla.create({**base, 'name': 'ZZPORTADA CON MUCHAS', 'website_sequence': -6000})
        cls.pocas = Plantilla.create({**base, 'name': 'ZZPORTADA CON POCAS', 'website_sequence': -5999})
        cls.agotada = Plantilla.create({**base, 'name': 'ZZPORTADA AGOTADA', 'website_sequence': -5998})
        ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        for plantilla, cantidad in ((cls.muchas, 12), (cls.pocas, 2)):
            cls.env['stock.quant']._update_available_quantity(plantilla.product_variant_id, ubicacion, cantidad)

    def test_quedan_pocas_y_agotado_sobre_la_foto_y_nunca_el_numero(self):
        arbol = lhtml.fromstring(self.url_open('/').text)
        for plantilla, estado, texto in ((self.muchas, None, None),
                                         (self.pocas, 'pocas', 'Quedan pocas'),
                                         (self.agotada, 'agotado', 'Agotado')):
            with self.subTest(producto=plantilla.name):
                tarjetas = arbol.xpath(
                    f'//article[contains(@class, "o_dcasa_pcard")][.//h3/a[@href="{plantilla.website_url}"]]')
                self.assertTrue(tarjetas, f'la portada no trae la tarjeta de {plantilla.name}')
                etiquetas = tarjetas[0].xpath('.//p[contains(@class, "o_dcasa_pcard_estado")]')
                if estado is None:
                    self.assertFalse(etiquetas, '«Disponible» no se pinta')
                    continue
                self.assertEqual(len(etiquetas), 1)
                etiqueta = etiquetas[0]
                self.assertEqual(etiqueta.get('data-estado'), estado)
                self.assertEqual(etiqueta.text_content().strip(), texto)
                self.assertNotRegex(etiqueta.text_content(), r'\d', 'nunca el número de existencias')
                anterior = etiqueta.getprevious()
                self.assertEqual(anterior.tag, 'h3', 'va después del nombre')
