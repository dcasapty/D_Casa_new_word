"""El cron que manda la cola a Meta: lotes, reintentos, token, entornos y retención. Ninguna prueba llama a Meta."""
import json
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CODIGO, CORREO, PIXEL, TOKEN, MetaCase, respuesta


@tagged('post_install', '-at_install')
class TestCola(MetaCase):

    def compra(self, partner=None):
        """Una compra de tienda pagada, con consentimiento, en la cola."""
        partner = partner or self.cliente
        self.aceptar(partner)
        factura = self.factura(partner=partner)
        self.pagar(factura)
        fila = self.fila(factura)
        self.assertEqual(fila.estado, 'pendiente')
        return fila

    def correr(self):
        return self.Evento._dcasa_cron_enviar()

    def test_sin_token_no_se_llama_a_meta(self):
        self.encender(token=False)
        fila = self.compra()
        self.correr()
        self.post.assert_not_called()
        self.assertEqual(fila.estado, 'pendiente')

    def test_con_los_interruptores_apagados_no_se_manda(self):
        self.encender()
        fila = self.compra()
        self.ICP.set_param('dcasa_meta.capi_tienda', False)
        self.correr()
        self.post.assert_not_called()
        self.assertEqual(fila.estado, 'pendiente')

    def test_sin_la_seccion_de_meta_en_la_politica_no_se_manda(self):
        self.encender(privacidad=False)
        fila = self.compra()
        self.correr()
        self.post.assert_not_called()
        self.assertEqual(fila.estado, 'pendiente')

    def test_envio_ok_con_el_token_en_el_cuerpo(self):
        self.encender()
        fila = self.compra()
        self.responder()
        self.assertEqual(self.correr(), 1)
        self.post.assert_called_once()
        url = self.post.call_args.args[0]
        self.assertEqual(url, f'https://graph.facebook.com/v26.0/{PIXEL}/events')
        self.assertNotIn(TOKEN, url)
        cuerpo = self.post.call_args.kwargs['data']
        self.assertEqual(cuerpo['access_token'], TOKEN)
        self.assertNotIn('test_event_code', cuerpo, 'En producción sale sin código de prueba')
        enviado = json.loads(cuerpo['data'])
        self.assertEqual([e['event_id'] for e in enviado], [fila.event_id])
        self.assertEqual((fila.estado, fila.fbtrace_id, fila.intentos), ('enviado', 'AbCdEfTrace', 1))
        self.assertTrue(fila.enviado_en)

    def test_en_staging_sin_codigo_de_prueba_no_sale_nada(self):
        self.encender()
        self.en_staging()
        fila = self.compra()
        self.correr()
        self.post.assert_not_called()
        self.assertEqual(fila.estado, 'omitido')
        self.assertFalse(fila.datos)
        self.assertIn('pruebas', fila.motivo)

    def test_en_staging_solo_sale_con_el_codigo_de_prueba(self):
        self.encender()
        self.en_staging()
        self.ICP.set_param('dcasa_meta.test_event_code', CODIGO)
        fila = self.compra()
        self.responder()
        self.correr()
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.kwargs['data']['test_event_code'], CODIGO)
        self.assertEqual(fila.estado, 'enviado')

    def test_un_400_del_lote_se_reintenta_uno_por_uno(self):
        self.encender()
        buena = self.compra()
        mala = self.compra(self.otro)
        rechazo = respuesta(400, {'error': {'code': 100, 'message': 'Invalid parameter', 'fbtrace_id': 'X1'}})
        self.responder(rechazo, respuesta(), rechazo)
        self.correr()
        self.assertEqual(self.post.call_count, 3, 'El lote y después cada uno por su lado')
        self.assertEqual(buena.estado, 'enviado')
        self.assertEqual((mala.estado, mala.intentos), ('pendiente', 1))
        self.assertIn('Invalid parameter', mala.ultimo_error)
        # Al segundo rechazo queda con error.
        mala.proximo_intento = fields.Datetime.now() - timedelta(minutes=1)
        self.responder(rechazo)
        self.correr()
        self.assertEqual((mala.estado, mala.intentos), ('error', 2))

    def test_un_500_espera_y_reintenta(self):
        self.encender()
        fila = self.compra()
        self.responder(respuesta(500, {}, 'Internal error'))
        antes = fields.Datetime.now()
        self.correr()
        self.assertEqual((fila.estado, fila.intentos), ('pendiente', 1))
        self.assertGreaterEqual(fila.proximo_intento, antes + timedelta(seconds=59))
        # Mientras no llega su hora no se vuelve a llamar.
        self.post.reset_mock()
        self.correr()
        self.post.assert_not_called()
        # Pasada la espera, sale.
        fila.proximo_intento = fields.Datetime.now() - timedelta(seconds=1)
        self.responder()
        self.correr()
        self.assertEqual((fila.estado, fila.intentos), ('enviado', 2))

    def test_sin_red_tambien_espera(self):
        self.encender()
        fila = self.compra()
        self.post.side_effect = requests.Timeout('tardó demasiado')
        self.correr()
        self.assertEqual((fila.estado, fila.intentos), ('pendiente', 1))
        self.assertTrue(fila.proximo_intento)

    def test_un_401_deja_todo_pendiente_y_avisa_en_ajustes(self):
        self.encender()
        filas = self.compra() | self.compra(self.otro)
        self.responder(respuesta(401, {'error': {'code': 190, 'message': 'Invalid OAuth access token'}}))
        self.correr()
        self.assertEqual(self.post.call_count, 1, 'Con el token malo no se insiste')
        self.assertEqual(set(filas.mapped('estado')), {'pendiente'})
        self.assertEqual(filas.mapped('intentos'), [0, 0])
        ajustes = self.env['res.config.settings'].create({})
        self.assertIn('no funciona', ajustes.dcasa_meta_token_estado)
        self.assertNotIn(TOKEN, ajustes.dcasa_meta_token_estado)
        # Cuando vuelve a funcionar, el aviso se quita solo.
        self.responder()
        self.correr()
        self.assertEqual(set(filas.mapped('estado')), {'enviado'})
        self.assertFalse(self.ICP.get_param('dcasa_meta.token_rechazado'))

    def test_lo_de_mas_de_seis_dias_se_descarta(self):
        self.encender()
        fila = self.compra()
        fila.event_time = fields.Datetime.now() - timedelta(days=6, hours=1)
        self.correr()
        self.post.assert_not_called()
        self.assertEqual(fila.estado, 'descartado')
        self.assertFalse(fila.datos)

    def test_ni_el_token_ni_el_correo_aparecen_en_el_registro(self):
        self.encender()
        fila = self.compra()
        texto = f'Error: access_token={TOKEN} usuario {CORREO.lower()} {fila.datos}'
        self.responder(respuesta(500, {'error': {'code': 2, 'message': texto, 'is_transient': True}}, texto))
        with self.assertLogs('odoo.addons.dcasa_meta_eventos', level='INFO') as registro:
            self.correr()
            self.responder(respuesta(400, {'error': {'code': 100, 'message': texto}}, texto))
            fila.proximo_intento = False
            self.correr()
        salida = '\n'.join(registro.output)
        for prohibido in (TOKEN, CORREO, CORREO.lower(), json.loads(fila.datos)['user_data']['em']):
            self.assertNotIn(prohibido, salida)
        self.assertNotIn(TOKEN, fila.ultimo_error)
        self.assertNotIn(CORREO.lower(), fila.ultimo_error)

    def test_reintentar_ahora_exige_gerencia(self):
        self.encender()
        fila = self.compra()
        fila.write({'estado': 'error', 'intentos': 2})
        with self.assertRaises(AccessError):
            self.env['dcasa.meta.evento'].with_user(self.vendedora).browse(fila.id).action_dcasa_meta_reintentar()
        self.env['dcasa.meta.evento'].with_user(self.gerencia).browse(fila.id).action_dcasa_meta_reintentar()
        self.assertEqual((fila.estado, fila.intentos), ('pendiente', 0))
        # Sin nada marcado (la cabecera de la lista llama con ids=[]): todo lo que tiene error.
        fila.write({'estado': 'error'})
        self.env['dcasa.meta.evento'].with_user(self.gerencia).browse().action_dcasa_meta_reintentar()
        self.assertEqual(fila.estado, 'pendiente')

    def test_nadie_crea_ni_escribe_eventos_por_rpc(self):
        for usuario in (self.vendedora, self.gerencia, self.admin):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.env['dcasa.meta.evento'].with_user(usuario).create({
                    'event_name': 'Purchase', 'event_id': f'falso-{usuario.id}', 'event_time': fields.Datetime.now()})
        self.assertFalse(self.env['dcasa.meta.evento'].with_user(self.vendedora).has_access('read'))
        self.assertTrue(self.env['dcasa.meta.evento'].with_user(self.gerencia).has_access('read'))


