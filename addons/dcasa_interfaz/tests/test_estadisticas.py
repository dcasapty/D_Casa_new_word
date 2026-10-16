"""Estadísticas del negocio, íconos con color y categoría Envíos (pedido del jefe, 2026-10-16)."""
import base64
import re

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools.misc import file_path
from odoo.tools.safe_eval import safe_eval

from .test_inicio_por_rol import VentasCommon

# Un color por familia (decisión de la dueña, 2026-10-16). El amarillo de la marca nunca es de fondo.
FAMILIAS = {
    'azul': '#1340B1', 'verde': '#0B6E6E', 'naranja': '#B4531A', 'cielo': '#1E6FC0', 'indigo': '#4B3FA8',
}
ICONOS = {
    'dcasa_interfaz/static/src/img/iconos/ventas.svg': 'azul',
    'dcasa_interfaz/static/src/img/iconos/crm.svg': 'azul',
    'dcasa_interfaz/static/src/img/iconos/contactos.svg': 'azul',
    'dcasa_interfaz/static/src/img/iconos/estadisticas.svg': 'azul',
    'dcasa_interfaz/static/src/img/iconos/facturacion.svg': 'verde',
    'dcasa_interfaz/static/src/img/iconos/contabilidad.svg': 'verde',
    'dcasa_nomina/static/src/img/nomina.svg': 'verde',
    'dcasa_interfaz/static/src/img/iconos/inventario.svg': 'naranja',
    'dcasa_interfaz/static/src/img/iconos/compras.svg': 'naranja',
    'dcasa_interfaz/static/src/img/iconos/envios.svg': 'naranja',
    'dcasa_interfaz/static/src/img/iconos/sitio_web.svg': 'cielo',
    'dcasa_conversaciones/static/description/icon.svg': 'cielo',
    'dcasa_interfaz/static/src/img/iconos/socios.svg': 'indigo',
    'dcasa_equipo/static/src/img/empleados.svg': 'indigo',
}


@tagged('post_install', '-at_install')
class TestEstadisticas(VentasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendida = cls.env['product.product'].create({
            'name': 'Cama estadística vendida', 'list_price': 200.0, 'standard_price': 120.0, 'is_storable': True})
        cls.sin_costo = cls.env['product.product'].create({
            'name': 'Silla estadística sin costo', 'list_price': 50.0, 'standard_price': 0.0})
        cls.parada = cls.env['product.product'].create({
            'name': 'Mesa estadística parada', 'list_price': 90.0, 'standard_price': 40.0, 'is_storable': True})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.parada, almacen.lot_stock_id, 4.0)
        cls.env['stock.quant']._update_available_quantity(cls.vendida, almacen.lot_stock_id, 50.0)

    def _menus(self, usuario):
        menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
        return {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

    def test_el_menu_de_estadisticas_es_solo_de_gerencia(self):
        propios = {'dcasa_interfaz.menu_estadisticas', 'dcasa_interfaz.menu_estadisticas_mas_vendido',
                   'dcasa_interfaz.menu_estadisticas_margen', 'dcasa_interfaz.menu_estadisticas_sin_movimiento'}
        self.assertTrue(propios <= self._menus(self.gerencia))
        self.assertFalse(propios & self._menus(self.vendedora))

    def test_lo_mas_vendido_cuenta_lo_facturado_y_no_las_cotizaciones(self):
        vendido = self.pedido(producto=self.vendida, cantidad=3)
        self.facturar(vendido)
        cotizacion = self.pedido(producto=self.vendida, cantidad=9, confirmar=False)
        accion = self.env.ref('dcasa_interfaz.accion_mas_vendido')
        lineas = self.env['sale.order.line'].with_user(self.gerencia).search(safe_domain(accion.domain))
        self.assertIn(vendido.order_line, lineas)
        self.assertNotIn(cotizacion.order_line, lineas)
        grupos = self.env['sale.order.line'].with_user(self.gerencia).read_group(
            safe_domain(accion.domain) + [('product_id', '=', self.vendida.id)], ['product_uom_qty:sum'], [])
        self.assertGreaterEqual(grupos[0]['product_uom_qty'], 3)

    def test_mejor_margen_deja_fuera_la_mercancia_sin_costo(self):
        con_costo = self.pedido(producto=self.vendida)
        self.facturar(con_costo)
        sin_costo = self.pedido(producto=self.sin_costo)
        self.facturar(sin_costo)
        accion = self.env.ref('dcasa_interfaz.accion_mejor_margen')
        lineas = self.env['sale.order.line'].with_user(self.gerencia).search(safe_domain(accion.domain))
        self.assertIn(con_costo.order_line, lineas)
        self.assertNotIn(sin_costo.order_line, lineas)
        self.assertAlmostEqual(
            sum(lineas.filtered(lambda linea: linea == con_costo.order_line).mapped('dcasa_utilidad')),
            con_costo.order_line.price_subtotal - 120.0, places=2)

    def test_lo_que_no_se_mueve_lista_lo_que_tiene_existencias_y_no_se_vende(self):
        vendido = self.pedido(producto=self.vendida)
        self.facturar(vendido)
        accion = self.env['product.product'].with_user(self.gerencia).dcasa_accion_sin_movimiento()
        productos = self.env['product.product'].with_user(self.gerencia).search(accion['domain'])
        self.assertIn(self.parada, productos)
        self.assertNotIn(self.vendida, productos, 'se vendió: sí se mueve')

    def test_lo_que_no_se_mueve_es_solo_de_gerencia(self):
        with self.assertRaises(AccessError):
            self.env['product.product'].with_user(self.vendedora).dcasa_accion_sin_movimiento()

    def test_el_menu_de_estadisticas_abre_sin_errores_para_gerencia(self):
        for xmlid in ('accion_mas_vendido', 'accion_mejor_margen'):
            accion = self.env.ref(f'dcasa_interfaz.{xmlid}').with_user(self.gerencia)
            vistas = self.env['sale.order.line'].with_user(self.gerencia).get_views(
                [(False, 'pivot'), (False, 'graph'), (False, 'list'), (False, 'search')])
            self.assertTrue(vistas['views'], xmlid)
            self.assertEqual(accion.res_model, 'sale.order.line')

    # --- Íconos con color ---------------------------------------------------------------------

    def test_cada_icono_lleva_el_color_de_su_familia(self):
        for ruta, familia in ICONOS.items():
            with open(file_path(ruta), encoding='utf-8') as archivo:
                fondo = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', archivo.read()).group(1).upper()
            with self.subTest(ruta=ruta):
                self.assertEqual(fondo, FAMILIAS[familia], 'el fondo es el color de la familia')
                self.assertNotEqual(fondo, '#FED00F', 'el amarillo nunca es de fondo: tocaría el blanco de la barra')

    def test_actualizar_vuelve_a_leer_el_archivo_del_icono(self):
        """Odoo solo guarda la imagen al escribir ``web_icon``: un ícono recoloreado seguiría igual sin este paso."""
        menu = self.env.ref('dcasa_interfaz.menu_estadisticas')
        menu.web_icon_data = base64.b64encode(b'<svg>viejo</svg>')
        self.env['dcasa.tablero']._dcasa_refrescar_iconos()
        menu.invalidate_recordset()
        esperado = self.env['ir.ui.menu']._compute_web_icon_data(menu.web_icon)
        self.assertEqual(base64.b64decode(menu.web_icon_data), base64.b64decode(esperado))


def safe_domain(dominio):
    return safe_eval(dominio) if isinstance(dominio, str) else dominio

