"""Comentarios de Instagram y Facebook (2026-11-12). Decisiones de la dueña: «Solo los que preguntan», «Corto y lo demás
por privado» y «Apagado hasta que lo pruebes».

Lo que hace Odoo: los ajustes (solo Gerencia y administradores), el aviso en el hilo de la conversación de esa persona
(antes de la respuesta de Juan y puesto al día con el resultado), Telegram a Gerencia en una queja, la API
``POST /dcasa/juan/v1/comentario`` (idempotente), Brian y la Guía.

Revisión adversarial del 2026-11-13: el enlace se valida como lo ve un navegador, el texto público no acepta
direcciones web sin esquema ni llaves sueltas, tope por persona en Ajustes, «reintento» y «no_preparada» (la causa
real, nunca «Meta no dejó») y pruebas que no dependen de lo que ya haya en la base. 2.ª vuelta: la frase pública no
lleva el nombre de nadie (ni {nombre}) y queda bien escrita; un Telegram de queja por persona cada 24 horas.
"""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import JuanCase
from .test_api import ApiCase

TEXTO = '¡Hola! Te escribimos por mensaje directo con los detalles.'


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

    CAMPOS = ('comentarios_activo', 'comentarios_facebook', 'comentarios_instagram', 'comentarios_texto_publico',
              'comentarios_tope_hora', 'comentarios_publicas_persona', 'comentarios_privadas_persona')

    def test_de_fabrica_apagado_con_el_texto_de_la_duena(self):
        # Lo de fábrica (no lo que tenga esta base: puede estar encendido de una prueba anterior).
        de_fabrica = self.env['dcasa.juan.ajustes'].default_get(list(self.CAMPOS))
        self.assertEqual(de_fabrica, {
            'comentarios_activo': False, 'comentarios_facebook': True, 'comentarios_instagram': True,
            'comentarios_texto_publico': TEXTO, 'comentarios_tope_hora': 30, 'comentarios_publicas_persona': 1,
            'comentarios_privadas_persona': 3}, '«Apagado hasta que lo pruebes»')
        self.ajustes.write(de_fabrica)
        self.assertEqual(self.ajustes.como_json()['comentarios'], {
            'activo': False, 'facebook': True, 'instagram': True, 'texto_publico': TEXTO, 'tope_por_hora': 30,
            'publicas_por_persona': 1, 'privadas_por_persona': 3})

    def test_el_worker_recibe_lo_que_cambia_gerencia(self):
        self.ajustes.with_user(self.gerente).write({
            'comentarios_activo': True, 'comentarios_facebook': False, 'comentarios_instagram': True,
            'comentarios_tope_hora': 10, 'comentarios_publicas_persona': 0, 'comentarios_privadas_persona': 5,
            'comentarios_texto_publico': 'Gracias: te escribimos por privado.'})
        self.assertEqual(self.ajustes.como_json()['comentarios'], {
            'activo': True, 'facebook': False, 'instagram': True,
            'texto_publico': 'Gracias: te escribimos por privado.', 'tope_por_hora': 10,
            'publicas_por_persona': 0, 'privadas_por_persona': 5})

    def test_solo_gerencia_y_administradores_los_cambian(self):
        self.ajustes.with_user(self.gerente).comentarios_activo = True
        administrador = new_test_user(self.env, login='juan_admin_comentarios', name='Admin Prueba',
                                      groups='base.group_user,base.group_system,dcasa_base.group_gerencia')
        self.ajustes.with_user(administrador).comentarios_tope_hora = 12
        self.assertEqual(self.ajustes.with_user(self.vendedora).comentarios_tope_hora, 12)   # leer, sí
        for campo, valor in (('comentarios_activo', False), ('comentarios_texto_publico', 'Hola'),
                             ('comentarios_tope_hora', 99), ('comentarios_publicas_persona', 2),
                             ('comentarios_privadas_persona', 2)):
            with self.subTest(campo), self.assertRaises(AccessError):
                self.ajustes.with_user(self.vendedora).write({campo: valor})

    def test_validaciones_del_texto_y_el_tope(self):
        for valores in ({'comentarios_texto_publico': '   '}, {'comentarios_texto_publico': 'x' * 301},
                        {'comentarios_texto_publico': 'Hola {cliente}, te escribimos.'},
                        {'comentarios_texto_publico': 'Mira https://dcasapty.com'},
                        {'comentarios_tope_hora': -1}, {'comentarios_tope_hora': 201},
                        {'comentarios_publicas_persona': -1}, {'comentarios_publicas_persona': 11},
                        {'comentarios_privadas_persona': 0}, {'comentarios_privadas_persona': 11}):
            with self.subTest(valores), self.assertRaises(ValidationError):
                self.ajustes.write(valores)
        self.ajustes.write({'comentarios_texto_publico': 'Hola, te escribimos', 'comentarios_tope_hora': 0,
                            'comentarios_publicas_persona': 0, 'comentarios_privadas_persona': 10})

    def test_el_texto_publico_no_acepta_direcciones_sin_esquema_ni_llaves_sueltas(self):
        # Revisión adversarial (pasaban): un dominio sin «https://» o un correo también es un enlace; una llave
        # suelta, un error.
        for texto in ('¡Hola, {nombre}! Mira dcasapty.com/ofertas', 'Escríbenos: bit.ly/dcasa {nombre}',
                      'Escríbenos a info@dcasapty.com', 'wa.me/50760261919', 'Visita www.dcasapty', '{nombre',
                      'Hola {nombre}} te escribimos', 'Hola nombre} y {'):
            with self.subTest(texto), self.assertRaises(ValidationError):
                self.ajustes.with_user(self.gerente).write({'comentarios_texto_publico': texto})
        # Lo que sí vale: puntos de fin de frase, cifras y signos.
        for texto in (TEXTO, '¡Gracias! Te escribimos al privado. Abrimos 8:00-17:00.',
                      'Te escribimos. ¡Gracias!', '¿Te interesa? Te escribimos por privado.'):
            with self.subTest(texto):
                self.ajustes.with_user(self.gerente).write({'comentarios_texto_publico': texto})
                self.assertEqual(self.ajustes.comentarios_texto_publico, texto)

    def test_la_frase_publica_no_lleva_el_nombre_de_nadie_y_queda_bien_escrita(self):
        # 2.ª vuelta de la revisión (pasaban): con {nombre} quitado, estas quedaban «: te escribimos…» o «¡! …».
        for texto in ('¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.',
                      '{nombre}: te escribimos por mensaje directo.', '¡{nombre}! Te escribimos por mensaje directo.',
                      ': te escribimos por privado', '¡! Te escribimos', '¡Hola! ¿?', '!!', '...', '¡A!'):
            with self.subTest(texto), self.assertRaises(ValidationError):
                self.ajustes.with_user(self.gerente).write({'comentarios_texto_publico': texto})

    def test_un_texto_de_antes_con_nombre_le_llega_al_worker_sin_el(self):
        # Guardado antes de la regla (sin pasar por la validación): el Worker lo recibe limpio.
        self.env.cr.execute("UPDATE dcasa_juan_ajustes SET comentarios_texto_publico = %s WHERE id = %s",
                            ['¡{nombre}, gracias! Te escribimos por privado.', self.ajustes.id])
        self.ajustes.invalidate_recordset(['comentarios_texto_publico'])
        self.assertEqual(self.ajustes.como_json()['comentarios']['texto_publico'],
                         '¡Gracias! Te escribimos por privado.')

    def test_la_migracion_quita_el_nombre_de_la_frase_guardada(self):
        ruta = Path(__file__).resolve().parent.parent / 'migrations' / '19.0.1.4.0' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('dcasa_migracion_1_4_0', ruta)
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        for antes, despues in (('¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.', TEXTO),
                               ('{nombre}: te escribimos por mensaje directo.', 'Te escribimos por mensaje directo.'),
                               ('{nombre}', TEXTO), ('Hola, te escribimos', 'Hola, te escribimos')):
            with self.subTest(antes):
                self.env.cr.execute("UPDATE dcasa_juan_ajustes SET comentarios_texto_publico = %s WHERE id = %s",
                                    [antes, self.ajustes.id])
                migracion.migrate(self.env.cr, '19.0.1.3.0')
                self.ajustes.invalidate_recordset(['comentarios_texto_publico'])
                self.assertEqual(self.ajustes.comentarios_texto_publico, despues)

    def test_los_cambios_quedan_en_el_historial(self):
        self.ajustes.comentarios_activo = True
        self.env.cr.precommit.run()
        campos = self.ajustes.message_ids.tracking_value_ids.field_id.mapped('field_description')
        self.assertIn('Responder comentarios', campos)

    def test_el_grupo_esta_en_la_pantalla_de_ajustes(self):
        arco = self.env.ref('dcasa_conversaciones.view_dcasa_juan_ajustes_form').arch
        self.assertIn('Comentarios de Instagram y Facebook', arco)
        for campo in self.CAMPOS:
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
        self.assertEqual(self.Comentario.sudo().search_count([('id_comentario', '=', '18100000000000002')]), 1)
        self.assertEqual(len(self.avisos(comentario.conversacion_id)), 1)
        self.assertIn('tope de Ajustes de Juan', comentario.aviso_id.texto)

    def test_cada_resultado_dicho_en_palabras(self):
        casos = {
            ('respondida', 'fallo', '(#200) Permissions error'):
                'en público no salió ((#200) Permissions error)',
            ('respondida', 'no', None): 'Juan le respondió por privado; en público no.',
            ('respondida', 'no', 'tope por persona: ya se le respondió en público una vez en 24 horas'):
                'en público no (tope por persona: ya se le respondió en público una vez en 24 horas).',
            ('fallo', 'no', '(#10900) Activity already replied to'): 'Meta no dejó responderle por privado',
            ('no_preparada', 'no', 'la IA no respondió (overloaded)'):
                'Juan no pudo prepararle la respuesta (la IA no respondió (overloaded)), ni en los reintentos',
            ('incierta', 'no', None): 'no se sabe si le llegó',
            ('vendedora', 'no', None): 'una persona del equipo atiende esta conversación',
            ('no', 'no', 'se apagó «Responder comentarios»'): 'No se le respondió (se apagó «Responder comentarios»).',
            ('no', 'no', 'tope por persona: ya se le respondieron 3 comentarios por privado en 24 horas'):
                'No se le respondió (tope por persona',
        }
        for i, ((privada, publica, motivo), esperado) in enumerate(casos.items()):
            with self.subTest(privada=privada, publica=publica, motivo=motivo):
                comentario, _que = self.Comentario._registrar(datos(
                    id_comentario=f'1810000000000010{i}', privada=privada, publica=publica, motivo=motivo))
                self.assertIn(esperado, comentario.aviso_id.texto)
                if privada != 'fallo':
                    self.assertNotIn('Meta no dejó', comentario.aviso_id.texto, 'la causa real, no Meta')

    def test_si_la_ia_falla_dice_reintento_y_despues_el_resultado_en_el_mismo_aviso(self):
        comentario, _que = self.Comentario._registrar(datos(id_comentario='r1'))
        aviso = comentario.aviso_id
        comentario, que = self.Comentario._registrar(datos(id_comentario='r1', privada='reintento',
                                                           motivo='la IA no respondió (overloaded)'))
        self.assertEqual(que, 'actualizado')
        self.assertIn('todavía no pudo prepararle la respuesta (la IA no respondió (overloaded)) y lo vuelve a '
                      'intentar', aviso.texto)
        # El mismo «reintento» otra vez no cambia nada; uno con otra causa, sí; un «pendiente» tardío no lo regresa.
        self.assertEqual(self.Comentario._registrar(datos(id_comentario='r1', privada='reintento',
                                                          motivo='la IA no respondió (overloaded)'))[1], 'repetido')
        otra_causa = 'Odoo no le dio a Juan el catálogo ni los precios'
        self.assertEqual(self.Comentario._registrar(datos(id_comentario='r1', privada='reintento',
                                                          motivo=otra_causa))[1], 'actualizado')
        self.assertEqual(self.Comentario._registrar(datos(id_comentario='r1'))[1], 'repetido')
        self.assertEqual(comentario.privada, 'reintento')
        comentario, que = self.Comentario._registrar(datos(id_comentario='r1', privada='respondida',
                                                           publica='respondida'))
        self.assertEqual(que, 'actualizado')
        self.assertEqual(comentario.aviso_id, aviso)
        self.assertIn('Juan le respondió en público y por privado.', aviso.texto)

    def test_una_queja_no_se_responde_y_avisa_a_gerencia_por_telegram(self):
        comentario, _que = self.Comentario._registrar(datos(
            red='facebook', canal='messenger', id_externo='2838000000000001', nombre='Ana María López',
            id_comentario='777_888', texto='Estafadores, pagué y nunca llegó', clase='queja', privada='no',
            publica='no', enlace='https://www.facebook.com/dcasapty/posts/pfbid0abc'))
        self.assertEqual(comentario.aviso_id.texto, 'Queja en un comentario de Facebook: "Estafadores, pagué y nunca '
                                                    'llegó" · no se respondió. Se avisó a Gerencia.')
        self.assertEqual(len(self.telegram), 1)
        texto, usuarios, acciones = self.telegram[0]
        self.assertTrue(texto.startswith('📣 Para Gerencia: una queja en un comentario\n'), texto)
        self.assertIn('Ana María López se quejó en un comentario de Facebook: "Estafadores, pagué y nunca llegó". '
                      'Juan no la respondió.', texto)
        self.assertIn('Contéstale tú o pídeselo a alguien', texto)
        self.assertIn('https://www.facebook.com/dcasapty/posts/pfbid0abc', texto)
        self.assertIn(self.gerente, usuarios, 'a Gerencia')
        self.assertNotIn(self.vendedora, usuarios)
        self.assertFalse(acciones, 'sin «Atender»: por mensaje no se le puede escribir a quien solo comentó')
        # Repetida, no avisa otra vez.
        self.Comentario._registrar(datos(red='facebook', canal='messenger', id_externo='2838000000000001',
                                         id_comentario='777_888', texto='x', clase='queja', privada='no', publica='no'))
        self.assertEqual(len(self.telegram), 1)

    def test_un_solo_telegram_de_queja_por_persona_cada_24_horas(self):
        # 2.ª vuelta de la revisión (pasaba): 15 quejas de la misma persona = 15 Telegram a Gerencia.
        for i in range(15):
            comentario, _que = self.Comentario._registrar(datos(
                id_externo='17841400000000999', nombre='@troll', id_comentario=f'q{i}', texto=f'Estafadores {i}',
                clase='queja', privada='no', publica='no'))
            self.assertIn('Se avisó a Gerencia' if i == 0 else 'Gerencia ya recibió hoy un aviso',
                          comentario.aviso_id.texto)
        self.assertEqual(len(self.telegram), 1)
        self.assertEqual(self.Comentario.sudo().search_count([('conversacion_id', '=', comentario.conversacion_id.id),
                                                              ('clase', '=', 'queja')]), 15, 'todas en el hilo')
        # Otra persona sí avisa; y pasadas 24 horas, la misma también.
        self.Comentario._registrar(datos(id_externo='17841400000000888', id_comentario='otra', clase='queja',
                                         privada='no', publica='no'))
        self.assertEqual(len(self.telegram), 2)
        self.env.cr.execute("UPDATE dcasa_comentario SET create_date = create_date - interval '25 hours' "
                            "WHERE conversacion_id = %s", [comentario.conversacion_id.id])
        self.Comentario._registrar(datos(id_externo='17841400000000999', id_comentario='q-manana', clase='queja',
                                         privada='no', publica='no'))
        self.assertEqual(len(self.telegram), 3)

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
        claves = ('preguntas_respondidas', 'preguntas_sin_respuesta_de_juan', 'preguntas_en_curso',
                  'quejas_avisadas_a_gerencia', 'sin_clasificar')

        def cuentas():
            respuesta = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
                'resumen_de_conversaciones', {'periodo': '7_dias'})
            self.assertTrue(respuesta['ok'], respuesta)
            return respuesta['datos']['comentarios']
        antes = cuentas()   # lo que ya haya en la base (la prueba cuenta lo que suma)
        ahora = fields.Datetime.now() - timedelta(minutes=5)
        self.Comentario._registrar(datos(ts=ahora, id_comentario='b1', privada='respondida', publica='respondida'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='b2', privada='fallo', publica='no'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='b5', privada='no_preparada', publica='no'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='b6', privada='reintento'))
        self.Comentario._registrar(datos(ts=ahora, id_comentario='b3', clase='queja', privada='no', publica='no'))
        self.Comentario._registrar(datos(ts=ahora - timedelta(days=40), id_comentario='b4', clase='queja',
                                         privada='no', publica='no'))
        despues = cuentas()
        self.assertEqual(tuple(despues[k] - antes[k] for k in claves), (1, 2, 1, 1, 0))
        self.assertIn('Responder comentarios', despues['como_se_cuenta'])

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
        antes = self.env['dcasa.comentario'].sudo().search_count([])
        for extra in malos:
            with self.subTest(extra):
                self.assertEqual(self.post('comentario', self.cuerpo(**extra)).status_code, 400)
        self.assertEqual(self.env['dcasa.comentario'].sudo().search_count([]), antes, 'ninguno se guardó')

    def test_un_enlace_que_no_es_de_meta_se_descarta(self):
        for i, enlace in enumerate(('https://evil.example/p', 'http://www.instagram.com/p/x', 'javascript:alert(1)',
                                    'https://instagram.com.evil.example/x',
                                    # Revisión adversarial (pasaban): urlsplit ve facebook.com; el navegador,
                                    # evil.example.
                                    'https://evil.example\\@www.facebook.com/x', 'https://evil.example\\.facebook.com/x',
                                    'https://evil.example@www.facebook.com/x', 'https://www.facebook.com:8443/x',
                                    'https://www.facebook.com/x\tz')):
            with self.subTest(enlace):
                r = self.post('comentario', self.cuerpo(id_comentario=f'c{i}', enlace=enlace))
                self.assertEqual(r.status_code, 200, r.text)
                comentario = self.env['dcasa.comentario'].sudo().browse(r.json()['comentario_id'])
                self.assertFalse(comentario.enlace)
                self.assertFalse(comentario.aviso_id.enlace)
        r = self.post('comentario', self.cuerpo(id_comentario='bueno', enlace='https://m.facebook.com/dcasapty/posts/1'))
        self.assertEqual(self.env['dcasa.comentario'].sudo().browse(r.json()['comentario_id']).enlace,
                         'https://m.facebook.com/dcasapty/posts/1')

    def test_reintento_y_no_preparada_entran_por_la_api(self):
        self.assertEqual(self.post('comentario', self.cuerpo(id_comentario='api1')).status_code, 200)
        r = self.post('comentario', self.cuerpo(id_comentario='api1', privada='reintento',
                                                 motivo='la IA no respondió (overloaded)'))
        self.assertFalse(r.json()['repetido'])
        r = self.post('comentario', self.cuerpo(id_comentario='api1', privada='no_preparada', publica='no',
                                                 motivo='la IA no respondió (overloaded)'))
        self.assertFalse(r.json()['repetido'])
        comentario = self.env['dcasa.comentario'].sudo().browse(r.json()['comentario_id'])
        self.assertEqual(comentario.privada, 'no_preparada')
        self.assertIn('Juan no pudo prepararle la respuesta', comentario.aviso_id.texto)

    def test_sin_token_no_entra(self):
        self.assertEqual(self.post('comentario', self.cuerpo(), token='otro-token-de-prueba-0123456789').status_code,
                         401)
        self.assertEqual(self.post('comentario', self.cuerpo(), token=None).status_code, 401)

    def test_ni_la_vendedora_ni_gerencia_editan_el_comentario_ni_su_aviso(self):
        r = self.post('comentario', self.cuerpo(id_comentario='z1'))
        comentario = self.env['dcasa.comentario'].sudo().browse(r.json()['comentario_id'])
        for login in ('vendedora_api_c', 'gerente_api_c'):
            grupos = 'base.group_user,sales_team.group_sale_salesman' if login.startswith('v') else \
                'base.group_user,sales_team.group_sale_manager'
            usuario = new_test_user(self.env, login=login, groups=grupos)
            with self.subTest(login), self.assertRaises(AccessError):
                comentario.with_user(usuario).with_context(dcasa_mensaje_sistema=True).write({'privada': 'respondida'})
            with self.subTest(login), self.assertRaises(AccessError):
                comentario.with_user(usuario).unlink()
            with self.subTest(login), self.assertRaises(AccessError):
                comentario.aviso_id.with_user(usuario).with_context(dcasa_mensaje_sistema=True).write(
                    {'enlace': 'javascript:alert(1)'})
