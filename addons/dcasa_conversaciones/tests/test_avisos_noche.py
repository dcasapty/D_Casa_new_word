"""Avisos de Telegram ordenados (la dueña, 2026-11-13): «son muchos o muy repetidos… a la 1 de la mañana veo vendedoras
activas porque no saben en qué momento llega un cliente». Aprobó tres cambios:

A. De noche nadie recibe clientes ni avisos (con interruptor, encendido de fábrica). Al abrir, cada vendedora recibe un
   solo Telegram por vuelta con su lista; el cliente vuelve con su vendedora de siempre.
B. Solo se avisa de comprobantes de pago de verdad, de cédulas y de archivos que Juan no lee (un PDF); las demás fotos
   se ven en el chat, sin aviso.
E. Todos los textos con la misma forma: emoji y título, quién y por dónde, qué pasó, qué hacer.

Todos los clientes y vendedoras de aquí son inventados.
"""
import importlib.util
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged
from odoo.tools.misc import file_path

from ..models.conversacion import PIE_DE_AVISO
from ..models.conversacion_archivos import FALLOS_SEGUIDOS
from .test_reparto_justo import panama
from .test_reparto_tomar import TomarCase

NOCHE = panama(2026, 10, 9, 23, 0)          # viernes, 11:00 p. m. en Panamá (la tienda abre de 8:00 a 17:00)
MADRUGADA = panama(2026, 10, 10, 1, 30)     # ya venció la pausa de 2 horas del asistente
APERTURA = panama(2026, 10, 10, 8, 0)       # sábado, abre la tienda
COMPROBANTE = {'tipo': 'imagen', 'nombre': 'yappy.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
               'sensible': True, 'clase': 'comprobante'}
CEDULA = {'tipo': 'imagen', 'nombre': 'cedula.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
          'sensible': True, 'clase': 'identidad'}
PDF = {'tipo': 'documento', 'nombre': 'transferencia.pdf', 'mime': 'application/pdf', 'url': None, 'base64': None,
       'sensible': False, 'clase': None}
INSTAGRAM = {'tipo': 'imagen', 'nombre': 'captura.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
             'sensible': False, 'clase': 'publicacion'}
# Una imagen que Juan no leyó (el lector falló o tardó, o era ilegible): llega sin clase.
SIN_LEER = {'tipo': 'imagen', 'nombre': 'IMG_0001.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
            'sensible': False, 'clase': None}
PROHIBIDO = ('!!', 'remate', 'CORRE', 'Fuera del horario laboral', 'Dentro del horario')


class NocheCase(TomarCase):
    """Ana («Vendedora Prueba»), Beto y Carla con el reparto parejo, y el reloj a las 11 de la noche de un viernes con
    «De noche nadie recibe clientes» encendido. Ana, Beto y Gerencia tienen su Telegram vinculado."""

    AHORA = NOCHE

    def setUp(self):
        super().setUp()
        self.ajustes.reparto_nadie_de_noche = True

    def pasar(self, motivo='Quiere el precio de la cama queen'):
        return super().pasar(motivo)

    def mandar(self, conv, adjunto, texto='mira'):
        self.registrar(texto, id_externo=conv.id_externo, nombre=conv.partner_id.name, adjuntos=[adjunto],
                       ts=fields.Datetime.now())

    def textos(self):
        return [c.args[1] for c in self.enviar.call_args_list]

    def avisos_a(self, usuario):
        """``[(texto, botones)]`` de lo que le llegó a ``usuario`` por Telegram."""
        return [(c.args[1], c.kwargs.get('botones')) for c in self.enviar.call_args_list
                if c.args[0] == self.chat_de[usuario]]

    def vence_la_pausa(self):
        """El mantenimiento de cada 5 minutos devuelve al asistente lo que tenía la pausa vencida."""
        with freeze_time(MADRUGADA):
            self.Conversacion.search([('estado', '=', 'humano')])._normalizar_pausa()

    def abrir(self, *activas, minutos=0):
        """Abre la tienda (más ``minutos``): ``activas`` usan Odoo y corre una vuelta del cron del reparto."""
        with freeze_time(APERTURA + timedelta(minutes=minutos)):
            for usuario in activas:
                self.activa(usuario)
            return self.Reparto._cron_reasignar()

    def assertForma(self, texto):
        """La forma de E: un título con su emoji, al menos quién y qué hacer, y la voz de la marca."""
        lineas = texto.split('\n')
        self.assertGreaterEqual(len(lineas), 3, texto)
        self.assertFalse(lineas[0][0].isalnum(), f'El título empieza con su emoji: {texto}')
        self.assertLessEqual(len(lineas[0]), 60, f'Título corto: {texto}')
        for palabra in PROHIBIDO:
            self.assertNotIn(palabra, texto)


