"""Revisión adversarial del «reparto justo» (2026-11-12): los caminos para quitarle el cliente a otra vendedora activa
sin confirmar, ya cerrados. Las primeras pruebas son las del revisor (``dcasa_rev_lote/tests/test_rev_reparto.py``),
que fallaban, con la expectativa de «debería»; las demás fijan cada decisión del coordinador:

1. «Atiende» de la ficha y ``write`` (formulario o RPC): asignárselo a sí misma pide la misma confirmación; pasárselo a
   otra o dejarlo sin dueña, no (si es suyo, sí, como siempre).
2. Devolver al asistente o cerrar el chat que atiende otra vendedora activa: no.
3. Un programado que al salir encuentra al cliente con otra vendedora no sale: queda dicho y se le avisa a quien lo
   programó (salvo que lo haya confirmado contra esa misma).
4. Solo entre vendedoras de piso: Caja y Contabilidad se comportan como Gerencia (y siguen recibiendo del reparto).
6. «Sí, lo tomo» vale solo contra la vendedora por la que se preguntó (``tomar_de`` = su id).
9. El tope del cron solo frena a los que esperan desde antes de abrir: de día nadie se queda sin dueña por el tope.
10. «Ya la atendí» saca a la conversación del reparto (``reparto_desde``).
"""
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from ..models.reparto import ClienteDeOtraVendedora
from .test_reparto_justo import panama
from .test_reparto_tomar import TOMO, TomarCase

NO_PUEDES = 'Este cliente lo atiende Vendedora Prueba, que está trabajando ahora: no puedes'


class RevisionCase(TomarCase):
    """Ana y Beto trabajando (Carla no)."""

    def setUp(self):
        super().setUp()
        self.activa(self.vendedora)
        self.activa(self.beto)

    def rastro(self, conv):
        return {'asignada': conv.asignada_a.name, 'tomadas': len(self.tomadas(conv)),
                'telegram_a_ana': len(self.telegram_a(self.vendedora))}


