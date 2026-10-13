"""Los ejemplos de staging: solo con existencias de prueba, solo Gerencia, sin precios inventados, repetibles."""
import re

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models.ejemplos import EJEMPLOS
from .common import JuanCase

PARAM = 'dcasa_catalogo.stock_prueba'


@tagged('post_install', '-at_install')
class TestEjemplos(JuanCase):

    def _ajustes(self, usuario=None):
        return self.env['dcasa.juan.ajustes'].with_user(usuario or self.gerente).obtener()

    def test_en_produccion_se_niega(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '0')
        with self.assertRaisesRegex(UserError, 'entorno de prueba'):
            self._ajustes().action_cargar_ejemplos()
        self.assertFalse(self.env['dcasa.conversacion'].sudo().search([('id_externo', '=like', '5076000000%')]))

    def test_solo_gerencia(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '1')
        with self.assertRaises(AccessError):
            self._ajustes().with_user(self.vendedora).action_cargar_ejemplos()

    def test_carga_cuatro_conversaciones_y_es_repetible(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '1')
        ajustes = self._ajustes()
        ajustes.action_cargar_ejemplos()
        ajustes.action_cargar_ejemplos()
        conversaciones = self.env['dcasa.conversacion'].sudo().search([('id_externo', '=like', '5076000000%')])
        self.assertEqual(len(conversaciones), 4)
        self.assertEqual(len(conversaciones.mapped('mensaje_ids').filtered(lambda m: m.tipo != 'nota')),
                         sum(len(e[5]) for e in EJEMPLOS))
        humano = conversaciones.filtered(lambda c: c.estado == 'humano')
        self.assertEqual(len(humano), 1)
        self.assertEqual(humano.asignada_a, self.gerente)
        self.assertTrue(all('(ejemplo)' in c.partner_id.name for c in conversaciones))

    def test_los_textos_no_traen_precios_ni_cifras_inventadas(self):
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '1')
        self._ajustes().action_cargar_ejemplos()
        textos = ' '.join(self.env['dcasa.mensaje'].sudo().search(
            [('conversacion_id.id_externo', '=like', '5076000000%')]).mapped('texto'))
        # Solo cifras del programa Socios (1 punto por $1, 100 puntos = $1); nada de precios de productos.
        self.assertFalse(re.findall(r'\$\s?\d{2,}', textos))

    def test_el_boton_solo_se_ve_en_prueba(self):
        ajustes = self._ajustes()
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '0')
        ajustes.invalidate_recordset()
        self.assertFalse(ajustes.es_entorno_de_prueba)
        self.env['ir.config_parameter'].sudo().set_param(PARAM, '1')
        ajustes.invalidate_recordset()
        self.assertTrue(ajustes.es_entorno_de_prueba)
