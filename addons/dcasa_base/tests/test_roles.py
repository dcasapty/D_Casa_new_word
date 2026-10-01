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
                      'purchase.group_purchase_manager'):
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
