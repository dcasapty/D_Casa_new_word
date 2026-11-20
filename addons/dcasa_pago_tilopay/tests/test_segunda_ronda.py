"""La segunda ronda de la revisión independiente (N-1 a N-6, sobre 43e2569): que nada que llegue por la web pueda
agotar las conexiones de la base, que un estado raro no pase en silencio, y las decisiones sobre lo que no se paga
solo. Siempre con el Tilopay simulado."""
import json
import time
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_pago_tilopay.controllers import main as controlador
from odoo.addons.dcasa_pago_tilopay.models import payment_transaction as modulo_tx
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.addons.dcasa_pago_tilopay.models.tilopay_ritmo import LimiteDeRitmo
from odoo.exceptions import ValidationError
from odoo.tests import BaseCase, HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException

from .common import ComunTilopay, SimuladorTilopay, entorno

RETORNO = '/payment/tilopay/return'
AVISO = '/payment/tilopay/webhook'
RESUMEN_TOTAL = 'Tilopay: cobro que no cuadra con el pedido'


@tagged('post_install', '-at_install')
class TestElTopeDeLlamadasALaVez(BaseCase):
    """N-1 (a): cada llamada a Tilopay retiene una conexión de la base hasta 15 s; hay un tope global y no se espera."""

    def test_el_tope_es_global_no_espera_y_se_suelta_siempre(self):
        antes = api.llamadas_en_vuelo()
        with ExitStack() as pila:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                pila.enter_context(api.cupo())
            self.assertFalse(api.hay_cupo())
            inicio = time.monotonic()
            with self.assertRaises(api.ErrorTilopay) as error, api.cupo():
                self.fail('no debería entrar')
            self.assertEqual(error.exception.tipo, 'ocupado')
            self.assertLess(time.monotonic() - inicio, 0.5, 'no espera: responde «ocupado» al instante')
        self.assertEqual(api.llamadas_en_vuelo(), antes, 'al salir se soltó todo')
        try:
            with api.cupo():
                raise ValueError('falla de prueba')
        except ValueError:
            pass
        self.assertEqual(api.llamadas_en_vuelo(), antes, 'también se suelta si algo falla adentro')

    def test_la_tarea_programada_tiene_una_reserva(self):
        with ExitStack() as pila:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                pila.enter_context(api.cupo())
            self.assertFalse(api.hay_cupo())
            self.assertTrue(api.hay_cupo(prioritario=True))
            for _i in range(api.RESERVA_PARA_LA_TAREA):
                pila.enter_context(api.cupo(prioritario=True))
            self.assertFalse(api.hay_cupo(prioritario=True))
            with self.assertRaises(api.ErrorTilopay):
                with api.cupo(prioritario=True):
                    pass

    def test_con_el_tope_lleno_el_cliente_ni_llama_a_tilopay(self):
        with entorno(), SimuladorTilopay() as tilopay, ExitStack() as pila:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                pila.enter_context(api.cupo())
            with self.assertRaises(api.ErrorTilopay) as error:
                api.Cliente(api.credenciales()).consultar('S00001-1-abcdef12')
            self.assertEqual(error.exception.tipo, 'ocupado')
            self.assertEqual(tilopay.llamadas, [], 'ni siquiera el inicio de sesión')

    def test_varios_hilos_a_la_vez_nunca_pasan_del_tope(self):
        import threading
        dentro, maximo, candado = [0], [0], threading.Lock()
        lleno = threading.Event()
        rechazados = []

        def intentar():
            try:
                with api.cupo():
                    with candado:
                        dentro[0] += 1
                        maximo[0] = max(maximo[0], dentro[0])
                    lleno.wait(1)
                    with candado:
                        dentro[0] -= 1
            except api.ErrorTilopay:
                rechazados.append(1)
        hilos = [threading.Thread(target=intentar) for _i in range(40)]
        for hilo in hilos:
            hilo.start()
        time.sleep(0.3)
        lleno.set()
        for hilo in hilos:
            hilo.join(5)
        self.assertEqual(maximo[0], api.TOPE_DE_LLAMADAS_A_LA_VEZ)
        self.assertEqual(len(rechazados), 40 - api.TOPE_DE_LLAMADAS_A_LA_VEZ)
        self.assertEqual(api.llamadas_en_vuelo(), 0)


