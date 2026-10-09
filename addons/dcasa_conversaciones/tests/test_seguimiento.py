"""Seguimiento (decisión de la dueña): 1.º a las 5 h solo en horario laboral, 2.º a los 5 días, máximo 2,
ninguno si ya compró o pidió que no lo contacten. Odoo decide; el Worker redacta y envía."""
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.addons.dcasa_socios.tests.common import SociosCommon
from odoo.tests import tagged

from .common import URL_WORKER, JuanCase, respuesta_http


def panama(anio, mes, dia, hora=0, minuto=0):
    return datetime(anio, mes, dia, hora, minuto) + timedelta(hours=5)


class SeguimientoCase(JuanCase):

    def pregunta_y_bot_contesta(self, hora_panama=9, dia=9, **kw):
        """El cliente pregunta y el asistente contesta 5 minutos después. Devuelve la conversación."""
        pregunta = panama(2026, 10, dia, hora_panama, 0)
        conv, _, _ = self.registrar('¿Tienen camas queen?', ts=pregunta, **kw)
        self.registrar('Sí, tenemos varias. ¿Para cuántas personas?', autor='bot', ts=pregunta + timedelta(minutes=5),
                       **{k: v for k, v in kw.items() if k in ('canal', 'id_externo')})
        return conv


@tagged('post_install', '-at_install')
class TestProgramarSeguimiento(SeguimientoCase):

    def test_5_horas_despues_del_ultimo_mensaje_en_horario_laboral(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        # El último mensaje fue a las 9:05; +5 h = 2:05 p. m., dentro del horario.
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 9, 14, 5))

    def test_si_cae_fuera_de_horario_espera_al_siguiente(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=15)
        # 3:05 p. m. + 5 h = 8:05 p. m.: fuera. Al día siguiente a las 8:00.
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 10, 8, 0))

    def test_no_hay_seguimiento_si_el_cliente_fue_el_ultimo_en_escribir(self):
        conv = self.conversacion()
        self.assertFalse(conv.seguimiento_proximo)

    def test_el_cliente_vuelve_a_escribir_y_se_cancela(self):
        conv = self.pregunta_y_bot_contesta()
        self.assertTrue(conv.seguimiento_proximo)
        self.registrar('Sí, para dos', ts=panama(2026, 10, 9, 9, 30))
        self.assertFalse(conv.seguimiento_proximo)
        self.assertEqual(conv.seguimientos_enviados, 0)

    def test_si_la_atiende_una_vendedora_no_hay_seguimiento(self):
        conv = self.pregunta_y_bot_contesta()
        self.registrar('Hola, soy Marta', autor='vendedora', ts=panama(2026, 10, 9, 9, 20))
        self.assertFalse(conv.seguimiento_proximo)
        self.assertEqual(conv.estado, 'humano')

    def test_si_la_devuelven_al_bot_cuenta_desde_ese_momento(self):
        conv = self.pregunta_y_bot_contesta()
        conv.write({'estado': 'humano', 'pausada_hasta': False, 'seguimiento_proximo': False})
        with freeze_time(panama(2026, 10, 12, 10, 0)):
            conv.with_user(self.vendedora).action_devolver_al_bot()
        self.assertEqual(conv.estado, 'bot')
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 12, 15, 0),
                         'Desde la devolución, no desde el último mensaje')

    def test_nada_si_el_seguimiento_esta_apagado_o_el_canal_apagado(self):
        self.ajustes.seguimiento_maximo = 0
        self.assertFalse(self.pregunta_y_bot_contesta().seguimiento_proximo)
        self.ajustes.seguimiento_maximo = 2
        self.ajustes.canal_telegram = False
        self.assertFalse(self.pregunta_y_bot_contesta(canal='telegram', id_externo='321').seguimiento_proximo)

    def test_sin_restriccion_de_horario(self):
        self.ajustes.seguimiento_solo_horario_laboral = False
        conv = self.pregunta_y_bot_contesta(hora_panama=15)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 9, 20, 5))

    def test_horario_distinto_de_la_duena(self):
        self.ajustes.write({'horario_inicio': 9.0, 'horario_fin': 12.0, 'dia_domingo': False})
        # 9:05 + 5 h = 2:05 p. m. > 12:00 → mañana (sábado 10) a las 9:00.
        self.assertEqual(self.pregunta_y_bot_contesta(hora_panama=9).seguimiento_proximo, panama(2026, 10, 10, 9, 0))


