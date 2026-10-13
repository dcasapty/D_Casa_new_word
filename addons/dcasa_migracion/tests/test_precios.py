"""Precios de proveedor: se enlazan por el número del proveedor y el código del producto; no se repiten ni se pisan."""
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
        self.uno = Producto.create({'name': 'Producto Uno', 'default_code': 'PRUEBA-001', 'type': 'consu'})
        self.dos = Producto.create({'name': 'Producto Dos', 'default_code': 'PRUEBA-002', 'type': 'consu'})

    def _proveedor(self, id_viejo):
        return self.env.ref(f'__import__.{C.xmlid_contacto(id_viejo)}')

    def _cargar(self, texto=ejemplos.PRECIOS):
        filas, errores = reglas.filas_precios_proveedor(texto)
        assert not errores
        return P.cargar_precios_proveedor(self.env, filas)

    def test_crea_los_precios_y_avisa_lo_que_no_pudo(self):
        resumen = self._cargar()
        self.assertEqual(resumen['creados'], [(70001, 'PRUEBA-001'), (70001, 'PRUEBA-002'), (70003, 'PRUEBA-001')])
        motivos = {(i, c): m for i, c, m in resumen['con_error']}
        self.assertIn('no hay un producto con ese código', motivos[(70001, 'NO-EXISTE')])
        self.assertIn('carga primero proveedores.csv', motivos[(99999, 'PRUEBA-002')])
        info = self.uno.seller_ids.filtered(lambda s: s.partner_id == self._proveedor(70001))
        self.assertEqual((info.price, info.min_qty), (80.5, 1.0))
        self.assertEqual(sorted(self.uno.seller_ids.mapped('price')), [80.5, 82.0])
        dos = self.dos.seller_ids
        self.assertEqual((dos.price, dos.min_qty), (20.0, 10.0))

    def test_volver_a_cargar_no_repite_ni_pisa_un_precio_cambiado(self):
        self._cargar()
        self.uno.seller_ids.filtered(lambda s: s.partner_id == self._proveedor(70001)).price = 99.0
        segunda = self._cargar()
        self.assertEqual(segunda['creados'], [])
        self.assertEqual(len(segunda['ya_estaban']), 3)
        self.assertEqual(len(self.uno.seller_ids), 2)
        self.assertIn(99.0, self.uno.seller_ids.mapped('price'))

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
