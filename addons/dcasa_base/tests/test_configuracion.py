from datetime import datetime, time, timedelta

import pytz

from odoo import Command, fields
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

    def test_ventas_de_hoy_con_el_dia_de_panama(self):
        """UI-06: la venta de anoche a las 8 p. m. (1 a. m. UTC de hoy) no es de hoy."""
        menu = self.env.ref('dcasa_base.menu_dcasa_ventas_hoy')
        self.assertEqual(menu.action, self.env.ref('dcasa_base.action_dcasa_ventas_hoy_abrir'))
        usuario = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendedora hoy', 'login': 'vendedora_hoy', 'tz': 'America/Panama',
            'group_ids': [Command.set([self.env.ref('dcasa_base.group_vendedora').id])],
        })
        accion = self.env.ref('dcasa_base.action_dcasa_ventas_hoy_abrir').with_user(usuario).run()
        self.assertEqual(accion['res_model'], 'sale.order')
        inicio, fin = self.env['sale.order'].with_user(usuario)._dcasa_limites_de_hoy()
        zona = pytz.timezone('America/Panama')
        hoy = fields.Date.context_today(self.env['sale.order'].with_context(tz='America/Panama'))
        self.assertEqual(pytz.utc.localize(inicio).astimezone(zona).replace(tzinfo=None),
                         datetime.combine(hoy, time.min))
        self.assertEqual(fin - inicio, timedelta(days=1))
        # Medianoche de Panamá = 5 a. m. UTC: el día no empieza a la medianoche UTC.
        self.assertEqual(inicio.hour, 5)
        self.assertIn(('date_order', '>=', fields.Datetime.to_string(inicio)), accion['domain'])
        self.assertIn(('date_order', '<', fields.Datetime.to_string(fin)), accion['domain'])

        cliente = self.env['res.partner'].create({'name': 'Cliente de anoche'})
        producto = self.env['product.product'].create({'name': 'Mesa de anoche', 'list_price': 10})
        anoche, hoy_temprano = self.env['sale.order'].create([{
            'partner_id': cliente.id, 'order_line': [Command.create({'product_id': producto.id})],
        } for _ in range(2)])
        (anoche | hoy_temprano).action_confirm()
        anoche.date_order = inicio - timedelta(hours=4)        # 8 p. m. de ayer en Panamá
        hoy_temprano.date_order = inicio + timedelta(hours=4)  # 4 a. m. de hoy en Panamá
        encontradas = self.env['sale.order'].search(accion['domain'])
        self.assertIn(hoy_temprano, encontradas)
        self.assertNotIn(anoche, encontradas)

    def test_cantidades_enteras(self):
        """Se venden camas, no cuartos de cama."""
        self.assertEqual(self.env.ref('uom.decimal_product_uom').digits, 0)
        self.assertEqual(self.env['res.lang']._lang_get(DCASA_LANG).decimal_point, '.')

    def test_interfaz_con_la_marca(self):
        from odoo.tools.misc import file_open
        with file_open('dcasa_base/static/src/scss/primary_variables.scss') as variables:
            self.assertIn('#1340B1', variables.read())
