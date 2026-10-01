from odoo.addons.dcasa_base import (
    DCASA_LANG,
    DCASA_TZ,
    DIARIOS_COBRO,
    MENUS_OCULTOS,
    _configurar_interfaz,
    _configurar_ventas_panama,
    archivar_itbms_incluido,
)
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConfiguracionTienda(TransactionCase):
    """Auditoría de UX: Odoo por dentro en español, con el ITBMS que se suma y al grano."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')

    def test_producto_nuevo_nace_con_itbms_que_se_suma(self):
        """Los precios de D'CASA son sin ITBMS: el 7 % se suma encima (decisión de la dueña)."""
        producto = self.env['product.template'].create({'name': 'Mueble nuevo', 'list_price': 39.99})
        self.assertEqual(producto.taxes_id, self.company.account_sale_tax_id)
        self.assertEqual(producto.taxes_id.amount, 7)
        self.assertFalse(producto.taxes_id.price_include)
        self.assertEqual(producto.taxes_id.name, 'ITBMS 7%')
        total = producto.taxes_id.compute_all(39.99)
        self.assertAlmostEqual(total['total_excluded'], 39.99, places=2)
        self.assertAlmostEqual(total['total_included'], 42.79, places=2)

    def test_linea_de_venta_suma_el_itbms(self):
        """$39.99 de lista → subtotal 39.99, ITBMS 2.80, total 42.79."""
        self.assertEqual(self.company.account_price_include, 'tax_excluded')
        orden = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Cliente'}).id,
            'order_line': [(0, 0, {'product_id': self.env['product.product'].create(
                {'name': 'Mesa', 'list_price': 39.99}).id})],
        })
        self.assertAlmostEqual(orden.order_line.price_subtotal, 39.99, places=2)
        self.assertAlmostEqual(orden.order_line.price_total, 42.79, places=2)
        self.assertAlmostEqual(orden.amount_untaxed, 39.99, places=2)
        self.assertAlmostEqual(orden.amount_tax, 2.80, places=2)
        self.assertAlmostEqual(orden.amount_total, 42.79, places=2)

    def test_reconfigurar_corrige_base_con_itbms_incluido(self):
        """Una base anterior (impuesto incluido por defecto) vuelve al ITBMS que se suma."""
        venta = self.company.account_sale_tax_id
        incluido = venta.copy({'name': 'ITBMS 7% incluido', 'price_include_override': 'tax_included'})
        self.company.write({'account_sale_tax_id': incluido.id, 'account_price_include': 'tax_included'})
        _configurar_ventas_panama(self.env)
        self.assertEqual(self.company.account_sale_tax_id, venta)
        self.assertEqual(self.company.account_price_include, 'tax_excluded')
        self.assertTrue(incluido.price_include, 'El incluido no cambia: lo archiva la migración del catálogo')

    def test_archiva_el_incluido_sin_uso(self):
        venta = self.company.account_sale_tax_id
        incluido = venta.copy({'name': 'ITBMS 7% incluido', 'price_include_override': 'tax_included'})
        producto = self.env['product.template'].create({'name': 'Viejo', 'taxes_id': [(6, 0, incluido.ids)]})
        self.assertEqual(archivar_itbms_incluido(self.env, self.company), incluido, 'Lo usa un producto')
        self.assertTrue(incluido.active)
        producto.taxes_id = venta
        self.assertFalse(archivar_itbms_incluido(self.env, self.company))
        self.assertFalse(incluido.active)
        self.assertTrue(venta.active)

    def test_compras_sin_itbms_incluido(self):
        compras = self.env['account.tax'].search([
            ('company_id', '=', self.company.id), ('type_tax_use', '=', 'purchase')])
        self.assertTrue(compras)
        self.assertFalse(any(compras.mapped('price_include')), 'La factura del proveedor trae el neto')

    def test_formas_de_cobro(self):
        diarios = self.env['account.journal'].search([('company_id', '=', self.company.id)])
        for codigo, nombre, tipo in DIARIOS_COBRO:
            diario = diarios.filtered(lambda d, c=codigo: d.code == c)
            self.assertEqual((diario.name, diario.type), (nombre, tipo))

    def test_interfaz_en_espanol_y_al_grano(self):
        admin = self.env.ref('base.user_admin')
        self.assertEqual(admin.lang, DCASA_LANG)
        self.assertEqual(admin.tz, DCASA_TZ)
        # Abre en Ventas (o en el «Inicio» de dcasa_interfaz, si está instalado), nunca en el chat.
        self.assertTrue(admin.action_id)
        self.assertTrue(admin.has_group('sale.group_discount_per_so_line'))
        self.assertTrue(admin.has_group('product.group_product_variant'))
        for xmlid in MENUS_OCULTOS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertEqual(menu.group_ids, self.env.ref('base.group_no_one'), xmlid)
        almacen = self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1)
        self.assertEqual(almacen.name, "D'CASA La Chorrera")

    def test_se_puede_repetir(self):
        impuestos = self.env['account.tax'].search_count([])
        diarios = self.env['account.journal'].search_count([])
        _configurar_ventas_panama(self.env)
        _configurar_interfaz(self.env)
        self.assertEqual(self.env['account.tax'].search_count([]), impuestos)
        self.assertEqual(self.env['account.journal'].search_count([]), diarios)

    def test_menu_hoy(self):
        accion = self.env.ref('dcasa_base.action_dcasa_cobros_hoy')
        self.assertEqual(accion.res_model, 'account.payment')
        self.assertIn('journal_id', accion.context)

    def test_cantidades_enteras(self):
        """Se venden camas, no cuartos de cama."""
        self.assertEqual(self.env.ref('uom.decimal_product_uom').digits, 0)
        self.assertEqual(self.env['res.lang']._lang_get(DCASA_LANG).decimal_point, '.')

    def test_interfaz_con_la_marca(self):
        from odoo.tools.misc import file_open
        with file_open('dcasa_base/static/src/scss/primary_variables.scss') as variables:
            self.assertIn('#1340B1', variables.read())
