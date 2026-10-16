"""La prueba de humo del arranque (incidente del 2026-10-16, #97).

Detecta el código nuevo sobre la base sin actualizar."""
import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from ..models.humo import PARAM_HUMO


@tagged('post_install', '-at_install')
class TestHumo(TransactionCase):

    def test_con_la_base_al_dia_todo_sale_bien(self):
        resultado = self.env['dcasa.humo']._revisar()
        self.assertEqual(resultado, {'ok': True, 'columnas_faltantes': [], 'modulos': [], 'errores': []})
        self.assertEqual(json.loads(self.env['ir.config_parameter'].sudo().get_param(PARAM_HUMO)), resultado)

    def test_una_columna_que_falta_se_detecta_como_en_produccion(self):
        """Lo de producción: el campo existe en el código y su columna no en la base."""
        self.env.cr.execute('ALTER TABLE sale_order RENAME COLUMN dcasa_utilidad TO dcasa_utilidad_x')
        self.env.invalidate_all()
        resultado = self.env['dcasa.humo']._revisar()
        self.assertFalse(resultado['ok'])
        self.assertIn('sale.order.dcasa_utilidad', resultado['columnas_faltantes'])
        self.assertIn('dcasa_base', resultado['modulos'], 'el arranque actualiza el módulo que define el campo')
        self.assertEqual(resultado['errores'], [],
                         'con columnas faltantes no se prueban pantallas: primero se actualiza')

    def test_una_pantalla_que_falla_se_informa_sin_romper_la_transaccion(self):
        def falla(env):
            env.cr.execute('SELECT columna_que_no_existe FROM sale_order')

        def cotizaciones(env):
            env['sale.order'].search_read([], limit=1)

        def sin_mensaje(env):
            raise AssertionError

        pruebas = [('Pantalla rota', falla), ('Cotizaciones', cotizaciones), ('Sin mensaje', sin_mensaje)]
        # «bad query» de odoo.sql_db es un ERROR en el log, y scripts/test.sh y la CI fallan con cualquier ERROR.
        with patch.object(type(self.env['dcasa.humo']), '_pruebas_de_pantallas', lambda self: pruebas), \
                mute_logger('odoo.sql_db'):
            resultado = self.env['dcasa.humo']._revisar()
        self.assertFalse(resultado['ok'])
        self.assertEqual(len(resultado['errores']), 2)
        self.assertIn('Pantalla rota: UndefinedColumn', resultado['errores'][0])
        self.assertEqual(resultado['errores'][1], 'Sin mensaje: AssertionError: ',
                         'un error sin texto también se informa')
        # La transacción sigue usable: el resto de la prueba y lo que venga después funcionan.
        self.env['res.partner'].search([], limit=1)

    def test_las_pantallas_se_arman_de_verdad_y_no_dejan_nada(self):
        antes = self.env['sale.order'].search_count([])
        errores = self.env['dcasa.humo']._pantallas()
        self.assertEqual(errores, [])
        self.assertEqual(self.env['sale.order'].search_count([]), antes)
        nombres = [nombre for nombre, _prueba in self.env['dcasa.humo']._pruebas_de_pantallas()]
        self.assertIn('Cotizaciones', nombres)

    def test_lee_solo_las_columnas_de_la_lista(self):
        """No lee todo el registro: ni la firma ni otros adjuntos que viven en R2 (un corte de R2 no es «humo»)."""
        leidos = []
        original = type(self.env['sale.order']).search_read

        def espia(modelo, domain=None, fields=None, *args, **kwargs):
            leidos.append(list(fields or []))
            return original(modelo, domain, fields, *args, **kwargs)

        with patch.object(type(self.env['sale.order']), 'search_read', espia):
            self.env['dcasa.humo']._leer_la_lista(self.env, 'sale.order')
        self.assertTrue(leidos and leidos[0], 'pide campos concretos, no todos')
        self.assertIn('name', leidos[0])
        self.assertNotIn('signature', leidos[0])
