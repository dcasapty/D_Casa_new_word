"""Ajustes de Juan: los valores por defecto SON las decisiones de la dueña; los secretos no se guardan."""
import os
from datetime import time
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TOKEN_ODOO, TOKEN_WORKER, URL_WORKER, JuanCase, respuesta_http


@tagged('post_install', '-at_install')
class TestAjustesPorDefecto(JuanCase):

    def test_decisiones_de_la_duena(self):
        a = self.ajustes
        self.assertEqual(a.nombre_publico, "el equipo de D'CASA")
        self.assertTrue(a.bot_activo_global)
        # Horario laboral: 8:00 a 17:00, todos los días, hora de Panamá.
        horario = a.horario()
        self.assertEqual((horario.inicio, horario.fin), (time(8, 0), time(17, 0)))
        self.assertEqual(horario.dias, frozenset(range(7)))
        self.assertEqual(horario.zona, 'America/Panama')
        # Seguimiento: 5 h, 5 días, máximo 2, solo en horario laboral.
        regla = a.regla_seguimiento()
        self.assertEqual((regla.primero_horas, regla.segundo_dias, regla.maximo, regla.solo_horario_laboral),
                         (5, 5, 2, True))
        self.assertEqual(a.presupuesto_ia_mensual_usd, 30)
        self.assertEqual(a.modelo_rapido, 'claude-haiku-4-5')
        self.assertEqual(a.modelo_inteligente, 'claude-sonnet-5-5')
        self.assertEqual(a.pausa_por_defecto_minutos, 120)

    def test_canales_por_defecto(self):
        self.assertEqual(self.ajustes.canales_activos(), {
            'whatsapp_qr': True, 'telegram': True,
            'whatsapp_cloud': False, 'messenger': False, 'instagram': False})   # plan B y Meta apagados

    def test_json_exacto_del_contrato(self):
        datos = self.ajustes.como_json()
        self.assertEqual(set(datos), {
            'nombre_publico', 'bot_activo_global', 'canales_activos', 'horario', 'seguimiento',
            'presupuesto_ia_mensual_usd', 'proveedor_ia', 'proveedor_respaldo_ia', 'modelo_rapido',
            'modelo_inteligente', 'modelos_por_defecto', 'precios', 'precios_ia', 'lecciones', 'mensaje_bienvenida',
            'texto_privacidad_corto', 'palabras_prohibidas', 'pausa_por_defecto_minutos'})
        self.assertEqual(datos['horario'], {'inicio': '08:00', 'fin': '17:00', 'dias': [0, 1, 2, 3, 4, 5, 6],
                                            'zona': 'America/Panama'})
        self.assertEqual(datos['seguimiento'], {'primero_horas': 5, 'segundo_dias': 5,
                                                'solo_horario_laboral': True, 'maximo': 2})
        self.assertEqual(datos['presupuesto_ia_mensual_usd'], 30)
        self.assertEqual(set(datos['canales_activos']), {'whatsapp_qr', 'whatsapp_cloud', 'telegram', 'messenger',
                                                         'instagram'})
        self.assertIsInstance(datos['palabras_prohibidas'], list)
        self.assertIn('remate', datos['palabras_prohibidas'])

    def test_textos_en_la_voz_de_la_marca(self):
        bienvenida = self.ajustes.mensaje_bienvenida
        self.assertIn('asistente automático', bienvenida)
        self.assertIn('*persona*', bienvenida)       # ofrece una persona
        self.assertNotIn('remate', bienvenida.lower())
        self.assertNotIn('!!', bienvenida)
        self.assertIn('inteligencia artificial', self.ajustes.texto_privacidad_corto)
        self.assertIn('persona', self.ajustes.texto_privacidad_corto)

    def test_es_un_solo_registro(self):
        self.assertEqual(self.env['dcasa.juan.ajustes'].obtener(), self.ajustes)
        with self.assertRaises(UserError):
            self.env['dcasa.juan.ajustes'].sudo().create({})
        with self.assertRaises(UserError):
            self.ajustes.unlink()

    def test_el_registro_viene_de_los_datos_del_modulo(self):
        self.assertEqual(self.env.ref('dcasa_conversaciones.ajustes_juan'), self.ajustes)