@tagged('post_install', '-at_install')
class TestCaminosParaQuitarElCliente(RevisionCase):
    """Las pruebas del revisor (1, 2 y 3) y lo que debe pasar en cada camino."""

    # --- write (formulario o RPC) ---------------------------------------------------------------------------------

    def test_rpc_write_asignada_a_no_le_quita_el_cliente(self):
        conv = self.de(self.vendedora)
        with self.assertRaises(ClienteDeOtraVendedora):
            call_kw(self.env(user=self.beto)['dcasa.conversacion'], 'write',
                    [[conv.id], {'asignada_a': self.beto.id}], {})
        self.assertEqual(conv.asignada_a, self.vendedora, self.rastro(conv))
        for otro in (self.carla.id, False):
            with self.subTest(otro=otro), self.assertRaisesRegex(UserError, NO_PUEDES):
                call_kw(self.env(user=self.beto)['dcasa.conversacion'], 'write', [[conv.id], {'asignada_a': otro}], {})
        self.assertEqual(conv.asignada_a, self.vendedora)

    def test_write_a_si_misma_confirmado_contra_ella_se_lo_queda_y_queda_dicho(self):
        conv = self.de(self.vendedora)
        conv.with_user(self.beto).with_context(dcasa_tomar_de=self.vendedora.id).write({'asignada_a': self.beto.id})
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(TOMO, self.avisos(conv))
        self.assertEqual(self.tomadas(conv).forma, 'asignar')
        self.assertEqual(len(self.telegram_a(self.vendedora)), 1)

    def test_write_de_gerencia_y_de_la_duena_como_siempre(self):
        conv = self.de(self.vendedora)
        conv.with_user(self.vendedora).write({'asignada_a': self.carla.id})     # su cliente: lo pasa a quien quiera
        self.assertEqual(conv.asignada_a, self.carla)
        conv.with_user(self.gerente).write({'asignada_a': self.beto.id})
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertFalse(self.tomadas(conv))

    # --- «Atiende» de la ficha (asignar) ----------------------------------------------------------------------------

    def test_asignarselo_a_si_misma_pide_la_misma_confirmacion(self):
        conv = self.de(self.vendedora)
        with self.assertRaises(ClienteDeOtraVendedora) as error:
            self.panel(self.beto).asignar(conv.id, self.beto.id)
        self.assertEqual(error.exception.context['dcasa_duena_id'], self.vendedora.id)
        self.assertEqual(conv.asignada_a, self.vendedora, self.rastro(conv))
        self.panel(self.beto).asignar(conv.id, self.beto.id, tomar_de=self.vendedora.id)
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertIn(TOMO, self.avisos(conv))
        tomada = self.tomadas(conv)
        self.assertEqual((tomada.anterior_id, tomada.forma), (self.vendedora, 'asignar'))
        self.assertEqual(len(self.telegram_a(self.vendedora)), 1)
        filas = self.env['dcasa.juan.panel'].with_user(self.gerente).reparto('hoy')['cambios_de_mano']['filas']
        self.assertEqual(filas[0]['como'], 'Lo tomó desde «Atiende»')

    def test_pasarselo_a_una_tercera_no_se_puede(self):
        conv = self.de(self.vendedora)
        with self.assertRaisesRegex(UserError, f'{NO_PUEDES} pasárselo a otra persona. Pídeselo a Vendedora Prueba o '
                                               'a Gerencia'):
            self.panel(self.beto).asignar(conv.id, self.carla.id)
        self.assertEqual(conv.asignada_a, self.vendedora, self.rastro(conv))

    def test_dejar_sin_asignar_y_tomar_no_se_salta_la_pregunta(self):
        conv = self.de(self.vendedora)
        with self.assertRaisesRegex(UserError, f'{NO_PUEDES} dejarlo sin asignar'):
            self.panel(self.beto).asignar(conv.id, None)
        with self.assertRaises(ClienteDeOtraVendedora):
            self.panel(self.beto).tomar(conv.id)
        self.assertEqual(conv.asignada_a, self.vendedora, self.rastro(conv))

    def test_su_propio_cliente_lo_pasa_a_otra_como_siempre_con_su_linea(self):
        conv = self.de(self.beto)
        self.panel(self.beto).asignar(conv.id, self.carla.id)
        self.assertEqual(conv.asignada_a, self.carla)
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertEqual((linea.regla, linea.anterior_id), ('manual', self.beto))

    def test_si_la_otra_no_esta_se_puede_pasar_o_soltar(self):
        self.activa(self.vendedora, 120)
        conv = self.de(self.vendedora)
        self.panel(self.beto).asignar(conv.id, self.carla.id)
        self.assertEqual(conv.asignada_a, self.carla)

    def test_gerencia_asigna_como_siempre(self):
        conv = self.de(self.vendedora)
        self.panel(self.gerente).asignar(conv.id, self.carla.id)
        self.panel(self.gerente).asignar(conv.id, None)
        self.assertFalse(conv.asignada_a)
        self.assertFalse(self.tomadas(conv))

    # --- Devolver o cerrar ----------------------------------------------------------------------------------------

    def test_devolver_o_cerrar_el_de_otra_activa_no_se_puede(self):
        for paso, que in (('devolver', 'devolverlo al asistente'), ('cerrar', 'cerrar la conversación')):
            conv = self.de(self.vendedora)
            with self.subTest(paso=paso):
                with self.assertRaisesRegex(UserError, f'{NO_PUEDES} {que}'):
                    getattr(self.panel(self.beto), paso)(conv.id)
                with self.assertRaises(ClienteDeOtraVendedora):
                    self.panel(self.beto).tomar(conv.id)
                self.assertEqual((conv.asignada_a, conv.estado), (self.vendedora, 'humano'), self.rastro(conv))
        conv = self.de(self.vendedora)
        for accion in ('action_devolver_al_bot', 'action_cerrar'):
            with self.subTest(accion=accion), self.assertRaisesRegex(UserError, NO_PUEDES):
                getattr(conv.with_user(self.beto), accion)()

    def test_si_la_otra_no_esta_o_es_gerencia_se_devuelve_y_se_cierra_como_siempre(self):
        self.activa(self.vendedora, 120)
        conv = self.de(self.vendedora)
        self.panel(self.beto).devolver(conv.id)
        self.assertEqual(conv.estado, 'bot')
        otra = self.de(self.vendedora)
        self.activa(self.vendedora)
        self.panel(self.gerente).cerrar(otra.id)
        self.assertEqual(otra.estado, 'cerrada')

    # --- El programado ----------------------------------------------------------------------------------------------

    def programar(self, conv, usuario, **kw):
        cuando = (fields.Datetime.now() + timedelta(hours=3)).isoformat() + 'Z'
        r = self.panel(usuario).enviar_respuesta(conv.id, 'Te escribo luego', None, cuando, **kw)
        self.assertTrue(r['programado'])

    def que_salga(self, *convs):
        """Llega la hora de lo programado en esas conversaciones. Devuelve cuántos salieron."""
        self.Mensaje.search([('conversacion_id', 'in', [c.id for c in convs]), ('estado_envio', '=', 'programado')]
                            ).with_context(dcasa_mensaje_sistema=True).sudo().programado_para = \
            fields.Datetime.now() - timedelta(minutes=1)
        return self.Mensaje._cron_enviar_programados()

    def test_programado_no_se_lo_quita_a_quien_lo_tomo_despues(self):
        conv = self.de(self.beto)                         # el cliente es de Beto
        self.programar(conv, self.beto)
        self.panel(self.vendedora).tomar(conv.id, None, tomar_de=self.beto.id)   # Ana lo toma (confirmando)
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.enviar.reset_mock()
        self.assertEqual(self.que_salga(conv), 0)
        self.assertEqual(conv.asignada_a, self.vendedora, f'{self.rastro(conv)}; {self.avisos(conv)[-200:]}')
        self.assertFalse(self.Mensaje.search([('conversacion_id', '=', conv.id), ('estado_envio', '=', 'programado')]),
                         'Queda cancelado')
        self.assertFalse(self.mensajes_de(conv, self.beto), 'Al cliente no le salió nada')
        self.assertIn('No salió el mensaje que Beto Vendedor dejó programado («Te escribo luego»): el cliente ahora lo '
                      'atiende Vendedora Prueba.', self.avisos(conv))
        aviso_a_beto = self.telegram_a(self.beto)
        self.assertEqual(len(aviso_a_beto), 1)
        self.assertIn('No salió el mensaje que dejaste programado', aviso_a_beto[0])
        bandeja = conv.message_ids.filtered(lambda m: self.beto.partner_id in m.partner_ids)
        self.assertTrue(bandeja, 'También le llega en Odoo')

    def test_programado_sale_si_sigue_siendo_suyo_o_de_nadie(self):
        suya = self.de(self.beto)
        self.programar(suya, self.beto)
        libre = self.cliente()
        self.programar(libre, self.beto)
        self.assertEqual(self.que_salga(suya, libre), 2)
        self.assertEqual((suya.asignada_a, libre.asignada_a), (self.beto, self.beto))

    def test_programado_confirmado_contra_ella_sale_si_sigue_con_ella_y_no_si_la_tomo_otra(self):
        conv = self.de(self.vendedora)
        self.programar(conv, self.beto, tomar_de=self.vendedora.id)
        otra = self.de(self.vendedora)
        self.programar(otra, self.beto, tomar_de=self.vendedora.id)
        self.panel(self.carla).tomar(otra.id, None, tomar_de=self.vendedora.id)   # Carla se la quitó a Ana
        self.assertEqual(self.que_salga(conv, otra), 1)
        self.assertEqual(conv.asignada_a, self.beto, 'Confirmó contra Ana y sigue con Ana: sale y se la queda')
        self.assertIn(TOMO, self.avisos(conv))
        self.assertEqual(otra.asignada_a, self.carla, 'Ahora la atiende Carla: no sale')
        self.assertIn('el cliente ahora lo atiende Carla Vendedora', self.avisos(otra))


