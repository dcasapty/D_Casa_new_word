"""El enlace para choferes (pedido de la dueña, 2026-11-09): la calculadora reducida, sin usuario de Odoo.

* El motor (sin base de datos): la distancia, los lugares más cercanos con su corte de 3 km, qué ubicación vale y que
  de un lugar solo sale el nombre, la zona, el precio o su aviso y la ruta.
* Las rutas: apagado u otro secreto dan el mismo 404; «Crear un enlace nuevo» deja sin efecto el anterior; las
  respuestas traen solo lo que ve el chofer (nunca km ni ids); sin tarifa aprobada no hay precios; se rechazan las
  coordenadas y los textos que no sirven; el límite por IP; las cabeceras (sin caché, sin indexar, sin referer, CSP).
* Quién lo ve y lo cambia: Gerencia y administradores; ni la vendedora ni el portal, tampoco por RPC."""
import json
import math
import re

from odoo.addons.dcasa_guia.models import guia as G
from odoo.exceptions import AccessError
from odoo.tests import BaseCase, HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException

from ..controllers import choferes as ruta
from ..motor import choferes
from ..motor.tarjeta import TIENDA
from .common import EnviosComun, fixture, importar

VILLA = (8.9011, -79.8011)          # Villa Prueba en el fixture
LEJOS = (9.3, -79.0)                # en Panamá, pero a más de 3 km de todo el fixture


