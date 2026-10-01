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
            self.assertEqual(producto.name, item['nombre_web'])
            self.assertTrue(producto.is_storable, 'Va al inventario')
            self.assertTrue(producto.allow_out_of_stock_order, 'Existencias sin confirmar: se vende igual')

    def test_precio_del_excel_sin_itbms(self):
        """El precio del Excel es SIN ITBMS («+ITBMS»): list_price = la cifra, y el 7 % se suma."""
        item = next(i for i in self.catalogo if len(i['precios']) == 1)
        producto = self.producto(item['codigo'])
        precio = item['precios']['']
        self.assertEqual(producto.list_price, precio)
        self.assertEqual(producto.default_code, item['codigo'])
        impuesto = producto.taxes_id
        self.assertEqual(impuesto, self.env.ref('base.main_company').account_sale_tax_id, 'El impuesto por defecto')
        self.assertFalse(impuesto.price_include)
        self.assertEqual(impuesto.amount, 7)
        total = impuesto.compute_all(precio, product=producto.product_variant_id)
        self.assertAlmostEqual(total['total_excluded'], precio, places=2)
        self.assertAlmostEqual(total['total_included'], round(precio * 1.07, 2), places=2)
        website = self.env['website'].get_current_website()
        self.assertEqual(website.show_line_subtotals_tax_selection, 'tax_excluded')

    def test_venta_de_39_99_suma_el_itbms(self):
        """Producto del catálogo a $39.99 → subtotal 39.99, ITBMS 2.80, total 42.79."""
        item = next(i for i in self.catalogo if i['precios'] == {'': 39.99})
        orden = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Cliente'}).id,
            'order_line': [(0, 0, {'product_id': self.producto(item['codigo']).product_variant_id.id})],
        })
        linea = orden.order_line
        self.assertAlmostEqual(linea.price_unit, 39.99, places=2)
        self.assertAlmostEqual(linea.price_subtotal, 39.99, places=2)
        self.assertAlmostEqual(linea.price_tax, 2.80, places=2)
        self.assertAlmostEqual(linea.price_total, 42.79, places=2)
        self.assertAlmostEqual(orden.amount_total, 42.79, places=2)

    def test_migracion_pasa_del_incluido_al_que_se_suma(self):
        """Bases cargadas con «ITBMS 7% incluido»: cambia el impuesto, no el precio."""
        from odoo.addons.dcasa_catalogo.catalogo import pasar_a_itbms_que_se_suma
        company = self.env.ref('base.main_company')
        venta = company.account_sale_tax_id
        incluido = venta.copy({'name': 'ITBMS 7% incluido', 'price_include_override': 'tax_included'})
        con_variantes = next(i for i in self.catalogo if len(i['precios']) > 1)
        viejo = self.producto(self.catalogo[0]['codigo']) | self.producto(con_variantes['codigo'])
        a_mano = self.producto(self.catalogo[1]['codigo'])
        exento = self.env['account.tax'].create({'name': 'Exento prueba', 'amount': 0, 'type_tax_use': 'sale'})
        viejo.taxes_id = incluido
        a_mano.taxes_id = exento  # la dueña le puso otro impuesto: no se toca
        precios = {p: (p.list_price, p.product_variant_ids.mapped('lst_price')) for p in viejo | a_mano}
        self.env['website'].search([]).show_line_subtotals_tax_selection = 'tax_included'

        self.assertEqual(pasar_a_itbms_que_se_suma(self.env), 2)
        self.assertEqual(viejo.taxes_id, venta)
        self.assertEqual(a_mano.taxes_id, exento)
        for producto, (lista, variantes) in precios.items():
            self.assertEqual(producto.list_price, lista, 'El precio del Excel no cambia')
            self.assertEqual(producto.product_variant_ids.mapped('lst_price'), variantes)
        self.assertFalse(incluido.active, 'Sin uso: archivado')
        self.assertEqual(self.env['website'].get_current_website().show_line_subtotals_tax_selection, 'tax_excluded')
        self.assertEqual(pasar_a_itbms_que_se_suma(self.env), 0, 'Se puede repetir')

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

    def test_combo_y_medidas_con_su_etiqueta(self):
        item = next(i for i in self.catalogo if i.get('combo') and i.get('medidas') and i['fotos'])
        producto = self.producto(item['codigo'])
        self.assertEqual(producto.dcasa_combo, item['combo'])
        self.assertEqual(producto.dcasa_medidas, item['medidas'])
        self.assertFalse(producto.description_ecommerce, 'El combo ya no se mezcla con la descripción')

    def test_nombres_distintos(self):
        """Ni el cliente ni la vendedora deben ver dos productos con el mismo nombre."""
        nombres = [self.producto(i['codigo']).name.lower() for i in self.catalogo]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_cama_de_un_tamano_filtra_por_tamano(self):
        item = next(i for i in self.catalogo if i['nombre'] == 'Cama king' and len(i['precios']) == 1)
        producto = self.producto(item['codigo'])
        self.assertEqual(producto.product_variant_count, 1)
        self.assertEqual(producto.attribute_line_ids.value_ids.name, 'King')
        self.assertEqual(producto.default_code, item['codigo'])

    def test_muebles_de_tv_en_su_categoria(self):
        item = next(i for i in self.catalogo if i['nombre'] == 'Mueble de TV')
        self.assertEqual(self.producto(item['codigo']).public_categ_ids,
                         self.env.ref('dcasa_catalogo.public_category_muebles_tv'))

    def test_busqueda_por_varias_palabras(self):
        item = next(i for i in self.catalogo if 'Queen' in i['precios'] and i['nombre'].lower().startswith('colch'))
        encontrados = self.env['product.product'].search([('display_name', 'ilike', 'colchón queen')])
        esperado = self.producto(item['codigo']).product_variant_ids.filtered(
            lambda v: v.product_template_attribute_value_ids.name == 'Queen')
        self.assertIn(esperado, encontrados)
        tamanos = encontrados.product_template_attribute_value_ids.mapped('name')
        self.assertNotIn('King', tamanos)

    def test_cotizacion_por_whatsapp(self):
        cliente = self.env['res.partner'].create({'name': 'Ana Pérez', 'phone': '6123-4567'})
        orden = self.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [(0, 0, {'product_id': self.producto(self.catalogo[0]['codigo']).product_variant_id.id})],
        })
        accion = orden.action_dcasa_whatsapp()
        self.assertTrue(accion['url'].startswith('https://wa.me/50761234567?text='))
        self.assertIn(orden.name, accion['url'])
        self.assertEqual(orden.state, 'sent')

    def test_actualizar_no_pisa_cambios(self):
        from odoo.addons.dcasa_catalogo.catalogo import actualizar_catalogo
        item = self.catalogo[0]
        producto = self.producto(item['codigo'])
        producto.name = 'Nombre de la dueña'
        actualizar_catalogo(self.env)
        self.assertEqual(producto.name, 'Nombre de la dueña')

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
        self.assertEqual(self.producto(item['codigo']).name, item['nombre_web'])


@tagged('post_install', '-at_install')
class TestBuscarProductos(TransactionCase):

    def test_filtros_rapidos_y_categorias(self):
        vista = self.env['product.template'].get_view(
            self.env.ref('product.product_template_search_view').id, 'search')
        arch = vista['arch']
        for nombre in ('dcasa_disponibles', 'dcasa_agotados', 'dcasa_precio_1', 'dcasa_precio_4', 'dcasa_en_web'):
            self.assertIn(f'name="{nombre}"', arch)
        self.assertIn('<searchpanel', arch)
        self.assertIn('public_categ_ids', arch)
        # Los dominios funcionan de verdad (campos buscables).
        Producto = self.env['product.template']
        barato = Producto.create({'name': 'Banco de prueba', 'list_price': 50, 'is_storable': True})
        caro = Producto.create({'name': 'Sofá de prueba', 'list_price': 900, 'is_storable': True})
        self.assertIn(barato, Producto.search([('list_price', '<=', 100)]))
        self.assertNotIn(caro, Producto.search([('list_price', '<=', 100)]))
        self.assertIn(caro, Producto.search([('is_storable', '=', True), ('qty_available', '<=', 0)]))

