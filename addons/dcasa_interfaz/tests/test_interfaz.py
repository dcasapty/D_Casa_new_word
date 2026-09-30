import re

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTablero(TransactionCase):

    def test_datos_del_tablero(self):
        datos = self.env['dcasa.tablero'].obtener_datos()
        claves = {c['clave'] for c in datos['cifras']}
        self.assertTrue({'ventas_hoy', 'cobrado_hoy', 'cotizaciones', 'web', 'por_cobrar', 'entregas', 'socios'}
                        <= claves)
        self.assertEqual(len(datos['semana']), 7)
        self.assertTrue(datos['semana'][-1]['hoy'])
        for cifra in datos['cifras']:
            self.assertIn('res_model', cifra['accion'])

    def test_venta_de_hoy_suma_en_el_tablero(self):
        antes = next(c['valor'] for c in self.env['dcasa.tablero'].obtener_datos()['cifras']
                     if c['clave'] == 'ventas_hoy')
        producto = self.env['product.product'].create({'name': 'Mesa tablero', 'list_price': 100})
        orden = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Cliente tablero'}).id,
            'order_line': [(0, 0, {'product_id': producto.id})],
        })
        orden.action_confirm()
        despues = next(c['valor'] for c in self.env['dcasa.tablero'].obtener_datos()['cifras']
                       if c['clave'] == 'ventas_hoy')
        self.assertAlmostEqual(despues - antes, orden.amount_total, places=2)

    def test_vendedora_sin_contabilidad_ve_su_tablero(self):
        vendedora = self.env['res.users'].create({
            'name': 'Vendedora', 'login': 'vendedora_tablero',
            'group_ids': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id])],
        })
        datos = self.env['dcasa.tablero'].with_user(vendedora).obtener_datos()
        self.assertTrue(datos['cifras'])

    def test_inicio_sin_recorrido_ni_odoobot(self):
        admin = self.env.ref('base.user_admin')
        self.assertEqual(admin.action_id.id, self.env.ref('dcasa_interfaz.action_dcasa_inicio').id)
        self.assertFalse(admin.tour_enabled)
        self.assertEqual(admin.odoobot_state, 'disabled')
        nuevo = self.env['res.users'].create({'name': 'Nueva', 'login': 'nueva_tablero'})
        self.assertFalse(nuevo.tour_enabled)

    def test_apps_con_iconos_propios(self):
        for xmlid in ('sale.sale_menu_root', 'stock.menu_stock_root', 'dcasa_interfaz.menu_dcasa_inicio'):
            menu = self.env.ref(xmlid)
            self.assertTrue(menu.web_icon.startswith('dcasa_interfaz,'), xmlid)
            self.assertTrue(menu.web_icon_data, xmlid)

    def test_catalogo_de_apps_sin_modulos_de_pago(self):
        self.assertIn('to_buy', self.env.ref('base.open_module_tree').domain)


@tagged('post_install', '-at_install')
class TestInterfazWeb(HttpCase):

    def test_login_sin_odoo(self):
        html = self.url_open('/web/login').text
        self.assertNotIn('Powered by', html)
        self.assertIn("D'CASA", html.replace('&#39;', "'"))

    def test_bundle_backend_con_la_marca(self):
        self.authenticate('admin', 'admin')
        html = self.url_open('/odoo').text
        css = re.findall(r'href="([^"]*web\.assets_web[^"]*\.css)"', html)
        self.assertTrue(css, 'El backend enlaza su CSS')
        contenido = self.url_open(css[0]).text
        self.assertIn('o_dcasa_inicio', contenido)
        self.assertIn('o_dcasa_en_desarrollo', contenido)
        self.assertNotIn('css error', contenido.lower())