@tagged('post_install', '-at_install')
class TestMotorDeChoferes(BaseCase):

    def test_distancia_en_metros(self):
        self.assertAlmostEqual(choferes.distancia_m(8.0, -79.0, 9.0, -79.0), 111_195, delta=10, msg='un grado')
        self.assertEqual(choferes.distancia_m(*VILLA, *VILLA), 0)
        self.assertAlmostEqual(choferes.distancia_m(8.9011, -79.8011, 8.9001, -79.8001), 156.3, delta=0.5)

    def test_los_mas_cercanos_y_el_corte_de_3_km(self):
        lat, lon = VILLA
        grado = choferes.distancia_m(lat, lon, lat + 1, lon)          # metros por grado de latitud aquí
        lugares = [
            {'nombre': 'A 2.9 km', 'lat': lat + 2900 / grado, 'lon': lon},
            {'nombre': 'Sin coordenadas', 'lat': None, 'lon': None},
            {'nombre': 'A 3.1 km', 'lat': lat - 3100 / grado, 'lon': lon},
            {'nombre': 'A 100 m', 'lat': lat, 'lon': lon + 100 / (grado * math.cos(math.radians(lat)))},
            {'nombre': 'Aquí', 'lat': lat, 'lon': lon},
            {'nombre': 'A 1 km', 'lat': lat + 1000 / grado, 'lon': lon},
        ]
        cerca = choferes.cercanos(lugares, lat, lon)
        self.assertEqual([lugares[p]['nombre'] for p, _m in cerca], ['Aquí', 'A 100 m', 'A 1 km'], 'los 3 más cerca')
        self.assertEqual([round(m) for _p, m in cerca], [0, 100, 1000])
        todos = choferes.cercanos(lugares, lat, lon, maximo=10)
        self.assertEqual([lugares[p]['nombre'] for p, _m in todos], ['Aquí', 'A 100 m', 'A 1 km', 'A 2.9 km'],
                         'el de 3.1 km queda fuera y el que no tiene coordenadas no cuenta')
        self.assertEqual(choferes.cercanos(lugares, lat + 1, lon), [], 'a 111 km no hay nada cerca')
        # Con el fixture: desde Villa Prueba, ella misma y sus vecinas, en orden.
        datos = fixture()['lugares']
        cerca = choferes.cercanos(datos, *VILLA)
        self.assertEqual([datos[p]['nombre'] for p, _m in cerca], ['Villa Prueba', 'Villa Prueba II',
                                                                     'Hospital del Ejemplo'])

    def test_que_ubicacion_vale(self):
        self.assertEqual(choferes.ubicacion_valida(8.9, -79.8), (8.9, -79.8))
        self.assertEqual(choferes.ubicacion_valida(9, -80), (9.0, -80.0), 'enteros también')
        for lat, lon in (('8.9', '-79.8'), (True, -79.8), (None, -79.8), (8.9, None), (math.nan, -79.8),
                         (8.9, math.inf), (0, 0), (40.7, -74.0), (8.9, 79.8), (-8.9, -79.8), (12.0, -79.8),
                         ([8.9], -79.8), ({'lat': 8.9}, -79.8)):
            with self.subTest(lat=lat, lon=lon):
                self.assertIsNone(choferes.ubicacion_valida(lat, lon))

    def test_la_distancia_se_dice_en_metros(self):
        for metros, texto in ((0, 'a 10 m'), (4, 'a 10 m'), (304, 'a 300 m'), (305, 'a 310 m'), (999, 'a 1,000 m'),
                              (1234, 'a 1,250 m'), (2990, 'a 3,000 m')):
            with self.subTest(metros=metros):
                self.assertEqual(choferes.distancia_txt(metros), texto)

    def test_de_un_lugar_solo_sale_lo_que_ve_el_chofer(self):
        tarjeta = {'nombre': 'Villa Prueba', 'corr': 'Barrio Prueba', 'dist': 'La Chorrera', 'con_precio': True,
                   'total_txt': '$15', 'km': 1.2, 'km_txt': '1.2 km', 'desglose': [{'texto': 'Tarifa base'}],
                   'texto_cliente': 'Envío a…', 'url_mapa': 'https://www.google.com/maps/dir/?api=1', 'id': 7,
                   'chips': [{'texto': 'barrio o urbanización', 'clase': 'tipo'}]}
        datos = choferes.para_chofer(tarjeta, aprobada=True)
        self.assertEqual(tuple(datos), choferes.CLAVES)
        self.assertEqual(datos, {'nombre': 'Villa Prueba', 'zona': 'Barrio Prueba · La Chorrera', 'precio': '$15',
                                 'aviso': '', 'mapa': 'https://www.google.com/maps/dir/?api=1'})
        self.assertEqual(choferes.para_chofer(tarjeta, aprobada=False)['precio'], '', 'en revisión, sin precio')
        self.assertEqual(choferes.para_chofer(tarjeta, aprobada=False)['aviso'], choferes.EN_REVISION)
        aparte = choferes.para_chofer(dict(tarjeta, con_precio=False), aprobada=True)
        self.assertEqual((aparte['precio'], aparte['aviso']), ('', choferes.APARTE))
        lancha = choferes.para_chofer(dict(tarjeta, chips=[{'texto': '+ lancha'}]), aprobada=True)
        self.assertEqual(lancha['precio'], '$15 + lancha')
        cerca = choferes.para_chofer(tarjeta, aprobada=True, metros=304)
        self.assertEqual((tuple(cerca), cerca['distancia']), (choferes.CLAVES_CERCA, 'a 300 m'))
        corregimiento = choferes.para_chofer(dict(tarjeta, nombre='Barrio Prueba'), aprobada=True)
        self.assertEqual(corregimiento['zona'], 'La Chorrera', 'sin repetir el nombre')

    def test_el_limite_por_ip(self):
        ruta.reiniciar_limite()
        self.addCleanup(ruta.reiniciar_limite)
        for i in range(ruta.MAX_POR_MINUTO):
            self.assertFalse(ruta.excede('10.0.0.1', ahora=100.0 + i * 0.1))
        self.assertTrue(ruta.excede('10.0.0.1', ahora=107.0), 'la 61.ª en el mismo minuto')
        self.assertFalse(ruta.excede('10.0.0.2', ahora=107.0), 'otra IP cuenta aparte')
        self.assertFalse(ruta.excede('10.0.0.1', ahora=161.0), 'pasado el minuto vuelve a dejar')


