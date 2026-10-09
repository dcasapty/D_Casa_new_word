"""Conversaciones y mensajes: la ficha del cliente (sin duplicar), la idempotencia, quién contesta y el chatter."""
import base64
from datetime import datetime, timedelta
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import JuanCase


@tagged('post_install', '-at_install')
class TestFichaDelCliente(JuanCase):
    """Cliente = res.partner con el celular como llave. Nunca duplica."""

    def test_crea_la_ficha_con_el_celular_de_whatsapp(self):
        conv, mensaje, creado = self.registrar(nombre='Karen')
        self.assertTrue(creado)
        self.assertEqual(conv.partner_id.name, 'Karen')
        self.assertEqual(conv.partner_id.phone, '+507 6123-4567')
        self.assertEqual(conv.partner_id.dcasa_creado_por, 'juan')
        self.assertEqual((conv.canal, conv.id_externo, conv.estado), ('whatsapp_qr', '50761234567', 'bot'))
        self.assertEqual(conv.celular, '+507 6123-4567')

    def test_reutiliza_la_ficha_que_ya_tiene_ese_telefono(self):
        existente = self.Partner.create({'name': 'Ana Gómez', 'phone': '6123-4567'})
        conv = self.conversacion(nombre='Otro nombre')
        self.assertEqual(conv.partner_id, existente)
        self.assertEqual(self.Partner.search_count([('dcasa_telefono_digitos', '=', '61234567')]), 1)
        self.assertEqual(existente.name, 'Ana Gómez', 'No se pisa el nombre de una ficha existente')

    def test_reutiliza_la_ficha_de_socio_por_su_llave_dcasa_celular(self):
        socio = self.Partner.create({'name': 'Luis Socio', 'dcasa_celular': '61234567'})
        self.assertEqual(self.conversacion().partner_id, socio)

    def test_la_ficha_archivada_tambien_ocupa_el_celular(self):
        archivada = self.Partner.create({'name': 'Vieja', 'phone': '+507 6123-4567', 'active': False})
        self.assertEqual(self.conversacion().partner_id, archivada)

    def test_dos_formas_de_escribir_el_numero_son_el_mismo_cliente(self):
        primero = self.conversacion(canal='whatsapp_qr', id_externo='50761234567')
        segundo = self.conversacion(canal='whatsapp_cloud', id_externo='50761234567')
        self.assertNotEqual(primero, segundo, 'Una conversación por canal')
        self.assertEqual(primero.partner_id, segundo.partner_id, 'pero el mismo cliente')

    def test_numero_de_otro_pais_no_se_confunde_con_uno_de_panama(self):
        panameno = self.Partner.create({'name': 'Panameño', 'phone': '+507 5555-6026'})
        extranjero = self.conversacion(id_externo='13055556026').partner_id
        self.assertNotEqual(extranjero, panameno)
        self.assertEqual(extranjero.phone, '+13055556026')
        self.assertEqual(self.conversacion(id_externo='13055556026').partner_id, extranjero)

    def test_telegram_sin_celular_crea_una_ficha_provisional(self):
        conv = self.conversacion(canal='telegram', id_externo='123456789', nombre=None)
        self.assertEqual(conv.partner_id.name, 'Telegram 123456789')
        self.assertFalse(conv.partner_id.phone)

    def test_telegram_con_celular_enlaza_con_la_ficha_existente(self):
        existente = self.Partner.create({'name': 'Rosa', 'phone': '6123-4567'})
        conv = self.conversacion(canal='telegram', id_externo='777', celular='+507 6123-4567')
        self.assertEqual(conv.partner_id, existente)

    def test_celular_que_llega_despues_se_enlaza(self):
        conv = self.conversacion(canal='telegram', id_externo='888', nombre='Tomás')
        self.assertFalse(conv.partner_id.phone)
        self.registrar(canal='telegram', id_externo='888', celular='6555-0707')
        self.assertEqual(conv.partner_id.phone, '+507 6555-0707')
        # Y si ese celular ya era de otra ficha, la conversación pasa a esa ficha (sin duplicar).
        dueno = self.Partner.create({'name': 'Dueño del 6555-0808', 'phone': '6555-0808'})
        otra = self.conversacion(canal='telegram', id_externo='889', nombre='Ana')
        self.registrar(canal='telegram', id_externo='889', celular='6555-0808')
        self.assertEqual(otra.partner_id, dueno)

    def test_el_nombre_real_reemplaza_al_provisional(self):
        conv = self.conversacion(canal='telegram', id_externo='999', nombre=None)
        self.assertEqual(conv.partner_id.name, 'Telegram 999')
        self.registrar(canal='telegram', id_externo='999', nombre='Marta')
        self.assertEqual(conv.partner_id.name, 'Marta')
        self.registrar(canal='telegram', id_externo='999', nombre='Otro')
        self.assertEqual(conv.partner_id.name, 'Marta', 'Un nombre ya real no se vuelve a pisar')

    def test_por_numero_y_canal_hay_una_sola_conversacion(self):
        self.registrar()
        self.registrar('Otro mensaje')
        self.assertEqual(self.Conversacion.search_count([('id_externo', '=', '50761234567')]), 1)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.Conversacion.sudo().create({'canal': 'whatsapp_qr', 'id_externo': '50761234567'})


