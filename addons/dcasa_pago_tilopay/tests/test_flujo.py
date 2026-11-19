"""De punta a punta con un Tilopay simulado: pedido → página de pago → confirmación (siempre preguntándole a Tilopay) →
pedido confirmado, cobro en el diario «Tilopay», factura cruzada y puntos de Socios. Y cada caso raro."""
import re
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import LLAVE, SECRETOS, ComunTilopay, SimuladorTilopay, entorno

CAMPOS_DOCUMENTADOS = {
    'redirect', 'key', 'amount', 'currency', 'orderNumber', 'capture', 'billToFirstName', 'billToLastName',
    'billToAddress', 'billToAddress2', 'billToCity', 'billToState', 'billToZipPostCode', 'billToCountry',
    'billToTelephone', 'billToEmail', 'subscription', 'platform', 'returnData', 'hashVersion', 'token_version'}


class BaseTilopay(ComunTilopay, TransactionCase):
    pass


@tagged('post_install', '-at_install')
class TestFlujoFeliz(BaseTilopay):

    def test_pedido_a_pagado_con_cobro_factura_y_puntos(self):
        pedido = self.pedido()
        total = pedido.amount_total
        self.assertEqual(total, 107.0, 'el ITBMS va incluido en el total que se cobra')
        tx = self.transaccion(pedido)
        with SimuladorTilopay() as tilopay:
            valores = tx._get_processing_values()
            orden = tx.dcasa_tilopay_orden
            # La página de Tilopay (formulario GET) y la orden guardada ANTES de llamar.
            self.assertIn('https://secure.tilopay.com/htmls/', valores['redirect_form_html'])
            self.assertIn(orden, valores['redirect_form_html'])
            self.assertEqual(tx.provider_reference, orden)
            self.assertEqual(tx.state, 'draft')
            cuerpo = tilopay.rutas(api.RUTA_PAGO)[0][1]
            self.assertEqual(cuerpo['amount'], '107.00')
            self.assertEqual(cuerpo['currency'], 'USD')
            self.assertEqual(cuerpo['key'], LLAVE)
            self.assertEqual(cuerpo['capture'], '1')
            self.assertEqual(cuerpo['redirect'], self.proveedor.get_base_url() + '/payment/tilopay/return')
            self.assertEqual(api.orden_de_return_data(cuerpo['returnData']), orden)
            self.assertLessEqual(set(cuerpo), CAMPOS_DOCUMENTADOS, 'solo lo que la documentación pide')
            self.assertEqual(cuerpo['billToEmail'], 'ana.prueba.pago@example.com')
            self.assertEqual(cuerpo['billToCountry'], 'PA')
            # Pago aprobado en Tilopay → Odoo pregunta y confirma.
            tilopay.aprobar(orden, total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'aprobado')
            self.assertEqual(self.llamadas_a_consulta(tilopay)[0][1],
                             {'key': LLAVE, 'orderNumber': orden}, 'se consulta con LA orden guardada')
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, '734312')
        self.assertEqual(tx.dcasa_tilopay_entorno_visto, 'prueba')
        # El mismo flujo que cualquier pago en línea de Odoo.
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertTrue(pedido.picking_ids, 'confirmar el pedido reserva el inventario')
        pago = tx.payment_id
        self.assertTrue(pago)
        self.assertEqual(pago.journal_id.code, 'TLP')
        self.assertEqual(pago.journal_id.name, 'Tilopay')
        self.assertEqual(pago.amount, total)
        self.assertEqual(pago.state, 'paid')
        self.assertTrue(pago.move_id.line_ids, 'el cobro deja asiento (el método del diario tiene su cuenta)')
        # Se factura y se publica: Odoo cruza solo el cobro, la factura queda pagada y Socios da sus puntos.
        factura = pedido._create_invoices()
        factura.action_post()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertTrue(pago.move_id.line_ids.filtered('reconciled'), 'el cobro quedó cruzado con la factura')
        self.assertTrue(factura.dcasa_compra_ids, 'la compra completa registra su compra en Socios')

    def test_al_confirmar_se_adelanta_el_cierre_de_odoo(self):
        """El cliente puede no estar mirando: se pide que la tarea que termina los pagos corra enseguida."""
        pedido = self.pedido()
        cron = self.env.ref('payment.cron_post_process_payment_tx')
        antes = self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)])
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.assertEqual(self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)]), antes)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('aviso')
        self.assertEqual(self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)]), antes + 1)

    def test_el_numero_de_orden_es_unico_aleatorio_y_valido(self):
        with SimuladorTilopay() as tilopay:
            ordenes = set()
            for _i in range(3):
                tx, orden = self.abrir(tilopay)
                self.assertTrue(api.orden_valida(orden), orden)
                self.assertTrue(re.match(r'^[A-Za-z0-9-]+-[0-9a-f]{8}$', orden), orden)
                self.assertTrue(orden.startswith(re.sub(r'[^A-Za-z0-9-]', '', tx.reference)[:24]))
                ordenes.add(orden)
            self.assertEqual(len(ordenes), 3)

    def test_referencias_con_barras_tambien_dan_una_orden_valida(self):
        pedido = self.pedido()
        tx = self.env['payment.transaction'].create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id, 'operation': 'online_redirect',
            'reference': 'INV/2026/00001-1', 'sale_order_ids': [Command.set(pedido.ids)]})
        with SimuladorTilopay():
            tx._get_processing_values()
        self.assertTrue(api.orden_valida(tx.dcasa_tilopay_orden), tx.dcasa_tilopay_orden)

    def test_dos_txs_con_la_misma_orden_no_existen(self):
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay)
            otra = self.transaccion(self.pedido())
            with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.cr.savepoint():
                otra.dcasa_tilopay_orden = orden
                otra.flush_recordset()


