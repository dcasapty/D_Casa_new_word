"""Ola 2 · «Resumir»: unas líneas de lo que pasó en la conversación, para quien la recibe. Se pide al apretar el botón,
se guarda en la conversación y no gasta IA si ya cubre el último mensaje."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import tagged

from .common import URL_WORKER, JuanCase, respuesta_http

RESUMEN = '• Busca una cama queen.\n• Le dijeron que cuesta $499.00 + ITBMS.'


@tagged('post_install', '-at_install')
class TestResumenIA(JuanCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.worker.return_value = respuesta_http(
            {'ok': True, 'texto': RESUMEN, 'avisos': [], 'modelo': 'claude-haiku-4-5'})
        self.conv = self.conversacion('Hola, busco una cama queen', nombre='Karen', id_externo='50761000001')
        self.registrar('La Milán queen cuesta $499.00 + ITBMS', id_externo='50761000001', autor='bot')
        self.panel = self.Conversacion.with_user(self.vendedora)

    def pedidos(self):
        return [c for c in self.worker.call_args_list if c.args[1] == f'{URL_WORKER}/odoo/resumir']

    def test_resume_guarda_y_devuelve(self):
        r = self.panel.resumir_conversacion(self.conv.id)
        self.assertEqual(r['texto'], RESUMEN)
        self.assertTrue(r['vigente'])
        self.assertFalse(r['desde_cache'])
        self.assertEqual(self.conv.resumen_ia, RESUMEN)
        self.assertEqual(self.conv.resumen_ia_hasta_id, max(self.conv.mensaje_ids.ids))
        (pedido,) = self.pedidos()
        cuerpo = pedido.kwargs['json']
        self.assertEqual((cuerpo['conversacion_id'], cuerpo['canal'], cuerpo['nombre']),
                         (self.conv.id, 'whatsapp_qr', 'Karen'))
        self.assertEqual([(m['autor'], m['texto']) for m in cuerpo['mensajes']],
                         [('cliente', 'Hola, busco una cama queen'),
                          ('asistente', 'La Milán queen cuesta $499.00 + ITBMS')])

    def test_si_ya_cubre_el_ultimo_mensaje_no_gasta_otra_vez(self):
        self.panel.resumir_conversacion(self.conv.id)
        r = self.panel.resumir_conversacion(self.conv.id)
        self.assertTrue(r['desde_cache'])
        self.assertEqual(len(self.pedidos()), 1)

    def test_con_un_mensaje_nuevo_se_actualiza_pero_no_antes_de_un_minuto(self):
        self.panel.resumir_conversacion(self.conv.id)
        self.registrar('Y tienen la gris?', id_externo='50761000001')
        r = self.panel.resumir_conversacion(self.conv.id)
        self.assertTrue(r['desde_cache'], 'Hace segundos que se pidió: se devuelve el guardado')
        self.assertFalse(r['vigente'], 'Pero se avisa que ya no cubre el último mensaje')
        self.assertEqual(len(self.pedidos()), 1)
        futuro = fields.Datetime.now() + timedelta(seconds=61)
        with patch.object(fields.Datetime, 'now', return_value=futuro):
            r = self.panel.resumir_conversacion(self.conv.id)
        self.assertFalse(r['desde_cache'])
        self.assertTrue(r['vigente'])
        self.assertEqual(len(self.pedidos()), 2)

    def test_regenerar_pide_otro_resumen_pasado_el_minuto(self):
        self.panel.resumir_conversacion(self.conv.id)
        self.panel.resumir_conversacion(self.conv.id, True)
        self.assertEqual(len(self.pedidos()), 1, 'Menos de un minuto: no se insiste')
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.now() + timedelta(seconds=61)):
            self.panel.resumir_conversacion(self.conv.id, True)
        self.assertEqual(len(self.pedidos()), 2)

    def test_no_viajan_notas_avisos_programados_ni_el_texto_de_un_archivo_sensible(self):
        self.Mensaje._crear_interno(self.conv, 'nota', 'Ojo: es cliente difícil', self.vendedora)
        self.Mensaje._crear_interno(self.conv, 'aviso', 'Ana tomó la conversación')
        programado = self.Mensaje.sudo().create({
            'conversacion_id': self.conv.id, 'id_mensaje': 'odoo-programado-1', 'tipo': 'mensaje',
            'direccion': 'saliente', 'autor': 'vendedora', 'texto': 'Esto sale mañana', 'origen': 'odoo',
            'estado_envio': 'programado', 'programado_para': fields.Datetime.now() + timedelta(days=1)})
        sensible = self.registrar('Aquí está mi cédula 8-123-4567', id_externo='50761000001')[1]
        sensible.sudo().with_context(dcasa_mensaje_sistema=True).tiene_sensible = True
        self.panel.resumir_conversacion(self.conv.id)
        textos = ' | '.join(m['texto'] for m in self.pedidos()[0].kwargs['json']['mensajes'])
        self.assertNotIn('cliente difícil', textos)
        self.assertNotIn('tomó la conversación', textos)
        self.assertNotIn('sale mañana', textos)
        self.assertNotIn('8-123-4567', textos)
        self.assertIn('[archivo sensible', textos)
        self.assertTrue(programado.exists())

    def test_lee_hasta_60_mensajes_los_mas_recientes(self):
        for n in range(70):
            self.registrar(f'Mensaje número {n}', id_externo='50761000001')
        self.panel.resumir_conversacion(self.conv.id)
        mensajes = self.pedidos()[0].kwargs['json']['mensajes']
        self.assertEqual(len(mensajes), 60)
        self.assertEqual(mensajes[-1]['texto'], 'Mensaje número 69')

    def test_errores_claros_y_no_se_guarda_nada(self):
        self.ajustes.resumen_ia_activo = False
        with self.assertRaisesRegex(UserError, 'apagado'):
            self.panel.resumir_conversacion(self.conv.id)
        self.ajustes.resumen_ia_activo = True
        for cuerpo in ({'ok': False, 'error': 'Falta ANTHROPIC_API_KEY'}, {'ok': True, 'texto': '   '}):
            self.worker.return_value = respuesta_http(cuerpo)
            with self.assertRaisesRegex(UserError, 'No pude resumir'):
                self.panel.resumir_conversacion(self.conv.id)
        self.assertFalse(self.conv.resumen_ia)

    def test_sin_worker_configurado_lo_dice(self):
        with patch.dict('os.environ', {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}), \
                self.assertRaisesRegex(UserError, 'Falta conectar el bot'):
            self.panel.resumir_conversacion(self.conv.id)

    def test_conversacion_sin_mensajes_o_sin_nada_del_cliente(self):
        vacia = self.Conversacion.sudo().create({'canal': 'telegram', 'id_externo': '999'})
        with self.assertRaisesRegex(UserError, 'no hay mensajes'):
            self.panel.resumir_conversacion(vacia.id)
        solo_bot = self.registrar('Hola, soy el asistente', id_externo='555', autor='bot', canal='telegram')[0]
        with self.assertRaisesRegex(UserError, 'nada del cliente'):
            self.panel.resumir_conversacion(solo_bot.id)

    def test_valida_lo_que_recibe_y_exige_ser_de_ventas(self):
        for malo in (0, -1, 'x', 99999999):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel.resumir_conversacion(malo)
        with self.assertRaises(UserError):
            self.panel.resumir_conversacion(self.conv.id, 'si')
        for usuario in (self.interno, self.portal):
            with self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'resumir_conversacion', [self.conv.id], {})

    def test_el_hilo_trae_el_resumen_guardado_y_si_sigue_al_dia(self):
        self.assertIsNone(self.panel.hilo(self.conv.id)['resumen_ia'])
        self.panel.resumir_conversacion(self.conv.id)
        guardado = self.panel.hilo(self.conv.id)['resumen_ia']
        self.assertEqual((guardado['texto'], guardado['vigente']), (RESUMEN, True))
        self.registrar('Una más', id_externo='50761000001')
        self.assertFalse(self.panel.hilo(self.conv.id)['resumen_ia']['vigente'])
        antes = self.panel.hilo(self.conv.id)['primer_id']
        viejo = self.panel.hilo(self.conv.id, antes_de_id=antes + 1)
        self.assertIsNone(viejo['resumen_ia'], 'Un tramo viejo no lo trae')

    def test_el_resumen_se_borra_con_la_conversacion(self):
        self.panel.resumir_conversacion(self.conv.id)
        self.conv.sudo().unlink()
        self.assertFalse(self.Conversacion.search([('id_externo', '=', '50761000001')]))

    def test_tambien_la_sugerencia_deja_fuera_lo_programado(self):
        self.Mensaje.sudo().create({
            'conversacion_id': self.conv.id, 'id_mensaje': 'odoo-programado-2', 'tipo': 'mensaje',
            'direccion': 'saliente', 'autor': 'vendedora', 'texto': 'Todavía no salió', 'origen': 'odoo',
            'estado_envio': 'programado', 'programado_para': fields.Datetime.now() + timedelta(days=1)})
        textos = [m['texto'] for m in self.conv._mensajes_para_sugerir()]
        self.assertNotIn('Todavía no salió', textos)
