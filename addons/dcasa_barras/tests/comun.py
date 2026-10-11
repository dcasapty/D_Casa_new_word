"""Productos y usuarios de prueba (todo inventado) para el lector de códigos de barras."""
from odoo.tests import TransactionCase, new_test_user


class BarrasCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.almacen = cls.env.ref('stock.warehouse0')
        cls.bodega = cls.almacen.lot_stock_id
        cls.Quant = cls.env['stock.quant']
        cls.Barras = cls.env['dcasa.barras']
        # Gerencia administra Inventario y Productos; la Vendedora solo usa Inventario; el tercero no tiene nada de él.
        cls.gerencia = new_test_user(
            cls.env, login='barras_gerencia', groups='stock.group_stock_manager,product.group_product_manager')
        cls.solo_inventario = new_test_user(cls.env, login='barras_inventario', groups='stock.group_stock_manager')
        cls.vendedora = new_test_user(cls.env, login='barras_vendedora', groups='stock.group_stock_user')
        cls.sin_inventario = new_test_user(cls.env, login='barras_nada', groups='base.group_user')
        cls.cama = cls.producto('Zzcama de prueba', 'ZZT-CAMA-1', precio=349.99, costo=77.77, unidades=12)
        cls.zapatera = cls.producto(
            'Zzzapatera de prueba', 'ZZT-ZAP-1', barcode='7501234567890', precio=89.5, unidades=0)

    @classmethod
    def producto(cls, nombre, referencia=False, barcode=False, precio=10.0, costo=1.0, unidades=0, **extra):
        producto = cls.env['product.product'].create({
            'name': nombre, 'default_code': referencia, 'barcode': barcode, 'type': 'consu', 'is_storable': True,
            'list_price': precio, 'standard_price': costo, **extra})
        if unidades:
            cls.Quant._update_available_quantity(producto, cls.bodega, unidades)
        return producto

    def como(self, usuario):
        return self.Barras.with_user(usuario)

    def existencia(self, producto, ubicacion=None):
        ubicacion = ubicacion or self.bodega
        return sum(self.Quant.search([('product_id', '=', producto.id), ('location_id', '=', ubicacion.id)])
                   .mapped('quantity'))
