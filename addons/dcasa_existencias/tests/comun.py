"""Datos de prueba de bodega: una Vendedora, Gerencia, un producto con costo y proveedor, y existencias."""
from odoo import Command
from odoo.tests import TransactionCase


def crear_usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'email': f'{login}@example.com',
        'group_ids': [Command.set([env.ref(g).id for g in ('base.group_user', *grupos)])],
    })


class BodegaComun(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'bodega_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'bodega_gerencia', 'dcasa_base.group_gerencia')
        cls.proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR DE PRUEBA BODEGA'})
        cls.producto = cls.env['product.product'].create({
            'name': 'SOFA DE PRUEBA BODEGA', 'default_code': 'ZZB-SOFA', 'is_storable': True, 'standard_price': 200.0,
            'list_price': 450.0, 'seller_ids': [Command.create({'partner_id': cls.proveedor.id, 'price': 200.0})]})
        cls.sin_costo = cls.env['product.product'].create({
            'name': 'SILLA SIN COSTO BODEGA', 'is_storable': True, 'standard_price': 0.0})
        cls.almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.ubicacion = cls.almacen.lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.producto, cls.ubicacion, 10)
        cls.env['stock.quant']._update_available_quantity(cls.sin_costo, cls.ubicacion, 3)
        cls.config = cls.env['dcasa.existencias.config']._de()
        Cuenta = cls.env['account.account']
        cls.c_mermas = Cuenta.create({'name': 'Mermas prueba', 'code': '9B0001', 'account_type': 'expense'})
        cls.c_contra = Cuenta.create({'name': 'Inventario prueba', 'code': '9B0002', 'account_type': 'asset_current'})
        cls.diario = cls.env['account.journal'].create({'name': 'Mermas prueba', 'code': 'MRP', 'type': 'general'})

    def _con_cuentas(self):
        self.config.write({'mermas_cuenta_gasto_id': self.c_mermas.id, 'mermas_cuenta_contra_id': self.c_contra.id,
                           'mermas_diario_id': self.diario.id})

    def _merma(self, usuario=None, cantidad=1, motivo='dano', producto=None, validar=True, **extra):
        Scrap = self.env['stock.scrap'].with_user(usuario or self.gerencia)
        scrap = Scrap.create({'product_id': (producto or self.producto).id, 'scrap_qty': cantidad,
                              'dcasa_motivo': motivo, 'location_id': self.ubicacion.id, **extra})
        if validar:
            scrap.action_validate()
        return scrap

    def _recibir(self, cantidad, precio):
        """Una recepción de proveedor validada (lo comprado del mes)."""
        proveedores = self.env.ref('stock.stock_location_suppliers')
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': self.almacen.in_type_id.id, 'partner_id': self.proveedor.id,
            'location_id': proveedores.id, 'location_dest_id': self.ubicacion.id,
            'move_ids': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': cantidad, 'price_unit': precio,
                'location_id': proveedores.id, 'location_dest_id': self.ubicacion.id})]})
        recepcion.action_confirm()
        recepcion.move_ids.quantity = cantidad
        recepcion.button_validate()
        return recepcion
