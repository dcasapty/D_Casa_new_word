"""De punta a punta con un Yappy falso: pedido → cobro abierto en Yappy → aviso FIRMADO → pedido confirmado y cobro en
el diario «Yappy». Y cada caso raro: los cuatro estados con su mensaje, el orden de llegada, el aviso repetido, el
pedido que cambió, el entorno, lo que ya estaba cerrado y el aviso que no llegó."""
import re
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.addons.dcasa_pago_yappy.models import payment_transaction as modelo_tx
from odoo.addons.dcasa_pago_yappy.models import yappy_api as api
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import CELULAR, CELULAR_LIMPIO, ID_COMERCIO, SECRETOS, ComunYappy, YappyFalso, entorno

CAMPOS_DOCUMENTADOS = ['merchantId', 'orderId', 'domain', 'paymentDate', 'aliasYappy', 'ipnUrl', 'discount', 'taxes',
                       'subtotal', 'total']


class BaseYappy(ComunYappy, TransactionCase):

    def actividades(self, pedido, texto=None):
        dominio = [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id)]
        if texto:
            dominio.append(('summary', 'ilike', texto))
        return self.env['mail.activity'].sudo().search(dominio)

    def notas(self, pedido):
        return ' '.join(pedido.message_ids.mapped(lambda m: re.sub(r'<[^>]+>', ' ', str(m.body or ''))))


