"""D1 con Brian: la clave del descuento llega por Telegram a Gerencia (a cada quien la suya), la vendedora la usa por
Brian o en pantalla, Gerencia decide por Brian; y los saldos de centavos."""
import os
import re
from unittest.mock import patch

from odoo import Command
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.addons.dcasa_brian.models.telegram import BrianTelegramEnlace
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAutorizacionesBrian(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env['ir.config_parameter'].sudo().set_param('dcasa.descuento_max_vendedora', '10')
        cls.vendedora = crear_usuario(env, 'aut_vendedora', 'dcasa_base.group_vendedora')
        cls.gerente = crear_usuario(env, 'aut_gerente', 'dcasa_base.group_gerencia')
        cls.otro_gerente = crear_usuario(env, 'aut_gerente2', 'dcasa_base.group_gerencia')
        cls.enlace = env['brian.telegram.enlace'].create({'user_id': cls.gerente.id, 'chat_id': '777001'})
        cls.cliente = env['res.partner'].create({
            'name': 'CLIENTE DE PRUEBA AUTORIZA', 'phone': '6000-0051', 'email': 'cliente.autoriza@example.com'})
        cls.producto = env['product.product'].create({'name': 'Sala autoriza', 'list_price': 500.0,
                                                      'taxes_id': [Command.clear()]})

    def setUp(self):
        super().setUp()
        self.enviados = []
        prueba = self

        def _api(enlace, metodo, datos=None):
            prueba.enviados.append(datos or {})
            return {'message_id': len(prueba.enviados)}

        parche = patch.object(BrianTelegramEnlace, '_api', autospec=True, side_effect=_api)
        parche.start()
        self.addCleanup(parche.stop)
        entorno = patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'token-de-prueba', 'BRIAN_TELEGRAM_CHATS': ''})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 2})]})

    def ejecutar(self, usuario, nombre, argumentos=None):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar(nombre, argumentos or {})

    def ok(self, respuesta):
        self.assertTrue(respuesta.get('ok'), respuesta)
        return respuesta['datos']

    def test_la_clave_llega_por_telegram_y_se_usa_por_brian(self):
        datos = self.ok(self.ejecutar(self.vendedora, 'pedir_descuento_a_gerencia', {
            'cotizacion': self.orden.name, 'porcentaje': 20, 'motivo': 'Lleva dos salas'}))
        self.assertIn(self.gerente.name, datos['mensaje'])
        self.assertEqual(len(self.enviados), 1, 'solo el gerente con Telegram vinculado recibe mensaje')
        mensaje = self.enviados[0]
        self.assertEqual(mensaje['chat_id'], '777001')
        self.assertIn(self.orden.name, mensaje['text'])
        self.assertIn('$1,000.00 → $800.00', mensaje['text'])
        self.assertIn('Lleva dos salas', mensaje['text'])
        clave = re.search(r'Tu clave: (\d{6})', mensaje['text']).group(1)
        respuesta = self.ejecutar(self.vendedora, 'aplicar_descuento_con_clave',
                                  {'cotizacion': self.orden.name, 'clave': '000000' if clave != '000000' else '1'})
        self.assertFalse(respuesta['ok'])
        datos = self.ok(self.ejecutar(self.vendedora, 'aplicar_descuento_con_clave',
                                      {'cotizacion': self.orden.name, 'clave': clave}))
        self.assertEqual(datos['autorizo'], self.gerente.name)
        self.assertAlmostEqual(self.orden.amount_total, 800.0, places=2)

    def test_sin_telegram_se_pide_en_persona_y_gerencia_decide_por_brian(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': ''}):
            datos = self.ok(self.ejecutar(self.vendedora, 'pedir_descuento_a_gerencia', {
                'cotizacion': self.orden.name, 'monto': 150, 'motivo': 'Cliente de siempre'}))
        self.assertIn('en persona', datos['mensaje'])
        self.assertFalse(self.enviados)
        lista = self.ok(self.ejecutar(self.gerente, 'descuentos_por_autorizar'))
        self.assertEqual(lista['descuentos'][0]['cotizacion'], self.orden.name)
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('decidir_descuento', nombres)
        respuesta = self.ejecutar(self.gerente, 'decidir_descuento',
                                  {'cotizacion': self.orden.name, 'decision': 'aprobar'})
        self.assertTrue(respuesta.get('requiere_confirmacion'), respuesta)
        self.env['brian.herramientas'].with_user(self.gerente).confirmar(respuesta['accion_id'])
        self.assertAlmostEqual(self.orden.amount_total, 850.0, places=2)

    def test_abonos_por_vencer_para_caja_y_gerencia(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('abonos_por_vencer', nombres)
        datos = self.ok(self.ejecutar(self.gerente, 'abonos_por_vencer'))
        self.assertEqual(datos['dias_de_aviso'], 5)

    def test_saldos_de_centavos_solo_gerencia_o_contabilidad(self):
        nombres = {h['name'] for h in self.env['brian.herramientas'].with_user(self.vendedora).catalogo()}
        self.assertNotIn('saldos_de_centavos', nombres)
        self.assertNotIn('cerrar_saldos_de_centavos', nombres)
        datos = self.ok(self.ejecutar(self.gerente, 'saldos_de_centavos'))
        self.assertIn('cuantos', datos)
