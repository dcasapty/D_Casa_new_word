"""Brian con productos tipo «Combo» (cama + colchón): cotiza con sus piezas y no vende un combo vacío."""
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBrianConCombos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.vendedor = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Brian Combos Vendedor', 'login': 'brian_combos_vendedor',
            'group_ids': [Command.set([ref('base.group_user').id, ref('sales_team.group_sale_salesman').id])]})
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        base = {'type': 'consu', 'is_storable': True, 'taxes_id': [Command.set(impuesto.ids)]}
        cls.cama = cls.env['product.product'].create({
            **base, 'name': 'Brianzeta Cama Combo', 'default_code': 'BRN-CAMA', 'list_price': 150.0})
        cls.colchon = cls.env['product.product'].create({
            **base, 'name': 'Brianzeta Colchón Combo', 'default_code': 'BRN-COL', 'list_price': 200.0})
        cls.otro = cls.env['product.product'].create({
            **base, 'name': 'Brianzeta Colchón Otro', 'default_code': 'BRN-COL2', 'list_price': 230.0})
        grupos = cls.env['product.combo'].create([
            {'name': 'Cama', 'combo_item_ids': [(0, 0, {'product_id': cls.cama.id})]},
            {'name': 'Colchón', 'combo_item_ids': [(0, 0, {'product_id': cls.colchon.id})]}])
        cls.combo = cls.env['product.template'].create({
            'name': 'Brianzeta Combo Cama y Colchón', 'default_code': 'BRN-COMBO', 'type': 'combo',
            'list_price': 320.0, 'taxes_id': [Command.set(impuesto.ids)], 'combo_ids': [Command.set(grupos.ids)]})
        cls.cliente = cls.env['res.partner'].create({'name': 'Brianzeta Cliente Combos', 'phone': '6123-4599'})

    def ejecutar(self, nombre, argumentos):
        return self.env['brian.herramientas'].with_user(self.vendedor).ejecutar(nombre, argumentos)

    def test_cotizar_un_combo_lleva_la_cama_y_el_colchon_y_el_total_del_combo(self):
        respuesta = self.ejecutar('crear_cotizacion', {'cliente': 'Brianzeta Cliente Combos', 'producto': 'BRN-COMBO'})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        orden = self.env['sale.order'].search([('name', '=', datos['numero'])])
        self.assertEqual(orden.order_line.product_id, self.combo.product_variant_id | self.cama | self.colchon)
        self.assertEqual((orden.amount_untaxed, orden.amount_total), (320.0, 342.4))
        self.assertEqual(datos['total'], '$342.40', 'El resumen de Brian dice el total del combo, no cero')

    def test_el_precio_de_un_combo_no_se_cambia_a_mano(self):
        antes = self.env['sale.order'].search_count([])
        respuesta = self.ejecutar('crear_cotizacion', {
            'cliente': 'Brianzeta Cliente Combos', 'producto': 'BRN-COMBO', 'precio': 100})
        self.assertFalse(respuesta['ok'])
        self.assertIn('no se cambia a mano', respuesta['error'])
        self.assertEqual(self.env['sale.order'].search_count([]), antes, 'La cotización a medias se deshace')

    def test_un_combo_con_opciones_pide_agregarlo_desde_ventas(self):
        self.combo.combo_ids.filtered(lambda g: g.name == 'Colchón').combo_item_ids = [
            (0, 0, {'product_id': self.otro.id, 'extra_price': 20.0})]
        respuesta = self.ejecutar('crear_cotizacion', {'cliente': 'Brianzeta Cliente Combos', 'producto': 'BRN-COMBO'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('hay que escoger', respuesta['error'])
        self.assertIn('Agrégalo desde Ventas', respuesta['error'])

    def test_un_combo_sin_sus_piezas_no_se_confirma(self):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': self.vendedor.id,
            'order_line': [(0, 0, {'product_id': self.combo.product_variant_id.id, 'product_uom_qty': 1})]})
        respuesta = self.ejecutar('confirmar_venta', {'venta': orden.name})
        confirmada = self.env['brian.herramientas'].with_user(self.vendedor).confirmar(respuesta['accion_id'])
        self.assertFalse(confirmada['ok'])
        self.assertIn('no tiene todas sus piezas', confirmada['error'])
        self.assertEqual(orden.state, 'draft')
