"""La carga de productos y existencias: usa las reglas del inventario anterior de dcasa_catalogo."""
from odoo.addons.dcasa_migracion import catalogo as K
from odoo.tests import TransactionCase, tagged

from . import ejemplos


@tagged('post_install', '-at_install')
class TestCargaDeCatalogo(TransactionCase):

    def setUp(self):
        super().setUp()
        company = self.env.ref('base.main_company')
        self.ubicacion = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1).lot_stock_id
        self.existente = self.env['product.template'].create({
            'name': 'PRODUCTO QUE YA EXISTÍA', 'default_code': 'PRUEBA-001', 'type': 'consu', 'is_storable': True,
            'list_price': 100.0, 'standard_price': 50.0})
        self._poner_stock(self.existente.product_variant_id, 5)

    def _poner_stock(self, variante, cantidad):
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': variante.id, 'location_id': self.ubicacion.id, 'inventory_quantity': cantidad,
        })._apply_inventory()

    def _stock(self, variante):
        return variante.with_context(location=self.ubicacion.id).qty_available

    def _producto(self, codigo):
        return self.env['product.product'].with_context(active_test=False).search([('default_code', '=', codigo)])

    def test_un_producto_que_ya_existe_solo_cambia_de_existencias(self):
        resumen, avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        variante = self.existente.product_variant_id
        self.assertEqual(self._stock(variante), 12)
        self.assertEqual((self.existente.list_price, variante.standard_price), (100.0, 50.0),
                         'Por defecto no se pisan el precio ni el costo de lo que ya existe')
        self.assertEqual(self.existente.name, 'PRODUCTO QUE YA EXISTÍA')
        self.assertIn('PRUEBA-001', resumen['actualizados'])
        self.assertEqual(avisos['archivados'], 1)

    def test_con_la_casilla_tambien_cambian_precio_y_costo(self):
        K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO, actualizar_precios=True)
        self.assertEqual(self.existente.list_price, 199.99)
        self.assertEqual(self.existente.product_variant_id.standard_price, 120.0)

    def test_los_productos_nuevos_entran_con_sus_existencias(self):
        resumen, _avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        dos = self._producto('PRUEBA-002')
        self.assertEqual((dos.lst_price, dos.standard_price, self._stock(dos)), (45.5, 28.75, 3))
        self.assertTrue(dos.is_storable)
        combo = self._producto('PRUEBA-005')
        self.assertEqual(self._stock(combo), 2, 'Se venden unidades enteras: 1.5 se redondea')
        self.assertIn('PRUEBA-002', resumen['creados'])

    def test_sin_codigo_la_llave_es_el_nombre_y_no_se_le_toca_la_existencia(self):
        resumen, avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        self.assertIn('Producto de Prueba 3', resumen['creados'])
        plantilla = self.env['product.template'].search([('name', '=ilike', 'Producto de Prueba 3')])
        self.assertEqual(plantilla.list_price, 89.0)
        self.assertEqual(self._stock(plantilla.product_variant_id), 0)
        self.assertEqual(avisos['sin_codigo'], ['Producto de Prueba 3'])
        self.assertEqual(avisos['existencias_sin_codigo'], [7.0])

    def test_un_producto_archivado_no_se_crea_y_sus_existencias_se_avisan(self):
        _resumen, avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        self.assertFalse(self._producto('PRUEBA-004'))
        self.assertEqual(avisos['huerfanos'], [('PRUEBA-004', -2.0)])

    def test_existencia_negativa_entra_en_cero_y_se_lista(self):
        productos = 'codigo,nombre,activo\nPRUEBA-001,PRODUCTO QUE YA EXISTÍA,si\n'
        resumen, _avisos = K.cargar_catalogo(self.env, productos, 'codigo_producto,cantidad\nPRUEBA-001,-4\n')
        self.assertEqual(resumen['negativos'], ['PRUEBA-001'])
        self.assertEqual(self._stock(self.existente.product_variant_id), 0)

    def test_las_existencias_con_decimales_se_redondean_y_se_avisan(self):
        _resumen, avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        self.assertEqual(avisos['decimales'], [('PRUEBA-005', 1.5)])

    def test_sin_inventario_no_se_toca_ninguna_existencia(self):
        K.cargar_catalogo(self.env, ejemplos.PRODUCTOS)
        self.assertEqual(self._stock(self.existente.product_variant_id), 5)

    def test_volver_a_cargar_no_cambia_nada(self):
        K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        total = self.env['product.template'].with_context(active_test=False).search_count([])
        resumen, _avisos = K.cargar_catalogo(self.env, ejemplos.PRODUCTOS, ejemplos.INVENTARIO)
        self.assertEqual(resumen['creados'], [])
        self.assertEqual(resumen['actualizados'], [])
        self.assertEqual(self.env['product.template'].with_context(active_test=False).search_count([]), total)