@tagged('post_install', '-at_install')
class TestAjustesEditables(JuanCase):

    def test_canal_activo_exige_el_encendido_global(self):
        self.assertTrue(self.ajustes.canal_activo('whatsapp_qr'))
        self.assertFalse(self.ajustes.canal_activo('messenger'))
        self.assertFalse(self.ajustes.canal_activo('canal_que_no_existe'))
        self.ajustes.bot_activo_global = False
        self.assertFalse(self.ajustes.canal_activo('whatsapp_qr'))
        self.assertFalse(self.ajustes.como_json()['bot_activo_global'])

    def test_horario_editable(self):
        self.ajustes.write({'horario_inicio': 9.5, 'horario_fin': 18.0, 'dia_domingo': False})
        datos = self.ajustes.como_json()['horario']
        self.assertEqual(datos['inicio'], '09:30')
        self.assertEqual(datos['fin'], '18:00')
        self.assertEqual(datos['dias'], [1, 2, 3, 4, 5, 6])   # sin el domingo (0)

    def test_horario_invalido(self):
        for valores in ({'horario_inicio': 17.0, 'horario_fin': 8.0}, {'horario_inicio': -1.0},
                        {'horario_fin': 24.0},
                        {'dia_lunes': False, 'dia_martes': False, 'dia_miercoles': False, 'dia_jueves': False,
                         'dia_viernes': False, 'dia_sabado': False, 'dia_domingo': False}):
            with self.subTest(valores=valores), self.assertRaises(ValidationError):
                self.ajustes.write(valores)

    def test_el_seguimiento_nunca_pasa_de_dos(self):
        self.ajustes.seguimiento_maximo = 1
        self.ajustes.seguimiento_maximo = 0
        for valores in ({'seguimiento_maximo': 3}, {'seguimiento_maximo': -1}, {'seguimiento_primero_horas': -1},
                        {'seguimiento_segundo_dias': -2}, {'presupuesto_ia_mensual_usd': -5},
                        {'pausa_por_defecto_minutos': -1}):
            with self.subTest(valores=valores), self.assertRaises(ValidationError):
                self.ajustes.write(valores)

    def test_precios_por_modelo_para_el_worker(self):
        """El Worker calcula el gasto por NOMBRE de modelo (``precios_ia``); Odoo los pide por nivel."""
        self.assertEqual(self.ajustes.como_json()['precios_ia'], {}, 'Sin precios cargados no se inventa ninguno')
        self.ajustes.write({
            'precio_rapido_entrada_usd_mtok': 1.0, 'precio_rapido_salida_usd_mtok': 5.0,
            'precio_rapido_cache_usd_mtok': 0.1,
            'precio_inteligente_entrada_usd_mtok': 3.0, 'precio_inteligente_salida_usd_mtok': 15.0})
        datos = self.ajustes.como_json()
        self.assertEqual(datos['precios_ia'], {
            'claude-haiku-4-5': {'entrada': 1.0, 'salida': 5.0, 'entrada_cache': 0.1},
            'claude-sonnet-5-5': {'entrada': 3.0, 'salida': 15.0}})
        self.assertEqual(datos['precios']['rapido'], {'entrada': 1.0, 'salida': 5.0, 'cache': 0.1})   # por nivel, como antes
        # Un nivel a medias (sin precio de salida) no cuenta: nunca una cifra a medio inventar.
        self.ajustes.precio_inteligente_salida_usd_mtok = 0
        self.assertNotIn('claude-sonnet-5-5', self.ajustes.como_json()['precios_ia'])
        # El mismo modelo en los dos niveles (p. ej. Meta): vale el más caro.
        self.ajustes.write({'modelo_rapido': 'muse-spark-1.3', 'modelo_inteligente': 'muse-spark-1.3',
                            'precio_inteligente_salida_usd_mtok': 15.0})
        self.assertEqual(self.ajustes.como_json()['precios_ia'], {
            'muse-spark-1.3': {'entrada': 3.0, 'salida': 15.0}})

    def test_palabras_prohibidas_una_por_linea(self):
        self.ajustes.palabras_prohibidas = 'remate\n  ofertón \n\ncorre'
        self.assertEqual(self.ajustes.lista_palabras_prohibidas(), ['remate', 'ofertón', 'corre'])

    def test_los_cambios_quedan_en_el_historial(self):
        self.ajustes.presupuesto_ia_mensual_usd = 45
        self.env.cr.precommit.run()   # el historial se escribe al cerrar la transacción
        campos = self.ajustes.message_ids.tracking_value_ids.field_id.mapped('field_description')
        self.assertIn('Tope de IA', ' '.join(campos))

    def test_solo_gerencia_edita(self):
        self.ajustes.with_user(self.gerente).presupuesto_ia_mensual_usd = 50
        self.assertEqual(self.ajustes.presupuesto_ia_mensual_usd, 50)
        self.assertEqual(self.ajustes.with_user(self.vendedora).presupuesto_ia_mensual_usd, 50)   # leer, sí
        with self.assertRaises(AccessError):
            self.ajustes.with_user(self.vendedora).presupuesto_ia_mensual_usd = 5
        with self.assertRaises(AccessError):
            self.ajustes.with_user(self.interno).read(['presupuesto_ia_mensual_usd'])