@tagged('post_install', '-at_install')
class TestMensajes(JuanCase):

    def test_registra_el_mensaje(self):
        conv, mensaje, creado = self.registrar('Hola', nombre='Karen')
        self.assertTrue(creado)
        self.assertEqual((mensaje.direccion, mensaje.autor, mensaje.texto), ('entrante', 'cliente', 'Hola'))
        self.assertEqual(mensaje.estado_envio, 'recibido')
        self.assertEqual(mensaje.ts, datetime(2026, 10, 9, 15, 0))
        self.assertEqual(conv.ultima_actividad, datetime(2026, 10, 9, 15, 0))
        self.assertEqual(conv.ultimo_mensaje_texto, 'Hola')
        self.assertEqual(conv.ultimo_mensaje_autor, 'cliente')
        self.assertEqual(conv.mensajes_count, 1)

    def test_idempotente_por_id_mensaje(self):
        datos = self.datos('Hola')
        primero = self.Conversacion._registrar_mensaje(datos)
        segundo = self.Conversacion._registrar_mensaje(dict(datos))
        self.assertTrue(primero[2])
        self.assertFalse(segundo[2], 'La repetición no crea nada')
        self.assertEqual(primero[1], segundo[1])
        self.assertEqual(primero[0].mensajes_count, 1)
        self.assertEqual(self.Mensaje.search_count([('id_mensaje', '=', datos['id_mensaje'])]), 1)

    def test_la_base_tambien_lo_impide(self):
        conv, mensaje, _ = self.registrar()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.Mensaje.sudo().create({'conversacion_id': conv.id, 'id_mensaje': mensaje.id_mensaje,
                                        'direccion': 'entrante', 'autor': 'cliente', 'texto': 'x'})

    def test_el_mismo_id_en_otra_conversacion_es_otro_mensaje(self):
        # Telegram numera por chat: el message_id 1 puede repetirse en chats distintos.
        a = self.Conversacion._registrar_mensaje(self.datos(canal='telegram', id_externo='1', id_mensaje='1'))
        b = self.Conversacion._registrar_mensaje(self.datos(canal='telegram', id_externo='2', id_mensaje='1'))
        self.assertTrue(a[2] and b[2])
        self.assertNotEqual(a[0], b[0])

    def test_direccion_y_autor_tienen_que_coincidir(self):
        conv = self.conversacion()
        for direccion, autor in (('entrante', 'bot'), ('entrante', 'vendedora'), ('saliente', 'cliente')):
            with self.subTest(direccion=direccion, autor=autor), self.assertRaises(IntegrityError), \
                    mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                self.Mensaje.sudo().create({'conversacion_id': conv.id, 'id_mensaje': f'x-{autor}',
                                            'direccion': direccion, 'autor': autor, 'texto': 'x'})

    def test_el_historial_no_se_edita(self):
        _, mensaje, _ = self.registrar('Original')
        for usuario in (self.vendedora, self.gerente):
            with self.assertRaises(AccessError):
                mensaje.with_user(usuario).write({'texto': 'Cambiado'})
        self.assertEqual(mensaje.texto, 'Original')

    def test_la_hora_mas_reciente_manda(self):
        conv, _, _ = self.registrar('nuevo', ts=datetime(2026, 10, 9, 16, 0))
        self.registrar('viejo que llega tarde', ts=datetime(2026, 10, 9, 14, 0))
        self.assertEqual(conv.ultima_actividad, datetime(2026, 10, 9, 16, 0))

    def test_cada_mensaje_queda_en_el_chatter_del_cliente(self):
        conv, _, _ = self.registrar('Quiero una cama queen', nombre='Karen')
        self.registrar('Claro, te muestro opciones.', autor='bot')
        notas = conv.partner_id.message_ids.filtered(lambda m: 'Quiero una cama queen' in (m.body or '')
                                                     or 'te muestro opciones' in (m.body or ''))
        self.assertEqual(len(notas), 2)
        cliente = notas.filtered(lambda m: 'Quiero una cama queen' in m.body)
        self.assertIn('WhatsApp (QR) · Cliente', cliente.body)
        self.assertEqual(cliente.author_id, conv.partner_id, 'Se ve como si lo dijera el cliente')
        self.assertEqual(cliente.subtype_id, self.env.ref('mail.mt_note'), 'Nota interna: no avisa a nadie')
        bot = notas - cliente
        self.assertIn('Asistente', bot.body)

    def test_el_texto_del_cliente_va_escapado_en_el_chatter(self):
        conv, _, _ = self.registrar('<script>alert(1)</script> & <b>negrita</b>')
        cuerpos = ' '.join(conv.partner_id.message_ids.mapped('body'))
        self.assertNotIn('<script>', cuerpos)
        self.assertIn('&lt;script&gt;', cuerpos)

    def test_un_adjunto_cae_al_chatter_y_a_la_conversacion(self):
        contenido = base64.b64encode(b'%PDF-1.4 prueba').decode()
        conv, mensaje, _ = self.registrar('Mira', adjuntos=[
            {'tipo': 'documento', 'nombre': 'orden.pdf', 'mime': 'application/pdf', 'url': None,
             'base64': contenido, 'sensible': False}])
        self.assertEqual(mensaje.adjunto_ids.mapped('name'), ['orden.pdf'])
        self.assertEqual(mensaje.adjunto_ids.raw, b'%PDF-1.4 prueba')
        self.assertEqual((mensaje.adjunto_ids.res_model, mensaje.adjunto_ids.res_id), ('dcasa.mensaje', mensaje.id))
        self.assertFalse(mensaje.adjunto_ids.public, 'Un adjunto de un cliente nunca es público')
        self.assertFalse(mensaje.tiene_sensible)
        chatter = conv.partner_id.message_ids.filtered(lambda m: 'Mira' in (m.body or ''))
        self.assertEqual(chatter.attachment_ids.mapped('name'), ['orden.pdf'])

    def test_adjunto_sensible_queda_marcado_para_la_vendedora(self):
        conv, mensaje, _ = self.registrar('Comprobante', adjuntos=[
            {'tipo': 'imagen', 'nombre': 'yappy.jpg', 'mime': 'image/jpeg', 'url': None,
             'base64': base64.b64encode(b'\xff\xd8\xff\xe0jpeg').decode(), 'sensible': True}])
        self.assertTrue(mensaje.tiene_sensible)
        self.assertTrue(mensaje.adjunto_ids.dcasa_sensible)
        chatter = conv.partner_id.message_ids.filtered(lambda m: 'Comprobante' in (m.body or ''))
        self.assertIn('no se le muestra a la IA', chatter.body)

    def test_adjunto_que_no_se_pudo_traer_no_tumba_el_mensaje(self):
        with patch('odoo.addons.dcasa_conversaciones.models.adjuntos.descargar', return_value=None):
            conv, mensaje, creado = self.registrar('Foto', adjuntos=[
                {'tipo': 'imagen', 'nombre': 'x.jpg', 'mime': 'image/jpeg', 'url': 'https://x.test/x.jpg',
                 'base64': None, 'sensible': False}])
        self.assertTrue(creado)
        self.assertEqual(mensaje.adjuntos_fallidos, 1)
        self.assertFalse(mensaje.adjunto_ids)
        self.assertIn('No se pudo traer 1 adjunto', mensaje._burbuja_html(self.ajustes.horario()))

    def test_si_el_worker_repite_el_mensaje_se_reintentan_los_adjuntos_que_fallaron(self):
        datos = self.datos('Foto', adjuntos=[
            {'tipo': 'imagen', 'nombre': 'x.jpg', 'mime': 'image/jpeg', 'url': 'https://x.test/x.jpg',
             'base64': None, 'sensible': False}])
        with patch('odoo.addons.dcasa_conversaciones.models.adjuntos.descargar', return_value=None):
            _, mensaje, _ = self.Conversacion._registrar_mensaje(datos)
        self.assertEqual(mensaje.adjuntos_fallidos, 1)
        with patch('odoo.addons.dcasa_conversaciones.models.adjuntos.descargar', return_value=b'\xff\xd8\xff\xe0jpeg'):
            _, mismo, creado = self.Conversacion._registrar_mensaje(dict(datos))
        self.assertFalse(creado)
        self.assertEqual(mismo, mensaje)
        self.assertEqual(mismo.adjuntos_fallidos, 0)
        self.assertEqual(len(mismo.adjunto_ids), 1)