@tagged('post_install', '-at_install')
class TestDeNocheNadieRecibe(NocheCase):
    """A, con el interruptor encendido: de noche no se asigna ni se avisa."""

    def test_viene_encendido_y_apagado_avisar_fotos(self):
        defecto = self.env['dcasa.juan.ajustes'].default_get(['reparto_nadie_de_noche', 'avisar_archivos'])
        self.assertEqual(defecto, {'reparto_nadie_de_noche': True, 'avisar_archivos': False})
        campo = self.env['dcasa.juan.ajustes']._fields['reparto_nadie_de_noche']
        self.assertEqual(campo.string, 'De noche nadie recibe clientes')
        self.assertIn('Fuera del horario de la tienda Juan atiende y anota; nadie recibe clientes ni avisos.',
                      campo.help)
        self.assertTrue(campo.tracking)

    def test_la_migracion_lo_enciende_y_apaga_el_aviso_de_fotos(self):
        spec = importlib.util.spec_from_file_location(
            'mig_noche', file_path('dcasa_conversaciones/migrations/19.0.1.5.0/post-migrate.py'))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        self.ajustes.write({'reparto_nadie_de_noche': False, 'avisar_archivos': True, 'avisar_comprobantes': True})
        self.env.flush_all()     # la migración usa SQL directo
        mig.migrate(self.env.cr, '19.0.1.4.0')
        self.ajustes.invalidate_recordset()
        self.assertTrue(self.ajustes.reparto_nadie_de_noche)
        self.assertFalse(self.ajustes.avisar_archivos)
        self.assertTrue(self.ajustes.avisar_comprobantes, 'Lo demás no se toca')

    def test_el_interruptor_esta_en_ajustes_de_juan_junto_al_reparto(self):
        arch = self.env.ref('dcasa_conversaciones.view_dcasa_juan_ajustes_form').arch
        self.assertLess(arch.index('name="reparto_modo"'), arch.index('name="reparto_nadie_de_noche"'))
        self.assertLess(arch.index('name="reparto_nadie_de_noche"'), arch.index('name="reparto_dias_misma_vendedora"'))

    def test_de_noche_no_se_asigna_a_nadie_aunque_haya_alguien_activa(self):
        for modo in ('parejo', 'turnos'):
            with self.subTest(modo=modo):
                self.ajustes.reparto_modo = modo
                self.activa(self.vendedora)
                self.activa(self.beto)
                self.enviar.reset_mock()
                conv = self.pasar()
                respuesta = conv._pasar_a_vendedora('Sigue esperando')
                self.assertFalse(conv.asignada_a, 'De noche nadie recibe clientes')
                self.assertEqual(conv.estado, 'humano')
                self.assertTrue(conv.reparto_desde, 'Queda esperando la apertura como lo entiende el cron')
                self.assertTrue(conv.aviso_de_noche and conv.traspaso_sin_atender_desde)
                self.assertFalse(self.enviar.called, self.textos())
                self.assertFalse(self.Reparto.search_count([('conversacion_id', '=', conv.id)]), 'Nada en el libro')
                self.assertEqual(conv.activity_ids.user_id, self.ajustes.responsable_id, 'La tarea, como siempre')
                self.assertIn('El asistente pasó la conversación a una vendedora. Motivo: Quiere el precio',
                              self.avisos(conv))
                self.assertIn('Llegó con la tienda cerrada: de noche nadie recibe clientes. Se reparte y se avisa '
                              'al abrir.', self.avisos(conv))
                self.assertFalse(respuesta['dentro_de_horario'])
                self.assertIn('Te escribe mañana a primera hora', respuesta['texto_para_el_cliente'],
                              'Lo que Juan le dice al cliente no cambia')

    def test_de_noche_no_se_le_quita_el_cliente_a_quien_lo_tenia(self):
        self.activa(self.vendedora)
        for duena in (self.beto, self.gerente):
            with self.subTest(duena=duena.name):
                self.enviar.reset_mock()
                conv = self.cliente()
                conv.sudo().asignada_a = duena
                conv._pasar_a_vendedora('Pregunta por su pedido')
                self.assertEqual(conv.asignada_a, duena)
                self.assertFalse(self.enviar.called)
                self.assertEqual(conv.activity_ids.user_id, duena)
                self.assertIn(f'Llegó con la tienda cerrada: de noche nadie recibe clientes. Al abrir sigue con '
                              f'{duena.name} si está disponible; si no, se reparte.', self.avisos(conv))

    def test_al_abrir_gerencia_no_se_queda_con_el_cliente_de_la_noche(self):
        """Gerencia no recibe del reparto: de día tampoco se quedaría con él."""
        conv = self.cliente()
        conv.sudo().asignada_a = self.gerente
        conv._pasar_a_vendedora('Duda')
        self.vence_la_pausa()
        self.abrir(self.vendedora)
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertIn('Abrió la tienda: Gerente Prueba no está para recibir a este cliente', self.avisos(conv))

    def test_de_noche_ningun_telegram_por_archivos_ni_por_esperas(self):
        self.ajustes.write({'avisar_archivos': True, 'aviso_espera_solo_horario': False})
        conv = self.cliente()
        self.mandar(conv, COMPROBANTE)
        self.assertEqual(conv.archivo_de_noche, 'comprobante')
        self.mandar(conv, CEDULA)
        self.assertEqual(conv.archivo_de_noche, 'comprobante', 'El comprobante pesa más que la cédula')
        otra = self.cliente()
        self.mandar(otra, PDF)
        self.mandar(otra, INSTAGRAM)
        self.assertEqual(otra.archivo_de_noche, 'documento', 'Una foto no queda para la mañana')
        espera = self.cliente()
        espera._poner_en_humano(usuario=self.vendedora)
        espera.sudo().write({'ultimo_mensaje_cliente': fields.Datetime.now() - timedelta(minutes=30),
                             'ultimo_mensaje_autor': 'cliente'})
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0,
                         'Aunque alguien haya apagado «Avisar solo en horario laboral»')
        self.assertFalse(self.enviar.called, self.textos())

    def test_de_noche_siguen_las_menciones_tomo_a_tu_cliente_y_lo_de_gerencia(self):
        conv = self.cliente()
        nota = self.Mensaje._crear_interno(conv, 'nota', 'Mañana le confirmas la entrega', self.beto)
        self.assertEqual(conv._avisar_mencion(nota, self.vendedora)['telegram'], 1)
        self.assertTrue(self.avisos_a(self.vendedora)[0][0].startswith('💬 Te mencionaron\n'))
        self.activa(self.vendedora)
        suyo = self.de(self.vendedora)
        self.panel(self.beto).tomar(suyo.id, tomar_de=self.vendedora.id)
        self.assertTrue(self.avisos_a(self.vendedora)[-1][0].startswith('👋 Tomaron a tu cliente\n'))
        self.env['ir.config_parameter'].sudo().set_param('dcasa_conversaciones.aviso_cuenta_pendiente_131042', '1')
        self.assertEqual(self.Mensaje._cron_avisos_de_cuenta(), 1)
        (aviso, _botones), = self.avisos_a(self.gerente)
        self.assertTrue(aviso.startswith('⚠️ WhatsApp no está entregando los mensajes\n'), aviso)


