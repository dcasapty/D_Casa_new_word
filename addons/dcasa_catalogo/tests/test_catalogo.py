from odoo.addons.dcasa_catalogo.catalogo import cargar_catalogo, leer_catalogo, xmlid_de
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCatalogo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catalogo = leer_catalogo()
        cls.por_codigo = {item['codigo']: item for item in cls.catalogo}

    def producto(self, codigo):
        return self.env.ref(f'dcasa_catalogo.{xmlid_de(codigo)}')

    def test_todos_los_codigos_cargados(self):
        for item in self.catalogo:
            producto = self.producto(item['codigo'])
            self.assertEqual(producto.name, item['nombre'])
            self.assertTrue(producto.is_storable, 'Va al inventario')
            self.assertTrue(producto.allow_out_of_stock_order, 'Existencias sin confirmar: se vende igual')

    def test_precio_con_itbms_igual_al_excel(self):
        """El precio del Excel es el precio final: el impuesto va incluido, la cifra no cambia."""
        item = next(i for i in self.catalogo if len(i['precios']) == 1)
        producto = self.producto(item['codigo'])
        precio = item['precios']['']
        self.assertEqual(producto.list_price, precio)
        self.assertEqual(producto.default_code, item['codigo'])
        impuesto = producto.taxes_id
        self.assertTrue(impuesto.price_include)
        self.assertEqual(impuesto.amount, 7)
        total = impuesto.compute_all(precio, product=producto.product_variant_id)
        self.assertAlmostEqual(total['total_included'], precio, places=2)
        self.assertAlmostEqual(total['total_excluded'], round(precio / 1.07, 2), places=2)
        website = self.env['website'].get_current_website()
        self.assertEqual(website.show_line_subtotals_tax_selection, 'tax_included')

    def test_tamanos_como_variantes(self):
        item = next(i for i in self.catalogo if len(i['precios']) > 1)
        producto = self.producto(item['codigo'])
        self.assertEqual(producto.product_variant_count, len(item['precios']))
        for variante in producto.product_variant_ids:
            tamano = variante.product_template_attribute_value_ids.name
            self.assertEqual(variante.lst_price, item['precios'][tamano])
            self.assertEqual(variante.default_code, f"{item['codigo']}-{tamano.upper()}")

    def test_fotos_y_publicacion(self):
        con_fotos = next(i for i in self.catalogo if len(i['fotos']) > 1)
        producto = self.producto(con_fotos['codigo'])
        self.assertTrue(producto.image_1920)
        self.assertEqual(len(producto.product_template_image_ids), len(con_fotos['fotos']) - 1)
        self.assertTrue(producto.is_published)
        self.assertEqual(producto.public_categ_ids,
                         self.env.ref(f"website_dcasa.public_category_{con_fotos['categoria']}"))

        sin_fotos = next(i for i in self.catalogo if not i['fotos'])
        producto = self.producto(sin_fotos['codigo'])
        self.assertFalse(producto.is_published, 'Sin foto no sale en la web')
        self.assertFalse(producto.image_1920)

    def test_combo_en_la_ficha(self):
        item = next(i for i in self.catalogo if i.get('combo'))
        self.assertIn(item['combo'], str(self.producto(item['codigo']).description_ecommerce))

    def test_idempotente_y_respeta_cambios(self):
        item = self.catalogo[0]
        producto = self.producto(item['codigo'])
        producto.list_price = 1  # la dueña lo cambió en Odoo
        antes = self.env['product.template'].search_count([])
        self.assertEqual(cargar_catalogo(self.env), 0)
        self.assertEqual(self.env['product.template'].search_count([]), antes)
        self.assertEqual(producto.list_price, 1)

    def test_vuelve_a_crear_lo_que_falta(self):
        item = self.catalogo[0]
        self.producto(item['codigo']).unlink()
        self.assertEqual(cargar_catalogo(self.env), 1)
        self.assertEqual(self.producto(item['codigo']).name, item['nombre'])