@tagged('post_install', '-at_install')
class TestQuienContesta(JuanCase):

    def test_el_bot_contesta_por_defecto(self):
        conv = self.conversacion()
        estado = conv._estado_para_worker()
        self.assertTrue(estado['bot_activo'])
        self.assertEqual(estado['estado'], 'bot')
        self.assertIsNone(estado['pausada_hasta'])
        self.assertIn('dentro_de_horario', estado)

    def test_apagado_global_o_por_canal(self):
        conv = self.conversacion()
        self.ajustes.canal_whatsapp_qr = False
        self.assertFalse(conv._estado_para_worker()['bot_activo'])
        self.ajustes.canal_whatsapp_qr = True
        self.ajustes.bot_activo_global = False
        self.assertFalse(conv._estado_para_worker()['bot_activo'])

    def test_un_canal_apagado_por_defecto_no_contesta(self):
        conv = self.conversacion(canal='messenger', id_externo='psid-1')
        self.assertFalse(conv._estado_para_worker()['bot_activo'])

    def test_si_escribe_una_vendedora_desde_el_telefono_el_bot_calla(self):
        conv = self.conversacion()
        self.registrar('Hola, soy Marta, te ayudo', autor='vendedora')
        self.assertEqual(conv.estado, 'humano')
        self.assertTrue(conv.pausada_hasta)
        estado = conv._estado_para_worker()
        self.assertFalse(estado['bot_activo'])
        self.assertEqual(estado['estado'], 'humano')
        self.assertTrue(estado['pausada_hasta'].endswith('Z'))

    def test_cada_mensaje_de_la_vendedora_renueva_la_pausa(self):
        conv = self.conversacion()
        conv.write({'estado': 'humano', 'pausada_hasta': fields.Datetime.now() + timedelta(minutes=10)})
        antes = conv.pausada_hasta
        self.registrar('Sigo aquí', autor='vendedora')
        self.assertGreater(conv.pausada_hasta, antes)

    def test_pausa_sin_limite_se_queda_asi(self):
        conv = self.conversacion()
        conv.write({'estado': 'humano', 'pausada_hasta': False})
        self.registrar('Sigo aquí', autor='vendedora')
        self.assertFalse(conv.pausada_hasta)
        self.assertFalse(conv._controla_bot())

    def test_la_pausa_vencida_devuelve_la_conversacion_al_bot(self):
        conv = self.conversacion()
        conv.write({'estado': 'humano', 'pausada_hasta': fields.Datetime.now() - timedelta(minutes=1)})
        self.assertTrue(conv._controla_bot(), 'Aun sin tocar el estado, el bot ya puede contestar')
        self.assertTrue(conv._estado_para_worker()['bot_activo'])
        conv._normalizar_pausa()
        self.assertEqual(conv.estado, 'bot')
        self.assertFalse(conv.pausada_hasta)

    def test_el_mensaje_del_cliente_con_pausa_vencida_vuelve_a_ser_del_bot(self):
        conv = self.conversacion()
        conv.write({'estado': 'humano', 'pausada_hasta': fields.Datetime.now() - timedelta(minutes=5)})
        self.registrar('¿Sigues ahí?')
        self.assertEqual(conv.estado, 'bot')

    def test_el_cliente_escribe_mientras_atiende_una_vendedora_y_el_bot_sigue_callado(self):
        conv = self.conversacion()
        conv.write({'estado': 'humano', 'pausada_hasta': fields.Datetime.now() + timedelta(hours=1)})
        self.registrar('Gracias')
        self.assertEqual(conv.estado, 'humano')
        self.assertFalse(conv._estado_para_worker()['bot_activo'])

    def test_una_conversacion_cerrada_se_reabre_con_el_cliente(self):
        conv = self.conversacion()
        conv.write({'estado': 'cerrada'})
        self.assertFalse(conv._estado_para_worker()['bot_activo'])
        self.registrar('Hola otra vez')
        self.assertEqual(conv.estado, 'bot')

    def test_sin_conversacion_el_estado_es_el_de_los_ajustes(self):
        estado = self.Conversacion._estado_sin_conversacion('whatsapp_qr')
        self.assertEqual((estado['bot_activo'], estado['estado'], estado['pausada_hasta']), (True, 'bot', None))
        self.assertFalse(self.Conversacion._estado_sin_conversacion('instagram')['bot_activo'])

    def test_dentro_de_horario_segun_la_hora_de_panama(self):
        con_hora = self.Conversacion._estado_sin_conversacion
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 10, 9, 15, 0)):     # 10 a. m. en Panamá
            self.assertTrue(con_hora('whatsapp_qr')['dentro_de_horario'])
        with patch.object(fields.Datetime, 'now', return_value=datetime(2026, 10, 10, 3, 0)):     # 10 p. m. en Panamá
            self.assertFalse(con_hora('whatsapp_qr')['dentro_de_horario'])


@tagged('post_install', '-at_install')
class TestOpcionesNoContactar(JuanCase):

    def test_si_pide_que_no_lo_contacten_se_marca_la_ficha(self):
        conv = self.conversacion()
        self.assertFalse(conv.partner_id.dcasa_no_contactar)
        self.registrar('Por favor no me escribas más')
        self.assertTrue(conv.partner_id.dcasa_no_contactar)
        self.assertTrue(any('no lo contactemos' in (m.body or '') for m in conv.message_ids))

    def test_un_mensaje_normal_no_la_marca(self):
        conv = self.conversacion('¿Tienen camas queen?')
        self.assertFalse(conv.partner_id.dcasa_no_contactar)

    def test_la_marca_vale_para_todas_las_conversaciones_de_la_persona(self):
        wa = self.conversacion(canal='whatsapp_qr', id_externo='50761234567')
        otra = self.conversacion(canal='telegram', id_externo='55', celular='6123-4567')
        self.assertEqual(wa.partner_id, otra.partner_id)
        self.registrar('no me contacten', canal='telegram', id_externo='55')
        self.assertTrue(wa.partner_id.dcasa_no_contactar)