class ChoferesComun:
    """El fixture cargado, la tarifa con su enlace encendido, y cómo pedir las rutas."""

    @classmethod
    def preparar(cls, env):
        cls.gerencia = new_test_user(env, login='ger_chofer', password='ger_chofer', name='Gerencia Choferes',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(env, login='vend_chofer', password='vend_chofer', name='Vendedora Choferes',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.portal = new_test_user(env, login='portal_chofer', password='portal_chofer', name='Portal Choferes',
                                   groups='base.group_portal')
        importar(env, cls.gerencia)
        cls.tarifa_g = env['dcasa.envio.tarifa'].search([]).with_user(cls.gerencia)
        cls.tarifa_g.write({'choferes_activo': True})

    @property
    def token(self):
        return self.tarifa_g.sudo().choferes_token

    def aprobar(self):
        self.tarifa_g.action_aprobar()


@tagged('post_install', '-at_install')
class TestRutasDeChoferes(ChoferesComun, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar(cls.env)

    def setUp(self):
        super().setUp()
        ruta.reiniciar_limite()
        self.addCleanup(ruta.reiniciar_limite)

    def pagina(self, token=None):
        return self.url_open(f'/envios/choferes/{self.token if token is None else token}')

    def post(self, que, cuerpo, token=None, crudo=None):
        url = f'/envios/choferes/{self.token if token is None else token}/{que}'
        datos = crudo if crudo is not None else json.dumps(cuerpo)
        return self.url_open(url, data=datos, headers={'Content-Type': 'application/json'})

    def assertNoExiste(self, respuesta):
        self.assertEqual((respuesta.status_code, respuesta.text), (404, 'Not Found'))
        self.assertTrue(respuesta.headers['Content-Type'].startswith('text/plain'))
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.assertNotIn('Set-Cookie', respuesta.headers)

    def assertSoloLoDelChofer(self, respuesta, claves=choferes.CLAVES):
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        datos = respuesta.json()
        for lugar in datos['resultados']:
            self.assertEqual(tuple(lugar), claves)
            self.assertTrue(lugar['mapa'].startswith('https://www.google.com/maps/dir/?api=1&origin=' + TIENDA))
        texto = respuesta.text
        self.assertIsNone(re.search(r'\bkm\b|kil[oó]metro', texto, re.I), f'salió algo de km: {texto[:300]}')
        for prohibida in ('"id"', '"km', 'desglose', 'texto_cliente', '"base"', '"total"', 'tramos', 'lat"'):
            self.assertNotIn(prohibida, texto)
        return datos

    # --- El enlace ---------------------------------------------------------------------------------------------
    def test_apagado_o_con_otro_secreto_es_el_mismo_404(self):
        self.assertEqual(self.pagina().status_code, 200)
        otro = self.token[:-4] + ('aaaa' if not self.token.endswith('aaaa') else 'bbbb')
        for token in (otro, 'x' * 10, 'x' * 70, self.token.upper() if self.token.upper() != self.token else 'Q' * 32):
            with self.subTest(token=token):
                self.assertNoExiste(self.pagina(token))
                self.assertNoExiste(self.post('buscar', {'texto': 'villa'}, token=token))
                self.assertNoExiste(self.post('cerca', {'lat': VILLA[0], 'lon': VILLA[1]}, token=token))
        self.tarifa_g.write({'choferes_activo': False})
        self.assertNoExiste(self.pagina())
        self.assertNoExiste(self.post('buscar', {'texto': 'villa'}))
        self.assertNoExiste(self.post('cerca', {'lat': VILLA[0], 'lon': VILLA[1]}))
        self.tarifa_g.write({'choferes_activo': True})
        self.assertEqual(self.pagina().status_code, 200, 'encenderlo de nuevo no cambia el enlace')

    def test_crear_un_enlace_nuevo_deja_sin_efecto_el_anterior(self):
        anterior = self.token
        self.assertEqual(self.pagina(anterior).status_code, 200)
        self.tarifa_g.action_choferes_enlace_nuevo()
        nuevo = self.token
        self.assertNotEqual(nuevo, anterior)
        self.assertGreaterEqual(len(nuevo), 32)
        self.assertNoExiste(self.pagina(anterior))
        self.assertNoExiste(self.post('buscar', {'texto': 'villa'}, token=anterior))
        self.assertEqual(self.pagina(nuevo).status_code, 200)
        self.assertEqual(self.tarifa_g.choferes_creado_por, self.gerencia)
        self.assertEqual(self.tarifa_g.choferes_url, f'{self.tarifa_g.get_base_url()}/envios/choferes/{nuevo}')
        notas = self.tarifa_g.sudo().message_ids.mapped('body')
        self.assertTrue(any('creó un enlace nuevo' in str(n) and 'Gerencia Choferes' in str(n) for n in notas))
        self.assertFalse(any(anterior in str(n) or nuevo in str(n) for n in notas), 'el secreto nunca va al historial')

    def test_la_pagina_no_se_guarda_ni_se_indexa(self):
        respuesta = self.pagina()
        self.assertEqual(respuesta.status_code, 200)
        cabeceras = respuesta.headers
        self.assertEqual(cabeceras['Cache-Control'], 'no-store')
        self.assertEqual(cabeceras['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(cabeceras['Referrer-Policy'], 'no-referrer')
        self.assertNotIn('Set-Cookie', cabeceras)
        nonce = re.search(r"script-src 'nonce-([^']+)'", cabeceras['Content-Security-Policy']).group(1)
        self.assertIn("default-src 'none'", cabeceras['Content-Security-Policy'])
        html = respuesta.text
        self.assertTrue(html.startswith('<!DOCTYPE html>'))
        self.assertIn(f'<script nonce="{nonce}">', html)
        for texto in ('Busca el barrio, edificio o lugar', 'Usar mi ubicación', 'no se guarda',
                      'OpenStreetMap (ODbL) y GeoNames (CC BY 4.0)',
                      '<meta name="robots" content="noindex, nofollow"/>'):
            self.assertIn(texto, html)
        self.assertIsNone(re.search(r'\bkm\b|kil[oó]metro|\btramos?\b|desglose', html, re.I))   # («encontramos» sí)
        self.assertIn('Tarifa en revisión: confirma el precio con la tienda', html, 'sin aprobar, lo dice arriba')
        self.aprobar()
        aprobada = self.pagina().text
        self.assertNotIn('Tarifa en revisión', aprobada)
        self.assertIn('<p class="aviso" role="status" hidden="hidden"></p>', aprobada)
        for que in ('buscar', 'cerca'):
            otra = self.post(que, {'texto': 'villa', 'lat': VILLA[0], 'lon': VILLA[1]})
            self.assertEqual((otra.headers['Cache-Control'], otra.headers['X-Robots-Tag']),
                             ('no-store', 'noindex, nofollow'))
            self.assertNotIn('Set-Cookie', otra.headers)

    # --- Buscar ------------------------------------------------------------------------------------------------
    def test_buscar_da_solo_nombre_zona_precio_y_ruta(self):
        self.aprobar()
        datos = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'vla prueba'}))
        self.assertEqual(datos['aviso_tarifa'], '')
        self.assertEqual(datos['resultados'][0], {
            'nombre': 'Villa Prueba', 'zona': 'Barrio Prueba · La Chorrera', 'precio': '$15', 'aviso': '',
            'mapa': 'https://www.google.com/maps/dir/?api=1&origin=8.8765881,-79.7867962&destination=8.9011%2C-79.8011'
                    '&travelmode=driving'})
        Lugar = self.env['dcasa.envio.lugar'].with_user(self.gerencia)
        Lugar.create([{'name': f'Ensayo Extra {n}', 'tipo': 'barrio', 'dist': 'La Chorrera', 'km': 5}
                      for n in range(4)])
        muchos = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'ensayo'}))
        self.assertEqual(len(muchos['resultados']), choferes.MAX_BUSQUEDA, 'de 12, a lo sumo 8')
        lejos = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'pueblo lejano'}))['resultados'][0]
        self.assertEqual((lejos['nombre'], lejos['precio'], lejos['aviso']), ('Pueblo Lejano', '', choferes.APARTE))
        sin_camino = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'monte sin camino'}))['resultados'][0]
        self.assertEqual((sin_camino['precio'], sin_camino['aviso']), ('', choferes.APARTE))
        isla = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'isla inventada'}))['resultados'][0]
        self.assertEqual(isla['precio'], '$70 + lancha')
        nada = self.assertSoloLoDelChofer(self.post('buscar', {'texto': 'pruebaxx zzz'}))
        self.assertEqual(nada['resultados'], [])
        self.assertIn('Villa Prueba', nada['sugerencias'])
        self.assertEqual(self.post('buscar', {'texto': 'v'}).json()['resultados'], [], 'una letra no busca')

    def test_sin_tarifa_aprobada_no_hay_precios(self):
        for que, cuerpo in (('buscar', {'texto': 'prueba'}), ('cerca', {'lat': VILLA[0], 'lon': VILLA[1]})):
            with self.subTest(que=que):
                datos = self.assertSoloLoDelChofer(self.post(que, cuerpo),
                                                   choferes.CLAVES_CERCA if que == 'cerca' else choferes.CLAVES)
                self.assertTrue(datos['resultados'])
                self.assertEqual({(lugar['precio'], lugar['aviso']) for lugar in datos['resultados']},
                                 {('', choferes.EN_REVISION)})
                self.assertEqual(datos['aviso_tarifa'], choferes.EN_REVISION)
                self.assertNotIn('$', json.dumps(datos))
        self.aprobar()
        self.tarifa_g.action_subir_5()          # un cambio de precios la devuelve a revisión: los choferes lo notan
        resultados = self.post('buscar', {'texto': 'prueba'}).json()['resultados']
        self.assertFalse(any(lugar['precio'] for lugar in resultados))

    def test_buscar_rechaza_lo_que_no_es_un_texto_corto(self):
        for cuerpo, crudo in (({'texto': 'x' * 121}, None), ({'texto': 7}, None), ({}, None), (None, 'no es json'),
                              (None, '["villa"]'), (None, json.dumps({'texto': 'villa', 'relleno': 'x' * 3000}))):
            with self.subTest(cuerpo=cuerpo, crudo=(crudo or '')[:20]):
                respuesta = self.post('buscar', cuerpo, crudo=crudo)
                self.assertEqual(respuesta.status_code, 400, respuesta.text)
                self.assertIn('error', respuesta.json())
        self.assertEqual(self.post('buscar', {'texto': 'x' * 120}).status_code, 200)

    # --- Usar mi ubicación -------------------------------------------------------------------------------------
    def test_cerca_da_hasta_3_lugares_a_menos_de_3_km(self):
        self.aprobar()
        datos = self.assertSoloLoDelChofer(self.post('cerca', {'lat': VILLA[0], 'lon': VILLA[1]}),
                                           choferes.CLAVES_CERCA)
        self.assertEqual([(lugar['nombre'], lugar['distancia'], lugar['precio']) for lugar in datos['resultados']],
                         [('Villa Prueba', 'a 10 m', '$15'), ('Villa Prueba II', 'a 20 m', '$15'),
                          ('Hospital del Ejemplo', 'a 160 m', '$15')])
        self.assertEqual(datos['mensaje'], '')
        lejos = self.post('cerca', {'lat': LEJOS[0], 'lon': LEJOS[1]}).json()
        self.assertEqual(lejos, {'resultados': [], 'mensaje': choferes.NADA_CERCA, 'aviso_tarifa': ''})

    def test_cerca_rechaza_coordenadas_que_no_sirven(self):
        for crudo in (json.dumps({'lat': '8.9', 'lon': '-79.8'}), json.dumps({'lat': 8.9}), json.dumps({}),
                      json.dumps({'lat': 0, 'lon': 0}), json.dumps({'lat': 40.7, 'lon': -74.0}),
                      json.dumps({'lat': True, 'lon': -79.8}), '{"lat": NaN, "lon": -79.8}',
                      '{"lat": Infinity, "lon": -79.8}', 'null', '[8.9, -79.8]', 'nada'):
            with self.subTest(crudo=crudo):
                respuesta = self.post('cerca', None, crudo=crudo)
                self.assertEqual(respuesta.status_code, 400, respuesta.text)
                self.assertEqual(respuesta.json(),
                                 {'error': 'No pudimos leer tu ubicación: busca el lugar por nombre.'})

    def test_la_ubicacion_no_se_guarda(self):
        def contar():
            self.env.flush_all()
            self.env.cr.execute("""SELECT (SELECT count(*) FROM mail_message), (SELECT count(*) FROM ir_logging),
                                          (SELECT count(*) FROM ir_attachment),
                                          (SELECT count(*) FROM dcasa_envio_lugar)""")
            return self.env.cr.fetchone()
        antes = contar()
        self.assertEqual(self.post('cerca', {'lat': 8.912345, 'lon': -79.812345}).status_code, 200)
        self.assertEqual(contar(), antes)
        self.env.cr.execute("SELECT count(*) FROM ir_config_parameter WHERE value LIKE '%%8.912345%%'")
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    # --- El límite ---------------------------------------------------------------------------------------------
    def test_muchas_peticiones_seguidas_desde_la_misma_ip(self):
        for _vez in range(ruta.MAX_POR_MINUTO - 1):
            ruta.excede('127.0.0.1')
        self.assertEqual(self.pagina().status_code, 200, 'la 60.ª todavía pasa')
        for respuesta in (self.pagina(), self.post('buscar', {'texto': 'villa'}),
                          self.post('cerca', {'lat': VILLA[0], 'lon': VILLA[1]}), self.pagina('otro' * 8)):
            with self.subTest(url=respuesta.url):
                self.assertEqual(respuesta.status_code, 429)
                self.assertEqual(respuesta.headers['Retry-After'], '60')
                self.assertIn('espera un minuto', respuesta.text)
        ruta.reiniciar_limite()
        self.assertEqual(self.pagina().status_code, 200)

    # --- Por RPC ---------------------------------------------------------------------------------------------
    def test_por_rpc_solo_gerencia_ve_y_cambia_el_enlace(self):
        tarifa = self.tarifa_g.sudo()
        llamadas = (
            ('read', [[tarifa.id], ['choferes_token']], {}),
            ('read', [[tarifa.id], ['choferes_url']], {}),
            ('web_read', [[tarifa.id]], {'specification': {'choferes_url': {}}}),
            ('write', [[tarifa.id], {'choferes_activo': False}], {}),
            ('action_choferes_enlace_nuevo', [[tarifa.id]], {}),
            ('_choferes_enlace_vale', [self.token], {}),
        )
        for login in ('vend_chofer', 'portal_chofer'):
            self.authenticate(login, login)
            for metodo, args, kwargs in llamadas:
                with self.subTest(login=login, metodo=metodo), self.assertRaises(JsonRpcException):
                    self.make_jsonrpc_request(f'/web/dataset/call_kw/dcasa.envio.tarifa/{metodo}', {
                        'model': 'dcasa.envio.tarifa', 'method': metodo, 'args': args, 'kwargs': kwargs})
        self.authenticate('vend_chofer', 'vend_chofer')
        leido = self.make_jsonrpc_request('/web/dataset/call_kw/dcasa.envio.tarifa/read', {
            'model': 'dcasa.envio.tarifa', 'method': 'read', 'args': [[tarifa.id]], 'kwargs': {}})[0]
        self.assertFalse([campo for campo in leido if campo.startswith('choferes_')], 'ni lo ve en «todos los campos»')
        self.assertEqual(self.pagina().status_code, 200, 'nada cambió')
        self.authenticate('ger_chofer', 'ger_chofer')
        leido = self.make_jsonrpc_request('/web/dataset/call_kw/dcasa.envio.tarifa/read', {
            'model': 'dcasa.envio.tarifa', 'method': 'read', 'args': [[tarifa.id], ['choferes_url']], 'kwargs': {}})
        self.assertTrue(leido[0]['choferes_url'].endswith('/envios/choferes/' + self.token))


