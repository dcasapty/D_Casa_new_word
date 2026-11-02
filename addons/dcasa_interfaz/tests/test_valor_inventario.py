"""«Valor del inventario» (pedido de la dueña, 2026-11-02): la mercancía de hoy al costo y a precio de venta sin ITBMS,
«solo para gerencia o administración».

* Al costo es la valuación de Odoo (``total_value``); a precio de venta, las unidades por el precio sin ITBMS (si a un
  producto le queda el impuesto incluido en el precio, se le quita).
* Lo negativo no suma; lo que no tiene costo o precio suma 0 y se avisa con su lista.
* La mercancía de terceros no cuenta; un producto archivado que todavía tiene existencias sí.
* Por tipo suman el total; cada cifra abre la lista de sus productos.
* La vendedora, Caja y contabilidad no lo ven: ni la conexión de datos, ni el menú, ni el atajo del Inicio.
"""
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_inicio_por_rol import VentasCommon, crear_usuario


@tagged('post_install', '-at_install')
class TestValorInventario(VentasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tipo = cls.env['product.category'].create({'name': 'TIPO VALOR INVENTARIO'})
        cls.ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)],
                                                          limit=1).lot_stock_id
        incluido = cls.env['account.tax'].create({
            'name': 'ITBMS 7% incluido valor inventario', 'amount': 7.0, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'price_include_override': 'tax_included'})
        cls.sofa = cls.crear_producto('SOFA VALOR INV', 300.0, 750.0, 2)
        cls.mesa = cls.crear_producto('MESA VALOR INV ITBMS INCLUIDO', 50.0, 107.0, 4, impuestos=incluido)
        cls.silla = cls.crear_producto('SILLA VALOR INV SIN COSTO', 0.0, 80.0, 5)
        cls.lampara = cls.crear_producto('LAMPARA VALOR INV SIN PRECIO', 20.0, 0.0, 1)
        cls.cama = cls.crear_producto('CAMA VALOR INV NEGATIVA', 200.0, 500.0, -2)
        cls.espejo = cls.crear_producto('ESPEJO VALOR INV SIN EXISTENCIAS', 10.0, 30.0, 0)
        cls.baul = cls.crear_producto('BAUL VALOR INV ARCHIVADO', 40.0, 90.0, 1)
        cls.baul.active = False
        cls.repisa = cls.crear_producto('REPISA VALOR INV DE TERCERO', 30.0, 60.0, 0)
        tercero = cls.env['res.partner'].create({'name': 'Proveedor que deja mercancía en consignación'})
        cls.env['stock.quant']._update_available_quantity(cls.repisa, cls.ubicacion, 3.0, owner_id=tercero)
        cls.caja = crear_usuario(cls.env, 'caja_valor_inventario', 'dcasa_base.group_caja')
        cls.contador = crear_usuario(cls.env, 'contador_valor_inventario', 'account.group_account_user')

    @classmethod
    def crear_producto(cls, nombre, costo, precio, unidades, impuestos=None):
        variante = cls.env['product.product'].create({
            'name': nombre, 'is_storable': True, 'categ_id': cls.tipo.id, 'standard_price': costo,
            'list_price': precio, 'taxes_id': [Command.set(impuestos.ids)] if impuestos else [Command.clear()]})
        if unidades:
            cls.env['stock.quant']._update_available_quantity(variante, cls.ubicacion, float(unidades))
        return variante

    def valor(self, usuario=None):
        return self.env['dcasa.tablero'].with_user(usuario or self.gerencia).valor_del_inventario()

    @staticmethod
    def ids(accion):
        (_campo, _op, ids), = accion['domain']
        return set(ids)

    def test_al_costo_es_la_valuacion_y_a_precio_de_venta_sin_itbms(self):
        """El tipo de la prueba: sofá 2 × 300 / 750, mesa 4 × 50 / 107 con ITBMS incluido (100 sin ITBMS), silla sin
        costo 5 × 80, lámpara sin precio 1 × 20 y el baúl archivado 1 × 40 / 90. La cama en negativo, el espejo sin
        existencias y la repisa de un tercero no cuentan."""
        # Todos los tipos a la vista: con el catálogo real cargado, el de la prueba quedaría dentro de «Otros».
        with patch('odoo.addons.dcasa_interfaz.models.inventario_valor.TIPOS_A_LA_VISTA', 1000):
            datos = self.valor()
        tipo = next(fila for fila in datos['tipos'] if fila['nombre'] == 'TIPO VALOR INVENTARIO')
        self.assertEqual(tipo['costo'], 600.0 + 200.0 + 0.0 + 20.0 + 40.0)
        self.assertEqual(tipo['venta'], 1500.0 + 400.0 + 400.0 + 0.0 + 90.0)
        self.assertEqual((tipo['unidades'], tipo['productos']), (13.0, 5))
        self.assertEqual(self.ids(tipo['accion']), {self.sofa.id, self.mesa.id, self.silla.id, self.lampara.id,
                                                    self.baul.id})
        self.assertEqual(tipo['accion']['contexto'], {'active_test': False}, 'la lista también trae el archivado')
        valorados = (self.sofa | self.mesa | self.lampara)._with_valuation_context()
        self.assertEqual(sum(valorados.mapped('total_value')), 820.0, 'al costo es la valuación de Odoo')
        total = self.ids(datos['total']['accion'])
        self.assertTrue({self.sofa.id, self.baul.id} <= total)
        self.assertFalse({self.cama.id, self.espejo.id, self.repisa.id} & total)

    def test_lo_que_falta_cargar_se_avisa_con_su_lista(self):
        avisos = self.valor()['avisos']
        self.assertIn(self.silla.id, self.ids(avisos['sin_costo']['accion']))
        self.assertIn(self.lampara.id, self.ids(avisos['sin_precio']['accion']))
        self.assertIn(self.cama.id, self.ids(avisos['negativos']['accion']))
        self.assertNotIn(self.sofa.id, self.ids(avisos['sin_costo']['accion'])
                         | self.ids(avisos['sin_precio']['accion']) | self.ids(avisos['negativos']['accion']))
        self.assertGreaterEqual(avisos['sin_costo']['monto'], 400.0, 'lo que la silla sí suma a precio de venta')
        self.assertGreaterEqual(avisos['negativos']['unidades'], 2.0, 'las unidades que faltan, en positivo')
        self.assertIsNone(avisos['negativos']['monto'])

    def test_una_entrada_nueva_suma_justo_lo_suyo(self):
        """El total de la tienda (con lo que ya hubiera) sube exactamente lo de la mercancía nueva, y el margen es la
        ganancia sobre el precio."""
        antes = self.valor()['total']
        self.crear_producto('ROPERO VALOR INV NUEVO', 10.0, 25.0, 3)
        despues = self.valor()['total']
        self.assertAlmostEqual(despues['costo'] - antes['costo'], 30.0, places=2)
        self.assertAlmostEqual(despues['venta'] - antes['venta'], 75.0, places=2)
        self.assertAlmostEqual(despues['unidades'] - antes['unidades'], 3.0, places=2)
        self.assertEqual(despues['productos'] - antes['productos'], 1)
        self.assertAlmostEqual(despues['ganancia'], despues['venta'] - despues['costo'], places=2)
        self.assertAlmostEqual(despues['margen'], round(despues['ganancia'] / despues['venta'] * 100, 1), places=1)

    def test_por_tipo_suman_el_total_y_lo_que_mas_vale_va_primero(self):
        datos = self.valor()
        self.assertAlmostEqual(sum(f['costo'] for f in datos['tipos']), datos['total']['costo'], places=2)
        self.assertAlmostEqual(sum(f['venta'] for f in datos['tipos']), datos['total']['venta'], places=2)
        costos = [f['costo'] for f in datos['productos']]
        self.assertEqual(costos, sorted(costos, reverse=True))
        self.assertLessEqual(len(datos['productos']), 10)
        self.assertTrue(datos['hora'].endswith(('a. m.', 'p. m.')))

    def test_solo_gerencia_y_los_administradores(self):
        for usuario in (self.vendedora, self.caja, self.contador):
            with self.subTest(usuario.login), self.assertRaises(AccessError):
                self.valor(usuario)
        admin = crear_usuario(self.env, 'admin_valor_inventario', 'base.group_system')
        self.assertIn('total', self.valor(admin))

    def test_el_menu_y_el_atajo_son_de_gerencia(self):
        def menus(usuario):
            cargados = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
            return {m['xmlid'] for m in cargados.values() if isinstance(m, dict) and m.get('xmlid')}

        def atajos(usuario):
            return {a['clave'] for a in self.env['dcasa.tablero'].with_user(usuario).obtener_datos()['atajos']}

        propios = {'dcasa_interfaz.menu_dcasa_valor_inventario', 'dcasa_interfaz.menu_estadisticas_valor_inventario'}
        self.assertTrue(propios <= menus(self.gerencia))
        self.assertIn('valor_inventario', atajos(self.gerencia))
        for usuario in (self.vendedora, self.caja, self.contador):
            with self.subTest(usuario.login):
                self.assertFalse(propios & menus(usuario))
                self.assertNotIn('valor_inventario', atajos(usuario))
