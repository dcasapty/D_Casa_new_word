from odoo.addons.dcasa_catalogo.catalogo import (
    PARAM_STOCK_PRUEBA,
    aplicar_stock_prueba,
    cargar_catalogo,
    leer_catalogo,
    xmlid_de,
)
from odoo.addons.dcasa_catalogo.inventario_anterior import leer_inventario_anterior
from odoo.addons.dcasa_catalogo.reglas import (
    asignar_foto,
    codigo_del_pedido,
    fila_para_comparar,
    precio_terminado_en_99,
)
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReglasPedido(TransactionCase):
    """Reglas sin Odoo: precio .99, código aparte y a qué fila va cada foto."""

    def test_precios_terminan_en_99(self):
        self.assertEqual(precio_terminado_en_99(318.66), 318.99)
        self.assertEqual(precio_terminado_en_99(318.65999999999997), 318.99, 'Así viene del Excel')
        self.assertEqual(precio_terminado_en_99(439.98), 439.99)
        self.assertEqual(precio_terminado_en_99(186.64), 186.99)
        self.assertEqual(precio_terminado_en_99(129.99), 129.99, 'Ya termina en .99: igual')
        self.assertEqual(precio_terminado_en_99(100), 100.99, 'Se conserva la parte entera')
        self.assertIsNone(precio_terminado_en_99(None), 'Celda vacía: no se inventa un precio')

    def test_codigo_que_ya_existe_va_aparte(self):
        self.assertEqual(codigo_del_pedido('Y0300300', {'Y0300300'}, 'LTSC07'), 'Y0300300-LTSC07')
        self.assertEqual(codigo_del_pedido('908K', {'Y0300300'}, 'LTSC07'), '908K')

    def filas(self):
        datos = [
            ('908K', 'Cama tapizada King – beige', '203 × 193 × 123 cm'),
            ('908K', 'Cama tapizada King – negro', '203 × 193 × 123 cm'),
            ('908K', 'Cama tapizada King – gris', '203 × 193 × 123 cm'),
            ('809Q', 'Cama tapizada Queen – beige', '213 × 158 × 120 cm'),
            ('811Q', 'Cama tapizada Queen – beige', '213 × 158 × 120 cm'),
            ('822F', 'Cama tapizada Full – blanco', '193 × 135 × 110 cm'),
            ('825Q', 'Cama tapizada Queen – crema', '205 × 151 × 110 cm'),
            ('HK-BF-022-N-F-1-W', 'Cama tapizada Full – blanco', 'Full'),
            ('Y0400300-Q', 'Cama tapizada Queen – tela negra', '205 × 151 × 110 cm'),
            ('Y0400400-Q', 'Cama tapizada Queen – tela marrón', '205 × 151 × 110 cm'),
        ]
        return [fila_para_comparar(*d) for d in datos]

    def test_foto_por_codigo(self):
        filas = self.filas()
        r = asignar_foto('908K Cama tapizada King – Gris 203 × 193 × 123 cm.jpg', filas)
        self.assertEqual((r['fila'], r['como']), (2, 'codigo'), 'Código con varios colores: manda el color')
        r = asignar_foto('HK-BF-022-N-F-1-W.jpg', filas)
        self.assertEqual((r['fila'], r['como']), (7, 'codigo'))
        r = asignar_foto('908K Cama tapizada King.jpg', filas)
        self.assertIsNone(r['fila'], 'Sin color no se sabe de cuál de los tres es')

    def test_foto_por_descripcion(self):
        filas = self.filas()
        r = asignar_foto('Cama tapizada Queen – crema 205 × 151 × 110 cm.jpg', filas)
        self.assertEqual((filas[r['fila']]['codigo'], r['como']), ('825Q', 'descripcion'))
        r = asignar_foto('Cama tapizada Full – blanco 193 × 135 × 110 cm.jpg', filas)
        self.assertEqual(filas[r['fila']]['codigo'], '822F', 'Las medidas descartan al Full blanco sin medidas')

    def test_foto_dudosa_no_se_adivina(self):
        filas = self.filas()
        archivo = 'Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg'
        r = asignar_foto(archivo, filas)
        self.assertEqual((r['fila'], r['como']), (None, 'ambigua'))
        self.assertIn('809Q', r['nota'])
        self.assertIn('811Q', r['nota'])
        r = asignar_foto(archivo, filas, {archivo: ('811Q', None, 'cabecero de canales')})
        self.assertEqual((filas[r['fila']]['codigo'], r['como']), ('811Q', 'decision'))
        self.assertEqual(asignar_foto('foto.jpg', filas)['como'], 'sin_coincidencia')

    def test_color_del_archivo_distinto_queda_avisado(self):
        filas = self.filas()
        archivo = 'Y0400300-Q  Queen tela marron205×151×110 cm.jpg'
        r = asignar_foto(archivo, filas)
        self.assertEqual(filas[r['fila']]['codigo'], 'Y0400300-Q')
        self.assertIn('marron', r['nota'], 'Se asigna por código, pero queda el aviso en el reporte')
        r = asignar_foto(archivo, filas, {archivo: ('Y0400400-Q', None, 'la cama es marrón')})
        self.assertEqual(filas[r['fila']]['codigo'], 'Y0400400-Q')


