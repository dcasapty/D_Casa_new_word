"""Comentarios de Instagram y Facebook (2026-11-12). Decisiones de la dueña: «Solo los que preguntan», «Corto y lo demás
por privado» y «Apagado hasta que lo pruebes».

Lo que hace Odoo: los ajustes (solo Gerencia y administradores), el aviso en el hilo de la conversación de esa persona
(antes de la respuesta de Juan y puesto al día con el resultado), Telegram a Gerencia en una queja, la API
``POST /dcasa/juan/v1/comentario`` (idempotente), Brian y la Guía.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import JuanCase
from .test_api import ApiCase

TEXTO = '¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.'


def datos(**extra):
    base = {
        'canal': 'instagram', 'id_externo': '17841400000000777', 'nombre': '@ana.muebles', 'red': 'instagram',
        'id_comentario': '18100000000000002', 'texto': '¿Cuánto cuesta el sofá?',
        'enlace': 'https://www.instagram.com/p/C0d1g0/', 'ts': datetime(2026, 11, 12, 15, 0), 'clase': 'pregunta',
        'privada': 'pendiente', 'publica': 'pendiente', 'motivo': None,
    }
    base.update(extra)
    return base


@tagged('post_install', '-at_install')
class TestAjustesDeComentarios(JuanCase):

    def test_de_fabrica_apagado_con_el_texto_de_la_duena(self):
        a = self.ajustes
        self.assertFalse(a.comentarios_activo, '«Apagado hasta que lo pruebes»')
        self.assertTrue(a.comentarios_facebook and a.comentarios_instagram)
        self.assertEqual(a.comentarios_texto_publico, TEXTO)
        self.assertEqual(a.comentarios_tope_hora, 30)
        self.assertEqual(a.como_json()['comentarios'], {
            'activo': False, 'facebook': True, 'instagram': True,
            'texto_publico': TEXTO, 'tope_por_hora': 30})

    def test_el_worker_recibe_lo_que_cambia_gerencia(self):
        self.ajustes.with_user(self.gerente).write({
            'comentarios_activo': True, 'comentarios_facebook': False, 'comentarios_tope_hora': 10,
            'comentarios_texto_publico': 'Gracias, {nombre}: te escribimos por privado.'})
        self.assertEqual(self.ajustes.como_json()['comentarios'], {
            'activo': True, 'facebook': False, 'instagram': True,
            'texto_publico': 'Gracias, {nombre}: te escribimos por privado.', 'tope_por_hora': 10})

    def test_solo_gerencia_y_administradores_los_cambian(self):
        self.ajustes.with_user(self.gerente).comentarios_activo = True
        administrador = new_test_user(self.env, login='juan_admin_comentarios', name='Admin Prueba',
                                      groups='base.group_user,base.group_system,dcasa_base.group_gerencia')
        self.ajustes.with_user(administrador).comentarios_tope_hora = 12
        self.assertEqual(self.ajustes.with_user(self.vendedora).comentarios_tope_hora, 12)   # leer, sí
        for campo, valor in (('comentarios_activo', False), ('comentarios_texto_publico', 'Hola'),
                             ('comentarios_tope_hora', 99)):
            with self.subTest(campo), self.assertRaises(AccessError):
                self.ajustes.with_user(self.vendedora).write({campo: valor})

    def test_validaciones_del_texto_y_el_tope(self):
        for valores in ({'comentarios_texto_publico': '   '}, {'comentarios_texto_publico': 'x' * 301},
                        {'comentarios_texto_publico': 'Hola {cliente}, te escribimos.'},
                        {'comentarios_texto_publico': 'Mira https://dcasapty.com'},
                        {'comentarios_tope_hora': -1}, {'comentarios_tope_hora': 201}):
            with self.subTest(valores), self.assertRaises(ValidationError):
                self.ajustes.write(valores)
        self.ajustes.write({'comentarios_texto_publico': 'Hola {nombre}', 'comentarios_tope_hora': 0})

    def test_los_cambios_quedan_en_el_historial(self):
        self.ajustes.comentarios_activo = True
        self.env.cr.precommit.run()
        campos = self.ajustes.message_ids.tracking_value_ids.field_id.mapped('field_description')
        self.assertIn('Responder comentarios', campos)

    def test_el_grupo_esta_en_la_pantalla_de_ajustes(self):
        arco = self.env.ref('dcasa_conversaciones.view_dcasa_juan_ajustes_form').arch
        self.assertIn('Comentarios de Instagram y Facebook', arco)
        for campo in ('comentarios_activo', 'comentarios_instagram', 'comentarios_facebook',
                      'comentarios_texto_publico', 'comentarios_tope_hora'):
            self.assertIn(f'name="{campo}"', arco)


@tagged('post_install', '-at_install')
class TestAvisosDeComentarios(JuanCase):

    def setUp(self):
        super().setUp()
        self.Comentario = self.env['dcasa.comentario']
        self.telegram = []
        parche = patch.object(type(self.Conversacion), '_avisar_por_telegram',
                              lambda conv, texto, usuarios=None, acciones=False: self.telegram.append(
                                  (texto, usuarios, acciones)) or 1)
        parche.start()
        self.addCleanup(parche.stop)

    def avisos(self, conv):
        return self.Mensaje.sudo().search([('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')])

    def test_una_pregunta_deja_el_aviso_antes_de_la_respuesta_y_despues_el_resultado(self):
        comentario, que = self.Comentario._registrar(datos())
        self.assertEqual(que, 'creado')
        conv = comentario.conversacion_id
        self.assertEqual((conv.canal, conv.id_externo), ('instagram', '17841400000000777'))
        self.assertEqual(conv.partner_id.name, '@ana.muebles')
        aviso = comentario.aviso_id
        self.assertEqual(aviso.texto, 'Comentó en una publicación de Instagram: "¿Cuánto cuesta el sofá?" · Juan le '
                                      'está respondiendo.')
        self.assertEqual(aviso.enlace, 'https://www.instagram.com/p/C0d1g0/')
        # La respuesta privada de Juan llega como un mensaje normal, DESPUÉS del aviso.
        _conv, respuesta, _c = self.Conversacion._registrar_mensaje({
            'canal': 'instagram', 'id_externo': '17841400000000777', 'id_mensaje': 'aWdfZ.priv.1',
            'direccion': 'saliente', 'autor': 'bot', 'texto': 'Te escribo por tu comentario…',
            'ts': fields.Datetime.now()})
        comentario, que = self.Comentario._registrar(datos(privada='respondida', publica='respondida'))
        self.assertEqual(que, 'actualizado')
        self.assertEqual(self.avisos(conv), aviso, 'el mismo aviso, puesto al día: no uno nuevo')
        self.assertEqual(aviso.texto, 'Comentó en una publicación de Instagram: "¿Cuánto cuesta el sofá?" · Juan le '
                                      'respondió en público y por privado.')
        hilo = self.env['dcasa.conversacion'].with_user(self.vendedora).hilo(conv.id)['mensajes']
        self.assertEqual([m['tipo'] for m in hilo], ['aviso', 'mensaje'])
        self.assertEqual(hilo[0]['enlace'], 'https://www.instagram.com/p/C0d1g0/')
        self.assertEqual(hilo[1]['id'], respuesta.id)
        self.assertFalse(self.telegram, 'una pregunta no avisa a Gerencia')

    def test_el_comentario_no_es_un_mensaje_del_cliente(self):
        comentario, _que = self.Comentario._registrar(datos())
        conv = comentario.conversacion_id
        self.assertFalse(conv.ultimo_mensaje_cliente, 'no abre la ventana de 24 h ni cuenta como «el cliente escribió»')
        self.assertFalse(self.Mensaje.sudo().search_count(
            [('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje')]))
        self.assertTrue(conv.ultima_actividad, 'sí sube en la lista de Conversaciones')

    def test_un_resultado_final_no_se_pisa_y_se_repite_sin_duplicar(self):
        self.Comentario._registrar(datos(privada='respondida', publica='tope'))
        comentario, que = self.Comentario._registrar(datos(privada='fallo', publica='no', motivo='otro'))
        self.assertEqual(que, 'repetido')
        self.assertEqual((comentario.privada, comentario.publica), ('respondida', 'tope'))
        self.assertEqual(self.Comentario.sudo().search_count([]), 1)
        self.assertEqual(len(self.avisos(comentario.conversacion_id)), 1)
        self.assertIn('tope de Ajustes de Juan', comentario.aviso_id.texto)

    def test_cada_resultado_dicho_en_palabras(self):
        casos = {
            ('respondida', 'fallo', '(#200) Permissions error'):
                'en público Meta no lo dejó ((#200) Permissions error)',
            ('respondida', 'no', None): 'Juan le respondió por privado.',
            ('fallo', 'no', '(#10900) Activity already replied to'): 'Meta no dejó responderle por privado',
            ('incierta', 'no', None): 'no se sabe si le llegó',
            ('vendedora', 'no', None): 'una persona del equipo atiende esta conversación',
        }
        for i, ((privada, publica, motivo), esperado) in enumerate(casos.items()):
            with self.subTest(privada=privada, publica=publica):
                comentario, _que = self.Comentario._registrar(datos(
                    id_comentario=f'1810000000000010{i}', privada=privada, publica=publica, motivo=motivo))
                self.assertIn(esperado, comentario.aviso_id.texto)

    def test_una_queja_no_se_responde_y_avisa_a_gerencia_por_telegram(self):
        comentario, _que = self.Comentario._registrar(datos(
            red='facebook', canal='messenger', id_externo='2838000000000001', nombre='Ana María López',
            id_comentario='777_888', texto='Estafadores, pagué y nunca llegó', clase='queja', privada='no',
            publica='no', enlace='https://www.facebook.com/dcasapty/posts/pfbid0abc'))
        self.assertEqual(comentario.aviso_id.texto, 'Queja en un comentario de Facebook: "Estafadores, pagué y nunca '
                                                    'llegó" · no se respondió. Se avisó a Gerencia.')
        self.assertEqual(len(self.telegram), 1)
        texto, usuarios, acciones = self.telegram[0]
        self.assertIn('Para Gerencia: queja en un comentario de Facebook de Ana María López', texto)
        self.assertIn('https://www.facebook.com/dcasapty/posts/pfbid0abc', texto)
        self.assertIn(self.gerente, usuarios, 'a Gerencia')
        self.assertNotIn(self.vendedora, usuarios)
        self.assertFalse(acciones, 'sin «Atender»: por mensaje no se le puede escribir a quien solo comentó')
        # Repetida, no avisa otra vez.
        self.Comentario._registrar(datos(red='facebook', canal='messenger', id_externo='2838000000000001',
                                         id_comentario='777_888', texto='x', clase='queja', privada='no', publica='no'))
        self.assertEqual(len(self.telegram), 1)

    def test_si_a_nadie_de_gerencia_le_llega_va_a_los_avisos_de_siempre(self):
        self.telegram_llamadas = []

        def telegram(conv, texto, usuarios=None, acciones=False):
            self.telegram_llamadas.append(usuarios)
            return 0 if usuarios else 1
        with patch.object(type(self.Conversacion), '_avisar_por_telegram', telegram):
            self.Comentario._registrar(datos(clase='queja', privada='no', publica='no'))
        self.assertEqual(len(self.telegram_llamadas), 2)
        self.assertIsNone(self.telegram_llamadas[1])

    def test_sin_clasificar_lo_dice_para_que_alguien_lo_mire(self):
        comentario, _que = self.Comentario._registrar(datos(clase='sin_clasificar', privada='no', publica='no'))
        self.assertIn('Juan no pudo saber si era una pregunta (falló la IA)', comentario.aviso_id.texto)
        self.assertFalse(self.telegram)

    def test_el_registro_no_se_edita_y_se_borra_con_la_conversacion(self):
        comentario, _que = self.Comentario._registrar(datos())
        with self.assertRaises(AccessError):
            comentario.with_user(self.gerente).write({'texto': 'otro'})
        with self.assertRaises(AccessError):
            self.Comentario.with_user(self.vendedora).create({
                'conversacion_id': comentario.conversacion_id.id, 'red': 'instagram', 'id_comentario': 'x',
                'ts': fields.Datetime.now(), 'clase': 'queja', 'privada': 'no', 'publica': 'no'})
        comentario.conversacion_id.unlink()
        self.assertFalse(comentario.exists(), 'Ley 81: se borra con la conversación')

    def test_brian_cuenta_comentarios_atendidos_y_quejas(self):
        ahora = fields.Datetime.now() - timedelta(minutes=5)
        self.Comentario._registrar(datos(ts=ahora, privada='respondida', publica='respondida'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='2', privada='fallo', publica='no'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='3', clase='queja', privada='no', publica='no'))
        self.Comentario._registrar(datos(ts=ahora - timedelta(days=40), id_comentario='4', clase='queja',
                                         privada='no', publica='no'))
        respuesta = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
            'resumen_de_conversaciones', {'periodo': '7_dias'})
        self.assertTrue(respuesta['ok'], respuesta)
        comentarios = respuesta['datos']['comentarios']
        self.assertEqual((comentarios['preguntas_respondidas'], comentarios['preguntas_sin_respuesta_de_juan'],
                          comentarios['quejas_avisadas_a_gerencia'], comentarios['sin_clasificar']), (1, 1, 1, 0))
        self.assertIn('Responder comentarios', comentarios['como_se_cuenta'])

    def test_la_guia_explica_donde_se_enciende(self):
        try:
            from odoo.addons.dcasa_guia.models import guia as G
        except ImportError:
            self.skipTest('dcasa_guia no está en esta instalación')
        tarea = next(t for t in G.cargar_catalogo()['tareas'] if t['id'] == 'juan-comentarios')
        self.assertEqual(tarea['titulo'], 'Que Juan responda los comentarios de Instagram y Facebook')
        self.assertEqual(tarea['destino']['menu'], 'dcasa_conversaciones.menu_dcasa_juan_ajustes')
        self.assertIn('Responder comentarios', tarea['nota'])
        self.assertIn('quejas', tarea['nota'].lower())


@tagged('post_install', '-at_install')
class TestApiComentario(ApiCase):

    def cuerpo(self, **extra):
        base = {
            'canal': 'instagram', 'id_externo': '17841400000000777', 'nombre': '@ana.muebles', 'red': 'instagram',
            'id_comentario': '18100000000000002', 'texto': '¿Cuánto cuesta?', 'ts': H.a_iso(self.hace_una_hora),
            'enlace': 'https://www.instagram.com/p/C0d1g0/', 'clase': 'pregunta', 'privada': 'pendiente',
            'publica': 'pendiente'}
        base.update(extra)
        return {k: v for k, v in base.items() if v is not None}

    def test_registra_y_es_idempotente(self):
        r = self.post('comentario', self.cuerpo())
        self.assertEqual(r.status_code, 200, r.text)
        datos_r = r.json()
        conv = self.conversacion('17841400000000777', 'instagram')
        self.assertEqual(datos_r, {'ok': True, 'conversacion_id': conv.id, 'comentario_id': datos_r['comentario_id'],
                                   'repetido': False})
        otra_vez = self.post('comentario', self.cuerpo()).json()
        self.assertEqual((otra_vez['repetido'], otra_vez['conversacion_id']), (True, conv.id), 'sin cambio')
        final = self.post('comentario', self.cuerpo(privada='respondida', publica='tope')).json()
        self.assertFalse(final['repetido'])
        self.assertTrue(self.post('comentario', self.cuerpo(privada='fallo', publica='no')).json()['repetido'])
        comentario = self.env['dcasa.comentario'].sudo().browse(datos_r['comentario_id'])
        self.assertEqual((comentario.privada, comentario.publica), ('respondida', 'tope'))

    def test_valida_cada_campo(self):
        malos = [
            {'red': 'tiktok'}, {'canal': 'messenger'}, {'canal': 'whatsapp_cloud', 'red': 'facebook'},
            {'id_comentario': 'a b'}, {'id_comentario': None}, {'texto': '   '}, {'clase': 'otro'},
            {'privada': 'si'}, {'publica': 'tal vez'}, {'ts': 'ayer'}, {'id_externo': 'x y'},
        ]
        for extra in malos:
            with self.subTest(extra):
                self.assertEqual(self.post('comentario', self.cuerpo(**extra)).status_code, 400)
        self.assertFalse(self.env['dcasa.comentario'].sudo().search_count([]))

    def test_un_enlace_que_no_es_de_meta_se_descarta(self):
        for enlace in ('https://evil.example/p', 'http://www.instagram.com/p/x', 'javascript:alert(1)',
                       'https://instagram.com.evil.example/x'):
            with self.subTest(enlace):
                r = self.post('comentario', self.cuerpo(id_comentario=f'c{len(enlace)}', enlace=enlace)).json()
                self.assertFalse(self.env['dcasa.comentario'].sudo().browse(r['comentario_id']).enlace)

    def test_sin_token_no_entra(self):
        self.assertEqual(self.post('comentario', self.cuerpo(), token='otro-token-de-prueba-0123456789').status_code,
                         401)
