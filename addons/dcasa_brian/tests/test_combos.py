"""Brian con productos tipo «Combo» (cama + colchón): cotiza con sus piezas y no vende un combo vacío."""
from odoo import Command
from odoo.tests import new_test_user, tagged
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


@tagged('post_install', '-at_install')
class TestBrianCombosArmables(TransactionCase):
    """Brian arma el combo cama + colchón con el mismo mecanismo que el panel (2026-10-22)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        base = {'type': 'consu', 'is_storable': True, 'taxes_id': [Command.set(impuesto.ids)]}

        def producto(codigo, nombre, precio, existencias=3, combo=0.0):
            variante = cls.env['product.product'].create({**base, 'name': nombre, 'default_code': codigo,
                                                          'list_price': precio})
            if combo:
                variante.dcasa_precio_combo = combo
            cls.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': variante.id, 'location_id': ubicacion.id,
                'inventory_quantity': existencias})._apply_inventory()
            return variante
        cls.cama = producto('BRZ-CAMA-K', 'BRIANZETA CAMA KING', 400.0)
        cls.colchon = producto('BRZ-COL-K', 'BRIANZETA COLCHON KING', 300.0, combo=260.0)
        cls.sin_precio = producto('BRZ-COL-K2', 'BRIANZETA COLCHON SIN PRECIO KING', 280.0)
        cls.queen = producto('BRZ-COL-Q', 'BRIANZETA COLCHON QUEEN', 250.0, combo=215.0)
        cls.vendedora = new_test_user(cls.env, login='brian_combo_vendedora', groups='dcasa_base.group_vendedora')
        cls.gerencia = new_test_user(cls.env, login='brian_combo_gerencia', groups='dcasa_base.group_gerencia')
        cls.cliente = cls.env['res.partner'].create({'name': 'BRIANZETA CLIENTE DE PRUEBA', 'phone': '6123-4598'})

    def ejecutar(self, usuario, nombre, argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos)

    def orden_de(self, respuesta):
        return self.env['sale.order'].search([('name', '=', respuesta['datos']['numero'])])

    def test_colchones_para_cama_solo_de_su_medida_con_precio_en_combo(self):
        respuesta = self.ejecutar(self.vendedora, 'colchones_para_cama', {'cama': 'BRZ-CAMA-K'})
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual(datos['medida'], 'King')
        por_codigo = {f['codigo']: f for f in datos['colchones']}
        self.assertNotIn('BRZ-COL-Q', por_codigo, 'Solo los de la medida de la cama')
        self.assertEqual((por_codigo['BRZ-COL-K']['precio_en_combo'], por_codigo['BRZ-COL-K']['ahorro']),
                         ('$260.00', '$40.00'))
        self.assertIn('sin precio en combo', por_codigo['BRZ-COL-K2']['precio_en_combo'])

    def test_armar_combo_en_una_cotizacion_nueva(self):
        respuesta = self.ejecutar(self.vendedora, 'armar_combo', {
            'cliente': 'BRIANZETA CLIENTE DE PRUEBA', 'cama': 'BRZ-CAMA-K', 'colchon': 'BRZ-COL-K'})
        self.assertTrue(respuesta['ok'], respuesta)
        orden = self.orden_de(respuesta)
        colchon = orden.order_line.filtered(lambda ln: ln.product_id == self.colchon)
        self.assertEqual(colchon.price_unit, 260.0)
        self.assertEqual(respuesta['datos']['el_cliente_ahorra_sin_itbms'], '$40.00')
        self.assertIn('Combo · ahorras $40.00', [linea.get('combo') for linea in respuesta['datos']['lineas']])

    def test_armar_combo_de_otra_medida_avisa(self):
        respuesta = self.ejecutar(self.vendedora, 'armar_combo', {
            'cliente': 'BRIANZETA CLIENTE DE PRUEBA', 'cama': 'BRZ-CAMA-K', 'colchon': 'BRZ-COL-Q'})
        self.assertFalse(respuesta['ok'])
        self.assertIn('misma medida', respuesta['error'])

    def test_cotizar_cama_y_colchon_sueltos_tambien_da_el_precio_en_combo(self):
        respuesta = self.ejecutar(self.vendedora, 'crear_cotizacion', {
            'cliente': 'BRIANZETA CLIENTE DE PRUEBA', 'lineas': 'BRZ-COL-K x 1; BRZ-CAMA-K x 1'})
        self.assertTrue(respuesta['ok'], respuesta)
        orden = self.orden_de(respuesta)
        self.assertEqual(orden.order_line.filtered(lambda ln: ln.product_id == self.colchon).price_unit, 260.0)

    def test_cambiar_el_colchon_del_combo(self):
        orden = self.orden_de(self.ejecutar(self.vendedora, 'armar_combo', {
            'cliente': 'BRIANZETA CLIENTE DE PRUEBA', 'cama': 'BRZ-CAMA-K', 'colchon': 'BRZ-COL-K'}))
        respuesta = self.ejecutar(self.vendedora, 'cambiar_combo', {'venta': orden.name, 'colchon_nuevo': 'BRZ-COL-K2'})
        self.assertTrue(respuesta['ok'], respuesta)
        self.assertEqual(orden.order_line.product_id, self.cama | self.sin_precio)
        self.assertEqual(orden.order_line.filtered(lambda ln: ln.product_id == self.sin_precio).price_unit, 280.0)
        self.assertNotIn('el_cliente_ahorra_sin_itbms', respuesta['datos'])

    def test_el_precio_en_combo_lo_pone_gerencia(self):
        respuesta = self.ejecutar(self.vendedora, 'poner_precio_en_combo', {'colchon': 'BRZ-COL-K', 'precio': 200})
        self.assertFalse(respuesta['ok'])
        self.assertEqual(self.colchon.dcasa_precio_combo, 260.0)
        respuesta = self.ejecutar(self.gerencia, 'poner_precio_en_combo', {'colchon': 'BRZ-COL-K', 'precio': 300})
        self.assertFalse(respuesta['ok'])
        self.assertIn('menor que su precio normal', respuesta['error'])
        respuesta = self.ejecutar(self.gerencia, 'poner_precio_en_combo', {'colchon': 'BRZ-COL-K', 'precio': 249.99})
        self.assertTrue(respuesta['ok'], respuesta)
        self.assertEqual(self.colchon.dcasa_precio_combo, 249.99)
        self.assertEqual(respuesta['datos']['ahorro'], '$50.01')