@tagged('post_install', '-at_install')
class TestAlAbrir(NocheCase):
    """A, al abrir: un solo Telegram por vendedora y por vuelta, de a pocos y con su vendedora de siempre."""

    def test_cada_vendedora_recibe_un_solo_telegram_con_su_lista(self):
        clientes = []
        for n in range(4):
            conv = self.cliente()
            if n == 0:
                self.mandar(conv, COMPROBANTE, 'te mando el pago')   # lo manda y Juan la pasa
            conv._pasar_a_vendedora(f'Quiere la cama número {n + 1}')
            clientes.append(conv)
        self.vence_la_pausa()
        self.assertEqual({c.estado for c in clientes}, {'bot'}, 'De noche la pausa venció')
        self.assertEqual(self.abrir(self.vendedora, self.beto), 4)
        self.assertEqual({c.estado for c in clientes}, {'humano'}, 'Volvieron al reparto: el asistente calla')
        self.assertEqual(sorted(c.asignada_a.name for c in clientes),
                         ['Beto Vendedor', 'Beto Vendedor', 'Vendedora Prueba', 'Vendedora Prueba'])
        for conv in clientes:
            self.assertEqual(conv.reparto_desde, APERTURA, 'Sus 15 minutos cuentan desde que su vendedora se enteró')
        listas = {}
        for usuario in (self.vendedora, self.beto):
            with self.subTest(usuario=usuario.name):
                (texto, botones), = [(t, b) for t, b in self.avisos_a(usuario) if t.startswith('☀️')]
                listas[usuario] = texto
                suyos = [c for c in clientes if c.asignada_a == usuario]
                self.assertTrue(texto.startswith(f'☀️ Buenos días, {usuario.name.split()[0]}\n'), texto)
                self.assertIn('Te tocan 2 clientes que escribieron de noche:', texto)
                self.assertIn('Toca «Atender» en el que vas a contestar.', texto)
                self.assertNotIn('Conversación n.º', texto, 'Varios clientes: se responde al «Listo» de cada uno')
                self.assertEqual(sorted(b[0]['callback_data'] for b in botones),
                                 sorted(f'juan:t:{c.id}' for c in suyos))
                self.assertTrue(all(b[0]['text'].startswith('Atender ') for b in botones))
                for conv in suyos:
                    self.assertIn(conv.partner_id.name, texto)
        con_pago = clientes[0]
        # El comprobante les llega TAMBIÉN a las de siempre (a quién le llega no cambia), en su propio aviso.
        for usuario in (self.vendedora, self.beto, self.gerente):
            with self.subTest(comprobante_a=usuario.name):
                (pago, botones), = [(t, b) for t, b in self.avisos_a(usuario) if not t.startswith('☀️')]
                self.assertTrue(pago.startswith('💵 Posible comprobante de pago\n'), pago)
                self.assertIn(f'Lo atiende {con_pago.asignada_a.name}.', pago)
                self.assertIn(PIE_DE_AVISO % con_pago.id, pago)
        texto_pago = listas[con_pago.asignada_a]
        renglon = next(r for r in texto_pago.split('\n') if con_pago.partner_id.name in r)
        self.assertIn('Mandó un comprobante de pago: verifícalo en el banco antes de entregar nada.', renglon)
        self.assertIn('Quiere la cama número 1.', renglon)
        self.assertFalse(any(c.aviso_de_noche or c.archivo_de_noche for c in clientes), 'Ya se avisó')
        self.enviar.reset_mock()
        self.assertEqual(self.abrir(minutos=5), 0)
        self.assertFalse(self.enviar.called, 'La vuelta siguiente no repite nada')

    def test_de_a_pocos_y_cada_vuelta_un_solo_aviso(self):
        self.ajustes.reparto_max_esperando = 2
        clientes = [self.pasar(f'Pregunta {n}') for n in range(3)]
        self.vence_la_pausa()
        self.abrir(self.vendedora)
        (texto, botones), = self.avisos_a(self.vendedora)
        self.assertIn('Te tocan 2 clientes', texto)
        self.assertEqual(len(botones), 2)
        tercero = next(c for c in clientes if not c.asignada_a)
        self.assertTrue(tercero.aviso_de_noche, 'Espera su turno sin que nadie reciba un aviso')
        # Ana contesta uno: en la vuelta siguiente le llega el tercero, solo, con el aviso de siempre.
        primero = next(c for c in clientes if c.asignada_a)
        with freeze_time(APERTURA + timedelta(minutes=3)):
            self.panel(self.vendedora).enviar_respuesta(primero.id, 'Hola, ya te ayudo')
        self.abrir(self.vendedora, minutos=5)
        self.assertEqual(tercero.asignada_a, self.vendedora)
        avisos = self.avisos_a(self.vendedora)
        self.assertEqual(len(avisos), 2)
        texto, botones = avisos[-1]
        self.assertTrue(texto.startswith('🟢 Cliente nuevo para ti\n'), texto)
        self.assertIn('Escribió de noche, con la tienda cerrada.', texto)
        self.assertIn('Juan anotó: Pregunta', texto)
        self.assertIn(PIE_DE_AVISO % tercero.id, texto)
        self.assertEqual(botones, [[{'text': 'Atender', 'callback_data': f'juan:t:{tercero.id}'}]])
        self.assertForma(texto.split('\n\n')[0])

    def test_vuelve_con_su_vendedora_de_siempre_aunque_este_llena(self):
        conv = self.cliente()
        with freeze_time(panama(2026, 10, 8, 11, 0)):   # Beto lo atendió anteayer
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv._pasar_a_vendedora('Quiere cambiar el color del sofá')
        self.assertFalse(conv.asignada_a)
        with freeze_time(APERTURA):
            for _n in range(3):   # Beto ya tiene 3 clientes del reparto sin contestar (el tope)
                self.cliente().sudo().write({'estado': 'humano', 'asignada_a': self.beto.id,
                                             'reparto_desde': fields.Datetime.now()})
        self.abrir(self.vendedora, self.beto)
        self.assertEqual(conv.asignada_a, self.beto, 'Su vendedora de siempre, antes que otra')
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertEqual(linea.regla, 'misma')
        self.assertIn('Sigue con Beto Vendedor: ya atendió a este cliente hace 2 días.', self.avisos(conv))
        (texto, _b), = self.avisos_a(self.beto)
        self.assertTrue(texto.startswith('🟢 Volvió un cliente tuyo\n'), texto)
        self.assertIn('Ya lo atendiste antes.', texto)
        self.assertFalse(self.avisos_a(self.vendedora))

    def test_el_cliente_que_ya_era_suyo_le_llega_al_abrir(self):
        conv = self.cliente()
        with freeze_time(NOCHE - timedelta(days=3)):   # Beto lo atendió hace 3 días (dentro de los 14)
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.vence_la_pausa()
        self.abrir(self.vendedora, self.beto)
        self.assertEqual(conv.asignada_a, self.beto)
        (texto, _b), = self.avisos_a(self.beto)
        self.assertTrue(texto.startswith('🟢 Volvió un cliente tuyo\n'), texto)
        self.assertFalse(self.avisos_a(self.vendedora))

    def test_con_el_reparto_apagado_un_solo_aviso_a_las_de_siempre(self):
        self.ajustes.reparto_modo = 'manual'
        primero, segundo = self.pasar('Quiere una cotización'), self.pasar('Pregunta por el envío')
        solo_pago = self.cliente()
        self.mandar(solo_pago, COMPROBANTE)
        self.assertFalse(self.enviar.called)
        self.abrir()
        for usuario in (self.vendedora, self.beto, self.gerente):
            with self.subTest(usuario=usuario.name):
                (texto, botones), = self.avisos_a(usuario)
                self.assertTrue(texto.startswith('☀️ Buenos días\n'), texto)
                self.assertIn('Esto llegó de noche, con la tienda cerrada:', texto)
                self.assertIn(f'{primero.partner_id.name} (WhatsApp) pide una persona: Quiere una cotización.', texto)
                self.assertIn(f'{segundo.partner_id.name} (WhatsApp) pide una persona', texto)
                self.assertIn(f'{solo_pago.partner_id.name} (WhatsApp) mandó un comprobante de pago', texto)
                self.assertEqual(len(botones), 3)
        self.assertFalse(primero.asignada_a, 'Con el reparto apagado nadie se lo queda solo')

    def test_si_al_abrir_no_hay_ninguna_vendedora_se_avisa_una_vez_a_las_de_siempre(self):
        conv = self.pasar('Quiere comprar hoy el comedor')
        self.vence_la_pausa()
        self.abrir()   # nadie usó Odoo todavía: una mañana normal (todavía tienen tiempo de llegar)
        self.assertFalse(self.enviar.called, 'Dentro del plazo para llegar no se avisa a todas')
        self.abrir(minutos=31)   # pasado «Recibe solo quien usó el sistema hace poco» y sigue sin venir nadie
        self.assertFalse(conv.asignada_a)
        for usuario in (self.vendedora, self.beto, self.gerente):
            (texto, _b), = self.avisos_a(usuario)
            self.assertTrue(texto.startswith('🙋 Un cliente pide una persona\n'), texto)
            self.assertIn('Escribió de noche, con la tienda cerrada.', texto)
            self.assertIn('Nadie lo tiene todavía', texto)
        self.assertTrue(conv.reparto_desde and conv.aviso_de_noche, 'Sigue esperando su turno en el reparto')
        self.enviar.reset_mock()
        self.abrir(minutos=36)
        self.assertFalse(self.enviar.called, 'No se repite en cada vuelta')
        self.abrir(self.vendedora, minutos=40)   # llega Ana: el cliente es suyo y le llega su aviso
        self.assertEqual(conv.asignada_a, self.vendedora)
        (texto, _b), = self.avisos_a(self.vendedora)
        self.assertTrue(texto.startswith('🟢 Cliente nuevo para ti\n'), texto)
        self.assertFalse(conv.aviso_de_noche)

    def test_lo_de_la_noche_no_suena_otra_vez_como_cliente_que_espera(self):
        self.ajustes.aviso_espera_minutos = 10
        conv = self.pasar()
        self.registrar('¿Hola?', id_externo=conv.id_externo, ts=fields.Datetime.now())   # escribe otra vez de noche
        self.abrir(self.vendedora)
        self.assertEqual(len(self.avisos_a(self.vendedora)), 1)
        with freeze_time(APERTURA + timedelta(minutes=5)):
            self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 0)

    def test_si_alguien_lo_atiende_antes_de_abrir_no_se_avisa(self):
        conv = self.pasar()
        with freeze_time(panama(2026, 10, 10, 7, 30)):
            self.registrar('Buenos días, ya te atiendo', id_externo=conv.id_externo, autor='vendedora',
                           ts=fields.Datetime.now())
        self.assertFalse(conv.aviso_de_noche)
        self.abrir(self.vendedora)
        self.assertFalse(self.enviar.called)