@tagged('post_install', '-at_install')
class TestNuncaSeConfiaEnElNavegador(BaseTilopay):

    def test_monto_distinto_no_paga(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total - 0.01)
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'monto')
        self.assertEqual(tx.state, 'error')
        self.assertIn('cobro distinto', tx.state_message)
        tx._post_process()
        self.assertEqual(pedido.state, 'draft')
        self.assertFalse(tx.payment_id)
        notas = pedido.message_ids.filtered(lambda m: 'NO se tomó como pago' in (m.body or ''))
        self.assertEqual(len(notas), 1, 'el equipo se entera, una sola vez')

    def test_un_cambio_de_modo_con_pagos_a_medias_no_mezcla_pruebas_con_real(self):
        """Creada en modo de prueba (is_live = False) no se paga con un pago real aunque ahora todo diga
        «produccion»."""
        pedido = self.pedido()
        with SimuladorTilopay(entorno='Production') as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.assertFalse(tx.is_live)
            self.proveedor.state = 'enabled'
            tilopay.aprobar(orden, pedido.amount_total)
            with entorno(TILOPAY_ENTORNO='produccion'):
                self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'entorno')
        self.assertEqual(tx.state, 'draft')
        # Y al revés: creada en real, un pago de «Test» no la paga aunque ahora todo diga «prueba».
        self.proveedor.state = 'enabled'
        pedido2 = self.pedido()
        with entorno(TILOPAY_ENTORNO='produccion'), SimuladorTilopay(entorno='Test') as tilopay:
            tx2, orden2 = self.abrir(tilopay, pedido2)
            self.assertTrue(tx2.is_live)
            self.proveedor.state = 'test'
            tilopay.aprobar(orden2, pedido2.amount_total)
            with entorno(TILOPAY_ENTORNO='prueba'):
                self.assertEqual(tx2._dcasa_tilopay_confirmar('aviso'), 'entorno')
        self.assertEqual(tx2.state, 'draft')

    def test_un_texto_de_tilopay_nunca_se_vuelve_html_en_la_nota_del_pedido(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total, moneda='<script>alert(1)</script>')
            tx._dcasa_tilopay_confirmar('aviso')
        notas = pedido.message_ids.filtered(lambda m: 'Tilopay dice haber cobrado' in (m.body or ''))
        self.assertTrue(notas)
        for nota in notas:
            self.assertNotIn('<script>', str(nota.body))

    def test_pagar_de_mas_tampoco(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total + 50)
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'monto')
        self.assertEqual(tx.state, 'error')

    def test_moneda_distinta_no_paga(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total, moneda='CRC')
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'moneda')
        self.assertEqual(tx.state, 'error')
        self.assertEqual(pedido.state, 'draft')

    def test_un_pago_de_prueba_no_paga_produccion(self):
        self.proveedor.state = 'enabled'
        pedido = self.pedido()
        with entorno(TILOPAY_ENTORNO='produccion'), SimuladorTilopay(entorno='Test') as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'entorno')
        self.assertEqual(tx.state, 'draft', 'queda como estaba: nunca pagado')
        self.assertEqual(tx.dcasa_tilopay_veredicto, 'entorno')
        self.assertEqual(tx.dcasa_tilopay_entorno_visto, 'prueba')
        self.assertEqual(pedido.state, 'draft')
        self.assertTrue(pedido.message_ids.filtered(lambda m: 'no se pudo tomar como pago' in (m.body or '')))

    def test_un_pago_real_no_paga_un_entorno_de_prueba(self):
        pedido = self.pedido()
        with SimuladorTilopay(entorno='Production') as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'entorno')
        self.assertEqual(tx.state, 'draft')

    def test_la_orden_de_otra_transaccion_no_paga_esta(self):
        pedido_a, pedido_b = self.pedido(), self.pedido()
        with SimuladorTilopay() as tilopay:
            tx_a, orden_a = self.abrir(tilopay, pedido_a)
            tx_b, orden_b = self.abrir(tilopay, pedido_b)
            tilopay.aprobar(orden_a, pedido_a.amount_total)
            self.assertEqual(tx_b._dcasa_tilopay_confirmar('retorno'), 'sin_registro')
            self.assertEqual(self.llamadas_a_consulta(tilopay)[-1][1]['orderNumber'], orden_b,
                             'cada transacción pregunta por SU orden')
            self.assertEqual(tx_a._dcasa_tilopay_confirmar('aviso'), 'aprobado')
        self.assertEqual((tx_a.state, tx_b.state), ('done', 'draft'))

    def test_aprobada_para_otro_monto_de_otro_pedido(self):
        grande, chico = self.pedido(cantidad=3), self.pedido()
        with SimuladorTilopay() as tilopay:
            tx_grande, orden_grande = self.abrir(tilopay, grande)
            tilopay.aprobar(orden_grande, chico.amount_total)       # pagó lo del pedido chico
            self.assertEqual(tx_grande._dcasa_tilopay_confirmar('aviso'), 'monto')
        self.assertEqual(grande.state, 'draft')

    def test_los_datos_que_no_salen_de_una_consulta_se_ignoran(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
        with self.assertLogs('odoo.addons.dcasa_pago_tilopay.models.payment_transaction', 'WARNING'):
            tx._process('tilopay', {'reference': tx.reference, 'veredicto': 'aprobado', 'monto': 107.0, 'moneda':
            'USD'})
        self.assertEqual(tx.state, 'draft')
        with self.assertLogs('odoo.addons.dcasa_pago_tilopay.models.payment_transaction', 'WARNING'):
            tx._process('tilopay', dict(veredicto='aprobado', reference=tx.reference))
        self.assertEqual(tx.state, 'draft', 'ni un diccionario igualito: tiene que ser el de una consulta')

    def test_una_transaccion_de_otro_proveedor_no_se_busca_por_la_orden(self):
        pedido = self.pedido()
        otro = self.env['payment.provider'].search([('code', '=', 'custom')], limit=1)
        tx = self.env['payment.transaction'].create({
            'provider_id': otro.id, 'payment_method_id': otro.payment_method_ids[:1].id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id,
            'sale_order_ids': [Command.set(pedido.ids)]})
        tx.dcasa_tilopay_orden = 'ORDEN-DE-OTRO-PROVEEDOR-1'
        self.assertFalse(self.env['payment.transaction']._dcasa_tilopay_buscar('ORDEN-DE-OTRO-PROVEEDOR-1'))
        with SimuladorTilopay() as tilopay:
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), None)
            self.assertEqual(tilopay.llamadas, [])

    def test_el_monto_del_navegador_no_manda(self):
        """El portal de Odoo toma el monto que manda el navegador: Tilopay exige que sea el total del pedido."""
        pedido = self.pedido()
        for monto in (1.0, pedido.amount_total - 0.01, pedido.amount_total + 1, 0.0):
            tx = self.transaccion(pedido, monto)
            with self.subTest(monto=monto), SimuladorTilopay() as tilopay:
                with self.assertRaises(ValidationError):
                    tx._get_processing_values()
                self.assertEqual(tilopay.llamadas, [], 'ni se llama a Tilopay')
                self.assertFalse(tx.dcasa_tilopay_orden)

    def test_un_pedido_con_pagos_previos_no_se_paga_completo_otra_vez(self):
        pedido = self.pedido()
        otro = self.env['payment.provider'].search([('code', '=', 'custom')], limit=1)
        previo = self.env['payment.transaction'].create({
            'provider_id': otro.id, 'payment_method_id': otro.payment_method_ids[:1].id, 'amount': 10.0,
            'currency_id': pedido.currency_id.id, 'partner_id': self.cliente.id,
            'sale_order_ids': [Command.set(pedido.ids)]})
        previo._set_done()
        tx = self.transaccion(pedido)
        with SimuladorTilopay() as tilopay, self.assertRaises(ValidationError):
            tx._get_processing_values()
        self.assertEqual(tilopay.llamadas, [])

    def test_solo_un_proveedor_ofrecible_abre_la_pagina(self):
        """Aunque el navegador mande el proveedor a mano: apagado o sin claves, no se abre ninguna página."""
        pedido = self.pedido()
        self.proveedor.state = 'disabled'
        tx = self.transaccion(pedido)
        with SimuladorTilopay() as tilopay, self.assertRaises(ValidationError):
            tx._get_processing_values()
        self.assertEqual(tilopay.llamadas, [])
        self.proveedor.state = 'test'
        with entorno(TILOPAY_API_KEY=None), SimuladorTilopay() as tilopay, self.assertRaises(ValidationError):
            self.transaccion(pedido)._get_processing_values()
        self.assertEqual(tilopay.llamadas, [])

    def test_hay_un_tope_de_paginas_abiertas_por_pedido(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            for _i in range(5):
                self.abrir(tilopay, pedido)
            with self.assertRaises(ValidationError):
                self.abrir(tilopay, pedido)
            self.assertEqual(len(tilopay.rutas(api.RUTA_PAGO)), 5)
            self.abrir(tilopay, self.pedido())            # otro pedido: sin problema


@tagged('post_install', '-at_install')
class TestOrdenYRepeticiones(BaseTilopay):

    def test_repetir_la_confirmacion_no_duplica_nada(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'aprobado')
            tx._post_process()
            for origen in ('retorno', 'aviso', 'cron', 'estado'):
                self.assertEqual(tx._dcasa_tilopay_confirmar(origen), 'ya_pagada')
            tx._post_process()
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1, 'una vez pagada, no se vuelve a preguntar')
        self.assertEqual(self.env['account.payment'].search_count([('payment_transaction_id', '=', tx.id)]), 1)
        self.assertEqual(pedido.transaction_ids.filtered(lambda t: t.state == 'done'), tx)

    def test_retorno_y_aviso_en_cualquier_orden(self):
        for primero, segundo in (('retorno', 'aviso'), ('aviso', 'retorno')):
            with self.subTest(primero=primero):
                pedido = self.pedido()
                with SimuladorTilopay() as tilopay:
                    tx, orden = self.abrir(tilopay, pedido)
                    # La primera llega antes de que Tilopay registre el pago…
                    self.assertEqual(tx._dcasa_tilopay_confirmar(primero), 'sin_registro')
                    # …la segunda, enseguida, no vuelve a preguntar (freno de 5 s)…
                    tilopay.aprobar(orden, pedido.amount_total)
                    self.assertEqual(tx._dcasa_tilopay_confirmar(segundo), 'espera')
                    self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1)
                    # …y pasados los segundos, confirma.
                    tx.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(seconds=30)
                    self.assertEqual(tx._dcasa_tilopay_confirmar(segundo), 'aprobado')
                self.assertEqual(tx.state, 'done')

    def test_el_freno_de_cinco_segundos_protege_a_tilopay_del_goteo(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            resultados = [tx._dcasa_tilopay_confirmar('aviso') for _i in range(20)]
        self.assertEqual(resultados[0], 'sin_registro')
        self.assertEqual(set(resultados[1:]), {'espera'})
        self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1)

    def test_una_transaccion_cancelada_o_vencida_se_paga_si_llega_el_pago_correcto(self):
        for estado_previo in ('cancel', 'error'):
            with self.subTest(estado=estado_previo):
                pedido = self.pedido()
                with SimuladorTilopay() as tilopay:
                    tx, orden = self.abrir(tilopay, pedido)
                    if estado_previo == 'cancel':
                        tx._set_canceled('vencida')
                    else:
                        tx._set_error('antes dio error')
                    tilopay.aprobar(orden, pedido.amount_total)
                    self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'aprobado')
                self.assertEqual(tx.state, 'done', 'hay dinero real: no se pierde')
                self.assertTrue(pedido.message_ids.filtered(lambda m: 'llegó después' in (m.body or '')))

    def test_rechazo_deja_error_y_un_reintento_en_la_misma_pagina_lo_paga(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.rechazar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'rechazado')
            self.assertEqual(tx.state, 'error')
            self.assertIn('otra tarjeta', tx.state_message)
            self.assertNotIn('Fondos', tx.state_message, 'al cliente no se le repite el texto del banco')
            tilopay.aprobar(orden, pedido.amount_total)
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'aprobado')
        self.assertEqual(tx.state, 'done')

    def test_una_transaccion_hecha_no_la_cambia_un_rechazo_posterior(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('aviso')
            tilopay.pagos[orden] = [tilopay.fila(orden, pedido.amount_total, code='4')]
            tx.dcasa_tilopay_consulta = False
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'ya_pagada')
        self.assertEqual(tx.state, 'done')

    def test_el_navegador_que_vuelve_sin_pagar_cancela_solo_si_tilopay_no_tiene_nada(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno', navegador_cancelo=True), 'sin_registro')
            self.assertEqual(tx.state, 'cancel')
            # Pero si Tilopay SÍ tiene el pago aprobado, lo que diga el navegador no importa:
            tx2, orden2 = self.abrir(tilopay, self.pedido())
            tilopay.aprobar(orden2, tx2.amount)
            self.assertEqual(tx2._dcasa_tilopay_confirmar('retorno', navegador_cancelo=True), 'aprobado')
            self.assertEqual(tx2.state, 'done')

    def test_tilopay_caido_o_lento_nunca_paga_ni_tumba(self):
        pedido = self.pedido()
        for falla in ('tiempo', 'red', 'http500', 'basura', 'vacio'):
            with self.subTest(falla=falla), SimuladorTilopay() as tilopay:
                tx, orden = self.abrir(tilopay, pedido)
                tilopay.falla = falla
                tilopay.aprobar(orden, pedido.amount_total)   # aunque «ya» estuviera pagado, sin respuesta no se sabe
                api.olvidar_tokens()
                with self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'WARNING') as registros:
                    self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'sin_respuesta')
                self.assertEqual(tx.state, 'draft')
                self.assertEqual(pedido.state, 'draft')
                for secreto in SECRETOS:
                    self.assertNotIn(secreto, '\n'.join(registros.output))

    def test_al_crear_la_pagina_con_tilopay_caido_el_cliente_ve_un_mensaje_claro(self):
        pedido = self.pedido()
        tx = self.transaccion(pedido)
        with SimuladorTilopay() as tilopay:
            tilopay.falla = 'tiempo'
            with self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'WARNING'), \
                    self.assertRaises(ValidationError) as ctx:
                tx._get_processing_values()
        mensaje = str(ctx.exception)
        self.assertIn('otra forma de pago', mensaje)
        for secreto in SECRETOS:
            self.assertNotIn(secreto, mensaje)
        self.assertEqual(pedido.state, 'draft', 'la venta sigue intacta')

    def test_si_tilopay_rechaza_crear_la_pagina_tampoco_se_filtra_nada(self):
        tx = self.transaccion(self.pedido())
        with SimuladorTilopay() as tilopay:
            tilopay.claves_buenas = False
            with self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'WARNING'), \
                    self.assertRaises(ValidationError) as ctx:
                tx._get_processing_values()
        for secreto in SECRETOS:
            self.assertNotIn(secreto, str(ctx.exception))

    def test_proveedor_apagado_o_sin_claves_no_responde_con_datos(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            self.proveedor.state = 'disabled'
            self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'apagado')
            self.proveedor.state = 'test'
            with entorno(TILOPAY_API_USER=None):
                self.assertEqual(tx._dcasa_tilopay_confirmar('aviso'), 'apagado')
            self.assertEqual(self.llamadas_a_consulta(tilopay), [])
        self.assertEqual(tx.state, 'draft')


