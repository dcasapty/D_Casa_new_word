"""Solo Gerencia ajusta las existencias a mano (hallazgo del 2026-10-16): la Vendedora no puede editar ni aplicar un
conteo en Inventario › Inventario físico, aunque Odoo se lo permitiera."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


@tagged('post_install', '-at_install')
class TestAjusteDeExistencias(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'ajuste_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'ajuste_gerencia', 'dcasa_base.group_gerencia')
        cls.producto = cls.env['product.product'].create({'name': 'Cama ajuste', 'is_storable': True})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.ubicacion = almacen.lot_stock_id

    def _quants(self, usuario):
        return self.env['stock.quant'].with_user(usuario).with_context(inventory_mode=True)

    def test_gerencia_ajusta_las_existencias(self):
        quant = self._quants(self.gerencia).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 7})
        quant.action_apply_inventory()
        self.assertEqual(self.producto.with_user(self.gerencia).qty_available, 7)

    def test_la_vendedora_no_crea_un_conteo(self):
        with self.assertRaises(UserError):
            self._quants(self.vendedora).create({
                'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 7})
        self.assertEqual(self.producto.qty_available, 0)

    def test_la_vendedora_no_edita_ni_aplica_un_conteo(self):
        quant = self._quants(self.gerencia).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 7})
        quant.action_apply_inventory()
        propio = quant.with_user(self.vendedora).with_context(inventory_mode=True)
        with self.assertRaises(UserError):
            propio.write({'inventory_quantity': 99})
        with self.assertRaises(UserError):
            propio.write({'inventory_quantity_auto_apply': 99})
        with self.assertRaises(UserError):
            propio.action_apply_inventory()
        self.assertEqual(self.producto.qty_available, 7)

    def test_la_vendedora_sigue_recibiendo_y_entregando(self):
        """Validar una recepción mueve existencias por su movimiento, no por un ajuste: no se ve afectado."""
        proveedores = self.env.ref('stock.stock_location_suppliers')
        almacen = self.ubicacion.warehouse_id
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': almacen.in_type_id.id,
            'location_id': proveedores.id, 'location_dest_id': self.ubicacion.id,
            'move_ids': [(0, 0, {
                'product_id': self.producto.id, 'product_uom_qty': 4, 'location_id': proveedores.id,
                'location_dest_id': self.ubicacion.id,
            })],
        })
        recepcion.action_confirm()
        recepcion.move_ids.quantity = 4
        recepcion.with_user(self.vendedora).button_validate()
        self.assertEqual(recepcion.state, 'done')
        self.assertEqual(self.producto.qty_available, 4)

    # --- Revisión adversarial del 2026-10-16: sin el contexto ``inventory_mode`` -------------------------------

    def test_la_vendedora_no_escribe_la_cantidad_sin_pasar_por_el_modo_inventario(self):
        """El contexto lo pone el cliente: un RPC sin él caía en la rama sin restricciones de Odoo."""
        quant = self._quants(self.gerencia).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 7})
        quant.action_apply_inventory()
        sin_contexto = self.env['stock.quant'].with_user(self.vendedora)
        with self.assertRaises(UserError):
            sin_contexto.browse(quant.id).write({'quantity': 999})
        with self.assertRaises(UserError):
            sin_contexto.browse(quant.id).write({'reserved_quantity': 5})
        with self.assertRaises(UserError):
            sin_contexto.create({'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'quantity': 100})
        self.assertEqual(self.producto.qty_available, 7)

    def test_la_vendedora_sigue_reservando_y_entregando(self):
        """Reservar y entregar mueven la cantidad por dentro del sistema (sudo), no por una escritura de ella."""
        self._quants(self.gerencia).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 5}
        ).action_apply_inventory()
        almacen = self.ubicacion.warehouse_id
        clientes = self.env.ref('stock.stock_location_customers')
        entrega = self.env['stock.picking'].with_user(self.vendedora).create({
            'picking_type_id': almacen.out_type_id.id,
            'location_id': self.ubicacion.id, 'location_dest_id': clientes.id,
            'move_ids': [(0, 0, {
                'product_id': self.producto.id, 'product_uom_qty': 2, 'location_id': self.ubicacion.id,
                'location_dest_id': clientes.id,
            })],
        })
        entrega.action_confirm()
        entrega.action_assign()
        self.assertEqual(entrega.move_ids.quantity, 2, 'se reservó')
        entrega.move_ids.quantity = 2
        entrega.button_validate()
        self.assertEqual(entrega.state, 'done')
        self.assertEqual(self.producto.qty_available, 3)

    def test_el_sistema_y_gerencia_si_pueden_escribir_la_cantidad(self):
        quant = self._quants(self.gerencia).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 7})
        quant.action_apply_inventory()
        quant.sudo().write({'reserved_quantity': 0})
        quant.with_user(self.gerencia).write({'reserved_quantity': 0})
