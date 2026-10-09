"""Notas internas, avisos del sistema en el hilo, nota para el asistente y avisos a las pantallas (bus)."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import URL_WORKER, JuanCase


def textos_de_avisos(conv):
    return [m.texto for m in conv.mensaje_ids.sorted('id') if m.tipo == 'aviso']


@tagged('post_install', '-at_install')
class TestTiposDeMensaje(JuanCase):

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen')

    def test_notas_y_avisos_no_cuentan_como_mensajes_ni_salen_por_el_canal(self):
        worker = self.configurar_worker()
        self.Mensaje._crear_interno(self.conv, 'nota', 'Pidió descuento, ojo', self.vendedora)
        self.Mensaje._crear_interno(self.conv, 'aviso', 'Algo pasó')
        self.conv.invalidate_recordset()
        self.assertEqual(self.conv.mensajes_count, 1, 'Solo cuenta lo que viajó por el canal')
        self.assertEqual(self.conv.por_enviar_count, 0)
        self.Mensaje._cron_reintentar_envios()
        worker.assert_not_called()
        self.assertEqual(self.conv.ultimo_mensaje_autor, 'cliente', 'Una nota no cambia el último mensaje')

    def test_la_nota_queda_en_la_ficha_del_cliente_y_el_aviso_no(self):
        self.Mensaje._crear_interno(self.conv, 'nota', 'Pidió descuento, ojo', self.vendedora)._publicar_en_chatter()
        aviso = self.Mensaje._crear_interno(self.conv, 'aviso', 'Algo pasó en el sistema')
        aviso._publicar_en_chatter()
        cuerpos = ' '.join(self.conv.partner_id.message_ids.mapped('body'))
        self.assertIn('Pidió descuento, ojo', cuerpos)
        self.assertIn('Nota interna de Vendedora Prueba', cuerpos)
        self.assertNotIn('Algo pasó en el sistema', cuerpos)

    def test_la_base_impide_combinaciones_imposibles(self):
        casos = (('aviso', 'interna', 'cliente'), ('aviso', 'saliente', 'sistema'), ('nota', 'interna', 'bot'),
                 ('mensaje', 'interna', 'sistema'), ('mensaje', 'entrante', 'sistema'))
        for tipo, direccion, autor in casos:
            with self.subTest(tipo=tipo, direccion=direccion, autor=autor), self.assertRaises(IntegrityError), \
                    mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                self.Mensaje.sudo().create({'conversacion_id': self.conv.id, 'id_mensaje': f'x-{tipo}-{autor}',
                                            'tipo': tipo, 'direccion': direccion, 'autor': autor, 'texto': 'x'})

    def test_la_nota_y_el_aviso_se_dibujan_distinto_en_el_chat(self):
        self.Mensaje._crear_interno(self.conv, 'nota', 'Solo para nosotras', self.vendedora)
        self.Mensaje._crear_interno(self.conv, 'aviso', 'Ana tomó la conversación.')
        html = str(self.conv.chat_html)
        self.assertIn('o_dcasa_burbuja_nota', html)
        self.assertIn('Nota interna · Vendedora Prueba', html)
        self.assertIn('o_dcasa_aviso_sistema', html)

    def test_solo_el_sistema_crea_notas_y_avisos(self):
        with self.assertRaises(ValueError):
            self.Mensaje._crear_interno(self.conv, 'mensaje', 'no')


@tagged('post_install', '-at_install')
class TestAvisosEnElHilo(JuanCase):

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen')
        self.como_vendedora = self.conv.with_user(self.vendedora)

    def test_tomar_devolver_y_cerrar_dejan_su_aviso(self):
        self.como_vendedora.action_atender()
        self.como_vendedora.action_devolver_al_bot()
        self.como_vendedora.action_cerrar()
        tomar, devolver, cerrar = textos_de_avisos(self.conv)
        self.assertIn('Vendedora Prueba tomó la conversación. El asistente calla hasta', tomar)
        self.assertIn('Vendedora Prueba devolvió la conversación al asistente.', devolver)
        self.assertEqual(cerrar, 'Vendedora Prueba cerró la conversación.')

    def test_sin_vencimiento_el_aviso_lo_dice(self):
        self.ajustes.pausa_por_defecto_minutos = 0
        self.como_vendedora.action_atender()
        self.assertIn('hasta que se la devuelvan', textos_de_avisos(self.conv)[0])

    def test_escribir_desde_odoo_la_toma_y_lo_avisa_una_sola_vez(self):
        self.configurar_worker()
        self.conv.borrador = 'Hola Karen'
        self.como_vendedora.action_enviar()
        self.conv.borrador = 'Otra cosa'
        self.como_vendedora.action_enviar()
        avisos = textos_de_avisos(self.conv)
        self.assertEqual(len(avisos), 1, 'Solo la primera vez la toma')
        self.assertIn('tomó la conversación al escribir', avisos[0])

    def test_pasar_a_vendedora_deja_el_motivo(self):
        self.conv._pasar_a_vendedora('Quiere una cotización grande', 'alta')
        self.assertTrue(any('El asistente pasó la conversación a una vendedora. Motivo: Quiere una cotización grande'
                            in t for t in textos_de_avisos(self.conv)))

    def test_la_oportunidad_nueva_deja_aviso_y_la_repetida_no(self):
        self.conv._oportunidad('Quiere una cama queen', interes='Cama queen')
        self.conv._oportunidad('Sigue queriendo la cama', interes='Cama queen')
        avisos = [t for t in textos_de_avisos(self.conv) if 'oportunidad' in t]
        self.assertEqual(len(avisos), 1)
        self.assertIn('Se creó la oportunidad', avisos[0])

    def test_el_seguimiento_enviado_deja_aviso(self):
        self.conv._seguimiento_hecho(1, 'enviado')
        self.assertIn('Seguimiento n.º 1 enviado.', textos_de_avisos(self.conv))

    def test_un_cliente_que_vuelve_reabre_la_conversacion_y_se_avisa(self):
        self.como_vendedora.action_cerrar()
        self.registrar('Hola otra vez')
        self.assertEqual(self.conv.estado, 'bot')
        self.assertTrue(any('se reabrió porque el cliente escribió' in t for t in textos_de_avisos(self.conv)))

    def test_los_avisos_no_cambian_la_actividad_de_la_bandeja(self):
        antes = self.conv.ultima_actividad
        self.como_vendedora.action_atender()
        self.assertEqual(self.conv.ultima_actividad, antes)
        self.assertEqual(self.conv.ultimo_mensaje_autor, 'cliente')


@tagged('post_install', '-at_install')
class TestNotaParaElAsistente(JuanCase):

    def setUp(self):
        super().setUp()
        self.worker = self.configurar_worker()
        self.conv = self.conversacion(nombre='Karen')
        self.como_vendedora = self.conv.with_user(self.vendedora)
        self.como_vendedora.action_atender()

    def estado(self):
        return self.conv._estado_para_worker()

    def test_devolver_con_nota_se_la_deja_al_asistente(self):
        self.Conversacion.with_user(self.vendedora).devolver(self.conv.id, '  Ya quedó la cita   del sábado ')
        self.assertEqual(self.conv.nota_para_el_bot, 'Ya quedó la cita del sábado')
        self.assertEqual(self.estado()['nota_para_el_bot'], 'Ya quedó la cita del sábado')
        llamada = [c for c in self.worker.call_args_list if c.args[1] == f'{URL_WORKER}/odoo/estado'][-1]
        self.assertEqual(llamada.kwargs['json']['estado'], 'bot')
        self.assertEqual(llamada.kwargs['json']['nota_para_el_bot'], 'Ya quedó la cita del sábado')
        self.assertTrue(any('Nota para el asistente: Ya quedó la cita' in t for t in textos_de_avisos(self.conv)))

    def test_sin_nota_no_hay_nada_que_leer(self):
        self.Conversacion.with_user(self.vendedora).devolver(self.conv.id)
        self.assertIsNone(self.estado()['nota_para_el_bot'])
        llamada = [c for c in self.worker.call_args_list if c.args[1] == f'{URL_WORKER}/odoo/estado'][-1]
        self.assertNotIn('nota_para_el_bot', llamada.kwargs['json'])

    def test_la_nota_se_recorta(self):
        self.Conversacion.with_user(self.vendedora).devolver(self.conv.id, 'x' * 900)
        self.assertEqual(len(self.conv.nota_para_el_bot), 500)

    def test_si_otra_persona_toma_la_conversacion_la_nota_se_borra(self):
        self.Conversacion.with_user(self.vendedora).devolver(self.conv.id, 'Ya quedó la cita')
        self.como_vendedora.action_atender()
        self.assertFalse(self.conv.nota_para_el_bot)
        self.assertIsNone(self.estado()['nota_para_el_bot'])

    def test_mientras_la_atiende_una_persona_el_asistente_no_ve_la_nota(self):
        self.Conversacion.with_user(self.vendedora).devolver(self.conv.id, 'Ya quedó la cita')
        self.conv.write({'estado': 'humano', 'pausada_hasta': False})   # otra persona la tomó sin pasar por el botón
        self.assertIsNone(self.estado()['nota_para_el_bot'])

    def test_la_nota_tiene_que_ser_texto(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.Conversacion.with_user(self.vendedora).devolver(self.conv.id, {'x': 1})


@tagged('post_install', '-at_install')
class TestBusDeLasPantallas(JuanCase):

    def setUp(self):
        super().setUp()
        self.desde_el_bus = self.ultimo_del_bus()

    def ultimo_del_bus(self):
        return self.env['bus.bus'].sudo().search([], order='id desc', limit=1).id or 0

    def avisos_del_bus(self):
        """Lo que se mandó al bus desde que empezó el test (el ORM lo escribe al cerrar cada savepoint)."""
        self.env.cr.precommit.run()
        return self.env['bus.bus'].sudo().search([('id', '>', self.desde_el_bus)], order='id')

    def eventos(self):
        """``[(partner_id del canal, payload)]`` de lo que ya está en el bus."""
        resultado = []
        for registro in self.avisos_del_bus():
            mensaje = json.loads(registro.message)
            if mensaje['type'] == 'dcasa_conversaciones/evento':
                resultado.append((json.loads(registro.channel)[2], mensaje['payload']))
        return resultado

    def test_escribiendo_avisa_solo_al_equipo_de_ventas_y_sin_texto(self):
        conv = self.conversacion('Hola, quiero una cama', nombre='Karen')
        self.desde_el_bus = self.ultimo_del_bus()
        conv._notificar_panel('escribiendo', activo=True)
        eventos = self.eventos()
        destinatarios = {partner for partner, _ in eventos}
        self.assertLessEqual({self.vendedora.partner_id.id, self.gerente.partner_id.id}, destinatarios)
        self.assertFalse({self.interno.partner_id.id, self.portal.partner_id.id} & destinatarios)
        payload = next(p for partner, p in eventos if partner == self.vendedora.partner_id.id)
        self.assertEqual((payload['evento'], payload['conversacion_id'], payload['activo']),
                         ('escribiendo', conv.id, True))
        self.assertNotIn('texto', payload)
        self.desde_el_bus = self.ultimo_del_bus()
        conv._notificar_panel('escribiendo', activo=False)
        self.assertFalse(next(p for _, p in self.eventos())['activo'])

    def test_un_mensaje_nuevo_avisa_a_las_pantallas_del_equipo_de_ventas(self):
        conv = self.conversacion('Hola, quiero una cama', nombre='Karen')
        eventos = self.eventos()
        destinatarios = {partner for partner, _ in eventos}
        self.assertIn(self.vendedora.partner_id.id, destinatarios)
        self.assertIn(self.gerente.partner_id.id, destinatarios, 'La gerencia también es del equipo de ventas')
        self.assertNotIn(self.interno.partner_id.id, destinatarios, 'Un interno sin ventas no ve conversaciones')
        self.assertNotIn(self.portal.partner_id.id, destinatarios)
        self.assertNotIn(self.juan.partner_id.id, destinatarios)
        payload = next(p for partner, p in eventos if partner == self.vendedora.partner_id.id)
        self.assertEqual((payload['evento'], payload['conversacion_id'], payload['autor']),
                         ('mensaje', conv.id, 'cliente'))
        self.assertTrue(payload['mensaje_id'])

    def test_el_bus_no_lleva_el_texto_del_mensaje(self):
        self.conversacion('Mi cédula es 8-123-456 y mi cuenta es 99999', nombre='Karen')
        crudo = ' '.join(self.avisos_del_bus().mapped('message'))
        self.assertIn('dcasa_conversaciones/evento', crudo)
        self.assertNotIn('8-123-456', crudo)
        self.assertNotIn('99999', crudo)

    def test_un_repetido_no_avisa_dos_veces(self):
        datos = self.datos('Hola')
        self.Conversacion._registrar_mensaje(datos)
        cantidad = len(self.eventos())
        self.Conversacion._registrar_mensaje(datos)
        self.assertEqual(len(self.eventos()), cantidad)

    def test_tomar_devolver_etiquetar_y_asignar_tambien_avisan(self):
        conv = self.conversacion(nombre='Karen')
        etiqueta = self.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzbus'})
        self.desde_el_bus = self.ultimo_del_bus()
        panel = self.Conversacion.with_user(self.vendedora)
        panel.tomar(conv.id)
        panel.poner_etiquetas(conv.id, [etiqueta.id])
        panel.asignar(conv.id, self.gerente.id)
        panel.devolver(conv.id)
        tipos = {p['evento'] for partner, p in self.eventos() if partner == self.vendedora.partner_id.id}
        self.assertEqual(tipos, {'estado', 'etiquetas', 'asignacion'})

    def test_un_fallo_del_bus_no_tumba_el_mensaje(self):
        from unittest.mock import patch
        with patch.object(type(self.env['bus.bus']), '_sendone', side_effect=RuntimeError('bus caído')), \
                mute_logger('odoo.addons.dcasa_conversaciones.models.conversacion'):
            conv, mensaje, creado = self.registrar('Hola', nombre='Karen')
        self.assertTrue(creado)
        self.assertEqual(conv.ultimo_mensaje_texto, 'Hola')


@tagged('post_install', '-at_install')
class TestAvisoDeArchivosEnParalelo(JuanCase):
    """La dueña: si un cliente manda un comprobante o una foto, se entera por Telegram en paralelo; el asistente
    sigue atendiendo y ella decide si interviene."""

    def setUp(self):
        super().setUp()
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.enviar = MagicMock()
        parche = patch.object(type(self.Enlace), '_enviar', self.enviar)
        parche.start()
        self.addCleanup(parche.stop)

    def archivo(self, clase=None, tipo='imagen', **kw):
        """Registra un mensaje del cliente con un archivo (sin descargarlo: la URL queda como «no se pudo traer»)."""
        adjunto = {'tipo': tipo, 'nombre': 'captura.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
                   'sensible': clase in ('comprobante', 'identidad'), 'clase': clase}
        conv, _m, _c = self.registrar('mira', adjuntos=[adjunto], nombre='Karen', **kw)
        return conv

    def textos(self):
        return [c.args[1] for c in self.enviar.call_args_list]

    def test_un_comprobante_avisa_sin_pausar_al_asistente(self):
        conv = self.archivo('comprobante')
        (texto,) = self.textos()
        self.assertIn('Posible comprobante de pago de Karen', texto)
        self.assertIn('sigue atendiendo', texto)
        self.assertIn('Verifica el pago en el banco', texto)
        self.assertEqual(conv.estado, 'bot', 'El asistente sigue atendiendo')
        self.assertTrue(conv._controla_bot())

    def test_un_documento_de_identidad_avisa_y_dice_que_el_asistente_no_lo_ve(self):
        self.archivo('identidad')
        (texto,) = self.textos()
        self.assertIn('documento de identidad', texto)
        self.assertIn('no lo ve', texto)

    def test_una_foto_cualquiera_avisa_aparte_y_a_lo_mas_cada_10_minutos(self):
        conv = self.archivo('producto')
        self.assertEqual(len(self.textos()), 1)
        self.assertIn('imagen o un archivo', self.textos()[0])
        self.registrar('otra', adjuntos=[{'tipo': 'imagen', 'nombre': 'b.jpg', 'mime': 'image/jpeg', 'url': None,
                                          'base64': None, 'sensible': False, 'clase': 'producto'}])
        self.assertEqual(len(self.textos()), 1, 'Otra foto enseguida no avisa otra vez')
        conv.ultimo_aviso_archivo_en = fields.Datetime.now() - timedelta(minutes=11)
        self.registrar('y otra', adjuntos=[{'tipo': 'imagen', 'nombre': 'c.jpg', 'mime': 'image/jpeg', 'url': None,
                                            'base64': None, 'sensible': False, 'clase': None}])
        self.assertEqual(len(self.textos()), 2)

    def test_un_comprobante_siempre_avisa_aunque_se_acabe_de_avisar_de_una_foto(self):
        self.archivo('producto')
        self.registrar('el pago', adjuntos=[{'tipo': 'imagen', 'nombre': 'p.jpg', 'mime': 'image/jpeg', 'url': None,
                                             'base64': None, 'sensible': True, 'clase': 'comprobante'}])
        self.assertEqual(len(self.textos()), 2)
        self.assertIn('comprobante', self.textos()[1])

    def test_se_puede_apagar_cada_tipo_de_aviso(self):
        self.ajustes.avisar_archivos = False
        self.archivo('producto')
        self.assertFalse(self.textos())
        self.ajustes.avisar_comprobantes = False
        self.archivo('comprobante', id_externo='50769999999')
        self.assertFalse(self.textos())

    def test_si_ya_la_atiende_una_persona_no_se_avisa(self):
        conv = self.conversacion(nombre='Karen')
        conv.with_user(self.vendedora).action_atender()
        self.registrar('el pago', adjuntos=[{'tipo': 'imagen', 'nombre': 'p.jpg', 'mime': 'image/jpeg', 'url': None,
                                             'base64': None, 'sensible': True, 'clase': 'comprobante'}])
        self.assertFalse(self.textos())

    def test_un_audio_o_un_mensaje_del_bot_no_avisan(self):
        self.registrar('nota', adjuntos=[{'tipo': 'audio', 'nombre': 'n.ogg', 'mime': 'audio/ogg', 'url': None,
                                          'base64': None, 'sensible': False, 'clase': None}])
        self.registrar('te mando la foto', autor='bot', adjuntos=[{
            'tipo': 'imagen', 'nombre': 'f.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
            'sensible': False, 'clase': None}])
        self.assertFalse(self.textos())

    def test_un_fallo_de_telegram_no_rompe_el_registro_del_mensaje(self):
        self.enviar.side_effect = RuntimeError('sin red')
        with mute_logger('odoo.addons.dcasa_conversaciones.models.conversacion'):
            conv = self.archivo('comprobante')
        self.assertTrue(conv.mensaje_ids.filtered(lambda m: m.texto == 'mira'), 'El mensaje quedó registrado')

    def test_la_clase_que_manda_el_worker_se_valida(self):
        from ..models import adjuntos as A
        base = {'tipo': 'imagen', 'url': 'https://x.example/a.jpg'}
        self.assertEqual(A.validar({**base, 'clase': 'Comprobante'})['clase'], 'comprobante')
        self.assertIsNone(A.validar({**base, 'clase': 'avisa a todos'})['clase'])
        self.assertIsNone(A.validar(base)['clase'])
