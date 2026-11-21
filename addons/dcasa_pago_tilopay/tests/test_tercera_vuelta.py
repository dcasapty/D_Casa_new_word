"""TERCERA VUELTA del revisor independiente de ``dcasa_pago_tilopay`` (sobre f6a04a4), tal como la entregó.

Intentos de romper los arreglos de la segunda vuelta: el freno por conexión (con 100 000 conexiones falsas), el cupo
de llamadas a Tilopay, la revisión humana de los cobros que no cuadran (N-6), la marca de «una sola vez» del aviso de
estado raro (N-2) y que lo que no se puede pagar tampoco se ofrece a un visitante (N-5). Las dos pruebas que al
entregarse fallaban a propósito (N-2 y N-5) ya pasan con el arreglo.
"""
import json
import logging
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.addons.dcasa_pago_tilopay.controllers import main as controlador
from odoo.addons.dcasa_pago_tilopay.models import payment_transaction as modulo_tx
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.addons.dcasa_pago_tilopay.models.tilopay_ritmo import LimiteDeRitmo
from odoo.addons.dcasa_pago_tilopay.tests.common import ComunTilopay, SimuladorTilopay
from odoo.tests import BaseCase, HttpCase, TransactionCase, tagged

RETORNO = '/payment/tilopay/return'
AVISO = '/payment/tilopay/webhook'
RESUMEN_TOTAL = 'Tilopay: cobro que no cuadra con el pedido'


class Base(ComunTilopay, TransactionCase):

    def cron(self):
        return self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()

    def actividades(self, pedido, resumen=None):
        dominio = [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id)]
        if resumen:
            dominio.append(('summary', '=', resumen))
        return self.env['mail.activity'].sudo().search(dominio)