@tagged('post_install', '-at_install')
class TestAbrirElCobro(BaseYappy):

    def test_abre_el_cobro_con_los_dos_pasos_y_devuelve_solo_lo_del_boton(self):
        pedido = self.pedido()
        total = pedido.amount_total
        self.assertEqual(total, 107.0, 'el ITBMS va incluido en el total que se cobra')
        tx = self.transaccion(pedido)
        with YappyFalso() as yappy:
            valores = tx._get_processing_values()
            self.assertEqual(
                valores['state'], 'draft', 'crear la transacción no llama a Yappy: el cobro se abre al pulsar')
            self.assertEqual(yappy.llamadas, [])
            datos = tx._dcasa_yappy_iniciar(CELULAR)
        self.assertEqual(set(datos), {'transactionId', 'token', 'documentName'})
        self.assertEqual(tx.state, 'pending')
        orden = tx.dcasa_yappy_orden
        self.assertTrue(
            orden.startswith(pedido.name.replace('-', '').upper()), 'la orden empieza con el número del pedido')
        self.assertLessEqual(len(orden), 15)
        self.assertEqual(tx.provider_reference, orden)
        self.assertEqual(tx.dcasa_yappy_celular, CELULAR_LIMPIO)
        self.assertEqual(tx.dcasa_yappy_id, datos['transactionId'])
        self.assertTrue(tx.dcasa_yappy_iniciada)
        ruta, cuerpo, cabeceras = yappy.llamadas[1]
        self.assertEqual(list(cuerpo), CAMPOS_DOCUMENTADOS)
        self.assertEqual(cuerpo['total'], '107.00')
        self.assertEqual(cuerpo['orderId'], orden)
        self.assertEqual(cuerpo['ipnUrl'], self.proveedor.get_base_url() + '/payment/yappy/ipn')
        self.assertEqual(cuerpo['aliasYappy'], CELULAR_LIMPIO)
        self.assertEqual(cuerpo['merchantId'], ID_COMERCIO)

    def test_una_transaccion_abre_una_sola_orden(self):
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy)
            llamadas = len(yappy.llamadas)
            with self.assertRaises(ValidationError):
                tx._dcasa_yappy_iniciar(CELULAR)
            self.assertEqual(len(yappy.llamadas), llamadas, 'la segunda vez no llama a Yappy')

    def test_un_celular_malo_no_gasta_ninguna_llamada(self):
        for celular in ('', '123', 'abc', '0000 0000', None, '6' * 30):
            with self.subTest(celular=celular), YappyFalso() as yappy:
                tx = self.transaccion(self.pedido())
                with self.assertRaises(ValidationError) as ctx:
                    tx._dcasa_yappy_iniciar(celular)
                self.assertIn('celular de tu app de Yappy', str(ctx.exception.args[0]))
                self.assertEqual(yappy.llamadas, [])
                self.assertFalse(tx.dcasa_yappy_orden, 'sin orden guardada: el intento ni empezó')
                self.assertEqual(tx.state, 'draft')

    def test_numero_no_registrado_E005_dice_que_no_esta_en_yappy_y_cierra_el_intento(self):
        with YappyFalso() as yappy:
            yappy.no_registrados.add(CELULAR_LIMPIO)
            tx = self.transaccion(self.pedido())
            mensaje = self.iniciar_y_fallar(tx)
        self.assertIn('no está registrado en Yappy', mensaje)
        self.assertEqual(tx.state, 'error')
        self.assertEqual(tx.dcasa_yappy_codigo, 'E005')
        self.assertEqual(tx.sale_order_ids.state, 'draft', 'el pedido sigue ahí para reintentar')

    def test_los_errores_de_mi_lado_dan_un_mensaje_claro_y_cierran_el_intento(self):
        for codigo in ('E009', 'E010', 'E011', 'E100', 'E002', 'E006', 'E008', 'E012'):
            with self.subTest(codigo=codigo), YappyFalso() as yappy:
                yappy.errores[api.RUTA_ORDEN] = codigo
                tx = self.transaccion(self.pedido())
                mensaje = self.iniciar_y_fallar(tx)
                self.assertIn('No pudimos abrir el pago con Yappy', mensaje)
                self.assertIn('WhatsApp', mensaje)
                self.assertNotIn(codigo, mensaje, 'el código técnico no se le enseña a la clienta')
                self.assertEqual(tx.state, 'error')
                self.assertEqual(tx.dcasa_yappy_codigo, codigo)

    def test_E007_es_ya_estaba_y_no_un_fallo_la_transaccion_sigue_esperando(self):
        with YappyFalso() as yappy:
            yappy.errores[api.RUTA_ORDEN] = 'E007'
            tx = self.transaccion(self.pedido())
            mensaje = self.iniciar_y_fallar(tx)
        self.assertIn('Ya habíamos mandado', mensaje)
        self.assertEqual(tx.state, 'pending', 'no es un error: la orden existe en Yappy y un aviso tardío la reconoce')
        self.assertTrue(tx.dcasa_yappy_orden)

    def test_yappy_caido_lento_o_raro_deja_la_transaccion_esperando_nunca_pagada(self):
        for falla in ('tiempo', 'red', 'html', 'lista', 'orden_sin_body', 'sin_transaccion'):
            with self.subTest(falla=falla), YappyFalso() as yappy:
                yappy.falla = falla
                tx = self.transaccion(self.pedido())
                self.assertIn('No pudimos abrir el pago con Yappy', self.iniciar_y_fallar(tx))
                self.assertNotEqual(tx.state, 'done')
                self.assertTrue(tx.dcasa_yappy_orden, 'la orden queda guardada ANTES de llamar')

    def test_si_yappy_no_valida_el_comercio_se_cierra_y_no_se_crea_la_orden(self):
        with entorno(YAPPY_DOMINIO='otro-dominio.com'), YappyFalso() as yappy:
            tx = self.transaccion(self.pedido())
            self.iniciar_y_fallar(tx)
        self.assertEqual(len(yappy.llamadas), 1)
        self.assertEqual(tx.state, 'error')

    def test_apagado_o_incompleto_no_abre_ni_deja_crear_la_transaccion(self):
        casos = (('apagado', {}, 'disabled'), ('sin claves', {'YAPPY_CLAVE_SECRETA': None}, 'test'),
                 ('entorno que no coincide', {'YAPPY_ENTORNO': 'produccion', 'DCASA_ENTORNO': 'produccion'}, 'test'))
        for nombre, variables, estado in casos:
            with self.subTest(nombre), entorno(**variables), YappyFalso() as yappy:
                self.proveedor.state = estado
                tx = self.transaccion(self.pedido())
                with self.assertRaises(ValidationError):
                    tx._get_processing_values()
                with self.assertRaises(ValidationError):
                    tx._dcasa_yappy_iniciar(CELULAR)
                self.assertEqual(yappy.llamadas, [])
        self.proveedor.state = 'test'

    def test_el_pedido_cambio_el_monto_ya_no_es_el_del_pedido(self):
        pedido = self.pedido()
        tx = self.transaccion(pedido)
        pedido.order_line.product_uom_qty = 3
        with YappyFalso() as yappy, self.assertRaises(ValidationError) as ctx:
            tx._dcasa_yappy_iniciar(CELULAR)
        self.assertIn('solo paga el pedido completo', ctx.exception.args[0])
        self.assertEqual(yappy.llamadas, [])

    def test_un_monto_distinto_al_del_pedido_no_se_cobra(self):
        pedido = self.pedido()
        for monto in (1.0, pedido.amount_total - 0.01, pedido.amount_total + 5, 0.0, -10.0):
            with self.subTest(monto=monto), YappyFalso() as yappy:
                tx = self.transaccion(pedido, monto=monto)
                with self.assertRaises(ValidationError):
                    tx._dcasa_yappy_iniciar(CELULAR)
                self.assertEqual(yappy.llamadas, [])

    def test_un_pedido_en_cero_no_se_cobra(self):
        pedido = self.pedido()
        pedido.order_line.price_unit = 0.0
        self.assertEqual(pedido.amount_total, 0.0)
        with YappyFalso() as yappy:
            tx = self.transaccion(pedido)
            with self.assertRaises(ValidationError) as ctx:
                tx._dcasa_yappy_iniciar(CELULAR)
        self.assertIn('nada que pagar', ctx.exception.args[0])
        self.assertEqual(yappy.llamadas, [])

    def test_un_pedido_cancelado_no_se_cobra(self):
        pedido = self.pedido()
        tx = self.transaccion(pedido)
        pedido._action_cancel()
        with YappyFalso() as yappy, self.assertRaises(ValidationError) as ctx:
            tx._dcasa_yappy_iniciar(CELULAR)
        self.assertIn('se canceló', ctx.exception.args[0])
        self.assertEqual(yappy.llamadas, [])

    def test_un_pedido_con_pagos_previos_no_se_paga_completo_otra_vez(self):
        pedido = self.pedido()
        previo = self.transaccion(pedido)
        previo._set_done()
        self.env.invalidate_all()
        tx = self.transaccion(pedido)
        with YappyFalso() as yappy:
            if self.env.company.currency_id.compare_amounts(pedido.sudo().amount_paid, 0) > 0:
                with self.assertRaises(ValidationError):
                    tx._dcasa_yappy_iniciar(CELULAR)
                self.assertEqual(yappy.llamadas, [])

    def test_hay_un_tope_de_cobros_abiertos_por_pedido(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            for _i in range(modelo_tx.INTENTOS_EN_CURSO):
                self.abrir(yappy, pedido)
            llamadas = len(yappy.llamadas)
            tx = self.transaccion(pedido)
            with self.assertRaises(ValidationError) as ctx:
                tx._dcasa_yappy_iniciar(CELULAR)
            self.assertIn('varios intentos', ctx.exception.args[0])
            self.assertEqual(len(yappy.llamadas), llamadas, 'pasado el tope no se llama a Yappy')

    def test_hay_un_tope_global_de_ordenes_por_hora(self):
        from unittest.mock import patch  # noqa: PLC0415
        # Una base de desarrollo puede traer cobros recientes de pruebas a mano: el tope se fija «lo que ya hay + 2».
        ya_hay = self.env['payment.transaction'].sudo().search_count([
            ('provider_id', '=', self.proveedor.id), ('dcasa_yappy_orden', '!=', False), ('state', '!=', 'done'),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=1))])
        with YappyFalso() as yappy, patch.object(modelo_tx, 'TOPE_ORDENES_POR_HORA', ya_hay + 2):
            self.abrir(yappy)
            self.abrir(yappy)
            llamadas = len(yappy.llamadas)
            tx = self.transaccion(self.pedido())
            with self.assertRaises(ValidationError) as ctx:
                tx._dcasa_yappy_iniciar(CELULAR)
            self.assertIn('Hay muchos pagos en curso', ctx.exception.args[0])
            self.assertEqual(len(yappy.llamadas), llamadas)
            self.assertFalse(tx.dcasa_yappy_orden)

    def test_con_el_tope_de_llamadas_lleno_no_se_toca_nada(self):
        abiertos = []
        try:
            for _i in range(api.TOPE_DE_LLAMADAS_A_LA_VEZ):
                gestor = api.cupo()
                gestor.__enter__()
                abiertos.append(gestor)
            tx = self.transaccion(self.pedido())
            with YappyFalso() as yappy, self.assertRaises(ValidationError) as ctx:
                tx._dcasa_yappy_iniciar(CELULAR)
            self.assertIn('Hay muchos pagos en curso', ctx.exception.args[0])
            self.assertEqual(yappy.llamadas, [])
            self.assertFalse(tx.dcasa_yappy_orden)
            self.assertEqual(tx.state, 'draft')
        finally:
            for gestor in abiertos:
                gestor.__exit__(None, None, None)

    def test_la_orden_de_yappy_es_unica_y_se_exige_en_la_base(self):
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy)
            otra = self.transaccion(self.pedido())
            with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
                otra.dcasa_yappy_orden = orden
                otra.flush_recordset()

    def test_solo_el_equipo_abre_un_proveedor_sin_publicar(self):
        from odoo.tests import new_test_user  # noqa: PLC0415
        self.proveedor.is_published = False
        visitante = self.env.ref('base.public_user')
        interno = new_test_user(self.env, login='equipo_yappy', groups='base.group_user')
        with YappyFalso() as yappy:
            tx = self.transaccion(self.pedido())
            with self.assertRaises(ValidationError):
                tx.with_user(visitante).sudo()._dcasa_yappy_exigir_listo()
            tx.with_user(interno).sudo()._dcasa_yappy_exigir_listo()
            self.assertEqual(yappy.llamadas, [])


