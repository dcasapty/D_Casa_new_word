from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


def crear_usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login,
        'group_ids': [Command.set([env.ref(g).id for g in ('base.group_user', *grupos)])],
    })


@tagged('post_install', '-at_install')
class TestRoles(TransactionCase):
    """Roles «D'CASA / Vendedora» y «D'CASA / Gerencia» (UI-02, UI-03)."""

    def test_vendedora_vende_cobra_y_despacha(self):
        vendedora = self.env.ref('dcasa_base.group_vendedora')
        self.assertEqual(vendedora.full_name, "D'CASA / Vendedora")
        implicados = vendedora.all_implied_ids
        for xmlid in ('sales_team.group_sale_salesman', 'sales_team.group_sale_salesman_all_leads',
                      'account.group_account_invoice', 'stock.group_stock_user'):
            self.assertIn(self.env.ref(xmlid), implicados, xmlid)
        for xmlid in ('sales_team.group_sale_manager', 'account.group_account_user', 'account.group_account_readonly',
                      'stock.group_stock_manager', 'purchase.group_purchase_user', 'base.group_system',
                      'base.group_erp_manager', 'dcasa_base.group_gerencia'):
            self.assertNotIn(self.env.ref(xmlid), implicados, xmlid)

    def test_gerencia_controla_sin_ser_admin_tecnico(self):
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        self.assertEqual(gerencia.full_name, "D'CASA / Gerencia")
        implicados = gerencia.all_implied_ids
        for xmlid in ('dcasa_base.group_vendedora', 'sales_team.group_sale_manager', 'account.group_account_user',
                      'account.group_account_invoice', 'stock.group_stock_manager',
                      'purchase.group_purchase_manager', 'product.group_product_manager'):
            self.assertIn(self.env.ref(xmlid), implicados, xmlid)
        for xmlid in ('base.group_system', 'base.group_erp_manager', 'account.group_account_manager'):
            self.assertNotIn(self.env.ref(xmlid), implicados, xmlid)
        self.assertIn(self.env.ref('base.user_admin'), gerencia.all_user_ids)

    def test_vendedora_puede_registrar_cobros(self):
        usuario = crear_usuario(self.env, 'rol_vendedora', 'dcasa_base.group_vendedora')
        self.assertTrue(self.env['account.payment'].with_user(usuario).has_access('create'))
        self.assertTrue(self.env['sale.order'].with_user(usuario).has_access('create'))
        self.assertFalse(self.env['purchase.order'].with_user(usuario).has_access('create'))


