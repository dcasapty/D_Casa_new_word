"""Bitácora de bodega y el hueco del Inventario físico: cada ajuste con antes → después, motivo obligatorio y quién;
nadie la edita; la Vendedora no ajusta existencias por ningún camino."""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .comun import BodegaComun


@tagged('post_install', '-at_install')
class TestBitacora(BodegaComun):

    def _conteo(self, usuario, cantidad, **contexto):
        return self.env['stock.quant'].with_user(usuario).with_context(inventory_mode=True, **contexto).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': cantidad})

    def _filas(self):
        return self.env['dcasa.bitacora.bodega'].search([('producto_id', '=', self.producto.id)])

    def test_aplicar_sin_motivo_pide_el_motivo_y_no_cambia_nada(self):
        quant = self._conteo(self.gerencia, 7)
        accion = quant.action_apply_inventory()
        self.assertEqual(accion['res_model'], 'stock.inventory.adjustment.name')
        self.assertEqual(self.producto.qty_available, 10)
        self.assertFalse(self._filas())
        ventana = self.env['stock.inventory.adjustment.name'].with_user(self.gerencia).with_context(
            accion['context']).create({})
        self.assertFalse(ventana.inventory_adjustment_name, 'el motivo viene vacío (no «Inventario físico»)')
        with self.assertRaisesRegex(UserError, 'motivo'):
            ventana.action_apply()
        ventana.inventory_adjustment_name = 'Conteo de fin de mes'
        ventana.action_apply()
        self.assertEqual(self.producto.qty_available, 7)
        fila = self._filas()
        self.assertEqual((fila.antes, fila.despues, fila.diferencia), (10.0, 7.0, -3.0))
        self.assertEqual((fila.motivo, fila.origen, fila.usuario_id), ('Conteo de fin de mes', 'inventario_fisico',
                                                                         self.gerencia))
        self.assertEqual(fila.valor, -600.0)

    def test_sin_motivo_no_se_aplica_ni_por_debajo(self):
        quant = self._conteo(self.gerencia, 4)
        with self.assertRaisesRegex(UserError, 'motivo'):
            quant._apply_inventory()
        self.assertEqual(self.producto.qty_available, 10)

    def test_escribir_a_la_mano_directo_pide_contar_y_aplicar(self):
        quant = self.env['stock.quant'].search([('product_id', '=', self.producto.id),
                                                ('location_id', '=', self.ubicacion.id)])
        with self.assertRaisesRegex(UserError, 'Contado'):
            quant.with_user(self.gerencia).with_context(inventory_mode=True).write(
                {'inventory_quantity_auto_apply': 2})
        self.assertEqual(self.producto.qty_available, 10)

    def test_el_escaner_y_brian_dejan_su_motivo(self):
        self._conteo(self.gerencia, 12, inventory_name='Conteo con lector (Bodega Gerencia)').action_apply_inventory()
        self._conteo(self.gerencia, 11, inventory_name='se encontró dañado', dcasa_origen='brian') \
            .action_apply_inventory()
        filas = self._filas().sorted('id')
        self.assertEqual(filas.mapped('origen'), ['escaner', 'brian'])
        self.assertEqual(filas.mapped('diferencia'), [2.0, -1.0])

    def test_un_conteo_que_coincide_no_es_un_ajuste(self):
        self._conteo(self.gerencia, 10, inventory_name='Revisión').action_apply_inventory()
        self.assertFalse(self._filas())

    def test_el_sistema_sin_persona_queda_como_ajuste_del_sistema(self):
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.producto.id, 'location_id': self.ubicacion.id, 'inventory_quantity': 15,
        })._apply_inventory()
        fila = self._filas()
        self.assertEqual((fila.motivo, fila.origen), ('Ajuste del sistema', 'sistema'))

    # ------------------------------------------------------------------
    # La bitácora no se toca
    # ------------------------------------------------------------------

    def test_nadie_edita_ni_borra_la_bitacora_y_la_vendedora_no_la_ve(self):
        self._conteo(self.gerencia, 9, inventory_name='Conteo').action_apply_inventory()
        fila = self._filas()
        with self.assertRaises(UserError):
            fila.with_user(self.gerencia).write({'motivo': 'otro'})
        with self.assertRaises(UserError):
            fila.write({'motivo': 'otro'})
        with self.assertRaises(AccessError):
            fila.with_user(self.gerencia).unlink()
        with self.assertRaises(UserError):
            fila.unlink()
        with self.assertRaises(AccessError):
            self.env['dcasa.bitacora.bodega'].with_user(self.gerencia).create({
                'producto_id': self.producto.id, 'usuario_id': self.gerencia.id, 'motivo': 'inventado'})
        with self.assertRaises(AccessError):
            fila.with_user(self.vendedora).read(['motivo'])
        self.assertEqual(fila.with_user(self.gerencia).motivo, 'Conteo')

    # ------------------------------------------------------------------
    # El hueco: la Vendedora no ajusta por ningún camino
    # ------------------------------------------------------------------

    def test_la_vendedora_no_abre_la_ventana_de_ajuste(self):
        quant = self._conteo(self.gerencia, 5)
        with self.assertRaises(UserError):
            quant.with_user(self.vendedora).with_context(inventory_mode=True).action_apply_inventory()
        self.assertEqual(self.producto.qty_available, 10)

    def test_la_vendedora_no_deshace_un_ajuste_gerencia_si_y_queda_anotado(self):
        self._conteo(self.gerencia, 6, inventory_name='Conteo').action_apply_inventory()
        linea = self.env['stock.move.line'].search([('product_id', '=', self.producto.id),
                                                     ('is_inventory', '=', True)], limit=1)
        with self.assertRaises(AccessError):
            linea.with_user(self.vendedora).action_revert_inventory()
        self.assertEqual(self.producto.qty_available, 6)
        linea.with_user(self.gerencia).action_revert_inventory()
        self.assertEqual(self.producto.qty_available, 10)
        deshecho = self._filas().filtered(lambda f: f.origen == 'deshacer')
        self.assertEqual((deshecho.antes, deshecho.despues, deshecho.diferencia), (6.0, 10.0, 4.0))

    def test_la_vendedora_no_manda_mercancia_a_ajuste_de_inventario_ni_por_rpc(self):
        perdida = self.env['stock.location'].search([('usage', '=', 'inventory'),
                                                     ('company_id', '=', self.env.company.id)], limit=1)
        with self.assertRaisesRegex(AccessError, 'Ajuste de inventario'):
            self.env['stock.move'].with_user(self.vendedora).create({
                'product_id': self.producto.id, 'product_uom_qty': 1, 'location_id': self.ubicacion.id,
                'location_dest_id': perdida.id})
        with self.assertRaises(AccessError):
            self.env['stock.move.line'].with_user(self.vendedora).create({
                'product_id': self.producto.id, 'quantity': 1, 'location_id': self.ubicacion.id,
                'location_dest_id': perdida.id})

    def test_la_vendedora_sigue_entregando(self):
        clientes = self.env.ref('stock.stock_location_customers')
        entrega = self.env['stock.picking'].with_user(self.vendedora).create({
            'picking_type_id': self.almacen.out_type_id.id, 'location_id': self.ubicacion.id,
            'location_dest_id': clientes.id,
            'move_ids': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 2,
                                         'location_id': self.ubicacion.id, 'location_dest_id': clientes.id})]})
        entrega.action_confirm()
        entrega.action_assign()
        entrega.move_ids.quantity = 2
        entrega.button_validate()
        self.assertEqual(entrega.state, 'done')
        self.assertEqual(self.producto.qty_available, 8)
        self.assertFalse(self._filas(), 'una entrega no es un ajuste')

    def test_los_menus_y_acciones_de_ajuste_son_de_gerencia(self):
        Menu = self.env['ir.ui.menu']
        for xmlid in ('stock.menu_action_inventory_tree', 'stock.menu_stock_scrap',
                      'dcasa_existencias.menu_mermas', 'dcasa_existencias.menu_bitacora',
                      'dcasa_existencias.menu_resumen_mermas'):
            menu = self.env.ref(xmlid)
            with self.subTest(menu=xmlid):
                self.assertNotIn(menu.id, Menu.with_user(self.vendedora)._visible_menu_ids())
                self.assertIn(menu.id, Menu.with_user(self.gerencia)._visible_menu_ids())
        for xmlid in ('stock.action_scrap', 'stock.action_revert_inventory_adjustment'):
            with self.subTest(accion=xmlid):
                self.assertEqual(self.env.ref(xmlid).group_ids, self.env.ref('stock.group_stock_manager'))
