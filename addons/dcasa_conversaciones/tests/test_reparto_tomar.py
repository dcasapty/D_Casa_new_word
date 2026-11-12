"""Reparto justo (aprobado por la dueña el 2026-11-12): quién se queda con el cliente.

1. Una vendedora no le quita a otra vendedora que está trabajando el cliente que atiende sin confirmarlo (el servidor lo
   exige: ``tomar_de_otra``), y cuando un cliente cambia de mano entre vendedoras queda dicho en el hilo, en el libro
   (regla ``tomada``) y, si la otra estaba activa, le llega un aviso por Telegram. Si no estaba, se toma sin preguntar.
   «Solamente es para las vendedoras» (aclaración de la dueña): Gerencia y administradoras, como siempre.
2. Gerencia ve en «Reparto» los clientes que cambiaron de mano; la vendedora no.
3. Los chats de la noche se reparten parejo en la mañana: el cron no le da a nadie más de N clientes sin contestar.
"""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun import freeze_time

from odoo import fields
from odoo.addons.dcasa_brian.models import telegram as brian_telegram
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.conversacion import PIE_DE_AVISO
from ..models.reparto import ClienteDeOtraVendedora
from .test_reparto_justo import RepartoCase, panama

TOMO = 'Beto Vendedor tomó el cliente que atendía Vendedora Prueba.'


class TomarCase(RepartoCase):
    """Ana («Vendedora Prueba»), Beto y Carla; la regla de estar activa encendida (30 minutos) y un Worker de mentira.
    Ana, Beto y Gerencia tienen su Telegram vinculado con Brian."""

    def setUp(self):
        super().setUp()
        self.ajustes.write({'reparto_activa_minutos': 30, 'reparto_reasignar_minutos': 15})
        self.env['mail.presence'].sudo().search([('user_id', 'in', self.equipo.ids)]).unlink()
        self.worker = self.configurar_worker()
        self.chat_de = {}
        for usuario, chat in ((self.vendedora, '5551001'), (self.beto, '5551002'), (self.gerente, '5551003')):
            self.Enlace.create({'user_id': usuario.id, 'chat_id': chat})
            self.chat_de[usuario] = chat

    def activa(self, usuario, hace_minutos=1):
        """``usuario`` usó Odoo (teclado o ratón) hace ``hace_minutos``."""
        Presencia = self.env['mail.presence'].sudo()
        momento = fields.Datetime.now() - timedelta(minutes=hace_minutos)
        presencia = Presencia.search([('user_id', '=', usuario.id)])
        if presencia:
            presencia.write({'last_presence': momento, 'status': 'online'})
        else:
            Presencia.create({'user_id': usuario.id, 'last_presence': momento, 'status': 'online'})

    def de(self, usuario):
        """Un cliente que ``usuario`` atiende ahora (la conversación está con una persona, a su nombre)."""
        conv = self.cliente()
        conv._poner_en_humano(usuario=usuario)
        return conv

    def panel(self, usuario):
        return self.Conversacion.with_user(usuario)

    def mensajes_de(self, conv, usuario):
        return self.Mensaje.search_count([('conversacion_id', '=', conv.id), ('autor', '=', 'vendedora'),
                                          ('usuario_id', '=', usuario.id)])

    def telegram_a(self, usuario):
        """Lo que le llegó por Telegram a ``usuario``."""
        return [c.args[1] for c in self.enviar.call_args_list if c.args[0] == self.chat_de[usuario]]

    def tomadas(self, conv):
        return self.Reparto.search([('conversacion_id', '=', conv.id), ('regla', '=', 'tomada')])