@tagged('post_install', '-at_install')
class TestMotivosParaNoSeguir(SeguimientoCase, SociosCommon):
    """Cada razón por la que NO toca seguimiento, con la factura de verdad."""

    def setUp(self):
        super().setUp()
        self.conv = self.pregunta_y_bot_contesta(hora_panama=9, nombre='Eric Gómez')
        self.cliente_chat = self.conv.partner_id

    def motivo(self):
        return self.conv._motivo_sin_seguimiento(panama(2026, 10, 9, 14, 6))

    def factura_del_cliente(self, pagar=True, fecha=None):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente_chat.id,
            'invoice_date': fecha or fields.Date.today(),
            'invoice_line_ids': [(0, 0, {'product_id': self.producto.id, 'quantity': 1, 'price_unit': 100.0})]})
        factura.action_post()
        if pagar:
            self.pagar(factura)
        return factura

    def test_toca_cuando_nada_lo_impide(self):
        self.assertIsNone(self.motivo())

    def test_ya_compro_con_factura_pagada(self):
        self.factura_del_cliente(pagar=True)
        self.assertEqual(self.motivo(), 'ya compró')

    def test_una_factura_sin_pagar_no_cuenta_como_compra(self):
        self.factura_del_cliente(pagar=False)
        self.assertIsNone(self.motivo())

    def test_una_factura_pagada_anterior_a_la_conversacion_no_cuenta(self):
        self.factura_del_cliente(pagar=True, fecha=fields.Date.today() - timedelta(days=400))
        # La conversación empezó el 9/10/2026; una factura de hace más de un año es anterior.
        self.assertIsNone(self.motivo())

    def test_la_factura_de_otro_cliente_no_cuenta(self):
        factura = self.factura(self.cliente)   # factura pagada de OTRO cliente
        self.assertTrue(factura.payment_state in ('paid', 'in_payment'))
        self.assertIsNone(self.motivo())

    def test_pidio_que_no_lo_contacten(self):
        self.cliente_chat.dcasa_no_contactar = True
        self.assertEqual(self.motivo(), 'pidió que no lo contacten')

    def test_la_atiende_una_persona(self):
        self.conv.write({'estado': 'humano', 'pausada_hasta': False})
        self.assertEqual(self.motivo(), 'la atiende una persona')

    def test_conversacion_cerrada(self):
        self.conv.estado = 'cerrada'
        self.assertEqual(self.motivo(), 'la conversación está cerrada')

    def test_ya_recibio_los_dos(self):
        self.conv.seguimientos_enviados = 2
        self.assertEqual(self.motivo(), 'ya recibió todos los seguimientos')

    def test_el_ultimo_mensaje_es_del_cliente(self):
        self.registrar('Una pregunta más', ts=panama(2026, 10, 9, 9, 10))
        self.assertEqual(self.motivo(), 'el último mensaje no es del asistente')


