"""Pruebas de la revisión independiente de ``dcasa_pago_tilopay`` (hallazgos RV-1 a RV-10, 2026-11-19).

Las escribió quien revisó el módulo para romperlo; aquí están tal cual (con los nombres sin «hoy falla», porque ya
pasan) y cada una dice qué hallazgo demuestra. Las del final son intentos de romperlo que no prosperaron: quedan como
cobertura. La única que cambió de fondo es la de «Probar conexión» con una llave equivocada (RV-10): ver su docstring.
"""
import json as json_lib
import logging
from datetime import timedelta

from odoo import fields
from odoo.addons.dcasa_pago_tilopay.models import tilopay_api as api
from odoo.addons.dcasa_pago_tilopay.tests.common import (
    SECRETOS,
    ComunTilopay,
    SimuladorTilopay,
    entorno,
)
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import JsonRpcException

RETORNO = '/payment/tilopay/return'
AVISO = '/payment/tilopay/webhook'


class BaseRevision(ComunTilopay, TransactionCase):

    def envejecer(self, tx, **delta):
        antes = fields.Datetime.now() - timedelta(**delta)
        self.env.cr.execute('UPDATE payment_transaction SET create_date = %s WHERE id = %s', [antes, tx.id])
        tx.invalidate_recordset(['create_date'])