@tagged('post_install', '-at_install')
class TestTareaProgramada(BaseTilopay):

    def envejecer(self, tx, **delta):
        antes = fields.Datetime.now() - timedelta(**delta)
        self.env.cr.execute('UPDATE payment_transaction SET create_date = %s WHERE id = %s', [antes, tx.id])
        tx.invalidate_recordset(['create_date'])

    def test_confirma_los_pagos_que_el_aviso_no_trajo(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.envejecer(tx, minutes=10)
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(), 1)
        self.assertEqual(tx.state, 'done')

    def test_no_le_gana_al_cliente_que_todavia_esta_pagando(self):
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay)
            self.assertEqual(self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(), 0)
        self.assertEqual(self.llamadas_a_consulta(tilopay), [])

    def test_sin_proveedor_encendido_o_sin_claves_no_llama_a_nadie(self):
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay)
            self.envejecer(tx, minutes=10)
            tilopay.llamadas.clear()
            self.proveedor.state = 'disabled'
            self.assertEqual(self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(), 0)
            self.proveedor.state = 'test'
            with entorno(TILOPAY_API_KEY=None):
                self.assertEqual(self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(), 0)
            self.assertEqual(tilopay.llamadas, [])

    def test_las_de_mas_de_24_horas_sin_pago_vencen_y_las_de_mas_de_3_dias_se_dejan(self):
        with SimuladorTilopay() as tilopay:
            tx, _orden = self.abrir(tilopay)
            self.envejecer(tx, hours=25)
            viejo, _orden2 = self.abrir(tilopay)
            self.envejecer(viejo, days=4)
            tilopay.llamadas.clear()
            self.assertEqual(self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar(), 1)
            self.assertEqual(len(self.llamadas_a_consulta(tilopay)), 1, 'la de 4 días ya no se pregunta')
        self.assertEqual(tx.state, 'cancel')
        self.assertIn('venció', tx.state_message)
        self.assertEqual(viejo.state, 'draft')

    def test_un_error_en_una_no_detiene_a_las_demas(self):
        pedido_a, pedido_b = self.pedido(), self.pedido()
        with SimuladorTilopay() as tilopay:
            tx_a, orden_a = self.abrir(tilopay, pedido_a)
            tx_b, orden_b = self.abrir(tilopay, pedido_b)
            for tx in (tx_a, tx_b):
                self.envejecer(tx, minutes=10)
            tilopay.aprobar(orden_b, pedido_b.amount_total)
            Modelo = type(tx_a)
            original = Modelo._dcasa_tilopay_confirmar

            def confirmar(registro, *args, **kwargs):
                if registro.id == tx_a.id:
                    raise ValueError('falla de prueba')
                return original(registro, *args, **kwargs)
            from unittest.mock import patch
            with patch.object(Modelo, '_dcasa_tilopay_confirmar', confirmar), \
                    self.assertLogs('odoo.addons.dcasa_pago_tilopay', 'ERROR'):
                self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()
        self.assertEqual((tx_a.state, tx_b.state), ('draft', 'done'))

    def test_la_tarea_esta_programada(self):
        cron = self.env.ref('dcasa_pago_tilopay.cron_reconciliar')
        self.assertTrue(cron.active)
        self.assertIn('_cron_dcasa_tilopay_reconciliar', cron.code)
        self.assertEqual((cron.interval_number, cron.interval_type), (10, 'minutes'))