@tagged('post_install', '-at_install')
class TestSoloEntreVendedorasDePiso(RevisionCase):
    """«Cualquier administrativo puede entrar y responder, hacer y deshacer, y delegar y cambiar chats»: Caja (el jefe
    administrativo) y Contabilidad se comportan como Gerencia para esta regla. Quién recibe del reparto no cambia."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.caja = new_test_user(cls.env, login='juan_caja_revision', name='Caja Prueba',
                                 groups='base.group_user,dcasa_base.group_caja')
        cls.contadora = new_test_user(cls.env, login='juan_contadora_revision', name='Contadora Prueba',
                                      groups='base.group_user,sales_team.group_sale_salesman,account.group_account_user')

    def setUp(self):
        super().setUp()
        (self.caja | self.contadora).write({'dcasa_disponible': True})
        self.activa(self.caja)
        self.activa(self.contadora)

    def test_caja_sigue_recibiendo_del_reparto_pero_no_es_de_piso(self):
        Reparto = self.Reparto
        self.assertIn(self.caja, Reparto._vendedoras(), 'Quién recibe del reparto no cambia')
        self.assertNotIn(self.caja, Reparto._vendedoras_de_piso())
        self.assertNotIn(self.contadora, Reparto._vendedoras_de_piso())
        self.assertIn(self.beto, Reparto._vendedoras_de_piso())

    def test_caja_y_contabilidad_escriben_toman_y_asignan_como_siempre(self):
        for persona in (self.caja, self.contadora):
            with self.subTest(persona=persona.name):
                conv = self.de(self.vendedora)
                self.panel(persona).enviar_respuesta(conv.id, 'Hola, soy de la oficina')
                self.assertEqual(conv.asignada_a, persona)
                otra = self.de(self.vendedora)
                self.panel(persona).asignar(otra.id, self.carla.id)
                self.panel(persona).asignar(otra.id, None)
                tercera = self.de(self.vendedora)
                self.panel(persona).devolver(tercera.id)
                self.assertFalse(self.tomadas(conv) | self.tomadas(otra))
                self.assertNotIn('tomó el cliente que atendía', self.avisos(conv))
        self.assertFalse(self.telegram_a(self.vendedora))

    def test_al_cliente_de_caja_se_le_escribe_como_siempre(self):
        conv = self.de(self.caja)
        self.panel(self.beto).enviar_respuesta(conv.id, 'Hola')
        self.assertEqual(conv.asignada_a, self.beto)
        self.assertFalse(self.tomadas(conv))

    def test_la_pantalla_sabe_quien_es_de_piso(self):
        datos = self.Conversacion.with_user(self.beto).iniciar_panel()
        self.assertTrue(datos['usuario']['de_piso'])
        de_piso = {u['nombre']: u['de_piso'] for u in datos['equipo']}
        self.assertEqual((de_piso['Vendedora Prueba'], de_piso['Caja Prueba'], de_piso['Gerente Prueba']),
                         (True, False, False))
        self.assertFalse(self.Conversacion.with_user(self.caja).iniciar_panel()['usuario']['de_piso'])


@tagged('post_install', '-at_install')
class TestConfirmacionAtadaALaDuena(RevisionCase):

    def test_el_si_lo_tomo_vale_solo_para_la_duena_por_la_que_se_pregunto(self):
        """Carla ve «Este cliente lo atiende Ana»; mientras decide, Beto lo toma. Su «Sí, lo tomo» (contra Ana) no le
        quita el cliente a Beto: se le vuelve a preguntar, ahora por Beto."""
        conv = self.de(self.vendedora)
        with self.assertRaises(ClienteDeOtraVendedora) as error:
            self.panel(self.carla).enviar_respuesta(conv.id, 'Hola')
        self.assertEqual(error.exception.context['dcasa_duena_id'], self.vendedora.id)
        self.panel(self.beto).tomar(conv.id, None, tomar_de=self.vendedora.id)
        with self.assertRaises(ClienteDeOtraVendedora) as error:
            self.panel(self.carla).enviar_respuesta(conv.id, 'Hola', tomar_de=self.vendedora.id)
        self.assertEqual(error.exception.context, {'dcasa_duena_id': self.beto.id, 'dcasa_duena': 'Beto Vendedor'})
        self.assertEqual(conv.asignada_a, self.beto)
        self.panel(self.carla).enviar_respuesta(conv.id, 'Hola', tomar_de=self.beto.id)
        self.assertEqual(conv.asignada_a, self.carla)


@tagged('post_install', '-at_install')
class TestTopeSoloParaLosDeAntesDeAbrir(TomarCase):

    def setUp(self):
        super().setUp()
        (self.beto | self.carla).write({'dcasa_disponible': False})

    def tres_para_ana(self):
        self.activa(self.vendedora)
        mias = [self.pasar() for _ in range(3)]
        self.assertTrue(all(c.asignada_a == self.vendedora for c in mias))
        return mias

    def test_de_dia_un_sin_duena_se_da_aunque_la_unica_activa_este_llena(self):
        """La prueba del revisor: Ana tiene 3 sin contestar, se va a almorzar, llega un cliente (sin dueña); vuelve Ana
        y es la única activa: el cron se lo da igual."""
        self.tres_para_ana()
        self.activa(self.vendedora, 120)
        nuevo = self.pasar()
        self.assertFalse(nuevo.asignada_a)
        self.activa(self.vendedora)
        self.Reparto._cron_reasignar()
        self.assertEqual(nuevo.asignada_a, self.vendedora, 'De día nadie se queda sin dueña por el tope')

    def test_el_de_antes_de_abrir_si_espera_lugar_tambien_por_turnos(self):
        for modo in ('parejo', 'turnos'):
            with self.subTest(modo=modo):
                self.ajustes.reparto_modo = modo
                self.env['mail.presence'].sudo().search([('user_id', 'in', self.equipo.ids)]).unlink()
                with freeze_time(panama(2026, 10, 9, 6, 30)):    # antes de abrir: nadie activa
                    madrugador = self.pasar()
                self.assertFalse(madrugador.asignada_a)
                with freeze_time(panama(2026, 10, 9, 8, 20)):
                    self.activa(self.vendedora)
                    for _ in range(3):
                        self.cliente().sudo().write({'estado': 'humano', 'asignada_a': self.vendedora.id,
                                                     'reparto_desde': fields.Datetime.now()})
                    self.Reparto._cron_reasignar()
                self.assertFalse(madrugador.asignada_a, 'El de antes de abrir espera a que Ana conteste uno')

    def test_el_que_ya_tiene_duena_no_pasa_a_una_llena(self):
        self.activa(self.vendedora)
        conv = self.pasar()
        with freeze_time(self.AHORA + timedelta(minutes=16)):
            self.carla.dcasa_disponible = True
            self.activa(self.carla)
            for _ in range(3):
                self.cliente().sudo().write({'estado': 'humano', 'asignada_a': self.carla.id,
                                             'reparto_desde': fields.Datetime.now()})
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, self.vendedora, 'Se queda con quien lo tenía')

    def test_la_ayuda_del_ajuste_dice_lo_que_pasa(self):
        ayuda = self.env['dcasa.juan.ajustes']._fields['reparto_max_esperando'].help
        for frase in ('antes de abrir', 'dentro del horario se le da a una vendedora activa aunque todas',
                      '«Por turnos» no lo mira al dar un cliente nuevo'):
            self.assertIn(frase, ayuda)
        self.assertNotIn('ninguna vendedora recibe', ayuda)


@tagged('post_install', '-at_install')
class TestYaLaAtendiSaleDelReparto(TomarCase):

    def test_ya_la_atendi_limpia_reparto_desde(self):
        self.activa(self.vendedora)
        conv = self.pasar()
        self.assertTrue(conv.reparto_desde and conv.traspaso_sin_atender_desde)
        conv.with_user(self.vendedora).action_traspaso_atendido()
        self.assertFalse(conv.reparto_desde)
        self.assertEqual(self.Reparto._esperando_del_reparto(self.vendedora)[self.vendedora.id], 0)
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.activa(self.beto)
            self.assertEqual(self.Reparto._cron_reasignar(), 0)
        self.assertEqual(conv.asignada_a, self.vendedora)