@tagged('post_install', '-at_install')
class TestConElInterruptorApagado(NocheCase):
    """A, apagado: de noche todo como antes (se asigna y se avisa), con los textos nuevos."""

    def setUp(self):
        super().setUp()
        self.ajustes.reparto_nadie_de_noche = False

    def test_de_noche_se_asigna_y_se_avisa_como_siempre(self):
        self.activa(self.vendedora)
        conv = self.pasar()
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertFalse(conv.aviso_de_noche)
        (texto, botones), = self.avisos_a(self.vendedora)
        self.assertTrue(texto.startswith('🟢 Cliente nuevo para ti\n'), texto)
        self.assertIn('Escribió con la tienda cerrada: Juan le dijo que le escriben mañana a primera hora', texto)
        self.assertEqual(botones, [[{'text': 'Atender', 'callback_data': f'juan:t:{conv.id}'}]])
        self.enviar.reset_mock()
        otra = self.cliente()
        self.mandar(otra, COMPROBANTE)
        (texto,) = self.textos()[:1]
        self.assertTrue(texto.startswith('💵 Posible comprobante de pago\n'), texto)
        self.assertFalse(otra.archivo_de_noche)

    def test_de_noche_avisa_la_espera_si_asi_se_pidio(self):
        self.ajustes.write({'aviso_espera_minutos': 10, 'aviso_espera_solo_horario': False})
        espera = self.cliente()
        espera._poner_en_humano(usuario=self.vendedora)
        espera.sudo().write({'ultimo_mensaje_cliente': fields.Datetime.now() - timedelta(minutes=30),
                             'ultimo_mensaje_autor': 'cliente'})
        self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)

    def test_al_abrir_nada_extra(self):
        self.activa(self.vendedora)
        self.pasar()
        self.enviar.reset_mock()
        self.abrir(self.vendedora)
        self.assertFalse(self.enviar.called)