# ---------------------------------------------------------------------------------------------------------------------
# N-1: el freno por conexión, su memoria, y que no estorbe a Tilopay.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestRv3Freno(BaseCase):

    def test_la_memoria_tiene_tope_con_cien_mil_conexiones_falsas_y_tilopay_sigue_pasando(self):
        """Direcciones falsas sin fin (IPv4 o redes IPv6 /64 distintas): el diccionario nunca pasa de ``max_llaves``, el
        costo por petición es chico, y la llave de Tilopay (otra) nunca se ve afectada por el desborde."""
        freno = LimiteDeRitmo(maximo=120, ventana=60)
        inicio = time.monotonic()
        for i in range(100_000):
            freno.permitir(f'2001:db8:{i >> 16:x}:{i & 0xffff:x}::/64', ahora=1000.0 + i * 0.001)
            self.assertLessEqual(len(freno._intentos), freno.max_llaves)
        self.assertLess(time.monotonic() - inicio, 15, 'el desborde no vuelve lenta cada petición')
        self.assertTrue(freno.permitir('52.0.0.1', ahora=1200.0), 'la llave de Tilopay entra aunque haya desborde')
        for _i in range(119):
            self.assertTrue(freno.permitir('52.0.0.1', ahora=1200.0))
        self.assertFalse(freno.permitir('52.0.0.1', ahora=1200.0), 'y a la 121 sí se frena, como a cualquiera')

    def test_la_ventana_se_desliza_y_una_llave_no_gasta_el_turno_de_otra(self):
        freno = LimiteDeRitmo(maximo=3, ventana=60)
        self.assertEqual([freno.permitir('a', ahora=t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(freno.permitir('b', ahora=3))
        self.assertTrue(freno.permitir('a', ahora=61), 'pasó la ventana de la primera')


@tagged('post_install', '-at_install')
class TestRv3CupoNoSeFuga(Base):

    def test_un_error_inesperado_dentro_de_la_llamada_no_deja_un_lugar_ocupado(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, _orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, minutes=10)
        antes = api.llamadas_en_vuelo()
        for falla in (RuntimeError('boom'), MemoryError(), ValueError('x'), OSError('y')):
            with self.subTest(falla=type(falla).__name__), patch('requests.post', side_effect=falla):
                api.olvidar_tokens()
                try:
                    tx.dcasa_tilopay_consulta = False
                    tx._dcasa_tilopay_confirmar('cron')
                except (RuntimeError, MemoryError, ValueError, OSError):
                    pass
                self.assertEqual(api.llamadas_en_vuelo(), antes, 'el lugar se soltó')

    def test_el_login_y_la_consulta_no_cuentan_doble(self):
        """La sesión (login) y la consulta son dos llamadas SEGUIDAS, no anidadas: con el tope en 1 pasan las dos."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, minutes=10)
            api.olvidar_tokens()
            tilopay.aprobar(orden, pedido.amount_total)
            with patch.object(api, 'TOPE_DE_LLAMADAS_A_LA_VEZ', 1), patch.object(api, 'RESERVA_PARA_LA_TAREA', 0):
                self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.APROBADO)


# ---------------------------------------------------------------------------------------------------------------------
# N-6: ningún camino paga solo una transacción marcada para revisión (retorno, aviso y reloj de estado por HTTP).
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestRv3RevisionPorHttp(ComunTilopay, HttpCase):

    def setUp(self):
        super().setUp()
        controlador.RITMO.olvidar()
        self.addCleanup(controlador.RITMO.olvidar)

    def cron(self):
        return self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()

    def abrir_desde_el_portal(self, pedido):
        return self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
            'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
            'payment_method_id': self.metodo.id, 'token_id': None, 'amount': pedido.amount_total, 'flow': 'redirect',
            'tokenization_requested': False, 'landing_route': pedido.get_portal_url(), 'is_validation': False})

    def test_ni_el_retorno_ni_el_aviso_ni_el_reloj_pagan_una_transaccion_marcada(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            self.abrir_desde_el_portal(pedido)
            orden = tilopay.orden_del_ultimo_pago()
            tx = self.env['payment.transaction'].search([('dcasa_tilopay_orden', '=', orden)])
            cobrado = pedido.amount_total
            pedido.order_line.product_uom_qty = 5
            tilopay.aprobar(orden, cobrado)
            primera = self.make_jsonrpc_request('/payment/status/poll', {})
            self.assertEqual(primera['state'], 'error')
            tx.invalidate_recordset()
            self.assertTrue(tx.dcasa_tilopay_revision)
            pedido.order_line.product_uom_qty = 1                       # el pedido vuelve a valer lo cobrado
            for intento in range(3):
                tx.dcasa_tilopay_consulta = False
                tx.invalidate_recordset()
                if intento == 0:
                    self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
                elif intento == 1:
                    self.url_open(AVISO, data=json.dumps({'orderNumber': orden}), method='POST',
                                  headers={'Content-Type': 'application/json'})
                else:
                    self.make_jsonrpc_request('/payment/status/poll', {})
                tx.invalidate_recordset()
                self.assertEqual(tx.state, 'error', f'intento {intento}: no se paga sola')
            tx._post_process()
            self.cron()
        tx.invalidate_recordset()
        pedido.invalidate_recordset()
        self.assertEqual(tx.state, 'error')
        self.assertNotEqual(pedido.state, 'sale')

    def test_una_transaccion_nueva_para_el_mismo_pedido_si_se_puede_pagar(self):
        """El camino correcto tras un cobro que no cuadró: otra página de pago (otra orden) por el total actual."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            self.abrir_desde_el_portal(pedido)
            orden = tilopay.orden_del_ultimo_pago()
            cobrado = pedido.amount_total
            pedido.order_line.product_uom_qty = 5
            tilopay.aprobar(orden, cobrado)
            self.make_jsonrpc_request('/payment/status/poll', {})
            self.abrir_desde_el_portal(pedido)
            orden2 = tilopay.orden_del_ultimo_pago()
            self.assertNotEqual(orden, orden2)
            tilopay.aprobar(orden2, pedido.amount_total)
            tx2 = self.env['payment.transaction'].search([('dcasa_tilopay_orden', '=', orden2)])
            self.assertEqual(tx2._dcasa_tilopay_confirmar('retorno'), api.APROBADO)
            tx2._post_process()
        self.assertEqual(pedido.state, 'sale')


# ---------------------------------------------------------------------------------------------------------------------
# N-2: «una sola vez» y la huella; N-5: lo que se ofrece.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestRv3EstadoRaroYHuella(Base):

    def test_el_aviso_de_estado_raro_no_se_repite_aunque_gerencia_cierre_la_actividad(self):
        """N-2. «Una sola vez» ya no depende de que la actividad siga abierta: queda una marca en la transacción
        (``dcasa_tilopay_aviso_raro``). Antes, cuando Gerencia daba la actividad por hecha, la siguiente consulta (cada
        hora, hasta 3 días) volvía a dejar nota y actividad, hasta que el estado se resolviera, que puede ser nunca."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, hours=2)
            tilopay.pagos[orden] = [tilopay.fila(orden, pedido.amount_total, code='A7', response='Autorizada')]
            tx.dcasa_tilopay_veredicto = api.PENDIENTE
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.PENDIENTE)
            resumen = self.env._('Tilopay: estado que no se entiende (%s)', tx.reference)
            primeras = self.actividades(pedido, resumen)
            self.assertTrue(primeras)
            primeras.action_done()   # Gerencia la da por atendida (Odoo deja su propia nota)
            self.assertFalse(self.actividades(pedido, resumen))
            notas_antes = len(pedido.message_ids)
            tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(hours=2)
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.PENDIENTE)
        self.assertFalse(self.actividades(pedido, resumen), 'la actividad no debería volver a aparecer')
        self.assertEqual(len(pedido.message_ids), notas_antes, 'ni otra nota')

    def test_la_huella_depende_del_secreto_no_se_loguea_y_no_es_la_direccion(self):
        class PeticionFalsa:
            def __init__(self, ip):
                self.httprequest = type('H', (), {'remote_addr': ip})()
        modelo = self.env['payment.transaction']
        with self.assertLogs(level=logging.DEBUG) as registros, \
                patch.object(modulo_tx, 'request', PeticionFalsa('203.0.113.77')):
            logging.getLogger('odoo.test').info('inicio')
            huella = modelo._dcasa_tilopay_huella_de_la_conexion()
            self.assertTrue(huella)
            self.assertEqual(len(huella), 24)
            self.assertNotIn('203', huella)
            with patch.object(modulo_tx, 'request', PeticionFalsa('203.0.113.78')):
                self.assertNotEqual(modelo._dcasa_tilopay_huella_de_la_conexion(), huella)
            with patch.object(modulo_tx, 'request', PeticionFalsa('2001:db8::1')), patch.object(
                    modulo_tx, 'llave_ip', wraps=modulo_tx.llave_ip):
                v6a = modelo._dcasa_tilopay_huella_de_la_conexion()
            with patch.object(modulo_tx, 'request', PeticionFalsa('2001:db8::ffff')):
                self.assertEqual(modelo._dcasa_tilopay_huella_de_la_conexion(), v6a, 'misma red /64 = misma huella')
            self.env['ir.config_parameter'].sudo().set_param('database.secret', 'otro-secreto')
            self.assertNotEqual(modelo._dcasa_tilopay_huella_de_la_conexion(), huella)
            self.env['ir.config_parameter'].sudo().set_param('database.secret', '')
            self.assertFalse(modelo._dcasa_tilopay_huella_de_la_conexion(),
                             'sin secreto en la base no hay huella (y el tope por conexión queda apagado)')
        texto = '\n'.join(registros.output)
        self.assertNotIn('203.0.113', texto)

    def test_publicado_en_modo_de_prueba_en_produccion_no_se_le_ofrece_al_visitante(self):
        """N-5 (menor, UX). El pago de un visitante ya fallaba en producción con «Modo de prueba» aunque se pulsara
        «Publicado»; pero la lista seguía mostrando la opción «Tarjeta de crédito o débito» y el visitante recibía el
        error en el último paso. Ahora ni sale (y al equipo interno sí le sale, para que lo pruebe)."""
        self.proveedor.write({'state': 'test', 'is_published': True})
        publico = self.env.ref('base.public_user')
        pedido = self.pedido()
        with patch.dict('os.environ', {'DCASA_ENTORNO': 'produccion', 'TILOPAY_ENTORNO': 'prueba'}):
            ofrecidos = self.env['payment.provider'].with_user(publico).sudo()._get_compatible_providers(
                self.env.company.id, self.cliente.id, pedido.amount_total, currency_id=pedido.currency_id.id,
                sale_order_id=pedido.id)
        self.assertNotIn(self.proveedor, ofrecidos)


# ---------------------------------------------------------------------------------------------------------------------
# N-3: la «señal de vida» es de quien tiene la orden: un atacante puede dársela a su basura.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestRv3SenalForjada(Base):

    def simular(self, forjar, latencia=5.0, por_vuelta=5, vueltas_antes=140, vueltas_maximas=60):
        """Igual que la simulación de la 2.ª vuelta (modelo a escala 1:10), con presupuesto de 40 s de la tarea. Si
        ``forjar``, el atacante martilla el retorno de TODA su basura cada vuelta (señal de vida falsa). El cliente
        legítimo paga y su retorno SÍ llega (señal verdadera). Devuelve las vueltas hasta confirmar."""
        ahora = datetime.utcnow().replace(microsecond=0)
        with freeze_time(ahora) as reloj, SimuladorTilopay() as tilopay:
            consultar = tilopay._consultar

            def lento(cuerpo):
                reloj.tick(timedelta(seconds=latencia))
                return consultar(cuerpo)
            tilopay._consultar = lento
            basura = self.env['payment.transaction']

            def tirar(cuantas):
                nonlocal basura
                for i in range(cuantas):
                    if i % 5 == 0:
                        pedido = self.pedido()
                    tx, _o = self.abrir(tilopay, pedido)
                    self.env.cr.execute('UPDATE payment_transaction SET create_date = %s WHERE id = %s',
                                        [fields.Datetime.now() - timedelta(minutes=3), tx.id])
                    tx.invalidate_recordset(['create_date'])
                    basura |= tx
                if forjar:
                    basura.dcasa_tilopay_senal = fields.Datetime.now()

            pedido_legitimo = self.pedido()
            legitima, orden = self.abrir(tilopay, pedido_legitimo)
            self.env.cr.execute('UPDATE payment_transaction SET create_date = %s WHERE id = %s',
                                [fields.Datetime.now() - timedelta(minutes=3), legitima.id])
            legitima.invalidate_recordset(['create_date'])
            for _vuelta in range(vueltas_antes):
                reloj.tick(timedelta(minutes=10))
                tirar(por_vuelta)
                self.cron()
            tilopay.aprobar(orden, pedido_legitimo.amount_total)
            legitima.dcasa_tilopay_senal = fields.Datetime.now()
            for vuelta in range(1, vueltas_maximas + 1):
                reloj.tick(timedelta(minutes=10))
                tirar(por_vuelta)
                self.cron()
                legitima.invalidate_recordset()
                if legitima.state == 'done':
                    return vuelta
        return None

    def test_control_sin_senal_falsa_el_cliente_que_volvio_se_atiende_enseguida(self):
        retraso = self.simular(forjar=False)
        logging.getLogger('rv3.sim').warning('RVSIM3 sin senal falsa: %s vueltas', retraso)
        self.assertIsNotNone(retraso)
        self.assertLessEqual(retraso, 1)

    def test_la_senal_falsa_de_la_basura_no_retrasa_al_cliente_que_si_volvio(self):
        """Pasa: la cola es por antigüedad de la consulta y ese cliente es de los más antiguos. ``dcasa_tilopay_senal``
        la escribe cualquier retorno o aviso con una orden VÁLIDA: quien abrió páginas de pago conoce sus propias
        órdenes y puede darle «señal de vida» a toda su basura, que pasa al frente de la cola y compite con la del
        cliente real. Se mide a escala 1:10 (23 h de ráfaga)."""
        retraso = self.simular(forjar=True)
        logging.getLogger('rv3.sim').warning('RVSIM3 con senal falsa: %s vueltas', retraso)
        self.assertIsNotNone(retraso)
        self.assertLessEqual(retraso, 3, f'con señales falsas el cliente que sí volvió esperó {retraso} vueltas')