@tagged('post_install', '-at_install')
class TestClienteDeOtraVendedora(TomarCase):

    # --- La otra está trabajando: hay que confirmarlo ------------------------------------------------------------

    def test_sin_confirmar_no_se_le_manda_nada_ni_se_le_quita(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        beto = self.panel(self.beto)
        with self.assertRaises(ClienteDeOtraVendedora) as error:
            beto.enviar_respuesta(conv.id, 'Hola, te atiendo yo')
        self.assertIn('Este cliente lo atiende Vendedora Prueba', str(error.exception))
        self.assertEqual(error.exception.context, {'dcasa_duena_id': self.vendedora.id,
                                                   'dcasa_duena': 'Vendedora Prueba'},
                         'La pantalla arma la pregunta con esto')
        for llamada in (lambda: beto.tomar(conv.id),
                        lambda: beto.enviar_respuesta(conv.id, 'Mañana te escribo', None,
                                                      (fields.Datetime.now() + timedelta(hours=3)).isoformat() + 'Z'),
                        # Se mira antes de armar el PDF o las fotos (ni hay cotización ni producto: no llega a eso).
                        lambda: beto.enviar_cotizacion(conv.id),
                        lambda: beto.enviar_foto_catalogo(conv.id, 999999)):
            with self.subTest(llamada=llamada), self.assertRaises(ClienteDeOtraVendedora):
                llamada()
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertEqual(self.Mensaje.search_count([('conversacion_id', '=', conv.id), ('autor', '=', 'vendedora')]),
                         0, 'Nada salió ni quedó programado')
        self.assertFalse(self.tomadas(conv))
        self.assertFalse(self.telegram_a(self.vendedora))

    def test_desde_el_formulario_tampoco(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        conv.sudo().borrador = 'Hola'
        for accion in ('action_enviar', 'action_atender'):
            with self.subTest(accion=accion), self.assertRaises(ClienteDeOtraVendedora):
                getattr(conv.with_user(self.beto), accion)()
        self.assertEqual(conv.asignada_a, self.vendedora)

    def test_confirmado_se_lo_queda_y_queda_dicho_en_el_hilo_el_libro_y_telegram(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        r = self.panel(self.beto).enviar_respuesta(conv.id, 'Hola, te atiendo yo', tomar_de_otra=True)
        self.assertTrue(r['enviado'])
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertEqual(self.mensajes_de(conv, self.beto), 1)
        self.assertIn(TOMO, self.avisos(conv))
        self.assertNotIn('tomó la conversación al escribir', self.avisos(conv))
        tomada = self.tomadas(conv)
        self.assertEqual((tomada.usuario_id, tomada.anterior_id, tomada.forma), (self.beto, self.vendedora, 'escribir'))
        self.assertIn(TOMO, tomada.razon)
        avisos_a_ana = self.telegram_a(self.vendedora)
        self.assertEqual(len(avisos_a_ana), 1)
        self.assertIn('Beto Vendedor tomó a tu cliente Cliente 5076200', avisos_a_ana[0])
        self.assertIn('WhatsApp', avisos_a_ana[0])
        self.assertEqual(self.recibidas(self.beto), 0, 'Tomarlo no cuenta como una que Juan le pasó')

    def test_atender_confirmado_tambien(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        self.panel(self.beto).tomar(conv.id, None, tomar_de_otra=True)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(f'{TOMO} El asistente calla hasta', self.avisos(conv))
        self.assertEqual(self.tomadas(conv).forma, 'atender')
        self.assertEqual(len(self.telegram_a(self.vendedora)), 1)

    def test_el_permiso_es_si_o_no(self):
        conv = self.de(self.vendedora)
        for malo in ('si', 1, None):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.panel(self.beto).enviar_respuesta(conv.id, 'Hola', tomar_de_otra=malo)

    def test_programado_con_permiso_cambia_de_mano_cuando_sale(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        cuando = (fields.Datetime.now() + timedelta(hours=3)).isoformat() + 'Z'
        r = self.panel(self.beto).enviar_respuesta(conv.id, 'Te escribo luego', None, cuando, tomar_de_otra=True)
        self.assertTrue(r['programado'])
        self.assertEqual(conv.asignada_a, self.vendedora, 'Hasta que salga, sigue con Ana')
        self.Mensaje.search([('conversacion_id', '=', conv.id), ('estado_envio', '=', 'programado')]).with_context(
            dcasa_mensaje_sistema=True).sudo().programado_para = fields.Datetime.now() - timedelta(minutes=1)
        self.assertEqual(self.Mensaje._cron_enviar_programados(), 1)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(TOMO, self.avisos(conv))
        self.assertEqual(self.tomadas(conv).forma, 'escribir')

    # --- La otra no está: se toma sin preguntar (cubrir a una compañera ausente es ayudar) --------------------------

    def test_si_la_otra_no_esta_activa_se_toma_sin_preguntar_con_aviso_y_libro_sin_telegram(self):
        self.activa(self.vendedora, 120)   # se fue hace dos horas
        conv = self.de(self.vendedora)
        self.panel(self.beto).enviar_respuesta(conv.id, 'Hola, te atiendo yo')
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(TOMO, self.avisos(conv))
        self.assertEqual(self.tomadas(conv).anterior_id, self.vendedora)
        self.assertFalse(self.telegram_a(self.vendedora), 'Sin Telegram: no estaba trabajando')

    def test_no_disponible_o_fuera_del_reparto_cuenta_como_no_activa(self):
        self.activa(self.vendedora)
        for cambio in ({'dcasa_disponible': False}, {'dcasa_disponible': True, 'dcasa_fuera_del_reparto': True}):
            self.vendedora.write(cambio)
            conv = self.de(self.vendedora)
            with self.subTest(cambio=cambio):
                self.panel(self.beto).tomar(conv.id)
                self.assertEqual(conv.asignada_a, self.beto)
                self.assertTrue(self.tomadas(conv))
        self.assertFalse(self.telegram_a(self.vendedora))

    def test_con_cero_minutos_toda_la_que_esta_disponible_cuenta_como_activa(self):
        """La misma definición del reparto: con «0 = no mirarlo», se protege toda la que esté «Disponible»."""
        self.ajustes.reparto_activa_minutos = 0
        conv = self.de(self.vendedora)
        with self.assertRaises(ClienteDeOtraVendedora):
            self.panel(self.beto).enviar_respuesta(conv.id, 'Hola')

    # --- Gerencia y administradoras: como siempre ------------------------------------------------------------------

    def test_gerencia_toma_sin_confirmacion_y_sin_aviso_nuevo(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        self.panel(self.gerente).enviar_respuesta(conv.id, 'Hola, soy de Gerencia')
        self.assertEqual(conv.asignada_a, self.gerente)
        self.assertNotIn('tomó el cliente que atendía', self.avisos(conv))
        self.assertFalse(self.tomadas(conv))
        self.assertFalse(self.telegram_a(self.vendedora))
        otra = self.de(self.vendedora)
        self.panel(self.gerente).tomar(otra.id)
        self.assertIn('Gerente Prueba tomó la conversación. El asistente calla hasta', self.avisos(otra))
        self.assertNotIn('tomó el cliente que atendía', self.avisos(otra))
        linea = self.Reparto.search([('conversacion_id', '=', otra.id)], order='id desc', limit=1)
        self.assertEqual((linea.regla, linea.anterior_id), ('manual', self.env['res.users']), 'Como hoy')

    def test_la_administradora_tambien_como_siempre(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        self.panel(self.administrador).tomar(conv.id)
        self.assertEqual(conv.asignada_a, self.administrador)
        self.assertFalse(self.tomadas(conv))

    def test_al_cliente_de_gerencia_se_le_escribe_como_siempre(self):
        self.activa(self.gerente)
        conv = self.de(self.gerente)
        self.panel(self.beto).enviar_respuesta(conv.id, 'Hola')
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertFalse(self.tomadas(conv))

    # --- Lo que no es «el cliente de otra» ---------------------------------------------------------------------------

    def test_a_su_propio_cliente_se_le_escribe_sin_preguntar(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        self.panel(self.vendedora).enviar_respuesta(conv.id, 'Hola de nuevo')
        self.assertFalse(self.tomadas(conv))

    def test_si_volvio_al_asistente_o_se_cerro_ya_no_lo_atiende_nadie(self):
        self.activa(self.vendedora)
        devuelta = self.de(self.vendedora)
        devuelta._devolver(self.vendedora)
        cerrada = self.de(self.vendedora)
        cerrada._cerrar(self.vendedora)
        for conv in (devuelta, cerrada):
            with self.subTest(estado=conv.estado):
                self.panel(self.beto).enviar_respuesta(conv.id, 'Hola')
                self.assertEqual(conv.asignada_a, self.beto)
                self.assertIn('Beto Vendedor tomó la conversación al escribir', self.avisos(conv))
                self.assertFalse(self.tomadas(conv))

    def test_asignar_a_mano_deja_su_linea_con_quien_lo_tenia(self):
        conv = self.de(self.vendedora)
        self.panel(self.gerente).asignar(conv.id, self.beto.id)
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertEqual((linea.regla, linea.usuario_id, linea.anterior_id), ('manual', self.beto, self.vendedora))
        self.assertIn('Gerente Prueba asignó la conversación a Beto Vendedor', self.avisos(conv))


@tagged('post_install', '-at_install')
class TestClienteDeOtraPorTelegram(TomarCase):
    """Responder o «Atender» desde Telegram (no hay cómo preguntar): si es de otra vendedora activa, no se hace y se le
    dice por qué; si no, se toma con el aviso de siempre."""

    def setUp(self):
        super().setUp()
        brian_telegram._mensajes.clear()      # el límite de velocidad de Brian es por chat y vive en memoria
        parche = patch.object(type(self.Enlace), '_api', MagicMock(return_value={'message_id': 1}))
        parche.start()
        self.addCleanup(parche.stop)

    def responder(self, conv, texto, chat):
        aviso = {'message_id': 77, 'from': {'is_bot': True, 'id': 999}, 'chat': {'id': int(chat), 'type': 'private'},
                 'text': f'Cliente espera.\n\n{PIE_DE_AVISO % conv.id}'}
        self.Enlace._procesar_update({'update_id': 9000 + conv.id, 'message': {
            'message_id': 78, 'chat': {'id': int(chat), 'type': 'private'}, 'from': {'id': int(chat)},
            'text': texto, 'reply_to_message': aviso}})

    def pulsar(self, dato, chat):
        self.Enlace._procesar_update({'update_id': 9500 + len(self.enviar.call_args_list), 'callback_query': {
            'id': 'cb1', 'data': dato, 'from': {'id': int(chat)},
            'message': {'message_id': 90, 'chat': {'id': int(chat), 'type': 'private'}}}})

    def test_de_otra_activa_no_prepara_nada_y_se_le_dice_quien_lo_atiende(self):
        self.activa(self.vendedora)
        conv = self.de(self.vendedora)
        chat = self.chat_de[self.beto]
        self.responder(conv, 'Hola, te atiendo yo', chat)
        self.assertFalse(self.env['dcasa.telegram_borrador'].sudo().search_count([]))
        self.assertIn('Este cliente lo atiende Vendedora Prueba', self.telegram_a(self.beto)[-1])
        self.pulsar(f'juan:t:{conv.id}', chat)
        self.assertIn('Este cliente lo atiende Vendedora Prueba', self.telegram_a(self.beto)[-1])
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertFalse(self.tomadas(conv))

    def test_si_al_pulsar_enviar_la_otra_ya_esta_activa_no_se_manda(self):
        self.activa(self.vendedora, 120)
        conv = self.de(self.vendedora)
        chat = self.chat_de[self.beto]
        self.responder(conv, 'Hola, te atiendo yo', chat)
        borrador = self.env['dcasa.telegram_borrador'].sudo().search([], limit=1)
        self.assertTrue(borrador)
        self.activa(self.vendedora)   # volvió mientras tanto
        self.pulsar(f'juan:e:{borrador.id}', chat)
        self.assertIn('No se mandó: Este cliente lo atiende Vendedora Prueba', self.telegram_a(self.beto)[-1])
        self.assertEqual(self.mensajes_de(conv, self.beto), 0)

    def test_de_otra_que_no_esta_se_toma_con_aviso(self):
        self.activa(self.vendedora, 120)
        conv = self.de(self.vendedora)
        chat = self.chat_de[self.beto]
        self.responder(conv, 'Hola, te atiendo yo', chat)
        borrador = self.env['dcasa.telegram_borrador'].sudo().search([], limit=1)
        self.pulsar(f'juan:e:{borrador.id}', chat)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertEqual(self.mensajes_de(conv, self.beto), 1)
        self.assertIn(TOMO, self.avisos(conv))
        self.assertFalse(self.telegram_a(self.vendedora))


@tagged('post_install', '-at_install')
class TestCambiosDeManoEnLaPantalla(TomarCase):
    """«Clientes que cambiaron de mano» en la pantalla Reparto: solo Gerencia."""

    def cuatro_cambios(self):
        """Uno de cada: lo tomó al escribirle, con «Atender», se lo asignaron y pasó porque no contestó."""
        escrita = self.de(self.vendedora)
        self.panel(self.beto).enviar_respuesta(escrita.id, 'Hola')
        with freeze_time(self.AHORA + timedelta(minutes=1)):
            atendida = self.de(self.beto)
            self.panel(self.carla).tomar(atendida.id)
        with freeze_time(self.AHORA + timedelta(minutes=2)):
            asignada = self.de(self.carla)
            self.panel(self.gerente).asignar(asignada.id, self.vendedora.id)
        with freeze_time(self.AHORA + timedelta(minutes=3)):
            self.activa(self.vendedora)
            sin_contestar = self.pasar()
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.activa(self.carla)
            self.Reparto._cron_reasignar()
        return escrita, atendida, asignada, sin_contestar

    def test_gerencia_ve_quien_tomo_el_cliente_de_quien_lo_mas_reciente_arriba(self):
        escrita, atendida, asignada, sin_contestar = self.cuatro_cambios()
        with freeze_time(self.AHORA + timedelta(minutes=21)):
            cambios = self.env['dcasa.juan.panel'].with_user(self.gerente).reparto('hoy')['cambios_de_mano']
        filas = [(f['conversacion_id'], f['de'], f['a'], f['como']) for f in cambios['filas']]
        self.assertEqual(filas, [
            (sin_contestar.id, 'Vendedora Prueba', 'Carla Vendedora', 'Pasó porque no contestó'),
            (asignada.id, 'Carla Vendedora', 'Vendedora Prueba', 'Se lo asignaron'),
            (atendida.id, 'Beto Vendedor', 'Carla Vendedora', 'Lo tomó con «Atender»'),
            (escrita.id, 'Vendedora Prueba', 'Beto Vendedor', 'Lo tomó al escribirle'),
        ])
        self.assertEqual(cambios['mas'], 0)
        self.assertEqual(cambios['filas'][-1]['cliente'], escrita.partner_id.name)
        self.assertEqual(cambios['filas'][-1]['momento'], '2026-10-09T15:00:00Z')

    def test_lo_que_no_cambio_de_mano_no_sale(self):
        self.pasar()                                      # Juan se la pasó a alguien: no la tenía nadie
        propia = self.de(self.vendedora)
        self.panel(self.vendedora).enviar_respuesta(propia.id, 'Hola')
        del_gerente = self.de(self.vendedora)
        self.panel(self.gerente).tomar(del_gerente.id)   # Gerencia interviene: como siempre, no es «tomada»
        cambios = self.env['dcasa.juan.panel'].with_user(self.gerente).reparto('hoy')['cambios_de_mano']
        self.assertEqual(cambios, {'filas': [], 'mas': 0})

    def test_la_vendedora_no_lo_recibe(self):
        self.cuatro_cambios()
        datos = self.env['dcasa.juan.panel'].with_user(self.beto).reparto('hoy')
        self.assertIsNone(datos['cambios_de_mano'])
        texto = json.dumps(datos)
        for otra in (self.vendedora, self.carla):
            self.assertNotIn(otra.name, texto)

    def test_salen_los_ultimos_veinte_y_cuantos_mas(self):
        for n in range(23):
            with freeze_time(self.AHORA + timedelta(minutes=n)):
                conv = self.de(self.vendedora)
                self.panel(self.beto).tomar(conv.id)
        cambios = self.env['dcasa.juan.panel'].with_user(self.gerente).reparto('hoy')['cambios_de_mano']
        self.assertEqual((len(cambios['filas']), cambios['mas']), (20, 3))
        momentos = [f['momento'] for f in cambios['filas']]
        self.assertEqual(momentos, sorted(momentos, reverse=True))

    def test_el_periodo_manda(self):
        with freeze_time(self.AHORA - timedelta(days=10)):
            conv = self.de(self.vendedora)
            self.panel(self.beto).tomar(conv.id)
        panel = self.env['dcasa.juan.panel'].with_user(self.gerente)
        self.assertEqual(panel.reparto('7_dias')['cambios_de_mano']['filas'], [])
        self.assertEqual(len(panel.reparto('30_dias')['cambios_de_mano']['filas']), 1)

    def test_brian_lo_cuenta_sin_los_nombres_de_los_clientes(self):
        escrita, *_resto = self.cuatro_cambios()
        with freeze_time(self.AHORA + timedelta(minutes=21)):
            respuesta = self.env['brian.herramientas'].with_user(self.gerente).ejecutar(
                'reparto_de_conversaciones', {'periodo': 'hoy'})
            suyo = self.env['brian.herramientas'].with_user(self.beto).ejecutar(
                'reparto_de_conversaciones', {'periodo': 'hoy'})
        cambios = respuesta['datos']['clientes_que_cambiaron_de_mano']
        self.assertEqual(cambios['total'], 4)
        self.assertEqual(cambios['mas_recientes'][-1]['como'], 'Lo tomó al escribirle')
        self.assertNotIn(escrita.partner_id.name, json.dumps(respuesta['datos']))
        self.assertEqual(respuesta['datos']['reglas']['maximo_de_clientes_sin_contestar_a_la_vez'], 3)
        self.assertNotIn('clientes_que_cambiaron_de_mano', suyo['datos'])


@tagged('post_install', '-at_install')
class TestNadieAcaparaLosChatsDeLaNoche(TomarCase):
    """Ninguna vendedora recibe del cron más de «Máximo de clientes esperándole a la vez» (3 de fábrica) clientes que
    nadie ha contestado; en cuanto contesta uno, recibe otro; las que llegan reciben los demás."""

    NOCHE = panama(2026, 10, 8, 22, 0)      # jueves 10:00 p. m.: la tienda está cerrada y nadie está activa

    def chats_de_la_noche(self, cuantos=10):
        with freeze_time(self.NOCHE):
            convs = [self.pasar() for _n in range(cuantos)]
        self.assertFalse(any(c.asignada_a for c in convs), 'De noche nadie está activa: quedan sin dueña')
        return convs

    def vuelta(self, a_las, *activas):
        """Una vuelta del cron a esa hora de Panamá (del viernes), con esas personas activas."""
        with freeze_time(panama(2026, 10, 9, *a_las)):
            for usuario in activas:
                self.activa(usuario)
            return self.Reparto._cron_reasignar()

    def de_quien(self, convs):
        return [c.asignada_a for c in convs]

    def test_de_fabrica_tres_y_va_de_cero_a_cincuenta(self):
        self.assertEqual(self.env['dcasa.juan.ajustes'].default_get(['reparto_max_esperando']),
                         {'reparto_max_esperando': 3})
        for malo in (-1, 51):
            with self.subTest(malo=malo), self.assertRaises(ValidationError):
                self.ajustes.reparto_max_esperando = malo
        for bueno in (0, 3, 50):
            self.ajustes.reparto_max_esperando = bueno
        self.assertTrue(self.ajustes._fields['reparto_max_esperando'].tracking)
        vista = self.env.ref('dcasa_conversaciones.view_dcasa_juan_ajustes_form').arch
        self.assertIn('reparto_max_esperando', vista)

    def test_la_primera_que_llega_recibe_tres_contesta_uno_recibe_otro_y_la_que_llega_recibe_los_suyos(self):
        convs = self.chats_de_la_noche(10)
        self.assertEqual(self.vuelta((8, 5), self.vendedora), 3)
        suyas = [c for c in convs if c.asignada_a == self.vendedora]
        self.assertEqual(len(suyas), 3)
        self.assertEqual(self.vuelta((8, 10), self.vendedora), 0, 'Con tres esperándole, no recibe más')
        # Le contesta a uno: queda lugar y la próxima vuelta se adelanta (no espera 5 minutos).
        cron = self.env.ref('dcasa_conversaciones.ir_cron_reasignar_sin_respuesta')
        antes = self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)])
        with freeze_time(panama(2026, 10, 9, 8, 11)):
            self.panel(self.vendedora).enviar_respuesta(suyas[0].id, 'Buenos días, te atiendo yo')
        self.assertGreater(self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)]), antes)
        self.assertEqual(self.vuelta((8, 12), self.vendedora), 1)
        self.assertEqual(self.de_quien(convs).count(self.vendedora), 4)
        # Llega Beto: recibe los suyos (los que le esperan a Ana todavía tienen tiempo de contestarse).
        self.assertEqual(self.vuelta((8, 14), self.vendedora, self.beto), 3)
        self.assertEqual(self.de_quien(convs).count(self.beto), 3)
        self.assertEqual(sum(1 for c in convs if not c.asignada_a), 3, 'Los demás esperan lugar, sin dueña')

    def test_con_cero_es_como_antes_la_primera_recibe_todos(self):
        self.ajustes.reparto_max_esperando = 0
        convs = self.chats_de_la_noche(10)
        self.assertEqual(self.vuelta((8, 5), self.vendedora), 10)
        self.assertEqual(set(self.de_quien(convs)), {self.vendedora})

    def test_pasar_a_otra_si_no_contesta_tambien_respeta_el_tope(self):
        convs = self.chats_de_la_noche(6)
        self.assertEqual(self.vuelta((8, 1), self.vendedora, self.beto), 6)
        self.assertEqual(sorted(self.de_quien(convs).count(u) for u in (self.vendedora, self.beto)), [3, 3])
        # A las 8:16 nadie contestó: cada cliente pasa a otra con lugar. Llega Carla: recibe tres y no más; ninguna
        # queda con más de tres sin contestar.
        self.vuelta((8, 16), self.vendedora, self.beto, self.carla)
        cuantas = {u.name: self.de_quien(convs).count(u) for u in self.equipo}
        self.assertEqual(cuantas['Carla Vendedora'], 3, cuantas)
        self.assertLessEqual(max(cuantas.values()), 3, cuantas)
        self.assertEqual(sum(cuantas.values()), 6, 'Ninguno se quedó sin dueña')

    def test_de_dia_el_parejo_salta_a_quien_ya_tiene_el_maximo_si_hay_otra_con_lugar(self):
        self.ajustes.reparto_activa_minutos = 0
        for _n in range(3):
            self.cliente().sudo().write({'estado': 'humano', 'asignada_a': self.vendedora.id,
                                         'reparto_desde': fields.Datetime.now()})
        self.dar(self.beto, 2)
        self.dar(self.carla, 2)
        conv = self.pasar()
        self.assertIn(conv.asignada_a, self.beto | self.carla, 'Ana lleva menos hoy, pero ya le esperan tres')
        self.ajustes.reparto_max_esperando = 0
        self.assertEqual(self.pasar().asignada_a, self.vendedora, 'Sin tope, el orden de siempre')

    def test_de_dia_si_todas_estan_llenas_igual_se_asigna(self):
        self.ajustes.reparto_activa_minutos = 0
        for usuario in self.equipo:
            for _n in range(3):
                self.cliente().sudo().write({'estado': 'humano', 'asignada_a': usuario.id,
                                             'reparto_desde': fields.Datetime.now()})
        self.assertTrue(self.pasar().asignada_a, 'De día el cliente nunca se queda sin dueña por el tope')

    def test_de_dia_su_vendedora_de_siempre_lo_recibe_aunque_este_llena(self):
        self.ajustes.reparto_activa_minutos = 0
        primera = self.pasar()
        duena = primera.asignada_a
        primera._devolver(duena)
        for _n in range(3):
            self.cliente().sudo().write({'estado': 'humano', 'asignada_a': duena.id,
                                         'reparto_desde': fields.Datetime.now()})
        primera._pasar_a_vendedora('Volvió a escribir')
        self.assertEqual(primera.asignada_a, duena)