@tagged('post_install', '-at_install')
class TestEnlaceDeChoferes(EnviosComun):
    """La ficha de la tarifa: quién ve el enlace, lo enciende y crea uno nuevo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.importar()

    def test_apagado_de_fabrica_y_encenderlo_crea_el_enlace(self):
        # (La tarifa nació en esta misma transacción, al cargar el fixture: Odoo no rastrea sus cambios hasta cerrarla.)
        self.historial_al_dia()
        tarifa = self.tarifa.with_user(self.gerencia)
        self.assertFalse(tarifa.choferes_activo)
        self.assertFalse(tarifa.choferes_token)
        self.assertFalse(tarifa.choferes_url)
        self.assertFalse(self.env['dcasa.envio.tarifa']._choferes_enlace_vale(''))
        version = self.env['ir.config_parameter'].sudo().get_param('dcasa_envios.version_lugares')
        tarifa.write({'choferes_activo': True})
        self.historial_al_dia()
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dcasa_envios.version_lugares'), version,
                         'encender el enlace no rearma el buscador')
        token = tarifa.choferes_token
        self.assertTrue(token and len(token) >= 32)
        self.assertEqual((tarifa.choferes_creado_por, bool(tarifa.choferes_creado_el)), (self.gerencia, True))
        self.assertTrue(self.env['dcasa.envio.tarifa']._choferes_enlace_vale(token))
        self.assertFalse(self.env['dcasa.envio.tarifa']._choferes_enlace_vale(token + 'x'))
        self.assertFalse(self.env['dcasa.envio.tarifa']._choferes_enlace_vale(None))
        tarifa.write({'choferes_activo': False})
        self.historial_al_dia()
        self.assertEqual(tarifa.choferes_token, token, 'apagarlo no lo cambia')
        self.assertFalse(self.env['dcasa.envio.tarifa']._choferes_enlace_vale(token))
        rastreo = self.tarifa.sudo().message_ids.tracking_value_ids.filtered(
            lambda t: t.field_id.name == 'choferes_activo')
        self.assertEqual(len(rastreo), 2, 'encender y apagar quedan en el historial')
        self.assertEqual(rastreo.mail_message_id.author_id, self.gerencia.partner_id, 'con quién lo hizo')
        notas = ' '.join(str(b) for b in self.tarifa.sudo().message_ids.mapped('body'))
        self.assertIn('Enlace para choferes creado por Gerencia Envíos.', notas)
        self.assertNotIn(token, notas, 'el secreto nunca va al historial')

    def historial_al_dia(self):
        self.env.flush_all()
        self.env.cr.precommit.run()

    def test_nadie_escribe_el_secreto_a_mano(self):
        tarifa = self.tarifa.with_user(self.gerencia)
        tarifa.write({'choferes_activo': True, 'choferes_token': 'elegido-por-mi-' * 3,
                      'choferes_creado_por': self.vendedora.id})
        self.assertNotEqual(tarifa.choferes_token, 'elegido-por-mi-' * 3)
        self.assertEqual(tarifa.choferes_creado_por, self.gerencia)
        tarifa.write({'choferes_token': 'otro-elegido-' * 3})
        self.assertNotEqual(tarifa.choferes_token, 'otro-elegido-' * 3)

    def test_solo_gerencia_y_administradores(self):
        admin = new_test_user(self.env, login='admin_chofer', groups='base.group_user,base.group_system')
        self.tarifa.with_user(admin).action_choferes_enlace_nuevo()
        self.assertEqual(self.tarifa.sudo().choferes_creado_por, admin)
        for usuario in (self.vendedora, self.portal):
            tarifa = self.tarifa.with_user(usuario)
            for accion in (lambda t=tarifa: t.read(['choferes_token']), lambda t=tarifa: t.read(['choferes_url']),
                           lambda t=tarifa: t.read(['choferes_activo']),
                           lambda t=tarifa: t.write({'choferes_activo': True}),
                           tarifa.action_choferes_enlace_nuevo):
                with self.subTest(usuario=usuario.login, accion=accion), self.assertRaises(AccessError):
                    accion()
        self.assertFalse(self.tarifa.sudo().choferes_activo)

    def test_la_ficha_lo_muestra_solo_a_gerencia(self):
        def arch(usuario):
            return self.env['dcasa.envio.tarifa'].with_user(usuario).get_view(view_type='form')['arch']
        de_gerencia = arch(self.gerencia)
        for texto in ('name="choferes_activo"', 'name="choferes_url"', 'name="action_choferes_enlace_nuevo"',
                      'Enlace para choferes'):
            self.assertIn(texto, de_gerencia)
        de_vendedora = arch(self.vendedora)
        for texto in ('name="choferes_', 'action_choferes_enlace_nuevo', 'Enlace para choferes'):
            self.assertNotIn(texto, de_vendedora)

    def test_la_guia_le_dice_a_gerencia_donde_esta(self):
        tarea = next(t for t in G.cargar_catalogo()['tareas'] if t['id'] == 'envio-enlace-choferes')
        self.assertEqual(tarea['titulo'], 'Darle a los choferes el enlace de la calculadora')
        self.assertEqual(tarea['destino'], {'menu': 'dcasa_envios.menu_envios_tarifa'})
        if 'dcasa.guia' not in self.env:
            self.skipTest('dcasa_guia no está instalado en esta base')
        Guia = self.env['dcasa.guia']
        self.assertIn('envio-enlace-choferes',
                      [t['id'] for t in Guia.with_user(self.gerencia).buscar('link de choferes')])
        self.assertNotIn('envio-enlace-choferes',
                         [t['id'] for t in Guia.with_user(self.vendedora).buscar('link de choferes')])
