"""El pase (contrato §1 y contrato_cambios §1 y §2): la firma, la red, el sid de la sesión, el tope por red (también con
pedidos a la vez), el apagado y Turnstile."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import psycopg2.errors

from odoo import SUPERUSER_ID, api, fields, sql_db
from odoo.tests import tagged
from odoo.tools import mute_logger

from ..models import pase as P
from . import worker_simulado as W
from .common import TOKEN_WORKER, URL_WORKER, TiendaCase


def _payload(pase):
    cuerpo = pase.split('.')[0]
    return json.loads(base64.urlsafe_b64decode(cuerpo + '=' * (-len(cuerpo) % 4)))


@tagged('post_install', '-at_install')
class TestFirmaYRed(TiendaCase):

    def test_la_red_como_la_escribe_el_worker(self):
        for ip, red in (('190.140.12.34', '190.140.12.0/24'), ('2001:0db8:0000:0001:aaaa::1', '2001:db8:0:1::/64'),
                        ('::ffff:190.140.12.34', '190.140.12.0/24'), ('2001:db8::1', '2001:db8:0:0::/64'),
                        ('127.0.0.1', '127.0.0.0/24'), ('2800:e2:5c00:ab1::9', '2800:e2:5c00:ab1::/64')):
            with self.subTest(ip=ip):
                self.assertEqual(P.red_de(ip), red)
                self.assertEqual(W._red(ip), red, 'el Worker simulado (otra implementación) dice lo mismo')
        for malo in ('', None, 'no-es-ip', '300.1.1.1'):
            self.assertIsNone(P.red_de(malo))

    def test_la_firma_es_la_del_contrato(self):
        respuesta = self.post('pase', {'turnstile': ''})
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos['ok'], datos)
        self.assertEqual((datos['worker'], datos['vence_en']), (URL_WORKER, 1800))
        self.assertIsInstance(datos['noche'], bool)
        self.assertIn('p. m.', datos['horario_texto'])
        # La firma, calculada aparte: llave = HMAC(JUAN_WORKER_TOKEN, «brian-tienda-pase-v1»), 32 bytes crudos.
        cuerpo, firma = datos['pase'].split('.')
        llave = hmac.new(TOKEN_WORKER.encode(), b'brian-tienda-pase-v1', hashlib.sha256).digest()
        esperada = base64.urlsafe_b64encode(hmac.new(llave, cuerpo.encode(), hashlib.sha256).digest()).rstrip(b'=')
        self.assertEqual(firma, esperada.decode())
        self.assertNotIn('=', datos['pase'])
        payload = _payload(datos['pase'])
        self.assertEqual(set(payload), {'v', 'sid', 'exp', 'red', 'sitio'})
        self.assertEqual((payload['v'], payload['red'], payload['sitio']), (1, '127.0.0.0/24', self.website.id))
        self.assertEqual(len(payload['sid']), 22)
        self.assertAlmostEqual(payload['exp'], time.time() + 1800, delta=60)
        # El Worker (simulado, con su propia implementación) lo acepta; uno alterado o con otra llave, no.
        self.assertEqual(W.leer_pase(datos['pase'], TOKEN_WORKER)['sid'], payload['sid'])
        self.assertEqual(P.leer_pase(datos['pase'], TOKEN_WORKER)['sid'], payload['sid'])
        self.assertIsNone(W.leer_pase(datos['pase'], 'x' * 40))
        otro = dict(payload, red='10.0.0.0/24')
        alterado = base64.urlsafe_b64encode(json.dumps(otro).encode()).rstrip(b'=').decode() + '.' + firma
        self.assertIsNone(W.leer_pase(alterado, TOKEN_WORKER))
        self.assertIsNone(W.leer_pase(datos['pase'][:-2] + 'xx', TOKEN_WORKER))
        vencido = P.firmar(dict(payload, exp=int(time.time()) - 1), TOKEN_WORKER)
        self.assertIsNone(W.leer_pase(vencido, TOKEN_WORKER))
        self.assertIsNone(P.leer_pase(vencido, TOKEN_WORKER))

    def test_el_mismo_navegador_recibe_el_mismo_sid(self):
        primero = _payload(self.post('pase').json()['pase'])['sid']
        self.assertEqual(_payload(self.post('pase').json()['pase'])['sid'], primero)
        self.otra_sesion()
        self.assertNotEqual(_payload(self.post('pase').json()['pase'])['sid'], primero, 'otro navegador, otro sid')

    def test_sin_csrf_o_sin_json_no_hay_pase(self):
        self.assertEqual(self.post('pase', csrf=False).status_code, 403)
        self.assertEqual(self.post('pase', csrf=False).json()['motivo'], 'csrf')
        self.assertEqual(self.post('pase', csrf='0' * 40 + 'o9999999999').status_code, 403)
        self.assertEqual(self.post('pase', 'turnstile=', tipo='application/x-www-form-urlencoded').status_code, 415)
        self.assertEqual(self.post('pase', json.dumps({'turnstile': 'x' * 3000})).status_code, 413)
        self.assertEqual(self.post('pase', '[1, 2]').json()['motivo'], 'formato')

    def test_apagado_o_sin_worker_no_hay_pase(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'False')
        self.assertEqual(self.post('pase').json(), {'ok': False, 'motivo': 'apagado'})
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'True')
        with patch.dict('os.environ', {'JUAN_WORKER_TOKEN': ''}):
            self.assertEqual(self.post('pase').json(), {'ok': False, 'motivo': 'apagado'})
        with patch.dict('os.environ', {'JUAN_URL': 'http://otro-sitio.example.com'}):
            self.assertEqual(self.post('pase').json(), {'ok': False, 'motivo': 'apagado'}, 'solo https (o local)')

    def test_turnstile_solo_si_el_sitio_lo_tiene(self):
        Parametro = self.env['ir.config_parameter'].sudo()
        clase = type(self.env['ir.http'])
        with patch.object(clase, '_verify_turnstile_token', create=True, return_value='wrong_token') as verificar:
            self.assertTrue(self.post('pase').json()['ok'], 'sin claves, sin Turnstile (hoy)')
            verificar.assert_not_called()
            Parametro.set_param('cf.turnstile_site_key', '1x00000000000000000000AA')
            Parametro.set_param('cf.turnstile_secret_key', 'secreto-de-prueba')
            self.otra_sesion()
            self.assertEqual(self.post('pase', {'turnstile': ''}).json(), {'ok': False, 'motivo': 'verificacion'})
            self.assertEqual(self.post('pase', {'turnstile': 'malo'}).json()['motivo'], 'verificacion')
            verificar.return_value = 'is_human'
            self.assertTrue(self.post('pase', {'turnstile': 'bueno'}).json()['ok'])
            llamadas = verificar.call_count
            self.assertTrue(self.post('pase', {'turnstile': ''}).json()['ok'], 'verificada, la sesión no lo repite')
            self.assertEqual(verificar.call_count, llamadas)

    def test_la_pagina_de_quien_abrio_el_chat_se_sigue_sirviendo_del_borde(self):
        """El sid y la hora del pase no vuelven personal la sesión (dcasa_tienda_borde, CLAVES_NEUTRAS)."""
        if 'dcasa.tienda.pendiente' not in self.env:
            self.skipTest('dcasa_tienda_borde no está instalado en esta base')
        respuesta = self.post('pase')
        self.assertTrue(respuesta.json()['ok'])
        self.assertNotIn('dcasa_personal=1', respuesta.headers.get('Set-Cookie', ''))
        self.assertNotIn('dcasa_personal=1', self.url_open('/').headers.get('Set-Cookie', ''))


@tagged('post_install', '-at_install')
class TestTopeDePases(TiendaCase):

    def test_tope_por_red_y_por_hora(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.tope_pases_red_hora', '2')
        self.assertTrue(self.post('pase').json()['ok'])
        self.assertTrue(self.post('pase').json()['ok'], 'la misma sesión en la misma hora no gasta otro cupo')
        self.otra_sesion()
        self.assertTrue(self.post('pase').json()['ok'])
        self.otra_sesion()
        self.assertEqual(self.post('pase').json(), {'ok': False, 'motivo': 'tope'}, 'tercer navegador de la misma red')
        # Lo que se guarda no dice de quién es: la llave es una huella, nunca la red.
        llaves = self.env['dcasa.brian.tienda.cupo'].sudo().search([]).mapped('llave')
        self.assertTrue(llaves)
        self.assertFalse([llave for llave in llaves if '127.0.0' in llave])

    def test_el_tope_cuenta_la_ip_entera_o_la_64_nunca_la_24(self):
        """Muchos clientes del mismo operador comparten una /24 (y está el CGNAT): el tope cuenta la IPv4 entera o la
        red /64 de la IPv6, como el borde y el Worker (contrato_cambios, «2026-11-13 (2)»)."""
        self.assertEqual(P.conexion_de('::ffff:190.140.12.34'), '190.140.12.34')
        self.assertEqual(P.conexion_de('2800:e2:5c00:ab1::9'), '2800:e2:5c00:ab1::/64')
        self.assertIsNone(P.conexion_de('no-es-ip'))
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.tope_pases_red_hora', '1')
        Tienda = self.env['dcasa.brian.tienda'].sudo()

        def pase(ip):
            return Tienda._emitir({}, ip, self.website).get('motivo', 'ok')   # {} = un navegador nuevo cada vez

        self.assertEqual(pase('190.140.12.34'), 'ok')
        self.assertEqual(pase('190.140.12.34'), 'tope', 'otro navegador, la misma IP')
        self.assertEqual(pase('::ffff:190.140.12.34'), 'tope', 'la misma IPv4 escrita como IPv6')
        self.assertEqual(pase('190.140.12.35'), 'ok', 'la vecina de la misma /24 tiene su propio cupo')
        self.assertEqual(pase('2800:e2:5c00:ab1::9'), 'ok')
        self.assertEqual(pase('2800:e2:5c00:ab1:ffff::1'), 'tope', 'la misma /64')

    def test_cero_cierra_y_la_hora_siguiente_vuelve_a_empezar(self):
        Tienda = self.env['dcasa.brian.tienda'].sudo()
        llave = f'prueba:{uuid.uuid4().hex}'
        ahora = fields.Datetime.now().replace(minute=10)
        self.assertFalse(Tienda._reservar(llave, 0, ahora), '0 = cerrado')
        self.assertTrue(Tienda._reservar(f'{llave}b', 1, ahora))
        self.assertFalse(Tienda._reservar(f'{llave}b', 1, ahora))
        self.assertTrue(Tienda._reservar(f'{llave}b', 1, ahora.replace(hour=(ahora.hour + 1) % 24)),
                        'otra hora, cuenta nueva')

    def test_dos_pedidos_a_la_vez_no_se_llevan_el_mismo_cupo(self):
        """La lección B1 de la búsqueda por foto: B empieza su transacción (su «foto» de la base), A reserva el único
        cupo y confirma; B ya no puede tomarlo. PostgreSQL le da un error de serialización y Odoo repite la petición
        de B, que entonces ve la cuenta de A y recibe «tope». Contando filas, B se llevaba el mismo cupo."""
        llave = f'prueba-carrera:{uuid.uuid4().hex}'
        base = sql_db.db_connect(self.env.cr.dbname)
        cr_a, cr_b = base.cursor(), base.cursor()
        try:
            env_a = api.Environment(cr_a, SUPERUSER_ID, {})
            env_b = api.Environment(cr_b, SUPERUSER_ID, {})
            cr_b.execute('SELECT 1')   # B empieza su petición antes de que A confirme
            self.assertTrue(env_a['dcasa.brian.tienda']._reservar(llave, 1))
            cr_a.commit()
            with self.assertRaises(psycopg2.errors.SerializationFailure), mute_logger('odoo.sql_db'):
                env_b['dcasa.brian.tienda']._reservar(llave, 1)
            cr_b.rollback()
            # Odoo repite la petición: con la transacción nueva, la cuenta de A ya se ve.
            self.assertFalse(env_b['dcasa.brian.tienda']._reservar(llave, 1))
            cr_b.commit()
        finally:
            for cr in (cr_a, cr_b):
                cr.rollback()
            cr_a.execute('DELETE FROM dcasa_brian_tienda_cupo WHERE llave = %s', [llave])
            cr_a.commit()
            cr_a.close()
            cr_b.close()

    def test_los_contadores_viejos_se_borran(self):
        Cupo = self.env['dcasa.brian.tienda.cupo'].sudo()
        hace_tres_dias = fields.Datetime.now() - timedelta(days=3)
        viejo = Cupo.create({'llave': f'viejo:{uuid.uuid4().hex}', 'ventana': hace_tres_dias, 'cuenta': 3})
        nuevo = Cupo.create({'llave': f'nuevo:{uuid.uuid4().hex}', 'ventana': fields.Datetime.now(), 'cuenta': 1})
        Cupo._cron_limpiar()
        self.assertFalse(viejo.exists())
        self.assertTrue(nuevo.exists())