@tagged('post_install', '-at_install')
class TestSoloComprobantesDeVerdad(NocheCase):
    """B en Odoo, de día: las fotos no avisan; el comprobante, la cédula y el PDF sí."""

    AHORA = panama(2026, 10, 9, 10, 0)

    def setUp(self):
        super().setUp()
        self.ajustes.avisar_archivos = False   # el de fábrica

    def test_una_imagen_que_juan_no_pudo_leer_avisa_como_el_pdf(self):
        conv = self.cliente()
        self.mandar(conv, SIN_LEER, 'listo, ya te hice el Yappy')
        texto = self.textos()[0]
        self.assertTrue(texto.startswith('📎 Mandó una imagen que Juan no pudo leer\n'), texto)
        self.assertIn('mandó por WhatsApp una imagen que Juan no pudo leer: puede ser un comprobante.', texto)
        self.assertIn('Si es un pago, verifícalo en el banco antes de entregar nada.', texto)
        avisados = len(self.textos())
        self.mandar(conv, SIN_LEER, 'otra')
        self.assertEqual(len(self.textos()), avisados, 'A lo más uno cada 10 minutos')

    def test_un_envio_con_varios_archivos_avisa_por_lo_mas_importante(self):
        for adjuntos, titulo in (([PDF, CEDULA], '🪪 Mandó su cédula'), ([SIN_LEER, COMPROBANTE, CEDULA],
                                                                         '💵 Posible comprobante de pago'),
                                 ([INSTAGRAM, SIN_LEER], '📎 Mandó una imagen que Juan no pudo leer')):
            with self.subTest(titulo=titulo):
                self.enviar.reset_mock()
                conv = self.cliente()
                self.registrar('ahí va', id_externo=conv.id_externo, adjuntos=adjuntos, ts=fields.Datetime.now())
                self.assertTrue(self.textos() and all(t.startswith(f'{titulo}\n') for t in self.textos()),
                                self.textos())

    def test_una_foto_de_instagram_no_avisa(self):
        for clase in ('publicacion', 'producto', 'otra'):
            with self.subTest(clase=clase):
                self.mandar(self.cliente(), {**INSTAGRAM, 'clase': clase})
        self.assertFalse(self.enviar.called, self.textos())

    def test_un_pdf_avisa_aunque_las_fotos_esten_apagadas_y_a_lo_mas_cada_10_minutos(self):
        conv = self.cliente()
        self.mandar(conv, PDF, 'ahí va')
        texto = self.textos()[0]
        self.assertTrue(texto.startswith('📎 Mandó un archivo\n'), texto)
        self.assertIn('mandó por WhatsApp un archivo PDF. Juan no puede leerlo: puede ser un comprobante.', texto)
        self.assertIn('Si es un pago, verifícalo en el banco antes de entregar nada.', texto)
        self.assertIn(PIE_DE_AVISO % conv.id, texto)
        avisados = len(self.textos())
        self.mandar(conv, PDF, 'otro')
        self.assertEqual(len(self.textos()), avisados, 'Otro enseguida no avisa')
        conv.sudo().ultimo_aviso_archivo_en = fields.Datetime.now() - timedelta(minutes=11)
        self.mandar(conv, {**PDF, 'mime': 'application/msword', 'nombre': 'datos.doc'}, 'y otro')
        self.assertGreater(len(self.textos()), avisados)
        self.assertIn('mandó por WhatsApp un archivo. Juan no puede leerlo', self.textos()[-1])

    def test_la_cedula_y_el_comprobante_avisan(self):
        self.mandar(self.cliente(), CEDULA)
        self.assertTrue(self.textos()[0].startswith('🪪 Mandó su cédula\n'))
        self.enviar.reset_mock()
        self.mandar(self.cliente(), COMPROBANTE)
        self.assertTrue(self.textos()[0].startswith('💵 Posible comprobante de pago\n'))

    def test_con_avisar_comprobantes_apagado_tampoco_avisa_el_pdf(self):
        self.ajustes.avisar_comprobantes = False
        self.mandar(self.cliente(), PDF)
        self.mandar(self.cliente(), COMPROBANTE)
        self.assertFalse(self.enviar.called)

    def test_la_ayuda_de_los_ajustes_lo_dice(self):
        campos = self.env['dcasa.juan.ajustes']._fields
        self.assertIn('el precio de una publicación no cuenta', campos['avisar_comprobantes'].help)
        self.assertIn('un PDF', campos['avisar_comprobantes'].help)
        self.assertIn('Viene apagado', campos['avisar_archivos'].help)


