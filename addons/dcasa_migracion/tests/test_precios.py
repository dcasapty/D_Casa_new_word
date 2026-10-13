"""Precios de proveedor: se enlazan por el número del proveedor y el código (o el nombre) del producto; no se repiten ni
se pisan."""
from odoo.addons.dcasa_migracion import contactos as C
from odoo.addons.dcasa_migracion import precios as P
from odoo.addons.dcasa_migracion import reglas
from odoo.tests import TransactionCase, tagged

from . import ejemplos


@tagged('post_install', '-at_install')
class TestPreciosDeProveedor(TransactionCase):

    def setUp(self):
        super().setUp()
        proveedores, _ = reglas.filas_proveedores(ejemplos.PROVEEDORES)
        C.cargar_proveedores(self.env, proveedores)
        Producto = self.env['product.template']
        self.p1 = Producto.create({'name': 'Producto de Prueba 1', 'default_code': 'PRUEBA-001', 'type': 'consu'})
        self.p2 = Producto.create({'name': 'Producto de Prueba 2', 'default_code': 'PRUEBA-002', 'type': 'consu'})
        self.p3 = Producto.create({'name': 'Producto de Prueba 3', 'default_code': 'PRUEBA-003', 'type': 'consu'})
        self.p4 = Producto.create({'name': 'Producto de Prueba 4', 'type': 'consu'})  # sin código
        self.p5 = Producto.create({'name': 'Producto de Prueba 5', 'default_code': 'PRUEBA-005', 'type': 'consu'})

    def _proveedor(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}')

    def _cargar(self, texto=ejemplos.PRECIOS):
        filas, errores = reglas.filas_precios_proveedor(texto)
        assert not errores
        return P.cargar_precios_proveedor(self.env, filas)

    def test_los_cinco_ejemplos_de_la_receta(self):
        resumen = self._cargar()
        self.assertEqual(resumen['creados'], [(70001, 'PRUEBA-001'), (70001, 'PRUEBA-002'), (70002, 'PRUEBA-003'),
                                              (70005, 'PRUEBA-005')])
        self.assertEqual(resumen['omitidos'], [(70004, 'Producto de Prueba 4')], 'Precio 0: no se registró')
        self.assertEqual(resumen['con_error'], [])
        info = self.p1.seller_ids
        self.assertEqual((info.partner_id, info.price, info.min_qty), (self._proveedor(70001), 85.5, 1.0))
        self.assertEqual(self.p3.seller_ids.price, 140.0)
        self.assertFalse(self.p4.seller_ids)

    def test_sin_codigo_se_busca_por_el_nombre_exacto(self):
        resumen = self._cargar('id_proveedor_viejo,codigo_producto,nombre_producto,precio\n'
                               '70004,,Producto de Prueba 4,30\n70004,,No Hay Tal Producto,30\n')
        self.assertEqual(resumen['creados'], [(70004, 'Producto de Prueba 4')])
        self.assertEqual(self.p4.seller_ids.price, 30.0)
        self.assertEqual([m for _i, _p, m in resumen['con_error']],
                         ['no hay un solo producto con ese nombre: carga primero los productos'])

    def test_descuento_plazo_vigencia_y_cantidad_minima(self):
        self._cargar('id_proveedor_viejo,codigo_producto,precio,cantidad_minima,descuento,plazo_entrega_dias,'
                     'vigente_desde,vigente_hasta\n70001,PRUEBA-001,80,10,5,15,2026-10-01,2026-12-31\n')
        info = self.p1.seller_ids
        self.assertEqual((info.price, info.min_qty, info.discount, info.delay), (80.0, 10.0, 5.0, 15))
        self.assertEqual((str(info.date_start), str(info.date_end)), ('2026-10-01', '2026-12-31'))

    def test_el_proveedor_o_el_producto_que_faltan_se_avisan(self):
        resumen = self._cargar('id_proveedor_viejo,codigo_producto,precio\n99999,PRUEBA-001,5\n70001,NO-EXISTE,5\n')
        motivos = {(i, p): m for i, p, m in resumen['con_error']}
        self.assertIn('carga primero proveedores.csv', motivos[(99999, 'PRUEBA-001')])
        self.assertIn('no hay un producto con ese código', motivos[(70001, 'NO-EXISTE')])

    def test_una_moneda_que_no_es_la_de_la_empresa(self):
        resumen = self._cargar('id_proveedor_viejo,codigo_producto,precio,moneda\n'
                               '70002,PRUEBA-001,500,CNY\n70002,PRUEBA-002,5,XXX\n')
        self.assertEqual(self.p1.seller_ids.currency_id, self.env.ref('base.CNY'))
        self.assertEqual([m for _i, _p, m in resumen['con_error']], ['no conozco la moneda XXX'])

    def test_volver_a_cargar_no_repite_ni_pisa_un_precio_cambiado(self):
        self._cargar()
        self.p1.seller_ids.price = 99.0
        segunda = self._cargar()
        self.assertEqual(segunda['creados'], [])
        self.assertEqual(len(segunda['ya_estaban']), 4)
        self.assertEqual(self.p1.seller_ids.price, 99.0)
        self.assertEqual(len(self.p1.seller_ids), 1)

    def test_una_medida_de_un_producto_con_variantes_queda_en_esa_medida(self):
        atributo = self.env['product.attribute'].create({
            'name': 'Medida de prueba', 'value_ids': [(0, 0, {'name': 'Chica'}), (0, 0, {'name': 'Grande'})]})
        linea = {'attribute_id': atributo.id, 'value_ids': [(6, 0, atributo.value_ids.ids)]}
        mesa = self.env['product.template'].create({
            'name': 'Mesa con medidas', 'type': 'consu', 'attribute_line_ids': [(0, 0, linea)]})
        chica, grande = mesa.product_variant_ids
        chica.default_code, grande.default_code = 'MED-CHICA', 'MED-GRANDE'
        resumen = self._cargar('id_proveedor_viejo,codigo_producto,precio\n70001,MED-GRANDE,50\n')
        self.assertEqual(resumen['creados'], [(70001, 'MED-GRANDE')])
        self.assertEqual(mesa.seller_ids.product_id, grande)
