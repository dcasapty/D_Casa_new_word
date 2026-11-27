"""Las rutas públicas de la ubicación y la de la API de Juan: lo que responden, sus cabeceras y lo que guardan."""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_conversaciones.controllers.juan import RAIZ
from odoo.addons.dcasa_conversaciones.tests.common import TOKEN_ODOO
from odoo.addons.dcasa_envios.controllers.choferes import reiniciar_limite
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import HttpCase, new_test_user, tagged

from .common import CERCA, LEJOS


@tagged('post_install', '-at_install')
class TestRutas(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='ger_ubic_http', name='Gerencia Ubicación',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()
        cls.cliente = cls.env['res.partner'].create({'name': 'Bea Prueba', 'phone': '+507 6555-0000'})

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)
        entorno = patch.dict(os.environ, {'JUAN_ODOO_TOKEN': TOKEN_ODOO, 'JUAN_WORKER_TOKEN': '', 'JUAN_URL': '',
                                          'GOOGLE_MAPS_CLAVE_NAVEGADOR': '', 'GOOGLE_MAPS_CLAVE_SERVIDOR': ''})
        entorno.start()
        self.addCleanup(entorno.stop)

    def post_json(self, ruta, cuerpo, **cabeceras):
        return self.url_open(ruta, data=json.dumps(cuerpo),
                             headers={'Content-Type': 'application/json', **cabeceras})

    def enlace(self):
        return self.env['dcasa.ubicacion.enlace']._crear(self.cliente)

    # --- /u/<secreto> ----------------------------------------------------------------------------------------------

    def test_la_pagina_del_enlace(self):
        _enlace, url = self.enlace()
        ruta = '/u/' + url.rsplit('/u/', 1)[1]
        respuesta = self.url_open(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('¿Dónde te entregamos?', respuesta.text)
        self.assertIn('Mi ubicación', respuesta.text)
        self.assertIn('og:image', respuesta.text, 'la vista previa del enlace muestra un pin en un mapa')
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.assertIn('noindex', respuesta.headers['X-Robots-Tag'])
        self.assertIn("default-src 'none'", respuesta.headers['Content-Security-Policy'])
        self.assertNotIn('maps.googleapis.com', respuesta.headers['Content-Security-Policy'], 'sin clave, sin Google')
        inventado = self.url_open('/u/' + 'x' * 22)
        self.assertEqual(inventado.status_code, 404)
        self.assertIn('Este enlace ya no sirve', inventado.text)

    def test_con_clave_la_pagina_deja_cargar_google_maps(self):
        _enlace, url = self.enlace()
        with patch.dict(os.environ, {'GOOGLE_MAPS_CLAVE_NAVEGADOR': 'A' * 39}):
            respuesta = self.url_open('/u/' + url.rsplit('/u/', 1)[1])
        self.assertIn('https://*.googleapis.com', respuesta.headers['Content-Security-Policy'])
        self.assertIn('data-clave="' + 'A' * 39 + '"', respuesta.text)

    def test_zona_buscar_y_guardar(self):
        enlace, url = self.enlace()
        base = '/u/' + url.rsplit('/u/', 1)[1]
        zona = self.post_json(base + '/zona', {'lat': CERCA[0], 'lon': CERCA[1]}).json()
        self.assertIn('Villa Prueba II', zona['zona'])
        self.assertTrue(zona['precio'])
        malo = self.post_json(base + '/zona', {'lat': LEJOS[0], 'lon': LEJOS[1]})
        self.assertEqual((malo.status_code, malo.json()['motivo']), (422, 'fuera_de_panama'))
        lugares = self.post_json(base + '/buscar', {'texto': 'villa prueba'}).json()['lugares']
        self.assertTrue(lugares)
        self.assertEqual(set(lugares[0]), {'nombre', 'zona', 'lat', 'lon'}, 'sin precios, km ni ids')
        sin_referencia = self.post_json(base + '/guardar', {'lat': CERCA[0], 'lon': CERCA[1], 'origen': 'pin'})
        self.assertEqual(sin_referencia.status_code, 400)
        otro_origen = self.post_json(base + '/guardar', {'lat': CERCA[0], 'lon': CERCA[1], 'origen': 'whatsapp',
                                                         'referencia': 'Casa'})
        self.assertEqual(otro_origen.status_code, 400, 'la página solo marca con GPS, mapa o búsqueda')
        bien = self.post_json(base + '/guardar', {'lat': CERCA[0], 'lon': CERCA[1], 'origen': 'gps', 'precision': 9,
                                                  'referencia': 'Casa verde'})
        self.assertEqual(bien.status_code, 200, bien.text)
        self.cliente.invalidate_recordset()
        self.assertEqual((self.cliente.dcasa_ubic_origen, self.cliente.dcasa_ubic_precision_m), ('gps', 9))
        # Usado: ya no guarda otra vez y la página lo dice.
        self.assertEqual(self.post_json(base + '/guardar', {'lat': 8.95, 'lon': -79.85, 'origen': 'pin',
                                                            'referencia': 'Otra'}).status_code, 404)
        self.assertIn('Ya la tenemos', self.url_open(base).text)
        enlace.sudo().vence = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(self.url_open(base).status_code, 404)

    def test_un_cuerpo_gigante_o_roto_no_rompe_nada(self):
        _enlace, url = self.enlace()
        base = '/u/' + url.rsplit('/u/', 1)[1]
        self.assertEqual(self.url_open(base + '/zona', data='[' * 1500,
                                       headers={'Content-Type': 'application/json'}).status_code, 422)
        self.assertEqual(self.url_open(base + '/zona', data='x' * 5000,
                                       headers={'Content-Type': 'application/json'}).status_code, 413)

    # --- /entrega/<secreto> ----------------------------------------------------------------------------------------

    def test_la_pagina_del_chofer(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Portón negro')
        producto = self.env['product.product'].create({'name': 'Caja', 'list_price': 20, 'type': 'consu'})
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'order_line': [(0, 0, {'product_id': producto.id})],
            'carrier_id': self.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1).id})
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        respuesta = self.url_open('/entrega/' + entrega.sudo().token)
        self.assertEqual(respuesta.status_code, 200)
        for texto in ('Abrir en Waze', 'Abrir en Google Maps', 'Portón negro', 'tel:+50765550000', 'Bea'):
            self.assertIn(texto, respuesta.text)
        self.assertNotIn('Marcar entregado', respuesta.text, 'la página solo lee')
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.url_open('/entrega/' + 'y' * 24).status_code, 404)

    # --- POST /dcasa/juan/v1/ubicacion -----------------------------------------------------------------------------

    def conversacion(self):
        return self.env['dcasa.conversacion'].sudo()._registrar_mensaje({
            'canal': 'whatsapp_qr', 'id_externo': '50761239999', 'id_mensaje': 'wamid.ubic.1',
            'direccion': 'entrante', 'autor': 'cliente', 'texto': 'Hola', 'ts': datetime(2026, 10, 9, 15, 0),
            'nombre': None, 'celular': None, 'adjuntos': []})[0]

    def test_la_api_de_juan_guarda_la_ubicacion_del_chat(self):
        conv = self.conversacion()
        cab = {'Authorization': f'Bearer {TOKEN_ODOO}'}
        respuesta = self.post_json(f'{RAIZ}/ubicacion', {'conversacion_id': conv.id, 'lat': CERCA[0], 'lon': CERCA[1],
                                                         'origen': 'whatsapp', 'nombre_lugar': 'Mi casa'}, **cab)
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        resultado = respuesta.json()['resultado']
        self.assertTrue(resultado['guardada'])
        self.assertIn('Villa Prueba II', resultado['zona'])
        self.assertEqual(resultado['envio']['estado'], 'precio')
        self.assertTrue(resultado['envio']['por_ubicacion'])
        self.assertNotIn('8.9012', json.dumps(resultado), 'las coordenadas no vuelven al Worker (ni al modelo)')
        self.assertEqual(conv.partner_id.dcasa_ubic_origen, 'whatsapp')
        accion = self.env['brian.accion'].sudo().search([('dcasa_conversacion_id', '=', conv.id)], order='id desc',
                                                         limit=1)
        self.assertEqual(accion.herramienta, 'juan_cotizar_envio', 'auditado: agregar_envio lo reconoce')
        self.assertNotIn('8.9012', (accion.argumentos or '') + (accion.resultado or ''))
        # Lo que no sirve.
        lejos = {'conversacion_id': conv.id, 'lat': LEJOS[0], 'lon': LEJOS[1], 'origen': 'whatsapp'}
        for cuerpo, estado in ((lejos, 422),
                               ({'conversacion_id': conv.id, 'lat': 8.9, 'lon': -79.8, 'origen': 'gps'}, 400),
                               ({'conversacion_id': 'uno', 'lat': 8.9, 'lon': -79.8, 'origen': 'whatsapp'}, 400),
                               ({'conversacion_id': 999999, 'lat': 8.9, 'lon': -79.8, 'origen': 'whatsapp'}, 404)):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(self.post_json(f'{RAIZ}/ubicacion', cuerpo, **cab).status_code, estado)
        self.assertEqual(self.post_json(f'{RAIZ}/ubicacion', {'conversacion_id': conv.id}).status_code, 401)

    # --- /tienda/ubicacion/zona (checkout) --------------------------------------------------------------------------

    def test_la_vista_previa_del_checkout(self):
        datos = self.make_jsonrpc_request('/tienda/ubicacion/zona', {'lat': CERCA[0], 'lon': CERCA[1],
                                                                     'texto': 'Calle 3, Arraiján'})
        self.assertEqual(datos['distrito'], 'La Chorrera')
        self.assertIn('escribió Arraiján', datos['aviso'])
        self.assertTrue(datos['precio'])
        lugares = self.make_jsonrpc_request('/tienda/ubicacion/buscar', {'texto': 'villa prueba'})['lugares']
        self.assertTrue(lugares)