@tagged('post_install', '-at_install')
class TestImagenesQueJuanNoLeyo(NocheCase):
    """Revisión, segunda vuelta: Juan dice por qué no leyó una imagen («sin_leer»: fallo, ilegible, tope, apagado) y
    Odoo decide si avisa."""

    AHORA = panama(2026, 10, 9, 10, 0)

    def setUp(self):
        super().setUp()
        self.ajustes.avisar_archivos = False   # el de fábrica

    def sin_leer(self, motivo, nombre='IMG.jpg'):
        return {**SIN_LEER, 'nombre': nombre, 'clase': 'sin_leer', 'sin_leer': motivo}

    def test_el_contrato_valida_la_clase_y_el_porque(self):
        from ..models import adjuntos as A
        base = {'tipo': 'imagen', 'url': 'https://x.example/a.jpg'}
        self.assertEqual(A.validar({**base, 'clase': 'sin_leer', 'sin_leer': 'Tope'})['sin_leer'], 'tope')
        self.assertIsNone(A.validar({**base, 'clase': 'sin_leer', 'sin_leer': 'otro'})['sin_leer'])
        self.assertIsNone(A.validar({**base, 'clase': 'algo_nuevo'})['clase'], 'Una clase desconocida cae en None')

    def test_fallo_e_ilegible_avisan_como_ahora_uno_cada_10_minutos(self):
        for motivo in ('fallo', 'ilegible'):
            with self.subTest(motivo=motivo):
                self.enviar.reset_mock()
                conv = self.cliente()
                self.mandar(conv, self.sin_leer(motivo), 'mira')
                self.mandar(conv, self.sin_leer(motivo), 'y esta')
                (texto, _b), = self.avisos_a(self.vendedora)
                self.assertTrue(texto.startswith('📎 Mandó una imagen que Juan no pudo leer\n'), texto)
                with freeze_time(self.AHORA + timedelta(minutes=11)):
                    self.mandar(conv, self.sin_leer(motivo), 'otra')
                self.assertEqual(len(self.avisos_a(self.vendedora)), 2)

    def test_tope_o_apagado_avisan_si_habla_de_pago(self):
        for motivo, texto in (('tope', 'Listo, ya te hice el YAPPY'), ('apagado', 'te mandé la transferencia'),
                              ('tope', 'ahí va el depósito'), ('apagado', 'es el abono de la cama')):
            with self.subTest(motivo=motivo, texto=texto):
                self.enviar.reset_mock()
                conv = self.cliente()
                conv.sudo().ultimo_aviso_sin_leer_en = fields.Datetime.now()   # ya gastó el aviso del día
                self.mandar(conv, self.sin_leer(motivo), texto)
                self.assertEqual(len(self.avisos_a(self.vendedora)), 1, texto)

    def test_el_pago_puede_estar_en_un_mensaje_anterior(self):
        conv = self.cliente()
        conv.sudo().ultimo_aviso_sin_leer_en = fields.Datetime.now()
        self.registrar('Ya pagué, te mando la captura', id_externo=conv.id_externo, ts=fields.Datetime.now())
        self.mandar(conv, self.sin_leer('tope'), '')
        self.assertEqual(len(self.avisos_a(self.vendedora)), 1)

    def test_tope_o_apagado_sin_hablar_de_pago_un_aviso_por_conversacion_al_dia(self):
        conv = self.cliente()
        for minutos in (0, 15, 60, 23 * 60):
            with freeze_time(self.AHORA + timedelta(minutes=minutos)):
                self.mandar(conv, self.sin_leer('tope', f'ig{minutos}.jpg'), '¿y esta la tienen?')
        self.assertEqual(len(self.avisos_a(self.vendedora)), 1)
        with freeze_time(self.AHORA + timedelta(hours=24, minutes=1)):
            self.mandar(conv, self.sin_leer('tope', 'otra.jpg'), '¿y esta?')
        self.assertEqual(len(self.avisos_a(self.vendedora)), 2, 'Al día siguiente, otro')

    def test_una_imagen_sin_clase_ni_porque_es_un_fallo(self):
        conv = self.cliente()
        self.mandar(conv, SIN_LEER, '¿y esta?')
        (texto, _b), = self.avisos_a(self.vendedora)
        self.assertTrue(texto.startswith('📎 Mandó una imagen que Juan no pudo leer\n'), texto)
        mensaje = conv.mensaje_ids.filtered(lambda m: m.autor == 'cliente').sorted('id')[-1]
        self.assertEqual(mensaje.imagen_sin_leer, 'fallo')

    def test_gerencia_sabe_una_vez_al_dia_si_el_lector_esta_apagado(self):
        for n in range(3):
            self.mandar(self.cliente(), self.sin_leer('apagado'), f'mira {n}')
        del_lector = [t for t, _b in self.avisos_a(self.gerente) if t.startswith('⚠️ Para Gerencia: Juan no está')]
        self.assertEqual(len(del_lector), 1)
        self.assertIn('El lector de imágenes de Juan está apagado', del_lector[0])
        self.assertFalse([t for t, _b in self.avisos_a(self.vendedora) if 'Para Gerencia' in t])
        with freeze_time(self.AHORA + timedelta(days=1)):
            self.mandar(self.cliente(), self.sin_leer('apagado'), 'mira')
        self.assertEqual(len([t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo' in t]), 2)

    def test_gerencia_sabe_si_el_lector_falla_seguido(self):
        for n in range(FALLOS_SEGUIDOS - 1):
            self.mandar(self.cliente(), self.sin_leer('fallo'), f'mira {n}')
        self.assertFalse([t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo' in t],
                         'Un fallo suelto no es una alarma')
        with freeze_time(self.AHORA + timedelta(minutes=30)):
            self.mandar(self.cliente(), self.sin_leer('fallo'), 'una más')
        del_lector = [t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo' in t]
        self.assertEqual(len(del_lector), 1)
        self.assertIn(f'no pudo leer las fotos de {FALLOS_SEGUIDOS} mensajes de clientes', del_lector[0])
        self.assertForma(del_lector[0])

    def test_tope_no_alerta_a_gerencia(self):
        for n in range(5):
            self.mandar(self.cliente(), self.sin_leer('tope'), f'mira {n}')
        self.assertFalse([t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo' in t])

    def test_de_noche_tope_sin_pago_queda_para_la_manana(self):
        with freeze_time(NOCHE):
            conv = self.cliente()
            self.mandar(conv, self.sin_leer('tope'), '¿y esta?')
            self.assertEqual(conv.archivo_de_noche, 'documento')
            self.assertFalse(self.enviar.called)


@tagged('post_install', '-at_install')
class TestTextosClaros(NocheCase):
    """E: todos los avisos de Juan con la misma forma."""

    AHORA = panama(2026, 10, 9, 10, 0)

    def test_cada_aviso_tiene_la_misma_forma(self):
        conv = self.cliente()
        conv.sudo().asignada_a = self.vendedora
        textos = {
            'traspaso': conv._texto_traspaso('quiere el precio de la cama queen', False, para_ella=True),
            'traspaso urgente': conv._texto_traspaso('Está molesto', True, para_ella=False),
            'traspaso de siempre': conv._texto_traspaso('Volvió', False, para_ella=True, misma=True),
            'sin nadie': conv._texto_traspaso('Duda', False, para_ella=False, sin_nadie=True),
            'espera': conv._texto_espera(15, para_quien_lo_tiene=True),
            'espera a todas': conv._texto_espera(130, para_quien_lo_tiene=False),
            'mención': conv._texto_mencion('Beto Vendedor', 'Ojo con este cliente'),
            'pasó a otra': self.Reparto._texto_de_reasignada(conv, self.beto, 'reasignada', 15),
            'nadie lo tenía': self.Reparto._texto_de_reasignada(conv, self.env['res.users'], 'reasignada', 15),
            'Gerencia': self.Reparto._texto_para_gerencia(conv, self.beto, self.vendedora, 15),
        }
        for que in ('comprobante', 'identidad', 'documento', 'foto'):
            textos[que] = conv._texto_archivo(que, PDF)
        textos['imagen sin leer'] = conv._texto_archivo('documento', SIN_LEER)
        textos['de noche, sin saber cuál'] = conv._texto_archivo('documento', de_noche=True)
        for nombre, texto in textos.items():
            with self.subTest(nombre):
                self.assertForma(texto)
        self.assertEqual(textos['traspaso'].split('\n'), [
            '🟢 Cliente nuevo para ti', f'{conv.partner_id.name} te escribe por WhatsApp.',
            'Juan anotó: quiere el precio de la cama queen.', 'Toca «Atender» para contestarle.'])
        self.assertTrue(textos['traspaso urgente'].startswith('🔴 URGENTE: un cliente pide una persona\n'))
        self.assertIn('Lo tiene Vendedora Prueba.', textos['traspaso urgente'])
        self.assertIn('lleva 2 horas sin respuesta', textos['espera a todas'])
        self.assertIn('Lo atiende Vendedora Prueba.', textos['espera a todas'])
        self.assertTrue(textos['pasó a otra'].startswith('🔁 Te pasaron un cliente\n'))
        self.assertIn('Beto Vendedor no le contestó en 15 minutos: ahora es tuyo.', textos['pasó a otra'])
        self.assertTrue(textos['Gerencia'].startswith('🔁 Para Gerencia: un cliente cambió de vendedora\n'))
        self.assertIn('«Ojo con este cliente»', textos['mención'])

    def test_los_avisos_de_un_dia_cualquiera_tienen_la_forma(self):
        """Los que salen de verdad por Telegram (sin el pie para responder)."""
        self.activa(self.vendedora)
        conv = self.pasar()
        self.mandar(self.cliente(), COMPROBANTE)
        self.mandar(self.cliente(), PDF)
        self.mandar(self.cliente(), CEDULA)
        nota = self.Mensaje._crear_interno(conv, 'nota', 'Ojo', self.beto)
        conv._avisar_mencion(nota, self.vendedora)
        with freeze_time(self.AHORA + timedelta(minutes=16)):   # Ana no le contestó: pasa a Beto y se avisa a Gerencia
            self.activa(self.beto)
            self.Reparto._cron_reasignar()
        self.assertEqual(conv.asignada_a, self.beto)
        textos = self.textos()
        self.assertGreaterEqual(len(textos), 8)
        for texto in textos:
            with self.subTest(texto=texto[:40]):
                self.assertForma(texto.split('\n\n')[0])
        self.assertTrue(any(t.startswith('🔁 Para Gerencia: un cliente cambió de vendedora') for t in textos))