@tagged('post_install', '-at_install')
class TestElAvisoPaga(BaseYappy):

    def test_pedido_a_pagado_con_cobro_en_el_diario_yappy_y_factura_cruzada(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, orden, _datos = self.abrir(yappy, pedido)
        self.assertEqual(self.aviso(tx, 'E'), 'done')
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.dcasa_yappy_estado, 'E')
        self.assertTrue(tx.dcasa_yappy_aviso_fecha)
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertTrue(pedido.picking_ids, 'confirmar el pedido reserva el inventario')
        pago = tx.payment_id
        self.assertTrue(pago)
        self.assertEqual(pago.journal_id.name, 'Yappy')
        self.assertEqual(pago.amount, pedido.amount_total, 'se paga el monto de NUESTRA transacción')
        self.assertTrue(pago.move_id.line_ids)
        factura = pedido._create_invoices()
        factura.action_post()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    def test_el_pedido_pagado_conserva_todas_sus_lineas(self):
        pedido = self.pedido(cantidad=3)
        lineas = [(ln.product_id.id, ln.product_uom_qty, ln.price_unit) for ln in pedido.order_line]
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual([(ln.product_id.id, ln.product_uom_qty, ln.price_unit) for ln in pedido.order_line], lineas)

    def test_cada_estado_tiene_su_final_y_su_mensaje(self):
        esperados = {'R': 'No confirmaste el pago a tiempo', 'C': 'Cancelaste el pago en la app de Yappy',
                     'X': 'La solicitud de pago venció sin empezarse'}
        for estado, frase in esperados.items():
            with self.subTest(estado=estado), YappyFalso() as yappy:
                pedido = self.pedido()
                tx, _o, _d = self.abrir(yappy, pedido)
                self.assertEqual(self.aviso(tx, estado), 'cancel')
                self.assertIn(frase, tx.state_message)
                self.assertIn('Tu pedido sigue guardado', tx.state_message)
                self.assertEqual(pedido.state, 'draft', 'el pedido (con sus líneas) sigue ahí para retomarlo')
                tx._post_process()
                self.assertFalse(tx.payment_id)
        self.assertEqual(len({modelo_tx.MENSAJES_FINALES[e] for e in 'RCX'}), 3, 'los tres mensajes son distintos')

    def test_el_mismo_aviso_dos_veces_no_duplica_pago_ni_nota(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        pedido = tx.sale_order_ids
        self.aviso(tx, 'E')
        notas = self.notas(pedido)
        for _i in range(4):
            self.aviso(tx, 'E')
        self.assertEqual(self.notas(pedido), notas, 'un aviso repetido no escribe nada más')
        tx._post_process()
        tx._post_process()
        self.assertEqual(self.env['account.payment'].search_count([('payment_transaction_id', '=', tx.id)]), 1)
        self.assertEqual(tx.dcasa_yappy_avisos.count('E '), 1)

    def test_orden_de_llegada_de_los_avisos(self):
        """E→E, E→R, E→C, E→X, R→E, C→E, X→E, R→R, R→C y cada una con su resultado."""
        casos = [
            (('E', 'E'), 'done', False, False),
            (('E', 'R'), 'done', True, False),      # ya pagada: no se deshace; alguien lo mira
            (('E', 'C'), 'done', True, False),
            (('E', 'X'), 'done', True, False),
            (('R', 'E'), 'error', False, True),     # cerrada y llega un cobro: lo revisa una persona
            (('C', 'E'), 'error', False, True),
            (('X', 'E'), 'error', False, True),
            (('R', 'R'), 'cancel', False, False),
            (('R', 'C'), 'cancel', False, False),
            (('C', 'X'), 'cancel', False, False),
            (('R', 'C', 'X', 'R'), 'cancel', False, False),
        ]
        for secuencia, estado_final, contradiccion, revision in casos:
            with self.subTest(secuencia=secuencia), YappyFalso() as yappy:
                tx, _o, _d = self.abrir(yappy)
                pedido = tx.sale_order_ids
                for letra in secuencia:
                    self.aviso(tx, letra)
                self.assertEqual(tx.state, estado_final)
                self.assertEqual(bool(tx.dcasa_yappy_revision), revision)
                self.assertEqual(bool(self.actividades(pedido, 'avisos que se contradicen')), contradiccion)
                self.assertEqual(bool(self.actividades(pedido, 'cobro para revisar')), revision)
                tx._post_process()
                self.assertEqual(bool(tx.payment_id), estado_final == 'done',
                                 'solo un E con la transacción abierta crea un pago')

    def test_un_cobro_que_llega_a_una_transaccion_cerrada_nunca_se_paga_solo(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        pedido = tx.sale_order_ids
        self.aviso(tx, 'R')
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision)
        self.assertIn('Nuestro equipo lo revisa', tx.state_message)
        for _i in range(3):
            self.aviso(tx, 'E')
        tx._post_process()
        self.assertFalse(tx.payment_id)
        self.assertNotEqual(pedido.state, 'sale')
        actividad = self.actividades(pedido, 'cobro para revisar')
        self.assertTrue(actividad)
        self.assertIn('NO se tomó como pago solo', actividad[0].note)
        self.assertEqual(len(actividad), len(actividad.mapped('user_id')), 'una actividad por persona, sin repetirse')

    def test_el_aviso_de_una_transaccion_en_error_tampoco_la_paga_sola(self):
        with YappyFalso() as yappy:
            yappy.no_registrados.add(CELULAR_LIMPIO)
            tx = self.transaccion(self.pedido())
            self.iniciar_y_fallar(tx)
        self.assertEqual(tx.state, 'error')
        self.aviso(tx, 'E')
        self.assertTrue(tx.dcasa_yappy_revision)
        self.assertFalse(tx.payment_id)

    def test_una_orden_desconocida_no_encuentra_transaccion(self):
        with YappyFalso() as yappy:
            self.abrir(yappy)
        for orden in ('S99999ZZZZZ', '', 'x' * 40, "S1'; DROP TABLE payment_transaction;--"):
            self.assertFalse(self.env['payment.transaction']._dcasa_yappy_buscar(orden))

    def test_una_transaccion_de_otro_proveedor_no_se_busca_por_la_orden(self):
        transferencia = self.env.ref('payment.payment_provider_transfer')
        metodo = self.env['payment.method'].search([('code', '=', 'wire_transfer')], limit=1)
        pedido = self.pedido()
        otra = self.env['payment.transaction'].create({
            'provider_id': transferencia.id, 'payment_method_id': metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': pedido.partner_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(pedido.ids)]})
        otra.dcasa_yappy_orden = 'S00001ABCDE'
        self.assertFalse(self.env['payment.transaction']._dcasa_yappy_buscar('S00001ABCDE'))
        self.assertIsNone(otra._dcasa_yappy_aplicar_aviso(api.Aviso('S00001ABCDE', 'E', '')))
        self.assertEqual(otra.state, 'draft')

    def test_los_datos_que_no_son_un_aviso_verificado_se_ignoran(self):
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy)
        for dato in ({'estado': 'E', 'orden': orden}, api.Aviso(orden, 'E', ''),
                     {'reference': tx.reference, 'status': 'E'}):
            tx._process('yappy', dato)
            self.assertEqual(tx.state, 'pending', repr(dato))
        self.assertFalse(tx.payment_id)

    def test_el_aviso_paga_aunque_el_proveedor_ya_se_haya_apagado(self):
        """Quien pagó antes del apagón no pierde su pedido: el aviso viene firmado y la orden es nuestra."""
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        self.proveedor.state = 'disabled'
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')

    def test_el_numero_de_confirmacion_es_solo_informativo(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
            self.aviso(tx, 'E', confirmationNumber='CONF-998877')
        self.assertEqual(tx.dcasa_yappy_confirmacion, 'CONF-998877')
        self.assertIn('solo informativa', tx.sale_order_ids.dcasa_pago_texto)

    def test_el_estado_guardado_es_el_del_aviso_no_lo_que_diga_el_navegador(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        tx.sudo()._process('yappy', {'status': 'E', 'state': 'done', 'orderId': tx.dcasa_yappy_orden})
        self.assertEqual(tx.state, 'pending')


@tagged('post_install', '-at_install')
class TestElPedidoYElEntorno(BaseYappy):

    def test_el_pedido_cambio_mientras_pagaba_no_se_paga_solo_ni_aunque_vuelva_a_valer(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido.order_line.product_uom_qty = 3
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision)
        self.assertIn('Tu pedido cambió mientras pagabas', tx.state_message)
        actividad = self.actividades(pedido, 'no cuadra con el pedido')
        self.assertTrue(actividad)
        self.assertIn('El dinero entró', actividad[0].note)
        pedido.order_line.product_uom_qty = 1       # el pedido vuelve a valer lo cobrado
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error', 'marcado para una persona: nunca se paga solo')
        tx._post_process()
        self.assertFalse(tx.payment_id)
        self.assertNotEqual(pedido.state, 'sale')

    def test_el_pedido_que_baja_de_precio_tampoco_se_paga_solo(self):
        pedido = self.pedido(cantidad=2)
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido.order_line.product_uom_qty = 1
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision)

    def test_la_ultima_puerta_antes_de_confirmar_compara_otra_vez(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
        pedido.order_line.product_uom_qty = 2        # cambió entre el aviso y la tarea que confirma
        tx._post_process()
        self.assertNotEqual(pedido.state, 'sale', 'no se confirma solo un pedido que ya no vale lo cobrado')
        self.assertTrue(self.actividades(pedido, 'no cuadra con el pedido'))

    def test_un_pago_de_otro_entorno_no_se_toma_como_pago(self):
        """La transacción se abrió en «Modo de prueba» y llega un aviso cuando el servidor ya es el de producción."""
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.assertFalse(tx.is_live)
        self.proveedor.state = 'enabled'
        with entorno(YAPPY_ENTORNO='produccion', DCASA_ENTORNO='produccion'):
            self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'error')
        self.assertTrue(tx.dcasa_yappy_revision)
        self.assertFalse(tx.payment_id)

    def test_un_pago_de_prueba_deja_la_nota_de_prueba_en_el_pedido(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        self.assertIn('modo de PRUEBA', self.notas(pedido))

    def test_pedido_cancelado_cuando_llega_el_pago_el_dinero_entro_y_alguien_se_entera(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        pedido._action_cancel()
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done', 'el cobro es real: queda registrado')
        tx._post_process()
        self.assertEqual(pedido.state, 'cancel', 'el pedido cancelado no se confirma solo')
        self.assertTrue(self.actividades(pedido, 'ya no está vivo'))

    def test_pedido_pagado_por_otra_via_y_llega_otro_cobro_se_pide_devolver_uno(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            primera, _o, _d = self.abrir(yappy, pedido)
            segunda, _o2, _d2 = self.abrir(yappy, pedido)
        self.aviso(primera, 'E')
        self.aviso(segunda, 'E')
        self.assertEqual(primera.state, 'done')
        self.assertEqual(segunda.state, 'done')
        self.assertTrue(self.actividades(pedido, 'pagado dos veces'))
        self.assertIn('hay que devolverle uno', self.notas(pedido))

    def test_pagar_un_apartado_lo_suelta_del_vencimiento(self):
        pedido = self.pedido()
        if 'dcasa_apartado_vence' not in pedido._fields:
            self.skipTest('website_dcasa no está instalado')
        pedido.action_quotation_sent()
        self.assertTrue(pedido.dcasa_apartado_vence, 'un pedido de la web por cobrar queda como apartado')
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertFalse(pedido.dcasa_apartado_vence, 'pagado completo deja de ser un apartado por vencer')


@tagged('post_install', '-at_install')
class TestElAvisoQueNoLlego(BaseYappy):
    """Yappy no tiene consulta de estado: la tarea deja un pendiente a Caja, sin pagar ni cancelar sola."""

    def setUp(self):
        super().setUp()
        # Una base de desarrollo puede traer cobros viejos sin aviso (de pruebas a mano): se les da su pendiente ahora,
        # dentro de esta prueba (se deshace al terminar), para que la cuenta de abajo sea solo la de la prueba.
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()

    def test_pasados_15_minutos_sin_aviso_hay_un_pendiente_claro(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido)
        self.envejecer(tx, minutes=16)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 1)
        actividad = self.actividades(pedido, 'sin aviso de pago')
        self.assertTrue(actividad)
        nota = actividad[0].note
        self.assertIn(orden, nota)
        self.assertIn('Yappy Comercial', nota)
        self.assertIn('no pagó ni canceló nada solo', nota)
        self.assertIn(pedido.name, nota)
        self.assertEqual(tx.state, 'pending', 'ni paga ni cancela por su cuenta')
        self.assertTrue(tx.dcasa_yappy_sin_aviso)
        self.assertFalse(tx.payment_id)

    def test_el_pendiente_dice_que_compro_para_retomar_con_el_cliente(self):
        pedido = self.pedido(cantidad=2)
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.envejecer(tx, minutes=20)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        nota = self.actividades(pedido, 'sin aviso de pago')[0].note
        self.assertIn('sofá de prueba (yappy)', nota.lower())
        self.assertIn('2 ×', nota)
        self.assertIn('Ana Prueba Yappy', nota)

    def test_una_sola_vez_por_transaccion(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.envejecer(tx, minutes=30)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 1)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 0)
        actividades = self.actividades(pedido, 'sin aviso de pago')
        self.assertEqual(len(actividades), len(actividades.mapped('user_id')), 'una por persona, sin repetirse')

    def test_no_se_le_gana_a_quien_todavia_esta_pagando(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        self.envejecer(tx, minutes=14)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 0)

    def test_lo_que_ya_tuvo_aviso_o_esta_cerrado_no_se_pregunta(self):
        for estado in ('E', 'R', 'C', 'X'):
            with self.subTest(estado=estado), YappyFalso() as yappy:
                tx, _o, _d = self.abrir(yappy)
                self.aviso(tx, estado)
                self.envejecer(tx, minutes=60)
                self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 0)

    def test_lo_marcado_para_revision_ya_lo_tiene_una_persona(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        tx.dcasa_yappy_revision = True
        self.envejecer(tx, minutes=60)
        self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 0)

    def test_sin_claves_no_hace_nada(self):
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy)
        self.envejecer(tx, minutes=60)
        with entorno(YAPPY_ID_COMERCIO=None):
            self.assertEqual(self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso(), 0)

    def test_si_el_aviso_llega_tarde_igual_paga(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.envejecer(tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')

    def test_la_tarea_esta_programada_y_no_toca_nada_de_tilopay(self):
        cron = self.env.ref('dcasa_pago_yappy.cron_sin_aviso')
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (10, 'minutes'))
        self.assertIn('_cron_dcasa_yappy_sin_aviso', cron.code)


@tagged('post_install', '-at_install')
class TestNingunaClaveSale(BaseYappy):

    def test_ningun_registro_del_recorrido_trae_claves_ni_el_celular(self):
        with self.assertLogs('odoo', level='INFO') as registro, YappyFalso() as yappy:
            pedido = self.pedido()
            tx, _o, datos = self.abrir(yappy, pedido)
            self.aviso(tx, 'E')
            tx._post_process()
            yappy.falla = 'html'
            self.iniciar_y_fallar(self.transaccion(self.pedido()))
            self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        texto = '\n'.join(registro.output)
        for secreto in SECRETOS + (yappy.token, datos['token']):
            self.assertNotIn(secreto, texto)
        self.assertNotIn(CELULAR_LIMPIO, texto)

    def test_la_transaccion_no_guarda_ni_el_token_del_boton_ni_las_claves(self):
        with YappyFalso() as yappy:
            tx, _o, datos = self.abrir(yappy)
        valores = tx.read()[0]
        texto = str(valores) + str(tx.sale_order_ids.message_ids.mapped('body'))
        for secreto in SECRETOS + (yappy.token, datos['token']):
            self.assertNotIn(secreto, texto)
        self.assertNotIn(datos['documentName'], texto, 'lo que Yappy dio para el botón no se guarda')
