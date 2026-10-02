"""Panel más rápido y más claro (auditoría ronda 6, docs/auditoria/ronda6/panel.md)."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
from lxml import etree

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


def crear_usuario(env, login, grupo):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'tz': 'America/Panama',
        'group_ids': [Command.set([env.ref('base.group_user').id, env.ref(grupo).id])],
    })


@tagged('post_install', '-at_install')
class TestPanel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'vendedora_panel', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'gerencia_panel', 'dcasa_base.group_gerencia')
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente panel'})
        cls.producto = cls.env['product.product'].create({'name': 'Silla panel', 'list_price': 50})

    def _menus(self, usuario):
        menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
        return {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

    # --- Rendimiento ------------------------------------------------------------------------

    def test_lista_de_entregas_no_calcula_transportistas(self):
        """allowed_carrier_ids se calcula registro por registro (~245 consultas por página)."""
        vista = self.env['stock.picking'].with_user(self.vendedora).get_views([(False, 'list')])
        campos = vista['models']['stock.picking']['fields']
        self.assertIn('carrier_id', campos)
        self.assertNotIn('allowed_carrier_ids', campos)

    def test_tablero_lee_la_semana_de_una_vez(self):
        Order = self.env['sale.order']
        with patch.object(type(Order), 'search', autospec=True, side_effect=type(Order).search) as buscar:
            datos = self.env['dcasa.tablero'].obtener_datos()
        busquedas_de_pedidos = [c for c in buscar.call_args_list if c.args[0]._name == 'sale.order']
        self.assertFalse(busquedas_de_pedidos, 'la semana y «Vendido hoy» salen de una sola lectura')
        self.assertEqual(len(datos['semana']), 7)

    def test_tablero_cuenta_cada_venta_en_su_dia_de_panama(self):
        """Una venta a las 8 p. m. de ayer (1 a. m. UTC de hoy) es de ayer, no de hoy."""
        Tablero = self.env['dcasa.tablero'].with_user(self.gerencia)
        zona = pytz.timezone('America/Panama')
        hoy = fields.Date.context_today(Tablero.with_context(tz='America/Panama'))
        anoche = zona.localize(datetime.combine(hoy - timedelta(days=1), datetime.min.time()) + timedelta(hours=20))
        antes = Tablero.obtener_datos()
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'order_line': [Command.create({'product_id': self.producto.id})],
        })
        orden.action_confirm()
        orden.date_order = anoche.astimezone(pytz.utc).replace(tzinfo=None)
        despues = Tablero.obtener_datos()

        def cifra(datos):
            return next(c['valor'] for c in datos['cifras'] if c['clave'] == 'ventas_hoy')
        self.assertAlmostEqual(cifra(despues), cifra(antes), places=2)
        self.assertAlmostEqual(despues['semana'][-2]['monto'] - antes['semana'][-2]['monto'],
                               orden.amount_total, places=2)
        self.assertEqual(despues['semana'][-1]['monto'], antes['semana'][-1]['monto'])

    # --- Inicio de la vendedora ---------------------------------------------------------------

    def test_vendedora_ve_sus_cotizaciones_y_gerencia_no_duplica(self):
        self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id})],
        })
        cifras = {c['clave']: c for c in self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()['cifras']}
        self.assertEqual(cifras['mis_cotizaciones']['valor'], 1)
        self.assertIn(('user_id', '=', self.vendedora.id), cifras['mis_cotizaciones']['accion']['domain'])
        self.assertGreaterEqual(cifras['cotizaciones']['valor'], 1)
        claves = {c['clave'] for c in self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()['cifras']}
        self.assertNotIn('mis_cotizaciones', claves)

    def test_cotizaciones_abre_las_abiertas_de_toda_la_tienda(self):
        accion = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        self.assertIn("'search_default_draft': 1", accion['context'])
        self.assertNotIn('search_default_my_quotation', accion['context'])

    def test_clientes_de_ventas_muestra_a_todos_y_crea_personas(self):
        accion = self.env.ref('sale.res_partner_menu').action
        self.assertEqual(accion, self.env.ref('dcasa_interfaz.action_dcasa_clientes'))
        self.assertNotIn('search_default', accion.context)
        self.assertIn("'default_is_company': False", accion.context)
        # Quien solo pidió cotización (sin factura) también es cliente y se encuentra.
        self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'order_line': [Command.create({'product_id': self.producto.id})],
        })
        self.assertFalse(self.cliente.customer_rank)  # el filtro estándar lo escondería
        self.assertFalse(accion.domain)
        # Facturación › Clientes no cambia.
        self.assertIn('search_default_customer', self.env.ref('account.res_partner_action_customer').context)

    # --- Menús y columnas -----------------------------------------------------------------------

    def test_vendedora_sin_menus_que_no_usa(self):
        ocultos = {
            'website.menu_website_configuration', 'account.menu_finance_payables',
            'account.menu_finance_reports', 'sale.menu_products', 'sale.menu_product_pricelist_main',
            'stock.product_product_menu',
        }
        de_vendedora = self._menus(self.vendedora)
        self.assertFalse(ocultos & de_vendedora, ocultos & de_vendedora)
        # Lo de todos los días sigue ahí.
        for xmlid in ('sale.menu_sale_quotations', 'sale.menu_sale_order', 'account.menu_finance_receivables',
                      'stock.menu_stock_root', 'dcasa_base.menu_dcasa_ventas_hoy', 'dcasa_interfaz.menu_dcasa_inicio'):
            self.assertIn(xmlid, de_vendedora, xmlid)
        de_gerencia = self._menus(self.gerencia)
        for xmlid in ocultos - {'website.menu_website_configuration'}:
            self.assertIn(xmlid, de_gerencia, xmlid)

    def test_columnas_que_no_se_usan_quedan_opcionales(self):
        def opcional(modelo, campo):
            arch = self.env[modelo].with_user(self.vendedora).get_views([(False, 'list')])['views']['list']['arch']
            nodo = etree.fromstring(arch).xpath(f"//list/field[@name='{campo}']")
            self.assertTrue(nodo, f'{modelo}.{campo}')
            return nodo[0].get('optional')
        self.assertEqual(opcional('sale.order', 'activity_ids'), 'hide')
        self.assertEqual(opcional('res.partner', 'activity_ids'), 'hide')
        self.assertEqual(opcional('res.partner', 'avatar_128'), 'hide')
        self.assertEqual(opcional('product.template', 'standard_price'), 'hide')
        self.assertEqual(opcional('product.template', 'qty_available'), 'show')

    def test_sin_enriquecimiento_iap_de_la_empresa(self):
        compania = self.env.company
        if 'iap_enrich_auto_done' not in compania._fields:
            self.skipTest('partner_autocomplete no está instalado')
        compania.iap_enrich_auto_done = False
        self.env['dcasa.tablero']._dcasa_configurar_panel()
        self.assertTrue(compania.iap_enrich_auto_done)