@tagged('post_install', '-at_install')
class TestCronDeSeguimiento(SeguimientoCase):

    def setUp(self):
        super().setUp()
        self.llamadas = self.configurar_worker()

    def llamadas_a(self, ruta):
        return [c for c in self.llamadas.call_args_list if c.args[1].endswith(ruta)]

    def test_pide_el_primer_seguimiento_con_el_contrato(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            pedidos = self.Conversacion._cron_seguimientos()
        self.assertEqual(pedidos, 1)
        (llamada,) = self.llamadas_a('/odoo/seguimiento')
        self.assertEqual(llamada.args[0], 'POST')
        self.assertEqual(llamada.args[1], f'{URL_WORKER}/odoo/seguimiento')
        cuerpo = llamada.kwargs['json']
        self.assertEqual(cuerpo['conversacion_id'], conv.id)
        self.assertEqual((cuerpo['canal'], cuerpo['id_externo'], cuerpo['numero']), ('whatsapp_qr', '50761234567', 1))
        self.assertEqual(set(cuerpo['contexto']), {'interes', 'ultimo_mensaje_ts'})
        self.assertEqual(cuerpo['contexto']['ultimo_mensaje_ts'], '2026-10-09T14:05:00Z')
        self.assertIn('camas queen', cuerpo['contexto']['interes'])
        self.assertTrue(llamada.kwargs['headers']['Authorization'].startswith('Bearer '))
        self.assertTrue(conv.seguimiento_pedido_en)
        self.assertFalse(conv.seguimiento_proximo, 'No se vuelve a pedir mientras el Worker no confirme')

    def test_no_pide_antes_de_tiempo(self):
        self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 13, 59)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertFalse(self.llamadas_a('/odoo/seguimiento'))

    def test_no_pide_fuera_de_horario_aunque_ya_toque(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        conv.seguimiento_proximo = panama(2026, 10, 9, 12, 0)    # alguien lo adelantó a mano
        with freeze_time(panama(2026, 10, 9, 20, 0)):             # 8 p. m. en Panamá
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 10, 8, 0))

    def test_revisa_todo_otra_vez_antes_de_pedir(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        conv.partner_id.dcasa_no_contactar = True       # lo pidió después de programarse
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertFalse(self.llamadas_a('/odoo/seguimiento'))
        self.assertFalse(conv.seguimiento_proximo)

    def test_sin_el_bot_encendido_no_pide_nada(self):
        self.pregunta_y_bot_contesta(hora_panama=9)
        self.ajustes.bot_activo_global = False
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)

    def test_si_el_worker_no_responde_reintenta_con_pausa(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        self.llamadas.return_value = respuesta_http({'ok': False, 'error': 'caído'}, 503)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertEqual(conv.seguimiento_reintentos, 1)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 9, 14, 25))
        self.assertFalse(conv.seguimiento_pedido_en)

    def test_tras_varios_fallos_deja_de_insistir_y_lo_dice(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        self.llamadas.return_value = respuesta_http({'ok': False, 'error': 'caído'}, 503)
        conv.seguimiento_reintentos = 5
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        self.assertFalse(conv.seguimiento_proximo)
        self.assertTrue(any('No pude pedirle el seguimiento' in (m.body or '') for m in conv.message_ids))

    def test_sin_worker_configurado_no_hace_nada(self):
        entorno = patch.dict('os.environ', {'JUAN_WORKER_TOKEN': '', 'JUAN_URL': ''})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)

    def test_confirmacion_del_primero_programa_el_segundo_a_los_5_dias(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
            conv._seguimiento_hecho(1, 'enviado')
        self.assertEqual(conv.seguimientos_enviados, 1)
        self.assertFalse(conv.seguimiento_pedido_en)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 14, 14, 10))

    def test_el_mensaje_del_seguimiento_no_reprograma_el_primero(self):
        """El Worker registra el seguimiento como un mensaje del bot: no cuenta como un mensaje cualquiera."""
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        self.registrar('Hola, ¿pudiste ver las camas?', autor='bot', ts=panama(2026, 10, 9, 14, 11))
        self.assertFalse(conv.seguimiento_proximo)
        with freeze_time(panama(2026, 10, 9, 14, 12)):
            conv._seguimiento_hecho(1, 'enviado')
        self.assertEqual(conv.seguimientos_enviados, 1)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 14, 14, 12))

    def test_ciclo_completo_dos_seguimientos_y_nada_mas(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
            conv._seguimiento_hecho(1, 'enviado')
        with freeze_time(panama(2026, 10, 14, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 1)
            self.assertEqual(self.llamadas_a('/odoo/seguimiento')[-1].kwargs['json']['numero'], 2)
            conv._seguimiento_hecho(2, 'enviado')
        self.assertEqual(conv.seguimientos_enviados, 2)
        self.assertFalse(conv.seguimiento_proximo, 'Máximo 2: no hay un tercero')
        with freeze_time(panama(2026, 10, 30, 14, 10)):
            self.assertEqual(self.Conversacion._cron_seguimientos(), 0)
        self.assertEqual(len(self.llamadas_a('/odoo/seguimiento')), 2)

    def test_confirmar_dos_veces_es_inofensivo(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            conv._seguimiento_hecho(1, 'enviado')
            self.assertTrue(conv._seguimiento_hecho(1, 'enviado')['repetido'])
        self.assertEqual(conv.seguimientos_enviados, 1)

    def test_descartado_cierra_el_ciclo(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        conv._seguimiento_hecho(1, 'descartado', 'la persona ya respondió en otro canal')
        self.assertEqual(conv.seguimientos_enviados, 2)
        self.assertFalse(conv.seguimiento_proximo)
        self.assertFalse(conv.partner_id.dcasa_no_contactar)

    def test_descartado_porque_pidio_que_no_lo_contacten_marca_la_ficha(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        conv._seguimiento_hecho(1, 'descartado', 'no_contactar')
        self.assertTrue(conv.partner_id.dcasa_no_contactar)

    def test_cuando_el_cliente_vuelve_a_escribir_se_reinicia_el_ciclo(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        conv._seguimiento_hecho(1, 'enviado')
        self.registrar('Perdón, estaba ocupada. Sí, la queen', ts=panama(2026, 10, 11, 10, 0))
        self.assertEqual(conv.seguimientos_enviados, 0)
        self.assertFalse(conv.ultimo_seguimiento_en)

    def test_sin_confirmacion_del_worker_se_cierra_el_ciclo(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        # El Worker nunca confirmó y a las 24 h no hay ningún mensaje nuevo del asistente: no se insiste a ciegas.
        with freeze_time(panama(2026, 10, 10, 15, 0)):
            self.Conversacion._cerrar_seguimientos_sin_aviso()
        self.assertFalse(conv.seguimiento_pedido_en)
        self.assertEqual(conv.seguimientos_enviados, 2)

    def test_sin_confirmacion_pero_con_mensaje_del_bot_se_da_por_enviado(self):
        conv = self.pregunta_y_bot_contesta(hora_panama=9)
        with freeze_time(panama(2026, 10, 9, 14, 10)):
            self.Conversacion._cron_seguimientos()
        self.registrar('¿Pudiste ver las camas?', autor='bot', ts=panama(2026, 10, 9, 14, 11))
        with freeze_time(panama(2026, 10, 10, 15, 0)):
            self.Conversacion._cerrar_seguimientos_sin_aviso()
        self.assertEqual(conv.seguimientos_enviados, 1)
        self.assertEqual(conv.seguimiento_proximo, panama(2026, 10, 15, 15, 0))
