"""Citas, reenviados, reacciones y palomitas (pedido de la dueña, 2026-11-07).

«En ocasiones se dificulta si un cliente dice "este", seleccionando un mensaje y reenviándolo, porque solamente vemos la
palabra "este"… No vemos si hay visto, no vemos si se entregó, no vemos el estado del mensaje.»

* Una cita del cliente queda enlazada al mensaje citado (por su id del canal); si no está, se guarda el id igual.
* Los ids que el canal da a cada burbuja nuestra (``dcasa.mensaje.parte``) hacen posibles las citas y las palomitas.
* Las palomitas nunca bajan de estado, son idempotentes y lo desconocido se ignora sin ruido.
* Una reacción reemplaza a la anterior y, vacía, la quita.
* NADA de esto es un mensaje del cliente: ni la actividad, ni «sin leer», ni seguimientos, ni reparto, ni avisos.
Todos los números y nombres son de prueba.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import JuanCase, respuesta_http
from .test_api import ApiCase

CLIENTE = '50760001111'
CANAL = 'whatsapp_cloud'
T0 = datetime(2026, 10, 9, 15, 0)


class CitasCase(JuanCase):

    def entrante(self, texto, id_mensaje, minutos=0, **extra):
        return self.Conversacion._registrar_mensaje({
            'canal': CANAL, 'id_externo': CLIENTE, 'id_mensaje': id_mensaje, 'direccion': 'entrante',
            'autor': 'cliente', 'texto': texto, 'ts': T0 + timedelta(minutes=minutos), 'nombre': 'Cliente de Prueba',
            'celular': None, 'adjuntos': [], **extra})

    def del_bot(self, texto, partes, minutos=0):
        return self.Conversacion._registrar_mensaje({
            'canal': CANAL, 'id_externo': CLIENTE, 'id_mensaje': f'bot-{partes[0]["id_canal"]}',
            'direccion': 'saliente', 'autor': 'bot', 'texto': texto, 'ts': T0 + timedelta(minutes=minutos),
            'nombre': None, 'celular': None, 'adjuntos': [], 'partes': partes})

    def evento(self, tipo, id_mensaje, ts, **extra):
        return {'tipo': tipo, 'canal': CANAL, 'id_externo': CLIENTE, 'id_mensaje': id_mensaje, 'ts': ts, **extra}

    def foto_de_la_conversacion(self, conv):
        """Lo que mira la actividad del cliente: si un evento lo cambia, es un error."""
        conv.invalidate_recordset()
        campos = ['ultima_actividad', 'ultimo_mensaje_cliente', 'ultimo_mensaje_texto', 'ultimo_mensaje_autor',
                  'ultimo_cliente_msg_id', 'estado', 'pausada_hasta', 'asignada_a', 'seguimiento_proximo',
                  'seguimientos_enviados', 'espera_avisada_en', 'reparto_desde', 'write_date']
        foto = {c: conv[c] for c in campos if c in conv._fields}
        foto['mensajes'] = self.Mensaje.sudo().search_count([('conversacion_id', '=', conv.id)])
        foto['sin_leer'] = conv.with_user(self.gerente)._sin_leer(conv.ids)
        return foto


@tagged('post_install', '-at_install')
class TestCitasAlRecibir(CitasCase):

    def test_cita_de_una_burbuja_nuestra_muestra_justo_esa_burbuja(self):
        self.entrante('Hola, busco una cama queen', 'wamid.C1')
        _conv, bot, _ = self.del_bot('Tenemos la Cama Queen Milán.\n¿Para qué cuarto la quieres?', [
            {'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Tenemos la Cama Queen Milán.'},
            {'id_canal': 'wamid.B2', 'tipo': 'texto', 'texto': '¿Para qué cuarto la quieres?'}], minutos=1)
        _conv, este, _ = self.entrante('esta', 'wamid.C2', minutos=2, cita={'id_canal': 'wamid.B1', 'texto': None})
        self.assertEqual(este.cita_id, bot)
        cita = este._como_dict()['cita']
        self.assertEqual(cita['texto'], 'Tenemos la Cama Queen Milán.', 'justo esa burbuja, leída del original')
        self.assertEqual((cita['id'], cita['autor'], cita['en_historial']), (bot.id, 'bot', True))
        self.assertEqual(bot.parte_ids.mapped('id_canal'), ['wamid.B1', 'wamid.B2'])

    def test_cita_de_un_mensaje_suyo_y_de_una_foto_sin_texto(self):
        _conv, suyo, _ = self.entrante('Me gusta el sofá gris', 'wamid.C1')
        _conv, este, _ = self.entrante('¿y en beige?', 'wamid.C2', minutos=1, cita={'id_canal': 'wamid.C1'})
        self.assertEqual((este.cita_id, este._como_dict()['cita']['texto']), (suyo, 'Me gusta el sofá gris'))
        # Una foto nuestra sin pie se cita como «Foto».
        conv = este.conversacion_id
        mensaje = self.Mensaje.sudo().with_context(dcasa_mensaje_sistema=True).create({
            'conversacion_id': conv.id, 'id_mensaje': 'bot-foto', 'direccion': 'saliente', 'autor': 'bot',
            'texto': False, 'ts': T0, 'estado_envio': 'enviado'})
        mensaje._crear_partes([{'id_canal': 'wamid.F1', 'tipo': 'imagen'}])
        _conv, otra, _ = self.entrante('esa', 'wamid.C3', minutos=3, cita={'id_canal': 'wamid.F1'})
        self.assertEqual((otra.cita_id, otra._como_dict()['cita']['texto']), (mensaje, 'Foto'))

    def test_cita_de_algo_que_no_esta_en_el_historial(self):
        _conv, este, _ = self.entrante('este', 'wamid.C9', cita={'id_canal': 'wamid.QUE.NO.EXISTE'})
        self.assertFalse(este.cita_id)
        self.assertEqual(este.cita_id_canal, 'wamid.QUE.NO.EXISTE')
        self.assertEqual(este._como_dict()['cita'], {
            'id': None, 'autor': None, 'usuario': None, 'texto': '', 'en_historial': False})

    def test_si_la_cita_llega_antes_que_los_ids_de_la_burbuja_se_enlaza_despues(self):
        """La palomita y la cita del cliente pueden llegar antes de que Odoo registre la respuesta del asistente."""
        _conv, este, _ = self.entrante('esa', 'wamid.C2', cita={'id_canal': 'wamid.B7'})
        self.assertFalse(este.cita_id)
        _conv, bot, _ = self.del_bot('Tenemos la Cama Roble.', [
            {'id_canal': 'wamid.B7', 'tipo': 'texto', 'texto': 'Tenemos la Cama Roble.'}], minutos=-1)
        este.invalidate_recordset()
        self.assertEqual((este.cita_id, este._como_dict()['cita']['texto']), (bot, 'Tenemos la Cama Roble.'))

    def test_reenviado_y_reenviado_muchas_veces(self):
        _conv, uno, _ = self.entrante('Mira esta cama', 'wamid.R1', reenviado='una')
        _conv, muchas, _ = self.entrante('Promo cama king', 'wamid.R2', minutos=1, reenviado='muchas')
        self.assertEqual((uno._como_dict()['reenviado'], muchas._como_dict()['reenviado']), ('una', 'muchas'))

    def test_un_juan_viejo_sin_los_campos_nuevos_funciona_igual(self):
        conv, mensaje, creado = self.entrante('Hola', 'wamid.V1')
        self.assertTrue(creado)
        datos = mensaje._como_dict()
        self.assertEqual((datos['cita'], datos['reenviado'], datos['reaccion'], datos['estado_canal']),
                         (None, None, None, None))
        self.assertTrue(datos['se_puede_citar'], 'el id del cliente es del canal: se puede responder citándolo')
        self.assertEqual(conv.ultimo_mensaje_cliente, T0)

    def test_las_partes_son_idempotentes_al_repetir_el_registro(self):
        self.del_bot('Hola', [{'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Hola'}])
        _conv, bot, creado = self.del_bot('Hola', [{'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Hola'}])
        self.assertFalse(creado)
        self.assertEqual(len(bot.parte_ids), 1)

    def test_el_chatter_dice_a_que_responde(self):
        self.entrante('Me gusta el sofá gris', 'wamid.C1')
        _conv, este, _ = self.entrante('¿y en beige?', 'wamid.C2', minutos=1, cita={'id_canal': 'wamid.C1'},
                                       reenviado='una')
        cuerpo = str(este.chatter_id.body)
        self.assertIn('Responde a: «Me gusta el sofá gris»', cuerpo)
        self.assertIn('Reenviado', cuerpo)

    def test_sugerir_ve_lo_citado(self):
        self.entrante('Me gusta el sofá gris', 'wamid.C1')
        conv, _este, _ = self.entrante('este', 'wamid.C2', minutos=1, cita={'id_canal': 'wamid.C1'})
        textos = [m['texto'] for m in conv._mensajes_para_sugerir()]
        self.assertIn('(Responde a: «Me gusta el sofá gris») este', textos)


@tagged('post_install', '-at_install')
class TestPalomitasYReacciones(CitasCase):

    def setUp(self):
        super().setUp()
        self.entrante('Hola, busco una cama queen', 'wamid.C1')
        self.conv, self.bot, _ = self.del_bot('Tenemos la Cama Queen Milán.\n¿Para qué cuarto?', [
            {'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Tenemos la Cama Queen Milán.'},
            {'id_canal': 'wamid.B2', 'tipo': 'texto', 'texto': '¿Para qué cuarto?'}], minutos=1)
        self.avisos = []
        parche = patch.object(type(self.Conversacion), '_notificar_recibos',
                              lambda _self, cambios: self.avisos.append(cambios))
        parche.start()
        self.addCleanup(parche.stop)

    def aplicar(self, *eventos):
        return self.Mensaje._aplicar_eventos(list(eventos))

    def estado(self, mensaje=None):
        (mensaje or self.bot).invalidate_recordset()
        return (mensaje or self.bot).estado_canal

    def test_nunca_baja_de_estado_y_repetir_no_cambia_nada(self):
        t = T0 + timedelta(minutes=2)
        for id_canal in ('wamid.B1', 'wamid.B2'):
            self.aplicar(self.evento('estado', id_canal, t, estado='entregado'))
        self.assertEqual(self.estado(), 'entregado')
        # Llega tarde el «enviado» (Meta reintenta y desordena): no baja.
        r = self.aplicar(self.evento('estado', 'wamid.B1', t - timedelta(seconds=30), estado='enviado'))
        self.assertEqual((r['aplicados'], self.estado()), (0, 'entregado'))
        # Leído le gana a entregado; repetido, nada.
        self.aplicar(self.evento('estado', 'wamid.B1', t + timedelta(minutes=1), estado='leido'),
                     self.evento('estado', 'wamid.B2', t + timedelta(minutes=1), estado='leido'))
        self.assertEqual(self.estado(), 'leido')
        r = self.aplicar(self.evento('estado', 'wamid.B2', t + timedelta(minutes=1), estado='leido'),
                         self.evento('estado', 'wamid.B2', t + timedelta(minutes=5), estado='entregado'))
        self.assertEqual((r['aplicados'], self.estado()), (0, 'leido'))
        self.assertEqual(self.bot.canal_entregado_en, t)
        self.assertEqual(self.bot.canal_leido_en, t + timedelta(minutes=1))

    def test_el_mensaje_muestra_la_burbuja_mas_atrasada(self):
        t = T0 + timedelta(minutes=2)
        self.aplicar(self.evento('estado', 'wamid.B1', t, estado='leido'))
        self.assertEqual(self.estado(), 'leido', 'con una sola parte avisada, vale esa')
        self.aplicar(self.evento('estado', 'wamid.B2', t, estado='enviado'))
        self.assertEqual(self.estado(), 'enviado')
        # Leído llegó antes que entregado: cuenta como entregado a esa misma hora (la primera vez que llegó a leído).
        self.aplicar(self.evento('estado', 'wamid.B2', t + timedelta(seconds=40), estado='leido'))
        self.assertEqual((self.estado(), self.bot.canal_entregado_en, self.bot.canal_leido_en), ('leido', t, t))

    def test_no_llego_con_su_motivo_y_si_despues_llega_entregado_se_corrige(self):
        t = T0 + timedelta(minutes=2)
        motivo = 'Pasaron más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja escribirle con una ' \
                 'plantilla aprobada.'
        self.aplicar(self.evento('estado', 'wamid.B1', t, estado='enviado'),
                     self.evento('estado', 'wamid.B2', t, estado='fallido', error=motivo))
        self.assertEqual(self.estado(), 'fallido')
        self.assertEqual(self.bot.error_envio, motivo[:200])
        self.assertEqual(self.bot.estado_envio, 'enviado', 'no se reenvía solo: solo se avisa')
        self.assertEqual(self.bot._como_dict()['error'], motivo[:200])
        self.aplicar(self.evento('estado', 'wamid.B2', t + timedelta(minutes=1), estado='entregado'))
        self.aplicar(self.evento('estado', 'wamid.B1', t + timedelta(minutes=1), estado='entregado'))
        self.assertEqual((self.estado(), self.bot.error_envio), ('entregado', False))

    def test_lo_desconocido_se_ignora_sin_ruido_y_se_devuelve(self):
        antes = self.foto_de_la_conversacion(self.conv)
        r = self.aplicar(self.evento('estado', 'wamid.NO.EXISTE', T0, estado='leido'),
                         {**self.evento('estado', 'wamid.B1', T0, estado='leido'), 'id_externo': '50760009999'})
        self.assertEqual(r, {'aplicados': 0, 'desconocidos': ['wamid.NO.EXISTE', 'wamid.B1']})
        self.assertEqual(self.foto_de_la_conversacion(self.conv), antes)
        self.assertEqual(self.avisos, [])

    def test_un_mensaje_de_antes_con_su_wamid_pero_sin_partes_igual_recibe_palomitas(self):
        """Lo que una vendedora mandó antes de esta versión quedó con el wamid como id, sin partes: se le crea una."""
        viejo = self.Mensaje.sudo().with_context(dcasa_mensaje_sistema=True).create({
            'conversacion_id': self.conv.id, 'id_mensaje': 'wamid.VIEJO', 'direccion': 'saliente',
            'autor': 'vendedora', 'texto': 'Hola, te escribo de la tienda', 'ts': T0, 'estado_envio': 'enviado'})
        self.aplicar(self.evento('estado', 'wamid.VIEJO', T0 + timedelta(minutes=1), estado='entregado'))
        viejo.invalidate_recordset()
        self.assertEqual(viejo.estado_canal, 'entregado')
        self.assertEqual(viejo.parte_ids.mapped('id_canal'), ['wamid.VIEJO'])
        self.aplicar(self.evento('reaccion', 'wamid.VIEJO', T0 + timedelta(minutes=2), emoji='👍'))
        viejo.invalidate_recordset()
        self.assertEqual(viejo.reaccion, '👍')

    def test_las_palomitas_solo_son_de_lo_que_mandamos(self):
        r = self.aplicar(self.evento('estado', 'wamid.C1', T0, estado='leido'))
        cliente = self.Mensaje.sudo().search([('id_mensaje', '=', 'wamid.C1')])
        self.assertEqual((r['aplicados'], cliente.estado_canal), (0, False))

    def test_reaccion_poner_cambiar_quitar_y_una_vieja_no_gana(self):
        t = T0 + timedelta(minutes=3)
        self.aplicar(self.evento('reaccion', 'wamid.B2', t, emoji='👍'))
        self.assertEqual(self.bot._como_dict()['reaccion'], '👍')
        self.aplicar(self.evento('reaccion', 'wamid.B2', t + timedelta(seconds=10), emoji='❤️'))
        self.bot.invalidate_recordset()
        self.assertEqual(self.bot.reaccion, '❤️', 'una por persona y mensaje: la nueva reemplaza')
        self.aplicar(self.evento('reaccion', 'wamid.B2', t + timedelta(seconds=5), emoji='😮'))
        self.bot.invalidate_recordset()
        self.assertEqual(self.bot.reaccion, '❤️', 'una que llega tarde no le gana a la nueva')
        self.aplicar(self.evento('reaccion', 'wamid.B2', t + timedelta(seconds=20), emoji=''))
        self.bot.invalidate_recordset()
        self.assertFalse(self.bot.reaccion, 'vacía = la quitó')

    def test_reacciones_en_dos_burbujas_de_un_mismo_mensaje(self):
        t = T0 + timedelta(minutes=3)
        self.aplicar(self.evento('reaccion', 'wamid.B1', t, emoji='👍'),
                     self.evento('reaccion', 'wamid.B2', t + timedelta(seconds=5), emoji='🔥'))
        self.bot.invalidate_recordset()
        self.assertEqual(self.bot.reaccion, '🔥')
        self.aplicar(self.evento('reaccion', 'wamid.B2', t + timedelta(seconds=9), emoji=''))
        self.bot.invalidate_recordset()
        self.assertEqual(self.bot.reaccion, '👍', 'al quitar la de una burbuja queda la de la otra')

    def test_reaccion_a_un_mensaje_del_cliente(self):
        cliente = self.Mensaje.sudo().search([('id_mensaje', '=', 'wamid.C1')])
        self.aplicar(self.evento('reaccion', 'wamid.C1', T0 + timedelta(minutes=5), emoji='🙏'))
        cliente.invalidate_recordset()
        self.assertEqual(cliente.reaccion, '🙏')

    def test_ni_palomitas_ni_reacciones_son_un_mensaje_del_cliente(self):
        """Ni la actividad, ni «sin leer», ni seguimientos, ni reparto, ni la ventana de 24 h, ni avisos de mensaje."""
        self.conv.sudo().write({'estado': 'humano', 'asignada_a': self.vendedora.id,
                                'seguimiento_proximo': fields.Datetime.now() + timedelta(hours=5)})
        antes = self.foto_de_la_conversacion(self.conv)
        with patch.object(type(self.Conversacion), '_notificar_panel') as panel, \
                patch.object(type(self.Conversacion), '_avisar_por_telegram') as telegram, \
                patch.object(type(self.Conversacion), '_despues_de_mensaje') as despues:
            t = T0 + timedelta(minutes=10)
            self.aplicar(self.evento('estado', 'wamid.B1', t, estado='entregado'),
                         self.evento('estado', 'wamid.B1', t, estado='leido'),
                         self.evento('reaccion', 'wamid.B1', t, emoji='👍'),
                         self.evento('reaccion', 'wamid.C1', t, emoji='❤️'),
                         self.evento('reaccion', 'wamid.B1', t + timedelta(seconds=1), emoji=''))
        self.assertEqual(self.foto_de_la_conversacion(self.conv), antes)
        panel.assert_not_called()
        telegram.assert_not_called()
        despues.assert_not_called()
        # Las pantallas sí se enteran, con un aviso liviano (sin texto ni emoji) por tanda.
        self.assertEqual(len(self.avisos), 1)
        self.assertTrue(all(set(c) == {'conversacion_id', 'mensaje_id', 'estado_canal', 'canal_entregado_en',
                                       'canal_leido_en', 'reaccion'} for c in self.avisos[0]))

    def test_un_mensaje_de_la_vendedora_mandado_por_un_juan_viejo_tambien_tiene_palomitas(self):
        """Juan viejo: solo devuelve ``id_mensaje`` (el wamid). Odoo lo anota como la única parte."""
        worker = self.configurar_worker()
        worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.V1'})
        mensaje = self.conv._crear_mensaje_de_odoo('Te escribo de la tienda', usuario=self.vendedora)
        mensaje._enviar()
        mensaje = self.Mensaje.sudo().search([('id_mensaje', '=', 'wamid.V1')])
        self.assertEqual(mensaje.parte_ids.mapped('id_canal'), ['wamid.V1'])
        self.aplicar(self.evento('estado', 'wamid.V1', T0 + timedelta(minutes=9), estado='leido'))
        mensaje.invalidate_recordset()
        self.assertEqual(mensaje.estado_canal, 'leido')


@tagged('post_install', '-at_install')
class TestResponderCitando(CitasCase):

    def setUp(self):
        super().setUp()
        self.conv, self.cliente, _ = self.entrante('¿Tienen esta mesa?', 'wamid.C1')
        self.worker = self.configurar_worker()
        self.worker.return_value = respuesta_http({'ok': True, 'id_mensaje': 'wamid.O1', 'partes': [
            {'id_canal': 'wamid.O1', 'tipo': 'texto', 'texto': 'Sí, esa mesa la tenemos'}]})

    def al_worker(self):
        """Lo que Odoo le mandó a ``/odoo/enviar`` la última vez."""
        envios = [c.kwargs['json'] for c in self.worker.call_args_list if c.args[1].endswith('/odoo/enviar')]
        return envios[-1]

    def test_responder_pasa_la_cita_al_worker_y_guarda_las_partes(self):
        r = self.Conversacion.with_user(self.vendedora).enviar_respuesta(
            self.conv.id, 'Sí, esa mesa la tenemos', None, None, self.cliente.id)
        cuerpo = self.al_worker()
        self.assertEqual(cuerpo['responde_a'], 'wamid.C1')
        self.assertEqual(r['mensaje']['cita']['id'], self.cliente.id)
        self.assertEqual(r['mensaje']['cita']['texto'], '¿Tienen esta mesa?')
        mensaje = self.Mensaje.sudo().browse(r['mensaje']['id'])
        self.assertEqual(mensaje.parte_ids.mapped('id_canal'), ['wamid.O1'])

    def test_sin_id_del_canal_sale_igual_sin_cita(self):
        self.cliente.sudo().with_context(dcasa_mensaje_sistema=True).write({'id_mensaje': 'odoo-sin-canal'})
        self.Conversacion.with_user(self.vendedora).enviar_respuesta(self.conv.id, 'Hola', None, None, self.cliente.id)
        self.assertNotIn('responde_a', self.al_worker())

    def test_solo_a_un_mensaje_del_cliente_de_esta_conversacion(self):
        otra, ajeno, _ = self.Conversacion._registrar_mensaje({
            'canal': CANAL, 'id_externo': '50760002222', 'id_mensaje': 'wamid.X', 'direccion': 'entrante',
            'autor': 'cliente', 'texto': 'Hola', 'ts': T0, 'nombre': None, 'celular': None, 'adjuntos': []})
        del otra
        nota = self.conv._aviso('Ana tomó la conversación')
        for malo in (ajeno.id, nota.id, 999999, 'x', True):
            with self.subTest(responde_a=malo), self.assertRaises(UserError):
                self.Conversacion.with_user(self.vendedora).enviar_respuesta(self.conv.id, 'Hola', None, None, malo)

    def test_un_programado_conserva_la_cita_al_salir(self):
        cuando = (fields.Datetime.now() + timedelta(hours=2)).isoformat()
        self.Conversacion.with_user(self.vendedora).enviar_respuesta(self.conv.id, 'Mañana te confirmo', None, cuando,
                                                                     self.cliente.id)
        programado = self.Mensaje.sudo().search([('estado_envio', '=', 'programado')])
        self.assertEqual(programado.cita_id, self.cliente)
        nuevo = self.conv._despachar_programado(programado)
        self.assertEqual(nuevo.cita_id, self.cliente)


@tagged('post_install', '-at_install')
class TestApiCitasYEventos(ApiCase):

    def test_mensaje_con_cita_y_reenviado_y_la_respuesta_dice_que_decia(self):
        nube = {'canal': CANAL, 'id_externo': CLIENTE, 'celular': CLIENTE}
        primero = self.post('mensaje', self.mensaje(**nube, id_mensaje='wamid.api.C1', texto='Me gusta el gris'))
        self.assertEqual(primero.status_code, 200)
        r = self.post('mensaje', self.mensaje(**nube, id_mensaje='wamid.api.C2', texto='este',
                                              cita={'id_canal': 'wamid.api.C1'}, reenviado='muchas'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['cita'],
                         {'id_canal': 'wamid.api.C1', 'autor': 'cliente', 'texto': 'Me gusta el gris'})
        mensaje = self.env['dcasa.mensaje'].sudo().search([('id_mensaje', '=', 'wamid.api.C2')])
        self.assertEqual((mensaje.cita_id.id_mensaje, mensaje.reenviado), ('wamid.api.C1', 'muchas'))

    def test_campos_nuevos_mal_formados_se_ignoran_y_el_mensaje_entra(self):
        for extra in ({'cita': 'texto'}, {'cita': {'id_canal': 'con espacios'}}, {'reenviado': 'siempre'},
                      {'partes': 'x'}, {'cita': {'id_canal': 'a' * 300}}):
            with self.subTest(extra=extra):
                r = self.post('mensaje', self.mensaje(**extra))
                self.assertEqual(r.status_code, 200, r.text)
                self.assertNotIn('cita', r.json())

    def test_eventos_con_token_aplica_y_cuenta_lo_que_no_entiende(self):
        partes = [{'id_canal': 'wamid.api.B1', 'tipo': 'texto', 'texto': 'Hola, ¿en qué te ayudo?'}]
        conv_id = self.post('mensaje', self.mensaje(
            canal=CANAL, id_externo=CLIENTE, celular=CLIENTE, id_mensaje='bot-1', direccion='saliente', autor='bot',
            texto='Hola, ¿en qué te ayudo?', partes=partes)).json()['conversacion_id']
        ts = self.mensaje()['ts']
        de = {'canal': CANAL, 'id_externo': CLIENTE}
        r = self.post('eventos', {'eventos': [
            {'tipo': 'estado', **de, 'id_mensaje': 'wamid.api.B1', 'estado': 'leido', 'ts': ts},
            {'tipo': 'reaccion', **de, 'id_mensaje': 'wamid.api.B1', 'emoji': '👍', 'ts': ts},
            {'tipo': 'estado', **de, 'id_mensaje': 'wamid.api.NO', 'estado': 'leido', 'ts': ts},
            {'tipo': 'estado', **de, 'id_mensaje': 'wamid.api.B1', 'estado': 'visto'},
            {'tipo': 'reaccion', **de, 'id_mensaje': 'wamid.api.B1', 'emoji': 'hola'},
            {'tipo': 'otro'}, 'x',
        ]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {'ok': True, 'aplicados': 2, 'desconocidos': ['wamid.api.NO'], 'invalidos': 4})
        bot = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv_id), ('autor', '=', 'bot')])
        self.assertEqual((bot.estado_canal, bot.reaccion), ('leido', '👍'))

    def test_eventos_sin_token_401_y_sin_lista_400(self):
        self.assertEqual(self.post('eventos', {'eventos': []}, token='malo').status_code, 401)
        self.assertEqual(self.post('eventos', {'eventos': []}).status_code, 400)
        self.assertEqual(self.post('eventos', {'nada': 1}).status_code, 400)
        self.assertEqual(self.post('eventos', {'eventos': [{}] * 101}).status_code, 413)

    def test_la_ruta_de_eventos_responde_json_sin_cache(self):
        r = self.post('eventos', {'eventos': [{'tipo': 'estado'}]})
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(r.text)['invalidos'], 1)


@tagged('post_install', '-at_install')
class TestRevisionDeCitas(CitasCase):
    """Lo que encontró la revisión adversarial de las citas y las palomitas (2026-11-07)."""

    def setUp(self):
        super().setUp()
        self.avisos = []
        parche = patch.object(type(self.Conversacion), '_notificar_recibos',
                              lambda _self, cambios: self.avisos.append(cambios))
        parche.start()
        self.addCleanup(parche.stop)

    def de_la_vendedora(self, conv, texto, id_canal, cita=None):
        mensaje = conv._crear_mensaje_de_odoo(texto, usuario=self.vendedora, cita=cita)
        return mensaje.sudo()._marcar_enviado(id_canal, partes=[{'id_canal': id_canal, 'tipo': 'texto',
                                                                 'texto': texto}])

    def leer(self, registro):
        registro.invalidate_recordset()
        return registro

    # --- S4: borrar un mensaje (Ley 81) no deja su texto en las respuestas que lo citaban ---

    def test_s4_borrar_el_mensaje_citado_no_deja_su_texto_en_la_respuesta_ni_en_su_chatter(self):
        _conv, suyo, _ = self.entrante('Vivo en Calle de Prueba 123, casa azul', 'wamid.C1')
        _conv, este, _ = self.entrante('ahí es', 'wamid.C2', minutos=1, cita={'id_canal': 'wamid.C1'})
        self.assertIn('Calle de Prueba 123', str(este.chatter_id.body))
        self.assertEqual(este._como_dict()['cita']['texto'], 'Vivo en Calle de Prueba 123, casa azul')
        suyo.sudo().unlink()
        este = self.leer(este)
        self.assertFalse(este.cita_id)
        self.assertFalse(este.cita_texto)
        self.assertEqual(este.cita_id_canal, 'wamid.C1', 'el id del canal no es un dato del cliente: se queda')
        self.assertEqual(este._como_dict()['cita']['texto'], '')
        cuerpo = str(self.leer(este.chatter_id).body)
        self.assertNotIn('Calle de Prueba', cuerpo)
        self.assertIn('no está en el historial', cuerpo)
        self.assertIn('ahí es', cuerpo)

    def test_s4_responder_desde_odoo_no_copia_lo_citado_y_al_borrarlo_no_queda(self):
        conv, cliente, _ = self.entrante('Mi correo es prueba@example.com', 'wamid.C1')
        respuesta = self.de_la_vendedora(conv, 'Anotado', 'wamid.O1', cita=cliente)
        self.assertFalse(respuesta.cita_texto, 'lo citado está en Odoo: no se guarda una copia')
        self.assertEqual(respuesta._como_dict()['cita']['texto'], 'Mi correo es prueba@example.com')
        cliente.sudo().unlink()
        respuesta = self.leer(respuesta)
        self.assertEqual(respuesta._como_dict()['cita']['texto'], '')
        self.assertTrue(respuesta.chatter_id)
        self.assertNotIn('prueba@example.com', str(self.leer(respuesta.chatter_id).body))

    def test_s4_solo_se_copia_lo_citado_que_no_esta_en_odoo(self):
        """Telegram manda el texto citado: si ese mensaje no está en el historial, es lo único que hay."""
        _conv, fuera, _ = self.entrante('ese', 'wamid.C5', cita={'id_canal': 'tg:1:9', 'texto': 'Una cama de 2 metros'})
        self.assertEqual(fuera.cita_texto, 'Una cama de 2 metros')
        self.assertEqual(fuera._como_dict()['cita']['texto'], 'Una cama de 2 metros')
        _conv, bot, _ = self.del_bot('Tenemos la Cama Roble.', [
            {'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Tenemos la Cama Roble.'}], minutos=1)
        _conv, dentro, _ = self.entrante('esa', 'wamid.C6', minutos=2,
                                         cita={'id_canal': 'wamid.B1', 'texto': 'Tenemos la Cama Roble.'})
        self.assertEqual(dentro.cita_id, bot)
        self.assertFalse(dentro.cita_texto)
        self.assertEqual(dentro._como_dict()['cita']['texto'], 'Tenemos la Cama Roble.')

    def test_s4_la_cita_que_llega_antes_que_la_burbuja_suelta_su_copia_al_enlazarse(self):
        _conv, este, _ = self.entrante('esa', 'wamid.C2', cita={'id_canal': 'wamid.B7', 'texto': 'copia del canal'})
        self.assertEqual(este.cita_texto, 'copia del canal')
        self.del_bot('Tenemos la Cama Roble.\nY la Milán.', [
            {'id_canal': 'wamid.B6', 'tipo': 'texto', 'texto': 'Tenemos la Cama Roble.'},
            {'id_canal': 'wamid.B7', 'tipo': 'texto', 'texto': 'Y la Milán.'}], minutos=-1)
        este = self.leer(este)
        self.assertFalse(este.cita_texto)
        self.assertEqual(este._como_dict()['cita']['texto'], 'Y la Milán.', 'justo la burbuja citada')

    # --- S5: las palomitas azules de una respuesta en varias burbujas ---

    def test_s5_leido_en_la_ultima_burbuja_marca_leidas_las_anteriores_y_los_mensajes_anteriores(self):
        conv, _c, _ = self.entrante('Hola', 'wamid.C1')
        antes = self.de_la_vendedora(conv, 'Hola, te escribe Ana', 'wamid.V1')
        _conv, bot, _ = self.del_bot('Tenemos la Cama Queen Milán.\n¿Para qué cuarto?', [
            {'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Tenemos la Cama Queen Milán.'},
            {'id_canal': 'wamid.B2', 'tipo': 'texto', 'texto': '¿Para qué cuarto?'}], minutos=1)
        t = T0 + timedelta(minutes=5)
        # WhatsApp a veces solo avisa «leído» del último (los anteriores se quedan en «enviado»).
        self.Mensaje._aplicar_eventos([self.evento('estado', 'wamid.B1', t, estado='enviado'),
                                       self.evento('estado', 'wamid.B2', t, estado='leido')])
        self.assertEqual(self.leer(bot).estado_canal, 'leido')
        self.assertEqual(bot.parte_ids.mapped('estado_canal'), ['leido', 'leido'])
        self.assertEqual(self.leer(antes).estado_canal, 'leido')
        self.assertEqual(antes.canal_leido_en, t)
        avisados = {c['mensaje_id'] for c in self.avisos[-1]}
        self.assertEqual(avisados, {bot.id, antes.id}, 'las pantallas se enteran de los dos')

    def test_s5_entregado_sube_lo_anterior_pero_nunca_baja_ni_toca_un_fallido_ni_lo_posterior(self):
        conv, _c, _ = self.entrante('Hola', 'wamid.C1')
        fallido = self.de_la_vendedora(conv, 'Este no llegó', 'wamid.V1')
        leido = self.de_la_vendedora(conv, 'Este ya lo leyó', 'wamid.V2')
        medio = self.de_la_vendedora(conv, 'Este iba enviado', 'wamid.V3')
        _conv, bot, _ = self.del_bot('Ahora este', [{'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Ahora este'}],
                                     minutos=1)
        posterior = self.de_la_vendedora(conv, 'Y uno después', 'wamid.V9')
        t = T0 + timedelta(minutes=5)
        self.Mensaje._aplicar_eventos([
            self.evento('estado', 'wamid.V1', t, estado='fallido', error='No llegó'),
            self.evento('estado', 'wamid.V2', t, estado='leido'),
            self.evento('estado', 'wamid.V3', t, estado='enviado'),
            self.evento('estado', 'wamid.V9', t + timedelta(minutes=1), estado='enviado')])
        self.Mensaje._aplicar_eventos([self.evento('estado', 'wamid.B1', t + timedelta(seconds=30),
                                                   estado='entregado')])
        self.assertEqual(self.leer(bot).estado_canal, 'entregado')
        self.assertEqual(self.leer(medio).estado_canal, 'entregado')
        self.assertEqual(self.leer(leido).estado_canal, 'leido', 'nunca baja')
        self.assertEqual(self.leer(fallido).estado_canal, 'fallido', 'lo que no llegó no llegó')
        self.assertEqual(self.leer(posterior).estado_canal, 'enviado', 'lo posterior no se toca')

    # --- Nit 9: la palomita en vivo trae sus horas ---

    def test_el_aviso_en_vivo_trae_las_horas_de_entregado_y_leido(self):
        _conv, bot, _ = self.del_bot('Hola', [{'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Hola'}])
        t = T0 + timedelta(minutes=5)
        self.Mensaje._aplicar_eventos([self.evento('estado', 'wamid.B1', t, estado='leido')])
        cambio = self.avisos[-1][0]
        self.assertEqual(cambio['mensaje_id'], bot.id)
        self.assertEqual((cambio['canal_entregado_en'], cambio['canal_leido_en']),
                         ('2026-10-09T15:05:00Z', '2026-10-09T15:05:00Z'))

    # --- Nit 7: al fusionar con el eco, la respuesta conserva su cita ---

    def test_al_fusionar_con_el_eco_la_respuesta_conserva_la_cita(self):
        conv, cliente, _ = self.entrante('¿Tienen esta mesa?', 'wamid.C1')
        mensaje = conv._crear_mensaje_de_odoo('Sí, la tenemos', usuario=self.vendedora, cita=cliente)
        # Juan registró el eco (con otro texto: no se adoptó por texto) antes de que Odoo supiera el id.
        eco = self.Mensaje.sudo().with_context(dcasa_mensaje_sistema=True).create({
            'conversacion_id': conv.id, 'id_mensaje': 'wamid.O1', 'direccion': 'saliente', 'autor': 'vendedora',
            'texto': 'Sí, la tenemos ', 'ts': T0, 'estado_envio': 'enviado'})
        fusionado = mensaje.sudo()._marcar_enviado('wamid.O1')
        self.assertEqual(fusionado, eco)
        self.assertEqual((fusionado.cita_id, fusionado.cita_id_canal), (cliente, 'wamid.C1'))
        self.assertEqual(fusionado._como_dict()['cita']['texto'], '¿Tienen esta mesa?')

    # --- Nit 2: textos del canal sin sustitutos sueltos ni controles bidi; un evento que falla no tumba la tanda ---

    def test_texto_libre_y_emoji_rechazan_sustitutos_sueltos_y_controles_bidi(self):
        from odoo.addons.dcasa_conversaciones.controllers.juan import _emoji, _texto_libre
        self.assertEqual(_texto_libre('hola \u202emundo\ud83d \u2066x\u2069', 300), 'hola mundo x')
        for malo in ('\ud83d', '\u202e👍', '👍\u2067', '\u200f❤️'):
            with self.subTest(emoji=ascii(malo)):
                self.assertIsNone(_emoji(malo))
        self.assertEqual(_emoji('👍🏽'), '👍🏽')
        self.assertEqual(_emoji('👨‍👩‍👧'), '👨‍👩‍👧', 'el ZWJ une emojis: no es un control')

    def test_un_evento_que_falla_no_tumba_a_los_demas(self):
        _conv, bot, _ = self.del_bot('Hola', [{'id_canal': 'wamid.B1', 'tipo': 'texto', 'texto': 'Hola'}])
        t = T0 + timedelta(minutes=5)
        original = type(self.Mensaje)._aplicar_reaccion

        def falla_una(modelo, mensaje, parte, evento):
            if evento.get('emoji') == '🔥':
                raise ValueError('falla de prueba')
            return original(modelo, mensaje, parte, evento)

        with patch.object(type(self.Mensaje), '_aplicar_reaccion', falla_una), \
                self.assertLogs('odoo.addons.dcasa_conversaciones.models.mensaje', level='ERROR'):
            r = self.Mensaje._aplicar_eventos([self.evento('reaccion', 'wamid.B1', t, emoji='🔥'),
                                               self.evento('estado', 'wamid.B1', t, estado='leido')])
        self.assertEqual((r['aplicados'], r['fallidos']), (1, 1))
        self.assertEqual(self.leer(bot).estado_canal, 'leido')


@tagged('post_install', '-at_install')
class TestApiEventosRevision(ApiCase):

    def test_un_emoji_con_un_sustituto_suelto_es_invalido_no_un_500(self):
        partes = [{'id_canal': 'wamid.api.S1', 'tipo': 'texto', 'texto': 'Hola'}]
        self.post('mensaje', self.mensaje(canal=CANAL, id_externo=CLIENTE, celular=CLIENTE, id_mensaje='bot-s1',
                                          direccion='saliente', autor='bot', texto='Hola', partes=partes))
        de = {'canal': CANAL, 'id_externo': CLIENTE, 'id_mensaje': 'wamid.api.S1', 'ts': self.mensaje()['ts']}
        # json.dumps escribe el sustituto suelto como «\ud83d»: así lo mandaría un Juan que cortó un emoji a la mitad.
        r = self.post('eventos', {'eventos': [{'tipo': 'reaccion', **de, 'emoji': '\ud83d'},
                                              {'tipo': 'estado', **de, 'estado': 'fallido', 'error': 'x\udc00y'}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()['aplicados'], r.json()['invalidos']), (1, 1))