@tagged('post_install', '-at_install')
class TestPedidoLTSC07(TransactionCase):
    """Productos del pedido LTSC-07 en el inventario y en la web."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pedido = [i for i in leer_catalogo() if i.get('pedido') == 'LTSC-07']
        # El inventario del sistema anterior manda sobre el precio de los códigos que trae (regla de la dueña).
        cls.precio_inventario = {f['codigo']: f['precio'] for f in leer_inventario_anterior() if f['codigo']}

    def producto(self, codigo):
        return self.env.ref(f'dcasa_catalogo.{xmlid_de(codigo)}')

    def test_productos_creados_publicados_y_en_recamaras(self):
        self.assertEqual(len(self.pedido), 35)
        recamaras = self.env.ref('website_dcasa.public_category_recamaras')
        for item in self.pedido:
            producto = self.producto(item['codigo'])
            self.assertEqual(producto.list_price, self.precio_inventario.get(item['codigo'], item['precios']['']))
            self.assertEqual(round(item['precios'][''] * 100) % 100, 99, 'Todo precio del pedido termina en .99')
            self.assertEqual(producto.is_published, bool(item['fotos']), 'Con foto se publica')
            self.assertTrue(producto.image_1920)
            self.assertEqual(producto.public_categ_ids, recamaras)
            self.assertTrue(producto.is_storable)
            self.assertEqual(producto.dcasa_combo, item['combo'])
            self.assertTrue(producto.taxes_id and not producto.taxes_id.price_include, 'ITBMS que se suma')

    def test_combo_con_nombre_del_colchon_y_a_99(self):
        producto = self.producto('908Q')
        self.assertEqual(producto.dcasa_combo, 'Combo con colchón Dulce Sueños $318.99')
        self.assertEqual(self.producto('888K').dcasa_combo, 'Combo con colchón First Class $469.99')

    def test_908k_una_ficha_con_variantes_de_color(self):
        producto = self.producto('908K')
        self.assertEqual(producto.product_variant_count, 3)
        self.assertEqual(producto.list_price, 229.99)
        por_color = {
            v.product_template_attribute_value_ids.filtered(lambda a: a.attribute_id.name == 'Color').name: v
            for v in producto.product_variant_ids
        }
        self.assertEqual(set(por_color), {'Beige', 'Negro', 'Gris'})
        for color, variante in por_color.items():
            self.assertEqual(variante.lst_price, 229.99, 'El mismo precio en cada color')
            self.assertTrue(variante.image_variant_1920, f'{color} con su foto')
            self.assertEqual(variante.default_code, f'908K-{color.upper()}')
        self.assertEqual(len(por_color['Beige'].product_variant_image_ids), 2, 'El resto de fotos, a su galería')
        self.assertNotEqual(por_color['Negro'].image_variant_1920, por_color['Gris'].image_variant_1920)
        self.assertEqual(producto.attribute_line_ids.filtered(
            lambda linea: linea.attribute_id.name == 'Tamaño').value_ids.name, 'King')
        self.assertEqual(self.producto('908Q').product_variant_count, 2)

    def test_codigo_existente_no_se_toca_y_va_aparte(self):
        viejo = self.producto('Y0300300')
        self.assertEqual(viejo.list_price, 159.99, 'El producto que ya estaba conserva su precio')
        self.assertEqual(viejo.default_code, 'Y0300300')
        nuevo = self.producto('Y0300300-LTSC07')
        self.assertNotEqual(nuevo, viejo)
        self.assertEqual(nuevo.list_price, 129.99)
        self.assertEqual(nuevo.default_code, 'Y0300300-LTSC07')
        self.assertNotEqual(nuevo.image_1920, viejo.image_1920)
        self.assertNotIn('Y0300300', [i['codigo'] for i in self.pedido])
        codigos = self.env['product.product'].search([('default_code', '=', 'Y0300300')])
        self.assertEqual(codigos, viejo.product_variant_id, 'Una sola ficha con el código viejo')

    def test_no_duplica_un_codigo_que_ya_esta_en_odoo(self):
        """Si Brian ya creó el código desde el Excel del proveedor, la carga no lo duplica."""
        self.producto('6220Q').unlink()
        brian = self.env['product.template'].create({'name': 'Cama de Brian', 'default_code': '6220Q'})
        self.assertEqual(cargar_catalogo(self.env), 0)
        self.assertEqual(self.env['product.product'].search([('default_code', '=', '6220Q')]),
                         brian.product_variant_id)

    def test_stock_de_prueba(self):
        Producto = self.env['product.product']
        ubicacion = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.ref('base.main_company').id)], limit=1).lot_stock_id
        sin_nada = Producto.create({'name': 'Nuevo sin stock', 'is_storable': True})
        contado = Producto.create({'name': 'Contado', 'is_storable': True})
        vendido = Producto.create({'name': 'Vendido (0 con movimientos)', 'is_storable': True})
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)

        def contar(producto, cantidad):
            Quant.create({'product_id': producto.id, 'location_id': ubicacion.id,
                          'inventory_quantity': cantidad})._apply_inventory()

        contar(contado, 3)
        contar(vendido, 2)
        contar(vendido, 0)
        variante_908k = self.producto('908K').product_variant_ids[:1]

        parametros = self.env['ir.config_parameter'].sudo()
        parametros.set_param(PARAM_STOCK_PRUEBA, '0')
        self.assertEqual(aplicar_stock_prueba(self.env), 0, 'En 0 (producción) no hace nada')
        self.assertEqual(sin_nada.qty_available, 0)

        parametros.set_param(PARAM_STOCK_PRUEBA, '10')
        self.assertGreater(aplicar_stock_prueba(self.env), 0)
        self.env.invalidate_all()
        self.assertEqual(sin_nada.qty_available, 10)
        self.assertEqual(variante_908k.qty_available, 10, 'También los productos del catálogo')
        self.assertEqual(contado.qty_available, 3, 'Un conteo real no se pisa')
        self.assertEqual(vendido.qty_available, 0, 'Con movimientos no se toca')
        self.assertEqual(aplicar_stock_prueba(self.env), 0, 'Idempotente')
        self.assertEqual(sin_nada.qty_available, 10)