# ---------------------------------------------------------------------------------------------------------------------
# RV-1 (BLOQUEANTE) — el proveedor en «Modo de prueba» y SIN publicar lo puede abrir cualquier visitante a mano.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv1ProveedorSinPublicar(ComunTilopay, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Como lo deja docs/TILOPAY.md §7 paso 2 en PRODUCCIÓN: «Modo de prueba», TILOPAY_ENTORNO=prueba y SIN
        # «Publicado» («así los clientes no ven una opción de pruebas»).
        cls.proveedor.write({'state': 'test', 'is_published': False})

    def abrir_como_visitante(self, pedido):
        return self.make_jsonrpc_request(f'/my/orders/{pedido.id}/transaction', {
            'access_token': pedido._portal_ensure_token(), 'provider_id': self.proveedor.id,
            'payment_method_id': self.metodo.id, 'token_id': None, 'amount': pedido.amount_total,
            'flow': 'redirect', 'tokenization_requested': False, 'landing_route': pedido.get_portal_url(),
            'is_validation': False})

    def test_un_visitante_no_puede_abrir_un_proveedor_que_no_se_le_ofrece(self):
        """Hallazgo del revisor (ya corregido).

        Un visitante SIN sesión manda a mano ``provider_id``/``payment_method_id`` (enteros chicos,
        adivinables) a ``/my/orders/<id>/transaction`` y Tilopay le abre la página de pago aunque el proveedor esté en
        «Modo de prueba» y sin publicar. ``_dcasa_tilopay_ofrecible`` solo mira estado, claves y entorno; nunca
        ``is_published`` ni si quien pide es del equipo (lo que sí hace ``_get_compatible_providers`` al MOSTRARLO)."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            with self.assertRaises(JsonRpcException, msg='el visitante no debería poder abrir Tilopay en modo de '
                                                         'prueba sin publicar'):
                self.abrir_como_visitante(pedido)
            self.assertEqual(tilopay.rutas(api.RUTA_PAGO), [], 'ni se le pidió una página a Tilopay')

    def test_consecuencia_pedido_real_confirmado_con_una_tarjeta_de_prueba_publica(self):
        """Hallazgo del revisor (ya corregido).

        Consecuencia de RV-1: en producción con TILOPAY_ENTORNO=prueba, un visitante abre la página,
        paga con la tarjeta de prueba (pública en la documentación de Tilopay: no cuesta nada) y el pedido REAL queda
        confirmado, con el inventario reservado y un cobro registrado en el diario «Tilopay»."""
        pedido = self.pedido()
        with SimuladorTilopay(entorno='Test') as tilopay:
            try:
                self.abrir_como_visitante(pedido)
            except JsonRpcException:
                return          # bien: no se pudo abrir (el arreglo de RV-1)
            orden = tilopay.orden_del_ultimo_pago()
            tilopay.aprobar(orden, pedido.amount_total)          # tarjeta 4111111111111111 en modo prueba
            self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
        tx = self.env['payment.transaction'].search([('dcasa_tilopay_orden', '=', orden)])
        tx.invalidate_recordset()
        tx._post_process()
        pedido.invalidate_recordset()
        self.assertNotEqual(pedido.state, 'sale', 'un pago de PRUEBA confirmó un pedido real sin que nadie del equipo '
                                                  'hubiera publicado Tilopay')


# ---------------------------------------------------------------------------------------------------------------------
# RV-2 (BLOQUEANTE) — el total del pedido cambia DESPUÉS de abrir la página de pago.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv2TotalCambiaDespues(BaseRevision):

    def test_pagar_menos_y_que_el_pedido_se_confirme_por_el_total_nuevo(self):
        """Hallazgo del revisor (ya corregido).

        La transacción de Tilopay queda en «draft» mientras el cliente está en la página de Tilopay, y
        con la transacción en «draft» el carrito de la web SIGUE siendo editable (``website.sale_get_order`` solo lo
        reinicia con tx pending/authorized/done). Otra pestaña sube la cantidad: el pedido pasa de 107 a 535. El cliente
        paga los 107 de la página. ``evaluar_consulta`` compara con ``tx.amount`` (107, correcto), pero NADIE
        compara con el total ACTUAL del pedido, y como la empresa no exige pago en línea (``require_payment`` = False,
        ``portal_confirmation_pay`` no se enciende en ningún módulo de D'CASA) Odoo confirma el pedido con CUALQUIER
        transacción hecha: ``_get_prepayment_required_amount()`` es 0."""
        pedido = self.pedido()
        total_al_abrir = pedido.amount_total
        self.assertFalse(pedido.require_payment, 'premisa: en esta base el pago en línea no es obligatorio')
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            # la otra pestaña del cliente (o la vendedora en el panel) cambia el pedido
            pedido.order_line.product_uom_qty = 5
            self.assertGreater(pedido.amount_total, total_al_abrir)
            tilopay.aprobar(orden, total_al_abrir)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        pedido.invalidate_recordset()
        self.assertFalse(
            pedido.state == 'sale' and pedido.currency_id.compare_amounts(pedido.amount_paid, pedido.amount_total) < 0,
            f'pedido confirmado: total {pedido.amount_total} pero cobrado {pedido.amount_paid}')

    def test_si_el_total_baja_y_se_cobra_de_mas_el_equipo_se_entera(self):
        """Hallazgo del revisor (ya corregido, menor).

        Mismo hueco al revés: el cliente quita muebles en otra pestaña y paga el total viejo. El
        pedido queda confirmado y cobrado de MÁS; nada avisa que hay que devolver la diferencia
        en el panel de Tilopay."""
        pedido = self.pedido(cantidad=3)
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            cobrado = pedido.amount_total
            pedido.order_line.product_uom_qty = 1
            self.assertLess(pedido.amount_total, cobrado)
            tilopay.aprobar(orden, cobrado)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        nota = self.env.ref('mail.mt_note')
        notas = pedido.message_ids.filtered(lambda m: m.subtype_id == nota and 'Tilopay' in (m.body or ''))
        self.assertTrue(
            notas, f'cobrado {cobrado} de un pedido que ahora vale {pedido.amount_total}: sin aviso al equipo')

    def test_el_total_igual_si_confirma_normal(self):
        """Control (pasa): sin cambios el pedido se confirma como siempre."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')


# ---------------------------------------------------------------------------------------------------------------------
# RV-3 (IMPORTANTE) — la tarea programada se puede dejar sin servicio con intentos basura.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv3TareaProgramadaSeSatura(BaseRevision):

    def basura(self, tilopay, pedidos=10):
        """``pedidos`` carritos con 5 páginas de pago abiertas cada uno (el tope es por pedido, no hay tope global)."""
        for _i in range(pedidos):
            pedido = self.pedido()
            for _j in range(5):
                tx, _orden = self.abrir(tilopay, pedido)
                self.envejecer(tx, minutes=5)

    def escenario(self, pedidos_basura_por_vuelta):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            legitima, orden = self.abrir(tilopay, pedido)
            self.envejecer(legitima, minutes=11)
            self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()      # 1.ª vuelta: aún no ha pagado
            self.assertTrue(legitima.dcasa_tilopay_consulta)
            tilopay.aprobar(orden, pedido.amount_total)                           # paga y cierra la pestaña
            legitima.dcasa_tilopay_consulta = fields.Datetime.now() - timedelta(minutes=9)
            for _vuelta in range(4):                                              # 40 minutos de ráfaga
                self.basura(tilopay, pedidos=pedidos_basura_por_vuelta)            # 5 intentos nuevos por pedido
                self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()
        return legitima

    def test_control_sin_basura_la_tarea_confirma_el_pago_en_la_siguiente_vuelta(self):
        self.assertEqual(self.escenario(0).state, 'done')

    def test_el_pago_de_un_cliente_real_no_espera_horas_porque_alguien_abrio_paginas_basura(self):
        """Hallazgo del revisor (ya corregido).

        El cron toma 50 por vuelta ordenadas por ``dcasa_tilopay_consulta asc nulls first``: las
        transacciones NUEVAS (nunca consultadas) pasan por delante de las que ya se consultaron una vez. Un cliente que
        pagó y cerró la pestaña (el aviso de compras no se reintenta y todavía no está registrado) queda detrás de
        cualquier ráfaga sostenida de ≥ 50 intentos nuevos cada 10 minutos (5 por minuto, muy por debajo del tope del
        borde: 120/min por IP en /shop/payment)."""
        legitima = self.escenario(10)                                               # 50 intentos nuevos por vuelta
        self.assertEqual(legitima.state, 'done', 'el pago real sigue sin confirmarse tras 4 vueltas de la tarea')


# ---------------------------------------------------------------------------------------------------------------------
# RV-4 (IMPORTANTE) — pago aprobado de un pedido cancelado: dinero real, nadie del equipo se entera.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv4PedidoCanceladoPagado(BaseRevision):

    def test_pago_de_un_pedido_cancelado_deja_una_nota_para_el_equipo(self):
        """Hallazgo del revisor (ya corregido).

        El pedido se canceló (la vendedora o el cron de apartados) mientras el cliente pagaba. Tilopay
        aprueba. La transacción queda «done» y Odoo crea el cobro, pero el pedido sigue cancelado y NO hay ninguna nota
        interna: ``_dcasa_tilopay_anotar`` solo se llama si la TRANSACCIÓN estaba cancelada/en error, o si otro pago
        ya cubría el pedido. El equipo no se entera de que hay un cobro huérfano."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            pedido._action_cancel()
            self.assertEqual(pedido.state, 'cancel')
            tilopay.aprobar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'aprobado')
        tx._post_process()
        self.assertEqual(pedido.state, 'cancel', 'premisa: sigue cancelado')
        nota = self.env.ref('mail.mt_note')
        notas = pedido.message_ids.filtered(lambda m: m.subtype_id == nota and 'Tilopay' in (m.body or ''))
        self.assertTrue(notas, 'ninguna nota interna avisa que Tilopay cobró un pedido que ya no está vivo')


@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv4bPaginaParaPedidoCancelado(BaseRevision):

    def test_no_se_abre_una_pagina_de_pago_para_un_pedido_cancelado(self):
        """Hallazgo del revisor (ya corregido, menor).

        ``/my/orders/<id>/transaction`` (portal) no revisa el estado del pedido (la ruta de la
        tienda sí rechaza «cancelado»), y ``_dcasa_tilopay_exigir_listo`` tampoco: se puede abrir la página y cobrar un
        pedido que el equipo o la tarea de apartados ya anuló (inventario liberado)."""
        pedido = self.pedido()
        pedido._action_cancel()
        self.assertEqual(pedido.state, 'cancel')
        with SimuladorTilopay() as tilopay:
            from odoo.exceptions import ValidationError
            with self.assertRaises(ValidationError):
                self.abrir(tilopay, pedido)
            self.assertEqual(tilopay.rutas(api.RUTA_PAGO), [], 'no se le pidió una página de pago a Tilopay')


# ---------------------------------------------------------------------------------------------------------------------
# RV-5 (MENOR) — una transacción cancelada por el navegador o vencida deja de revisarse en la tarea programada.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv5CanceladaNoSeRecupera(BaseRevision):

    def test_la_tarea_recupera_un_pago_que_llego_despues_de_cancelarse_por_el_navegador(self):
        """Hallazgo del revisor (ya corregido).

        El navegador vuelve con ``code=0`` (cancelar en la página de Tilopay, o cualquiera que abra la
        URL de retorno con ese ``order``): si Tilopay aún no tiene nada, la transacción pasa a «cancel». Si después el
        cliente SÍ paga (misma página, otra pestaña) y no vuelve a la tienda, solo el aviso (que Tilopay entrega por
        Soporte) la rescata; la tarea programada busca únicamente ``draft``/``pending``."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno', navegador_cancelo=True), 'sin_registro')
            self.assertEqual(tx.state, 'cancel')
            self.envejecer(tx, minutes=30)
            tilopay.aprobar(orden, pedido.amount_total)                        # paga después, cierra la pestaña
            tx.dcasa_tilopay_consulta = False
            self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()
        self.assertEqual(tx.state, 'done', 'el cobro real quedó sin confirmar')


    def test_la_tarea_recupera_un_pago_aprobado_despues_de_un_rechazo(self):
        """Hallazgo del revisor (ya corregido).

        Mismo hueco con ``error``: primero el banco rechazó (tx en «error»), después el cliente pagó
        aprobado desde la misma página de Tilopay y cerró la pestaña. docs/TILOPAY.md §5.2 promete que «una consulta
        posterior que muestre un pago aprobado la pasa a pagada», pero nada hace esa consulta: ni el reloj de
        «Estado del pago» (solo ``draft``/``pending``) ni la tarea programada."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.rechazar(orden, pedido.amount_total)
            self.assertEqual(tx._dcasa_tilopay_confirmar('retorno'), 'rechazado')
            self.assertEqual(tx.state, 'error')
            self.envejecer(tx, minutes=30)
            tilopay.aprobar(orden, pedido.amount_total)
            tx.dcasa_tilopay_consulta = False
            self.env['payment.transaction']._cron_dcasa_tilopay_reconciliar()
        self.assertEqual(tx.state, 'done', 'el cobro aprobado quedó sin confirmar')


# ---------------------------------------------------------------------------------------------------------------------
# RV-6 (MENOR) — un pedido pagado con Tilopay queda marcado como «apartado» (con fecha de vencimiento).
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv6ApartadoEnPedidoPagado(BaseRevision):

    def test_un_pedido_pagado_no_queda_como_apartado(self):
        """Hallazgo del revisor (ya corregido).

        ``website_dcasa`` marca como apartado todo pedido de la web que confirma
        «la tienda sola» (usuario público o robot). El pago de Tilopay lo confirma así. La tarea nocturna de apartados
        lo libera después (porque ya hay una transacción hecha), pero hasta entonces el pedido pagado se ve como
        «Apartado por página web» con días por vencer."""
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(pedido.dcasa_apartado_vence, 'un pedido pagado completo aparece como apartado por vencer')


# ---------------------------------------------------------------------------------------------------------------------
# RV-7 (control, pasa) — el diario «Tilopay» no se puede borrar con el proveedor encendido; apagar, borrar y volver a
# encender lo recrea. Intentado como «el cobro cae en el primer banco»: NO prosperó.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv7DiarioBorrado(BaseRevision):

    def test_apagar_borrar_el_diario_y_volver_a_encender_cobra_en_tilopay(self):
        diario = self.proveedor._dcasa_tilopay_diario()
        otros = self.env['account.journal'].search([('type', '=', 'bank'), ('id', '!=', diario.id),
                                                    ('company_id', '=', diario.company_id.id)])
        if not otros:
            self.env['account.journal'].create({'name': 'Banco X', 'code': 'BXX', 'type': 'bank'})
        with self.assertRaises(UserError):
            diario.unlink()                       # Odoo lo impide con el proveedor encendido
        self.proveedor.state = 'disabled'
        self.proveedor.invalidate_recordset()
        self.env['account.journal'].search([('code', '=', 'TLP')]).unlink()
        self.proveedor.state = 'test'
        self.proveedor.invalidate_recordset()
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        self.assertEqual(tx.payment_id.journal_id.code, 'TLP')


# ---------------------------------------------------------------------------------------------------------------------
# Intentos que NO prosperaron (cobertura para el autor; todas pasan hoy).
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRvEvaluarConsultaNoSeDejaEngaNar(TransactionCase):
    """Formas raras de la respuesta de ``consult``: ninguna debe dar APROBADO salvo la fila buena y exacta."""

    ORDEN = 'S00001-1-abcdef12'

    def fila(self, **cambios):
        base = {'id_tilopay': 1, 'orderNumber': self.ORDEN, 'amount': '107.00', 'currency': 'USD', 'code': '1',
                'capture': 'Capture', 'environment': 'Test', 'type': 'Payment'}
        base.update(cambios)
        return base

    def evaluar(self, cuerpo, monto='107.00', entorno='prueba'):
        from decimal import Decimal
        return api.evaluar_consulta(cuerpo, self.ORDEN, Decimal(monto), 'USD', entorno)['veredicto']

    def ok(self, *filas):
        return {'type': '200', 'message': '', 'response': list(filas)}

    def test_la_fila_buena_si_paga(self):
        self.assertEqual(self.evaluar(self.ok(self.fila())), api.APROBADO)

    def test_una_rechazada_y_una_aprobada_paga_pero_dos_aprobadas_no(self):
        self.assertEqual(self.evaluar(self.ok(self.fila(code='4'), self.fila())), api.APROBADO)
        self.assertEqual(self.evaluar(self.ok(self.fila(), self.fila())), api.AMBIGUO)

    def test_estados_raros_no_pagan(self):
        for cambios in ({'code': '0'}, {'code': 'pendiente'}, {'code': ''}, {'code': None}, {'code': ' 1 x'},
                        {'code': True}, {'code': [1]}, {'type': 'Refund'}, {'type': 'Reversal'}, {'type': 'Void'},
                        {'type': ''}, {'type': None}, {'environment': 'Production'}, {'environment': ''},
                        {'environment': None}, {'environment': 'Sandbox2'}, {'currency': 'CRC'}, {'currency': ''},
                        {'amount': '106.99'}, {'amount': '107.01'}, {'amount': '1.0'}, {'amount': ''},
                        {'amount': None}, {'amount': 'NaN'}, {'amount': 'Infinity'}, {'amount': '-107.00'},
                        {'amount': True}, {'amount': [107]}, {'capture': 'Authorization'}, {'capture': 'Void'},
                        {'orderNumber': 'S00001-1-ABCDEF12'}, {'orderNumber': 'otra'}, {'orderNumber': None},
                        {'orderNumber': [self.ORDEN]}):
            with self.subTest(cambios=cambios):
                self.assertNotEqual(self.evaluar(self.ok(self.fila(**cambios))), api.APROBADO)

    def test_formas_de_cuerpo_inesperadas_nunca_pagan_ni_lanzan(self):
        formas = [None, [], {}, 'ok', 200, True, {'type': 200}, {'type': '200'}, {'type': '200', 'response': None},
                  {'type': '200', 'response': {}}, {'type': '200', 'response': 'x'},
                  {'type': '200', 'response': [None, 1, 'x', [], {}]},
                  {'type': '200', 'response': [self.fila(orderNumber=None)]},
                  {'type': '300', 'response': [self.fila()]},
                  {'type': '400', 'message': 'x', 'response': [self.fila()]},
                  {'error': 'Unauthorized'}, {'code': '1', 'description': 'x'},
                  {'type': '200', 'data': [self.fila()]}]
        for forma in formas:
            with self.subTest(forma=forma):
                self.assertNotEqual(self.evaluar(forma), api.APROBADO)

    def test_entorno_real_no_acepta_prueba_y_viceversa(self):
        self.assertEqual(self.evaluar(self.ok(self.fila(environment='Test')), entorno='produccion'), api.ENTORNO)
        self.assertEqual(self.evaluar(self.ok(self.fila(environment='Production')), entorno='prueba'), api.ENTORNO)
        self.assertEqual(self.evaluar(self.ok(self.fila(environment='PROD')), entorno='produccion'), api.APROBADO)
        self.assertEqual(self.evaluar(self.ok(self.fila(environment='TEST')), entorno='prueba'), api.APROBADO)

    def test_fila_de_otra_orden_mezclada_no_cuenta(self):
        otra = self.fila(orderNumber='S00002-1-00000000')
        self.assertEqual(self.evaluar(self.ok(otra)), api.SIN_REGISTRO)
        self.assertEqual(self.evaluar(self.ok(otra, self.fila())), api.APROBADO)
        self.assertEqual(self.evaluar(self.ok(otra, self.fila(), self.fila(type='Refund'))), api.AMBIGUO)


@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRvRutasNoSeDejanEngaNar(ComunTilopay, HttpCase):

    def post_json(self, ruta, cuerpo, **kwargs):
        import json
        return self.url_open(ruta, data=json.dumps(cuerpo), headers={'Content-Type': 'application/json'}, **kwargs)

    def test_retorno_y_aviso_con_la_orden_de_otro_cliente_o_de_otro_proveedor_no_pagan_nada(self):
        pedido, otro_pedido = self.pedido(), self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tx2, orden2 = self.abrir(tilopay, otro_pedido)
            tilopay.aprobar(orden2, otro_pedido.amount_total)            # solo la del otro está pagada
            llamadas = len(tilopay.rutas(api.RUTA_CONSULTA))
            # retorno de la pestaña de ``tx`` diciendo code=1 y la orden de ``tx`` (no pagada en Tilopay)
            self.url_open(RETORNO, params={'code': '1', 'order': orden}, allow_redirects=False)
            tx.invalidate_recordset()
            self.assertNotEqual(tx.state, 'done')
            # y con la orden del otro (que SÍ está pagada) la que cambia es la del otro, nunca la de ``tx``
            r_aviso = self.post_json(AVISO, {'orderNumber': orden2})
            tx.invalidate_recordset()
            tx2.invalidate_recordset()
            self.assertEqual(r_aviso.status_code, 200)
            self.assertEqual((tx.state, tx2.state), ('draft', 'done'))
            self.assertGreaterEqual(len(tilopay.rutas(api.RUTA_CONSULTA)), llamadas)

    def test_el_retorno_no_redirige_a_ningun_otro_sitio(self):
        pedido = self.pedido()
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            for params in ({'code': '1', 'order': orden, 'redirect': 'https://malo.example'},
                           {'order': orden, 'next': '//malo.example', 'returnData': 'aHR0cHM6Ly9tYWxvLmV4YW1wbGU='},
                           {'order': '<script>alert(1)</script>'}):
                r = self.url_open(RETORNO, params=params, allow_redirects=False)
                self.assertIn(r.status_code, (301, 302, 303, 307, 308))
                self.assertTrue(r.headers.get('Location', '').endswith('/payment/status'), r.headers.get('Location'))
                self.assertNotIn('malo.example', r.headers.get('Location', ''))
                self.assertNotIn('malo.example', r.text)
                self.assertNotIn('<script>alert(1)</script>', r.text)

    def test_el_aviso_con_cuerpo_gigante_o_mal_formado_no_cuesta_una_llamada_a_tilopay(self):
        with SimuladorTilopay() as tilopay:
            self.post_json(AVISO, {'orderNumber': 'A' * 100_000})
            self.url_open(AVISO, data=b'\xff\xfe{{{', headers={'Content-Type': 'application/json'})
            self.url_open(AVISO, data='orderNumber=' + 'x' * 70_000,
                          headers={'Content-Type': 'application/x-www-form-urlencoded'})
            self.assertEqual(tilopay.llamadas, [])

    def test_ningun_log_ni_respuesta_trae_secretos_con_tilopay_devolviendo_basura_con_las_claves_adentro(self):
        """Tilopay (o quien se haga pasar por él) devuelve un mensaje de error que repite las claves."""
        from unittest.mock import patch

        import requests

        from odoo.addons.dcasa_pago_tilopay.tests.common import RespuestaFalsa
        pedido = self.pedido()
        veneno = ' '.join(SECRETOS)

        def hostil(url, json=None, headers=None, timeout=None, **kw):
            if url.endswith('/login'):
                return RespuestaFalsa(200, {'access_token': 'tok-secreto-' + 'z' * 40, 'expires_in': 86400})
            return RespuestaFalsa(200, {'type': '400', 'message': veneno + ' tok-secreto-' + 'z' * 40})
        with self.assertLogs(level=logging.DEBUG) as registros, patch.object(requests, 'post', side_effect=hostil):
            logging.getLogger('odoo.test').info('inicio')
            tx = self.transaccion(pedido)
            try:
                tx._get_processing_values()
            except Exception as error:  # noqa: BLE001
                for secreto in (*SECRETOS, 'tok-secreto-'):
                    self.assertNotIn(secreto, str(error))
        texto = '\n'.join(registros.output)
        for secreto in (*SECRETOS, 'tok-secreto-'):
            self.assertNotIn(secreto, texto)


# ---------------------------------------------------------------------------------------------------------------------
# RV-8 (MENOR, endurecimiento) — TILOPAY_ENTORNO=produccion se obedece aunque este servidor NO sea producción.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv8EntornoDelServidor(TransactionCase):

    def test_un_servidor_que_no_es_produccion_nunca_acepta_pagos_reales(self):
        """Hallazgo del revisor (ya corregido).

        La convención de la casa (``dcasa_correo``, ``dcasa_meta_eventos``) es que lo que toca dinero o
        a clientes de verdad solo se activa con ``DCASA_ENTORNO=produccion``. Tilopay solo mira ``TILOPAY_ENTORNO``: en
        staging (``DCASA_ENTORNO=staging``) alguien que pegue ``produccion`` en el panel (o claves reales) pasaría a
        aceptar pagos reales; el único freno es que ``wrangler.jsonc`` fije ``prueba`` (no comprobado desde aquí)."""
        import os
        from unittest.mock import patch
        for servidor in ('staging', '', 'local'):
            with self.subTest(servidor=servidor), patch.dict(
                    os.environ, {'TILOPAY_ENTORNO': 'produccion', 'DCASA_ENTORNO': servidor}):
                self.assertEqual(api.entorno_esperado(), api.PRUEBA)
        with patch.dict(os.environ, {'TILOPAY_ENTORNO': 'produccion', 'DCASA_ENTORNO': 'produccion'}):
            self.assertEqual(api.entorno_esperado(), api.PRODUCCION)


# ---------------------------------------------------------------------------------------------------------------------
# RV-9 (MENOR) — un pago hecho en modo de prueba no queda marcado en el pedido.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv9PagoDePruebaSinMarca(BaseRevision):

    def test_un_pedido_confirmado_con_un_pago_de_prueba_lo_dice(self):
        """Hallazgo del revisor (ya corregido).

        En «Modo de prueba» (el equipo prueba en producción con TILOPAY_ENTORNO=prueba, docs §7) el
        pedido se confirma y el cobro entra al diario «Tilopay» como cualquier otro; nada en el pedido dice que fue una
        tarjeta de prueba, y quien prepara la entrega no lo puede saber."""
        pedido = self.pedido()
        self.assertEqual(self.proveedor.state, 'test')
        with SimuladorTilopay() as tilopay:
            tx, orden = self.abrir(tilopay, pedido)
            tilopay.aprobar(orden, pedido.amount_total)
            tx._dcasa_tilopay_confirmar('retorno')
        tx._post_process()
        nota = self.env.ref('mail.mt_note')
        notas = pedido.message_ids.filtered(
            lambda m: m.subtype_id == nota and all(x in (m.body or '').lower() for x in ('tilopay', 'prueba')))
        self.assertTrue(notas, 'ninguna nota interna del pedido dice que lo pagó una tarjeta de prueba')


# ---------------------------------------------------------------------------------------------------------------------
# RV-10 (MENOR) — «Probar conexión» decía que sí con la llave equivocada.
# ---------------------------------------------------------------------------------------------------------------------
@tagged('post_install', '-at_install', 'rv_tilopay')
class TestRv10ProbarConexionNoVerificaLaLlave(BaseRevision):

    def test_probar_conexion_no_dice_que_la_llave_esta_bien_porque_no_la_comprueba(self):
        """La prueba solo abre sesión con usuario y contraseña; la LLAVE (la más fácil de confundir entre las tres) no
        se usa hasta el primer cobro. El revisor pedía que con una llave equivocada la prueba saliera en rojo, pero
        Tilopay no publica qué contesta a una llave mala (ni ``consult`` ni ``processPayment``: docs/TILOPAY.md §2), y
        esta capa no inventa respuestas de Tilopay. Lo que sí se exige, y es lo honesto: que la pantalla NO diga «bien»
        a secas, que diga con todas las letras que la llave no se comprobó y cuándo se comprueba, y que no se haga
        ninguna llamada que no sea abrir sesión."""
        with entorno(TILOPAY_API_KEY='OTRA-LLAVE-QUE-NO-ES-LA-DE-ESTA-CUENTA'), SimuladorTilopay() as tilopay:
            respuesta = self.proveedor.action_dcasa_tilopay_probar()
        params = respuesta['params']
        self.assertNotEqual(params['type'], 'success', 'sin comprobar la llave, no se puede dar por «todo bien»')
        mensaje = params['message'].lower()
        self.assertIn('llave', mensaje)
        self.assertIn('primer cobro', mensaje)
        self.assertEqual([ruta for ruta, *_ in tilopay.llamadas], [api.RUTA_LOGIN],
                         'solo abre sesión: nada de cobros ni consultas de mentira para probar la llave')
        self.assertNotIn('OTRA-LLAVE', json_lib.dumps(respuesta))

    def test_la_pantalla_dice_claves_cargadas_y_no_conectado(self):
        """Los textos que ve la persona: «Claves cargadas» (no «Conectado»), y la última prueba no promete la llave."""
        self.assertEqual(self.proveedor._fields['dcasa_tilopay_conectado'].string, 'Claves cargadas')
        with entorno(), SimuladorTilopay():
            self.proveedor.action_dcasa_tilopay_probar()
        texto = self.proveedor.dcasa_tilopay_prueba_texto
        self.assertIn('sesión abierta', texto)
        self.assertIn('primer cobro de prueba', texto)
