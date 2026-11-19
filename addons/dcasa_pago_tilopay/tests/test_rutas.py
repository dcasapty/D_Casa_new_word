"""Las rutas públicas de verdad (HTTP): el aviso, el retorno del cliente y «Estado del pago». Siempre con el
Tilopay simulado."""
import json
import logging

from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException

from .common import SECRETOS, ComunTilopay, SimuladorTilopay

AVISO = '/payment/tilopay/webhook'
RETORNO = '/payment/tilopay/return'


class BaseHttp(ComunTilopay, HttpCase):

    def post_json(self, ruta, cuerpo, **kwargs):
        return self.url_open(ruta, data=json.dumps(cuerpo), headers={'Content-Type': 'application/json'}, **kwargs)

    def releer(self, *txs):
        for tx in txs:
            tx.invalidate_recordset()


@tagged('post_install', '-at_install')
class TestAviso(BaseHttp):

    def test_confirma_y_responde_lo_mismo_exista_o_no_la_orden(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            real = self.post_json(AVISO, {'orderNumber': orden, 'code': '1'})
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1)
            desconocida = self.post_json(AVISO, {'orderNumber': 'S99999-1-deadbeef'})
            basura = self.post_json(AVISO, ['esto', 'no', 'es', 'un', 'aviso'])
            sin_orden = self.post_json(AVISO, {'nada': 'util'})
            con_forma_rara = self.post_json(AVISO, {'orderNumber': {'a': 1}, 'order': ["x"]})
            inyeccion = self.post_json(AVISO, {'orderNumber': "x'; DROP TABLE payment_transaction;--"})
            vacio = self.url_open(AVISO, data='')
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1,
                             'ninguna orden inventada ni cuerpo raro hace llamar a Tilopay')
        respuestas = [real, desconocida, basura, sin_orden, con_forma_rara, inyeccion, vacio]
        self.assertEqual({r.status_code for r in respuestas}, {200})
        self.assertEqual(len({r.content for r in respuestas}), 1, 'el cuerpo no revela si la orden existe')
        self.assertEqual(real.json(), {'estado': 'ok'})
        for r in respuestas:
            self.assertNotIn('Set-Cookie', r.headers, 'no se le da una sesión a nadie')
            for secreto in SECRETOS:
                self.assertNotIn(secreto, r.text)
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_el_aviso_viaja_tambien_como_formulario(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            r = self.url_open(AVISO, data={'orderNumber': orden})
        self.assertEqual(r.status_code, 200)
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_solo_acepta_post(self):
        for metodo in ('GET', 'PUT', 'DELETE'):
            r = self.url_open(AVISO, method=metodo)
            self.assertEqual(r.status_code, 405, metodo)

    def test_un_cuerpo_enorme_se_rechaza_sin_llamar_a_nadie(self):
        with SimuladorTilopay() as tilopay:
            r = self.url_open(AVISO, data=json.dumps({'orderNumber': 'x' * 40_000}),
                              headers={'Content-Type': 'application/json'})
            self.assertEqual(r.status_code, 413)
            self.assertEqual(tilopay.llamadas, [])

    def test_repetir_el_mismo_aviso_no_duplica_ni_vuelve_a_preguntar(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            for _i in range(5):
                self.assertEqual(self.post_json(AVISO, {'orderNumber': orden}).status_code, 200)
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1)
        self.releer(tx)
        tx._post_process()
        self.assertEqual(self.env['account.payment'].search_count([('payment_transaction_id', '=', tx.id)]), 1)

    def test_apagado_el_aviso_no_cambia_nada(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.proveedor.state = 'disabled'
            r = self.post_json(AVISO, {'orderNumber': orden})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.llamadas_a_consulta(tilopay), [])
        self.releer(tx)
        self.assertEqual(tx.state, 'draft')

    def test_un_aviso_con_tilopay_caido_responde_igual_y_no_paga(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.falla = 'tiempo'
            api.olvidar_tokens()
            with self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'WARNING'):
                r = self.post_json(AVISO, {'orderNumber': orden})
        self.assertEqual((r.status_code, r.json()), (200, {'estado': 'ok'}))
        self.releer(tx)
        self.assertEqual(tx.state, 'draft')


@tagged('post_install', '-at_install')
class TestRetorno(BaseHttp):

    def volver(self, **parametros):
        return self.url_open(RETORNO, params=parametros, allow_redirects=False)

    def test_un_retorno_inventado_con_code_1_no_paga(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            r = self.volver(code='1', description='Transaction is approved.', order=orden, auth='123456',
                            OrderHash='b02927cb', tpt='4300')
            self.assertEqual(r.status_code, 303)
            self.assertTrue(r.headers['Location'].endswith('/payment/status'))
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1, 'se le preguntó a Tilopay, no al navegador')
        self.releer(tx)
        self.assertEqual(tx.state, 'draft')
        self.assertEqual(pedido.state, 'draft')

    def test_el_retorno_con_pago_real_confirma(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            r = self.volver(code='1', order=orden)
        self.assertEqual(r.status_code, 303)
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_si_order_no_es_la_nuestra_se_usa_return_data(self):
        """El ejemplo de Tilopay trae order=TPYS-…: si no es nuestra orden, vale lo que mandamos en returnData."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.volver(code='1', order='TPYS-881WROIBQA1405468', returnData=api.codificar_return_data(orden))
        self.releer(tx)
        self.assertEqual(tx.state, 'done')

    def test_vuelve_sin_pagar_y_sin_nada_en_tilopay_se_cancela(self):
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay)
            self.volver(code='0', order=orden, description='cancelado')
        self.releer(tx)
        self.assertEqual(tx.state, 'cancel')

    def test_el_mismo_destino_exista_o_no_la_orden_y_por_get_o_post(self):
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay)
            destinos = {
                self.volver(order=orden).headers['Location'],
                self.volver(order='S99999-1-deadbeef').headers['Location'],
                self.volver().headers['Location'],
                self.volver(order="x'; DROP TABLE x;--", returnData='!!!').headers['Location'],
                self.url_open(RETORNO, data={'code': '1', 'order': orden}, allow_redirects=False).headers['Location'],
            }
        self.assertEqual(len({d.rsplit('/payment/status', 1)[0] and '/payment/status' for d in destinos}), 1)
        self.assertTrue(all(d.endswith('/payment/status') for d in destinos))

    def test_no_se_llama_a_tilopay_con_una_orden_inventada(self):
        with SimuladorTilopay() as tilopay:
            self.volver(order='S99999-1-deadbeef', code='1')
            self.volver(returnData=api.codificar_return_data('S99999-1-deadbeef'))
            self.assertEqual(tilopay.llamadas, [])


@tagged('post_install', '-at_install')
class TestPagarDesdeElPortalYEstadoDelPago(BaseHttp):

    def abrir_desde_el_portal(self, pedido, monto=None):
        return self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
            'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
            'payment_method_id': self.metodo.id, 'token_id': None,
            'amount': pedido.amount_total if monto is None else monto, 'flow': 'redirect',
            'tokenization_requested': False, 'landing_route': pedido.get_portal_url(), 'is_validation': False})

    def test_pagar_desde_mis_pedidos_y_esperar_en_estado_del_pago(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            valores = self.abrir_desde_el_portal(pedido)
            self.assertIn('https://secure.tilopay.com/htmls/', valores['redirect_form_html'])
            orden = tilopay.orden_del_ultimo_pago()
            tx = self.env['payment.transaction'].search([('dcasa_tilopay_orden', '=', orden)])
            self.assertEqual(tx.amount, pedido.amount_total)
            # El cliente paga y todavía no vuelve; en «Estado del pago» el reloj de la página le pregunta a Tilopay.
            tilopay.aprobar(orden, pedido.amount_total)
            primera = self.make_jsonrpc_request('/payment/status/poll', {})
            self.assertEqual(primera['state'], 'done')
            self.assertEqual(primera['provider_code'], 'tilopay')
            self.assertEqual(primera['landing_route'], pedido.get_portal_url())
            segunda = self.make_jsonrpc_request('/payment/status/poll', {})
            self.assertEqual(segunda['state'], 'done')
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1, 'ya pagada: no se vuelve a preguntar')
        self.releer(tx, pedido)
        self.assertEqual(pedido.state, 'sale', 'el reloj de la página también termina el trabajo de Odoo')
        self.assertEqual(tx.payment_id.journal_id.code, 'TLP')

    def test_el_reloj_de_la_pagina_no_gasta_llamadas_de_mas(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            self.abrir_desde_el_portal(pedido)
            for _i in range(6):
                self.assertEqual(self.make_jsonrpc_request('/payment/status/poll', {})['state'], 'draft')
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1, 'una consulta cada 5 segundos, no cada vuelta')

    def test_el_monto_que_manda_el_navegador_no_sirve_en_el_portal(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            for monto in (1.0, pedido.amount_total - 1):
                with self.assertRaises(JsonRpcException):
                    self.abrir_desde_el_portal(pedido, monto)
            self.assertEqual(tilopay.llamadas, [])

    def test_ningun_registro_del_servidor_trae_claves_en_todo_el_recorrido(self):
        pedido = self.pedido()
        with self.assertLogs(level=logging.DEBUG) as registros, SimuladorTilopay() as tilopay:
            logging.getLogger('odoo.test').info('inicio')
            self.abrir_desde_el_portal(pedido)
            orden = tilopay.orden_del_ultimo_pago()
            self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
            tilopay.aprobar(orden, pedido.amount_total)
            self.post_json(AVISO, {'orderNumber': orden})
            tilopay.falla = 'tiempo'
            self.post_json(AVISO, {'orderNumber': orden})
            tilopay.claves_buenas = False
            api.olvidar_tokens()
            self.post_json(AVISO, {'orderNumber': orden})
        texto = '\n'.join(registros.output)
        for secreto in (*SECRETOS, tilopay.token):
            self.assertNotIn(secreto, texto)