@tagged('post_install', '-at_install')
class TestRetencion(MetaCase):

    def test_se_borra_lo_viejo(self):
        self.encender()
        self.aceptar()
        factura = self.factura()
        self.pagar(factura)
        fila = self.fila(factura)
        fila.estado = 'enviado'
        vieja = self.Evento.create({'event_name': 'PageView', 'event_id': 'prueba-vieja', 'origen': 'prueba',
                                    'event_time': fields.Datetime.now(), 'estado': 'enviado', 'es_prueba': True})
        pedido = self.pedido_web(partner=self.otro)
        pedido._dcasa_meta_guardar_navegador('fb.1.1700000000000.1', None, 'Mozilla', '203.0.113.9', 'https://x/')
        self.env.flush_all()
        self.env.cr.execute("UPDATE dcasa_meta_evento SET create_date = now() - interval '8 days' WHERE id = %s",
                            [fila.id])
        self.env.cr.execute("UPDATE dcasa_meta_evento SET create_date = now() - interval '181 days' WHERE id = %s",
                            [vieja.id])
        self.env.cr.execute("UPDATE sale_order SET dcasa_meta_consentimiento_navegador = now() - interval '31 days' "
                            "WHERE id = %s", [pedido.id])
        self.env.invalidate_all()
        with patch('requests.post') as post:
            self.Evento._dcasa_cron_retencion()
        post.assert_not_called()
        self.assertFalse(fila.datos, 'El JSON se borra a los 7 días')
        self.assertTrue(fila.exists(), 'La fila queda para la lista')
        self.assertFalse(vieja.exists(), 'A los 180 días se borra la fila')
        self.assertFalse(pedido.sudo().dcasa_meta_ua, 'Pedido sin pagar: el navegador se borra a los 30 días')
        self.assertFalse(pedido.sudo().dcasa_meta_ip)