@tagged('post_install', '-at_install')
class TestSecretos(JuanCase):
    """Los tokens viven en el entorno o en un parámetro; la pantalla solo dice si están puestos."""

    def con_entorno(self, **variables):
        parche = patch.dict(os.environ, variables)
        parche.start()
        self.addCleanup(parche.stop)

    def test_sin_configurar(self):
        self.assertEqual(self.ajustes.token_odoo(), '')
        self.assertEqual(self.ajustes.token_worker(), '')
        self.assertFalse(self.ajustes.token_odoo_configurado)
        self.assertFalse(self.ajustes.token_worker_configurado)
        self.assertFalse(self.env['dcasa.juan.cliente'].configurado())

    def test_el_token_sale_del_entorno(self):
        self.con_entorno(JUAN_ODOO_TOKEN=TOKEN_ODOO, JUAN_WORKER_TOKEN=TOKEN_WORKER, JUAN_URL=URL_WORKER)
        self.assertEqual(self.ajustes.token_odoo(), TOKEN_ODOO)
        self.assertEqual(self.ajustes.token_worker(), TOKEN_WORKER)
        self.assertTrue(self.ajustes.token_odoo_configurado)
        self.assertTrue(self.env['dcasa.juan.cliente'].configurado())

    def test_o_de_un_parametro_del_sistema(self):
        parametros = self.env['ir.config_parameter'].sudo()
        parametros.set_param('dcasa_conversaciones.juan_odoo_token', TOKEN_ODOO)
        self.assertEqual(self.ajustes.token_odoo(), TOKEN_ODOO)
        # El entorno manda sobre el parámetro.
        self.con_entorno(JUAN_ODOO_TOKEN='e' * 40)
        self.assertEqual(self.ajustes.token_odoo(), 'e' * 40)

    def test_un_token_corto_se_trata_como_no_configurado(self):
        self.con_entorno(JUAN_ODOO_TOKEN='corto', JUAN_WORKER_TOKEN='x' * 31)
        self.assertEqual(self.ajustes.token_odoo(), '')
        self.assertEqual(self.ajustes.token_worker(), '')

    def test_la_pantalla_no_expone_el_valor(self):
        self.con_entorno(JUAN_ODOO_TOKEN=TOKEN_ODOO, JUAN_WORKER_TOKEN=TOKEN_WORKER)
        campos = self.env['dcasa.juan.ajustes']._fields
        self.assertNotIn(TOKEN_ODOO, str(self.ajustes.read()))
        self.assertNotIn(TOKEN_WORKER, str(self.ajustes.read()))
        self.assertFalse([c for c in campos if 'token' in c and campos[c].type != 'boolean'])

    def test_la_url_del_worker_se_guarda_en_el_parametro_del_contrato(self):
        self.ajustes.juan_url = 'https://juan.dcasapty.com/'
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dcasa_conversaciones.juan_url'),
                         'https://juan.dcasapty.com')
        self.ajustes.invalidate_recordset()
        self.assertEqual(self.ajustes.juan_url, 'https://juan.dcasapty.com')
        for mala in ('http://juan.dcasapty.com', 'ftp://x', 'juan.dcasapty.com', 'javascript:1'):
            with self.subTest(url=mala), self.assertRaises(ValidationError):
                self.ajustes.juan_url = mala
        self.ajustes.juan_url = 'http://localhost:8787'    # para pruebas locales
        self.ajustes.juan_url = ''

    def test_probar_conexion(self):
        self.con_entorno(JUAN_WORKER_TOKEN=TOKEN_WORKER, JUAN_URL=URL_WORKER)
        with patch('requests.request', return_value=respuesta_http(
                {'ok': True, 'canales': {'whatsapp_qr': 'conectado'}})) as llamada:
            resultado = self.ajustes.with_user(self.gerente).action_probar_conexion()
        self.assertEqual(resultado['params']['type'], 'success')
        self.assertIn('whatsapp_qr: conectado', resultado['params']['message'])
        self.assertEqual(llamada.call_args.args[:2], ('GET', f'{URL_WORKER}/odoo/salud'))
        with patch('requests.request', return_value=respuesta_http({'ok': False, 'error': 'caído'}, 503)):
            self.assertEqual(self.ajustes.with_user(self.gerente).action_probar_conexion()['params']['type'], 'warning')
        with self.assertRaises(AccessError):
            self.ajustes.with_user(self.vendedora).action_probar_conexion()