@tagged('post_install', '-at_install')
class TestElFrenoPorConexion(BaseCase):
    """N-1 (d): el freno de ritmo en memoria, sin Odoo."""

    def test_cuenta_por_llave_y_por_ventana(self):
        limite = LimiteDeRitmo(maximo=3, ventana=60)
        self.assertEqual([limite.permitir('a', ahora=t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(limite.permitir('b', ahora=3), 'otra conexión tiene su propio turno')
        self.assertFalse(limite.permitir('a', ahora=59))
        self.assertTrue(limite.permitir('a', ahora=61), 'pasada la ventana vuelve a caber')

    def test_la_memoria_tiene_tope(self):
        limite = LimiteDeRitmo(maximo=1, ventana=60, max_llaves=100)
        for i in range(1000):
            limite.permitir(f'ip-{i}', ahora=i * 0.01)
        self.assertLessEqual(len(limite._intentos), 100)
        limite = LimiteDeRitmo(maximo=1, ventana=60, max_llaves=100)
        for i in range(500):
            limite.permitir(f'ip-{i}', ahora=1000 + i)          # cada una pasa de la ventana de la anterior
        self.assertLessEqual(len(limite._intentos), 100)


class BaseRonda(ComunTilopay, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = new_test_user(
            cls.env, login='til_gerencia_n', groups='base.group_user,dcasa_base.group_gerencia')

    def cron(self):
        return self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()

    def actividades(self, pedido, resumen=None):
        dominio = [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id), ('summary', 'like', 'Tilopay')]
        if resumen:
            dominio.append(('summary', '=', resumen))
        return self.env['mail.activity'].sudo().search(dominio)

    def notas(self, pedido, *palabras):
        nota = self.env.ref('mail.mt_note')
        return pedido.message_ids.filtered(
            lambda m: m.subtype_id == nota and all(p.lower() in (m.body or '').lower() for p in palabras))


@tagged('post_install', '-at_install')
class TestLaWebNoAgotaLasConexiones(BaseRonda):
    """N-1 (a) y (b): con el tope lleno la consulta se salta; las rutas web solo miran lo reciente."""

    def test_con_el_tope_lleno_la_consulta_responde_saturada_sin_llamar_ni_gastar_el_turno(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            llamadas = len(tilopay.llamadas)
            with ExitStack() as pila:
                for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                    pila.enter_context(api.cupo())
                self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'saturada')
                self.assertEqual(len(tilopay.llamadas), llamadas, 'no se llamó a Tilopay')
                self.assertFalse(tx.dcasa_tilopay_consulta, 'no se preguntó: no cuenta como pregunta')
                self.assertEqual(tx.state, 'draft')
                # La tarea programada, con su reserva, sí puede preguntar aunque la web haya llenado el tope.
                self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.APROBADO)
        self.assertEqual(tx.state, 'done')

    def test_si_el_tope_se_llena_justo_antes_de_llamar_tampoco_se_pierde_nada(self):
        """``hay_cupo`` dijo que sí y otro hilo se llevó el lugar: la llamada responde «ocupado» y la transacción queda
        como estaba."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, _orden = self.abrir(tilopay, pedido)
            tilopay.llamadas.clear()
            with patch.object(api, 'hay_cupo', return_value=True), ExitStack() as pila:
                for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                    pila.enter_context(api.cupo())
                self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'saturada')
            self.assertEqual(tilopay.llamadas, [])
        self.assertFalse(tx.dcasa_tilopay_consulta)

    def test_abrir_la_pagina_con_el_tope_lleno_le_dice_al_cliente_que_hay_mucho_movimiento(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay, ExitStack() as pila:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                pila.enter_context(api.cupo())
            with self.assertRaises(ValidationError) as error:
                self.abrir(tilopay, pedido)
            self.assertIn('Hay muchos pagos en curso', str(error.exception))
            self.assertEqual(tilopay.llamadas, [])

    def test_las_rutas_web_no_consultan_lo_viejo_pero_dejan_la_senal_y_la_tarea_pregunta_primero(self):
        pedido, otro = self.pedido(), self.pedido()
        with SimuladorTilopay() as tilopay:
            viejo, orden = self.abrir(tilopay, pedido)
            comun, _orden2 = self.abrir(tilopay, otro)
            self.envejecer(viejo, hours=5)
            self.envejecer(comun, hours=5)
            tilopay.aprobar(orden, pedido.amount_total)
            tilopay.llamadas.clear()
            for origen in modulo_tx.ORIGENES_WEB:
                viejo.dcasa_tilopay_consulta = False
                self.assertEqual(viejo._dcasa_tilopay_confirmar(origen), 'vieja')
            self.assertEqual(tilopay.llamadas, [], 'las rutas web no gastaron ni una llamada en lo viejo')
            self.assertTrue(viejo.dcasa_tilopay_senal)
            self.assertEqual(viejo.state, 'draft')
            # La tarea la atiende primero (señal de vida), antes que la otra vieja que lleva más rato esperando.
            primeras = self.env['payment.transaction']._dcasa_tilopay_pendientes(
                self.proveedor, fields.Datetime.now(), [], 5)
            self.assertEqual(primeras[0], viejo)
            self.assertEqual(self.cron(), 2)
        self.assertEqual(viejo.state, 'done')

    def test_una_transaccion_reciente_si_se_consulta_desde_la_web(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, hours=2)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('estado'), api.APROBADO)

    def test_la_senal_no_se_reescribe_cada_vez(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, _orden = self.abrir(tilopay, pedido)
            ahora = fields.Datetime.now()
            tx._dcasa_tilopay_marcar_senal(ahora - timedelta(seconds=30))
            primera = tx.dcasa_tilopay_senal
            tx._dcasa_tilopay_marcar_senal(ahora)
            self.assertEqual(tx.dcasa_tilopay_senal, primera, 'a lo más una vez por minuto')
            tx._dcasa_tilopay_marcar_senal(ahora + timedelta(seconds=40))
            self.assertGreater(tx.dcasa_tilopay_senal, primera)

    def test_lo_que_tilopay_nunca_vio_deja_de_preguntarse_al_dia_pero_la_senal_lo_revive(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tx._dcasa_tilopay_confirmar('retorno', navegador_cancelo=True)
            self.assertEqual((tx.state, tx.dcasa_tilopay_veredicto), ('cancel', api.SIN_REGISTRO))
            tx.dcasa_tilopay_senal = False
            self.envejecer(tx, hours=30)
            tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(hours=10)
            llamadas = len(tilopay.llamadas)
            self.assertEqual(self.cron(), 0, 'más de un día sin que Tilopay vea nada: ya no se pregunta')
            self.assertEqual(len(tilopay.llamadas), llamadas)
            # …pero si después llega un retorno o un aviso de esa orden, sí.
            tilopay.aprobar(orden, pedido.amount_total)
            tx.dcasa_tilopay_senal = fields.Datetime.now()
            self.assertEqual(self.cron(), 1)
        self.assertEqual(tx.state, 'done')


@tagged('post_install', '-at_install')
class TestLasRutasPorHttp(ComunTilopay, HttpCase):
    """N-1 (d) y N-4 por HTTP de verdad."""

    def setUp(self):
        super().setUp()
        controlador.RITMO.olvidar()
        self.addCleanup(controlador.RITMO.olvidar)

    def abrir_desde_el_portal(self, pedido):
        return self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
            'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
            'payment_method_id': self.metodo.id, 'token_id': None, 'amount': pedido.amount_total, 'flow': 'redirect',
            'tokenization_requested': False, 'landing_route': pedido.get_portal_url(), 'is_validation': False})

    def test_pasado_el_ritmo_de_la_conexion_el_retorno_y_el_aviso_no_procesan_pero_responden_igual(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay, patch.object(controlador.RITMO, 'maximo', 3):
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            llamadas = len(self.llamadas_a_consulta(tilopay))
            respuestas = []
            for _i in range(3):                  # cabe: pero cada orden desconocida no llama a Tilopay
                respuestas.append(self.url_open(RETORNO, params={'order': 'S99999-1-deadbeef'}, allow_redirects=False))
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), llamadas)
            # Esta ya pasó del ritmo: aunque la orden sea real y esté pagada, no se procesa (y el cliente igual vuelve).
            frenada = self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
            respuestas.append(frenada)
            aviso = self.url_open(AVISO, data=json.dumps({'orderNumber': orden}), method='POST',
                                  headers={'Content-Type': 'application/json'})
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), llamadas, 'frenada: ni una consulta a Tilopay')
        self.assertTrue(all(r.status_code in (301, 302, 303, 307, 308) for r in respuestas))
        self.assertEqual(len({r.headers['Location'] for r in respuestas}), 1, 'la respuesta no delata el freno')
        self.assertEqual((aviso.status_code, aviso.json()), (200, {'estado': 'ok'}))
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'draft')

    def test_dentro_del_ritmo_todo_sigue_igual(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, 'done')

    def test_una_conexion_no_puede_llenar_las_paginas_de_pago_ni_el_tope_global(self):
        """N-4: UNA conexión se topa con su propio límite antes de gastar el tope global de todos."""
        with SimuladorTilopay() as tilopay, patch.object(modulo_tx, 'TOPE_PAGINAS_POR_CONEXION_HORA', 3), \
                patch.object(modulo_tx, 'TOPE_PAGINAS_POR_HORA', 10):
            for _i in range(3):
                self.abrir_desde_el_portal(self.pedido())
            with self.assertRaises(JsonRpcException):
                self.abrir_desde_el_portal(self.pedido())
            self.assertEqual(len(tilopay.rutas(api.RUTA_PAGO)), 3, 'la cuarta ni llegó a Tilopay')
            huellas = self.env['payment.transaction'].search([('dcasa_tilopay_huella', '!=', False)]).mapped(
                'dcasa_tilopay_huella')
            self.assertEqual(len(set(huellas)), 1)
            self.assertNotIn('127.0.0.1', huellas[0], 'se guarda una huella, no la dirección')
            self.assertEqual(len(huellas[0]), 24)

    def test_las_paginas_ya_pagadas_no_cuentan_para_el_tope_ni_para_la_conexion(self):
        with SimuladorTilopay() as tilopay, patch.object(modulo_tx, 'TOPE_PAGINAS_POR_CONEXION_HORA', 2), \
                patch.object(modulo_tx, 'TOPE_PAGINAS_POR_HORA', 2):
            for _i in range(2):
                pedido = self.pedido()
                self.abrir_desde_el_portal(pedido)
                orden = tilopay.orden_del_ultimo_pago()
                tilopay.aprobar(orden, pedido.amount_total)
                tx = self.env['payment.transaction'].search([('dcasa_tilopay_orden', '=', orden)])
                self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.APROBADO)
            self.assertTrue(self.abrir_desde_el_portal(self.pedido()), 'las dos primeras se pagaron: hay lugar')


@tagged('post_install', '-at_install')
class TestUnEstadoQueNoSeEntiendeNoPasaEnSilencio(BaseRonda):
    """N-2."""

    def con_estado_raro(self, tilopay, horas):
        pedido = self.pedido()
        tx, orden = self.abrir(tilopay, pedido)
        self.envejecer(tx, hours=horas)
        tilopay.pagos[orden] = [tilopay.fila(orden, pedido.amount_total, code='A7', response='Autorizada')]
        return pedido, tx

    def test_pasada_una_hora_se_avisa_una_sola_vez(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx = self.con_estado_raro(tilopay, horas=2)
            for _i in range(3):
                tx.dcasa_tilopay_consulta = False
                self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.PENDIENTE)
        self.assertEqual(tx.state, 'draft', 'sigue esperando: no es un rechazo')
        actividades = self.actividades(pedido)
        self.assertIn(self.gerencia, actividades.user_id)
        self.assertEqual(len(actividades.filtered(lambda a: a.user_id == self.gerencia)), 1)
        self.assertEqual(len(self.notas(pedido, 'no entiende')), 1)

    def test_con_menos_de_una_hora_todavia_no_es_para_asustar(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx = self.con_estado_raro(tilopay, horas=0)
            self.envejecer(tx, minutes=10)
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.PENDIENTE)
        self.assertFalse(self.actividades(pedido))

    def test_al_vencer_siempre_se_avisa(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx = self.con_estado_raro(tilopay, horas=26)
            self.assertEqual(self.cron(), 1)
        self.assertEqual(tx.state, 'cancel')
        self.assertTrue(self.actividades(pedido))
        self.assertTrue(self.notas(pedido, 'no entiende'))

    def test_un_rechazo_claro_no_levanta_ese_aviso(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, hours=26)
            tilopay.rechazar(orden, pedido.amount_total)
            self.assertEqual(self.cron(), 1)
        self.assertEqual(tx.state, 'error', 'un rechazo del banco es un rechazo: nada raro que avisar')
        self.assertFalse(self.actividades(pedido))


@tagged('post_install', '-at_install')
class TestPublicadoEnModoDePruebaEnProduccion(BaseRonda):
    """N-5."""

    def abrir_como(self, usuario, pedido):
        tx = self.transaccion(pedido)
        return tx.with_user(usuario).sudo()._get_processing_values()

    def test_en_el_servidor_de_produccion_el_modo_de_prueba_es_del_equipo_aunque_este_publicado(self):
        self.proveedor.write({'state': 'test', 'is_published': True})
        publico = self.env.ref('base.public_user')
        with entorno(DCASA_ENTORNO='produccion', TILOPAY_ENTORNO='prueba'), SimuladorTilopay() as tilopay:
            with self.assertRaises(ValidationError):
                self.abrir_como(publico, self.pedido())
            self.assertEqual(tilopay.rutas(api.RUTA_PAGO), [])
            self.assertTrue(self.abrir_como(self.gerencia, self.pedido())['redirect_form_html'],
                            'el equipo sí puede probarlo')

    def test_en_staging_publicado_si_lo_ve_un_visitante(self):
        """Ahí es el punto de probar: el staging no cobra de verdad."""
        self.proveedor.write({'state': 'test', 'is_published': True})
        with entorno(DCASA_ENTORNO='staging'), SimuladorTilopay():
            self.assertTrue(self.abrir_como(self.env.ref('base.public_user'), self.pedido())['redirect_form_html'])

    def test_en_produccion_habilitado_y_publicado_cobra_normal(self):
        self.proveedor.write({'state': 'enabled', 'is_published': True})
        with entorno(DCASA_ENTORNO='produccion', TILOPAY_ENTORNO='produccion'), SimuladorTilopay():
            self.assertTrue(self.abrir_como(self.env.ref('base.public_user'), self.pedido())['redirect_form_html'])


@tagged('post_install', '-at_install')
class TestUnCobroQueNoCuadraNoSePagaSolo(BaseRonda):
    """N-6."""

    def total_distinto(self, tilopay):
        pedido = self.pedido()
        tx, orden = self.abrir(tilopay, pedido)
        cobrado = pedido.amount_total
        pedido.order_line.product_uom_qty = 5
        tilopay.aprobar(orden, cobrado)
        self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), api.TOTAL_PEDIDO)
        return pedido, tx, orden, cobrado

    def test_queda_marcada_para_una_persona_y_la_actividad_dice_como_resolverla(self):
        with SimuladorTilopay() as tilopay:
            pedido, tx, _orden, _cobrado = self.total_distinto(tilopay)
        self.assertTrue(tx.dcasa_tilopay_revision)
        actividad = self.actividades(pedido, RESUMEN_TOTAL)[:1]
        self.assertIn('no se va a pagar solo', actividad.note)
        self.assertIn('se devuelve el cobro desde el panel de Tilopay', actividad.note)
        self.assertIn('registras a mano', actividad.note)

    def test_aunque_una_consulta_intermedia_diga_otra_cosa_no_se_paga_sola(self):
        """El veredicto de la transacción cambia con cada consulta (un reembolso lo vuelve «ambiguo»); la marca de
        revisión no: el pago aprobado que llegue después tampoco la paga."""
        with SimuladorTilopay() as tilopay:
            pedido, tx, orden, cobrado = self.total_distinto(tilopay)
            tilopay.aprobar(orden, cobrado, tipo='Refund')
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.AMBIGUO)
            pedido.order_line.product_uom_qty = 1
            tilopay.pagos[orden] = [tilopay.fila(orden, cobrado)]      # y el reembolso ya no aparece
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(tx._dcasa_tilopay_confirmar('cron'), api.TOTAL_PEDIDO)
        self.assertEqual(tx.state, 'error')

    def test_la_tarea_no_la_vuelve_a_preguntar(self):
        with SimuladorTilopay() as tilopay:
            _pedido, tx, _orden, _cobrado = self.total_distinto(tilopay)
            self.envejecer(tx, hours=5)
            tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(hours=5)
            llamadas = len(tilopay.llamadas)
            self.assertEqual(self.cron(), 0)
            self.assertEqual(len(tilopay.llamadas), llamadas)

    def test_una_transaccion_normal_no_lleva_la_marca(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        self.assertFalse(tx.dcasa_tilopay_revision)
