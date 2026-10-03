"""Premio de ejemplo de la dueña (03/10/2026): «Dos almohadas» por 400 puntos.

Las cifras viven en data/premios_data.xml (el catálogo es inventario, no economía del programa).
"""
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models import reglas as R
from .test_socios_web import CarritoCommon


@tagged('post_install', '-at_install')
class TestPremioEjemploAlmohadas(CarritoCommon):

    def ejemplo(self):
        return self.env.ref('dcasa_socios.premio_ejemplo_almohadas')

    def recrear(self):
        """Vuelve a correr la función de datos como en una base nueva."""
        self.ejemplo().unlink()
        self.env['ir.config_parameter'].sudo().set_param('dcasa_socios.ejemplo_almohadas_creado', False)
        return self.env['dcasa.premio']._crear_ejemplo_almohadas('Dos almohadas', 400, 'ALMOHADA001', 2)

    def test_se_crea_al_instalar_editable_y_en_el_catalogo(self):
        premio = self.ejemplo()
        self.assertEqual((premio.name, premio.puntos, premio.tipo, premio.cantidad),
                         ('Dos almohadas', 400, 'producto', 2))
        self.assertTrue(premio.active)
        self.assertIn(premio, self.env['dcasa.premio']._catalogo())
        datos = self.env['ir.model.data'].search([('module', '=', 'dcasa_socios'),
                                                  ('name', '=', 'premio_ejemplo_almohadas')])
        self.assertTrue(datos.noupdate, 'Gerencia lo edita sin que una actualización se lo pise')

    def test_ligado_al_producto_si_existe(self):
        producto = self.env['product.product'].search([('default_code', '=', 'ALMOHADA001')], limit=1) \
            or self.env['product.product'].create({
                'name': 'ALMOHADA MICRO GEL (prueba)', 'default_code': 'ALMOHADA001',
                'list_price': 3.99, 'standard_price': 1.89})
        premio = self.recrear()
        self.assertEqual(premio.product_id, producto)
        self.assertAlmostEqual(premio.valor, producto.lst_price * 2, places=2)
        self.assertAlmostEqual(premio.costo, producto.standard_price * 2, places=2)
        self.assertEqual(self.ejemplo(), premio, 'el xmlid apunta al premio nuevo')

    def test_sin_el_producto_se_crea_igual_y_no_falla(self):
        self.env['product.product'].search([('default_code', '=', 'ALMOHADA001')]).action_archive()
        premio = self.recrear()
        self.assertTrue(premio)
        self.assertFalse(premio.product_id)
        self.assertFalse(premio.descripcion, 'el socio no ve notas internas en el catálogo')
        self.assertEqual((premio.valor, premio.costo, premio.puntos, premio.cantidad), (0, 0, 400, 2))

    def test_se_crea_una_sola_vez(self):
        self.ejemplo().action_archive()
        otra = self.env['dcasa.premio']._crear_ejemplo_almohadas('Dos almohadas', 400, 'ALMOHADA001', 2)
        self.assertFalse(otra, 'si Gerencia lo archivó o borró, una actualización no lo resucita')
        self.assertEqual(self.env['dcasa.premio'].with_context(active_test=False).search_count(
            [('name', '=', 'Dos almohadas')]), 1)

    def test_el_minimo_de_puntos_json_se_aplica_al_premio_no_al_saldo(self):
        """COMPORTAMIENTO ACTUAL (pendiente de la dueña): saldoMinimoParaCanjear se compara contra los
        puntos DEL PREMIO, no contra el saldo. Con el mínimo de puntos.json por encima de 400, nadie
        puede pedir las almohadas aunque le sobre saldo."""
        minimo = R.cargar_reglas()['canje']['saldoMinimoParaCanjear']
        premio = self.ejemplo()
        self.assertGreater(self.socia.dcasa_saldo, max(minimo, premio.puntos))
        if premio.puntos < minimo:
            with self.assertRaisesRegex(UserError, 'El canje mínimo es de'):
                self.env['dcasa.canje']._pedir(self.socia, premio)
            self.assertEqual(self.socia.dcasa_saldo, 1500, 'no se tocó el saldo')
        else:
            canje = self.env['dcasa.canje']._pedir(self.socia, premio)
            self.assertEqual(canje.puntos, premio.puntos)

    def test_premio_de_producto_no_entra_en_el_carrito(self):
        orden = self.carrito()
        with self.assertRaisesRegex(UserError, 'no se puede usar en la tienda web'):
            orden._dcasa_usar_puntos_web(premio=self.ejemplo())