@tagged('post_install', '-at_install')
class TestTopeDescuento(TransactionCase):
    """UI-08: la vendedora rebaja hasta el tope; Gerencia sin tope."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.vendedora = crear_usuario(cls.env, 'tope_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'tope_gerencia', 'dcasa_base.group_gerencia')
        cls.producto = cls.env['product.product'].create({'name': 'Sofá tope', 'list_price': 200.0})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente tope'})

    def _orden(self, usuario, **linea):
        return self.env['sale.order'].with_user(usuario).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, **linea})],
        })

    def test_vendedora_rebaja_hasta_el_tope(self):
        orden = self._orden(self.vendedora, discount=10)
        self.assertEqual(orden.order_line.discount, 10)
        orden.order_line.write({'price_unit': 185.0, 'discount': 0})  # 7,5 % menos: dentro del tope
        orden.order_line.write({'price_unit': 220.0, 'discount': 18})  # 180,40 neto: dentro del tope
        self.assertEqual(orden.order_line.discount, 18)

    def test_vendedora_no_pasa_el_tope_por_porcentaje(self):
        with self.assertRaisesRegex(ValidationError, 'Gerencia'):
            self._orden(self.vendedora, discount=15)
        orden = self._orden(self.vendedora)
        with self.assertRaises(ValidationError):
            orden.order_line.discount = 50

    def test_vendedora_no_baja_el_precio_bajo_el_piso(self):
        with self.assertRaises(ValidationError):
            self._orden(self.vendedora, price_unit=179.99)
        orden = self._orden(self.vendedora, price_unit=180.0)
        # Precio y descuento se suman: 190 con 6 % = 178,60 < 180.
        with self.assertRaises(ValidationError):
            orden.order_line.write({'price_unit': 190.0, 'discount': 6})

    def test_gerencia_sin_tope(self):
        orden = self._orden(self.gerencia, discount=50)
        orden.order_line.price_unit = 20.0
        self.assertAlmostEqual(orden.order_line.price_unit, 20.0)

    def test_el_tope_se_configura_en_ajustes(self):
        ajustes = self.env['res.config.settings'].create({'dcasa_descuento_max_vendedora': 25})
        ajustes.execute()
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dcasa.descuento_max_vendedora'), '25.0')
        self.assertEqual(self.env['res.config.settings'].create({}).dcasa_descuento_max_vendedora, 25)
        orden = self._orden(self.vendedora, discount=20)
        self.assertEqual(orden.order_line.discount, 20)
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({'dcasa_descuento_max_vendedora': 120})

    def test_lineas_que_no_son_rebaja_no_cuentan(self):
        orden = self._orden(self.vendedora)
        orden.with_user(self.vendedora).write({'order_line': [
            Command.create({'display_type': 'line_note', 'name': 'Entrega el sábado'}),
        ]})
        self.assertEqual(len(orden.order_line), 2)


@tagged('post_install', '-at_install')
class TestTopeDescuentoGlobal(TransactionCase):
    """Hallazgo del 2026-10-16: el botón «Descuento» (global en % y de importe fijo) crea líneas negativas con un
    producto de precio cero y se saltaba el tope de la vendedora. Ahora el tope se mide sobre el pedido entero."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.vendedora = crear_usuario(cls.env, 'global_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'global_gerencia', 'dcasa_base.group_gerencia')
        cls.itbms = cls.env['account.tax'].create({
            'name': 'ITBMS prueba 7%', 'amount': 7.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'company_id': cls.env.company.id})
        cls.cama = cls.env['product.product'].create({
            'name': 'Cama tope global', 'list_price': 200.0, 'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.mesa = cls.env['product.product'].create({
            'name': 'Mesa tope global', 'list_price': 100.0, 'taxes_id': [Command.set(cls.itbms.ids)]})
        # El producto de descuento que Odoo crea la primera vez que Gerencia usa el botón.
        cls.producto_descuento = cls.env['product.product'].create({
            'name': 'Descuento', 'type': 'service', 'list_price': 0.0, 'taxes_id': [Command.clear()]})
        cls.env.company.sale_discount_product_id = cls.producto_descuento
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente tope global'})

    # assertRaises (no assertRaisesRegex) deshace lo que alcanzó a escribir la operación rechazada, como hace la
    # petición real al fallar: sin eso, la línea de descuento rechazada seguiría en el pedido.

    def _orden(self, usuario, productos=None, **linea):
        productos = productos or [self.cama]
        return self.env['sale.order'].with_user(usuario).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id, **linea}) for p in productos],
        })

    def _descuento(self, usuario, orden, tipo, porcentaje=0.0, importe=0.0):
        """Lo mismo que hace el botón «Descuento» de la cotización."""
        asistente = self.env['sale.order.discount'].with_user(usuario).with_context(
            active_id=orden.id, active_model='sale.order').create({
                'sale_order_id': orden.id, 'discount_type': tipo,
                'discount_percentage': porcentaje, 'discount_amount': importe})
        asistente.action_apply_discount()

    def test_descuento_global_dentro_del_tope_pasa(self):
        orden = self._orden(self.vendedora)
        self._descuento(self.vendedora, orden, 'so_discount', porcentaje=0.10)
        self.assertAlmostEqual(orden.amount_untaxed, 180.0, places=2)

    def test_descuento_global_sobre_el_tope_se_bloquea(self):
        orden = self._orden(self.vendedora)
        with self.assertRaises(ValidationError) as bloqueo:
            self._descuento(self.vendedora, orden, 'so_discount', porcentaje=0.50)
        self.assertIn('Gerencia', str(bloqueo.exception))

    def test_descuento_de_importe_fijo_sobre_el_tope_se_bloquea(self):
        orden = self._orden(self.vendedora)
        with self.assertRaises(ValidationError):
            self._descuento(self.vendedora, orden, 'amount', importe=80.0)
        self._descuento(self.vendedora, orden, 'amount', importe=10.0)  # ~5 % del neto: dentro del tope

    def test_el_descuento_por_linea_y_el_global_se_suman(self):
        orden = self._orden(self.vendedora, discount=6)  # 6 % por línea
        with self.assertRaises(ValidationError):
            self._descuento(self.vendedora, orden, 'so_discount', porcentaje=0.06)  # 6 % más: 11,64 % en total

    def test_no_se_puede_dejar_la_rebaja_fija_sobre_un_pedido_mas_chico(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.cama.id}),
                           Command.create({'product_id': self.mesa.id, 'product_uom_qty': 2})],
        })  # 400 de tarifa: el tope de 10 % deja rebajar hasta 40
        self._descuento(self.vendedora, orden, 'amount', importe=40.0)  # 40 con ITBMS = 37,38 sin él: dentro del tope
        linea_mesa = orden.order_line.filtered(lambda linea: linea.product_id == self.mesa)
        with self.assertRaises(ValidationError):
            linea_mesa.write({'product_uom_qty': 1})  # los mismos 37,38 sobre 300 de tarifa pasarían de 10 %
        with self.assertRaises(ValidationError):
            linea_mesa.unlink()  # y sobre 200 también

    def test_una_linea_negativa_de_un_producto_sin_precio_tampoco_se_salta_el_tope(self):
        servicio = self.env['product.product'].create({'name': 'Ajuste libre', 'type': 'service', 'list_price': 0.0})
        orden = self._orden(self.vendedora)
        with self.assertRaises(ValidationError):
            orden.with_user(self.vendedora).write({'order_line': [
                Command.create({'product_id': servicio.id, 'price_unit': -100.0})]})

    def test_gerencia_no_tiene_tope_global(self):
        orden = self._orden(self.gerencia)
        self._descuento(self.gerencia, orden, 'so_discount', porcentaje=0.50)
        self.assertAlmostEqual(orden.amount_untaxed, 100.0, places=2)

    def test_el_itbms_se_calcula_sobre_el_precio_ya_rebajado(self):
        """Los tres tipos de descuento bajan la base y el ITBMS (7 %) sale del neto, no del precio de lista."""
        casos = (('sol_discount', {'porcentaje': 0.10}, 180.0),
                 ('so_discount', {'porcentaje': 0.10}, 180.0),
                 ('amount', {'importe': 21.40}, 180.0))  # el importe fijo incluye el ITBMS: 21,40 = 20 + 7 %
        for tipo, valores, neto in casos:
            with self.subTest(tipo=tipo):
                orden = self._orden(self.gerencia)
                self._descuento(self.gerencia, orden, tipo, **valores)
                self.assertAlmostEqual(orden.amount_untaxed, neto, places=2)
                self.assertAlmostEqual(orden.amount_tax, round(neto * 0.07, 2), places=2)
                self.assertAlmostEqual(orden.amount_total, round(neto * 1.07, 2), places=2)
