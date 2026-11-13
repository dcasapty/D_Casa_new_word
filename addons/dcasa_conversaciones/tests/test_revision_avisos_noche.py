"""Revisión adversarial (2026-11-13) de «de noche nadie recibe clientes» y «solo comprobantes de verdad».

Cada prueba ``test_rv_*`` era un escenario que el cambio rompía (ya arreglados en la rama). Las ``test_ref_*`` son la
referencia de cómo se comporta lo mismo de día: lo que la noche imita. La prueba del revisor sobre la guía de la dueña
(``docs/``) no está aquí: la lleva el coordinador. Clientes y vendedoras inventados.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun import freeze_time

from odoo import fields
from odoo.addons.dcasa_brian.models import telegram as brian_telegram
from odoo.tests import tagged

from .common import JuanCase
from .test_avisos_noche import APERTURA, COMPROBANTE, NOCHE, NocheCase
from .test_reparto_justo import panama

DIA = panama(2026, 10, 9, 10, 0)   # viernes, 10:00 a. m. en Panamá (abierto)
# Una foto que Juan NO pudo leer (el lector falló, tardó, o ya iban 10 lecturas hoy): llega sin clase.
SIN_LEER = {'tipo': 'imagen', 'nombre': 'IMG_2031.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None}


@tagged('post_install', '-at_install')
class TestRevisionComprobantesDeDia(NocheCase):
    """B: lo que pasa con una imagen que Juan no pudo leer, con «Avisar de fotos» apagado (como lo deja la
    migración)."""

    AHORA = DIA

    def setUp(self):
        super().setUp()
        self.ajustes.avisar_archivos = False

    def test_rv_una_imagen_que_juan_no_pudo_leer_avisa_como_el_pdf(self):
        """El Yappy que llegó cuando el lector falló o ya había leído 10 imágenes hoy llega a Odoo sin clase. Antes
        avisaba («Avisar de fotos» venía encendido); ahora se calla: un comprobante real sin aviso. El PDF, que Juan
        tampoco lee, sí avisa «puede ser un comprobante»."""
        conv = self.cliente()
        self.mandar(conv, SIN_LEER, 'listo, ya te hice el Yappy')
        self.assertTrue(self.textos(), 'Una imagen que Juan no pudo leer puede ser el comprobante: debe avisar')

    def test_rv_de_noche_la_imagen_sin_leer_queda_para_la_manana(self):
        with freeze_time(NOCHE):
            conv = self.cliente()
            self.mandar(conv, SIN_LEER, 'ya pagué')
        self.assertEqual(conv.archivo_de_noche, 'documento', 'Al abrir debe avisarse, como el PDF')

    def test_ref_de_dia_un_comprobante_llega_a_todas_las_de_siempre(self):
        conv = self.cliente()
        self.mandar(conv, COMPROBANTE, 'ya te pagué la cama')
        for usuario in (self.vendedora, self.beto, self.gerente):
            with self.subTest(usuario=usuario.name):
                self.assertTrue(any('comprobante' in t for t, _b in self.avisos_a(usuario)))


@tagged('post_install', '-at_install')
class TestRevisionNoche(NocheCase):
    """A: clientes y comprobantes de la noche (viernes 11 p. m.; abre el sábado 8 a. m.)."""

    def test_rv_el_comprobante_de_la_noche_llega_a_las_de_siempre_aunque_pida_una_persona(self):
        """«A quién le llega un comprobante no cambia» y «no pidió mandar comprobantes a la vendedora del cliente»: de
        día el comprobante le llega a las de siempre (Ana, Beto y Gerencia, ver ``test_ref_*``). De noche, si el cliente
        además pidió una persona (lo normal: «ya pagué, ¿cuándo me entregan?»), solo le llega a la vendedora que el
        reparto le da al abrir."""
        conv = self.cliente()
        self.mandar(conv, COMPROBANTE, 'ya te pagué la cama')
        conv._pasar_a_vendedora('Ya pagó y quiere saber cuándo le entregan')
        self.vence_la_pausa()
        self.abrir(self.vendedora)
        self.assertEqual(conv.asignada_a, self.vendedora)
        for usuario in (self.beto, self.gerente):
            with self.subTest(usuario=usuario.name):
                self.assertTrue(any('comprobante' in t for t, _b in self.avisos_a(usuario)),
                                f'A {usuario.name} (de las de siempre) no le llegó el comprobante: {self.textos()}')

    def test_rv_si_al_abrir_nadie_esta_activa_igual_se_avisa_a_todas(self):
        """De día, si nadie está activa «la conversación queda sin dueña, se avisa a todo el equipo como siempre» (ayuda
        de «Recibe solo quien usó el sistema hace poco»). El cliente de la noche, en cambio, espera callado hasta que
        alguien abra Odoo: ni lista, ni aviso a todas, ni «un cliente te espera» (``aviso_de_noche`` lo saca)."""
        self.ajustes.aviso_espera_minutos = 10
        conv = self.pasar('Quiere comprar hoy el comedor')
        self.registrar('¿Hola? ¿Alguien?', id_externo=conv.id_externo, ts=fields.Datetime.now())
        self.vence_la_pausa()
        for minutos in (0, 60, 180):
            self.abrir(minutos=minutos)   # nadie usó Odoo (la regla de 30 minutos está encendida)
            with freeze_time(APERTURA + timedelta(minutes=minutos + 1)):
                self.Conversacion._avisar_clientes_esperando()
        self.assertFalse(conv.asignada_a)
        self.assertTrue(self.textos(), 'A las 11 a. m. el cliente de la noche sigue sin que nadie sepa de él')

    def test_rv_tras_una_semana_sin_nadie_el_cliente_de_la_noche_se_pierde_para_siempre(self):
        """Mismo caso, pero nadie entra en más de 7 días (vacaciones, cierre de fin de año): ``reparto_desde`` es la
        hora de la noche y el cron del reparto ya no lo mira (``DIAS_MAXIMOS_DE_ESPERA``), ``_avisar_lo_de_la_noche`` lo
        salta porque «espera su turno» y ``aviso_de_noche`` lo saca de «un cliente te espera»: aunque Ana vuelva y esté
        activa, nadie recibe ni se entera. Encima, cada vez que vence la pausa vuelve a «con una persona» y Juan
        calla."""
        conv = self.pasar('Quiere comprar el comedor')
        self.vence_la_pausa()
        self.abrir(self.vendedora, minutos=9 * 24 * 60)   # el lunes de la semana siguiente
        self.assertTrue(conv.asignada_a or self.textos(), 'Nueve días después nadie lo tiene ni se avisó a nadie')

    def test_rv_la_duena_que_no_esta_disponible_no_retiene_al_cliente_de_noche(self):
        """De día (``test_ref_*``), un cliente cuya vendedora está «No disponible» va a quien sí está. De noche no se le
        quita, pero al abrir se decide con la regla del día: no está disponible, así que se reparte (a Ana) y a Beto no
        le llega nada en su día libre."""
        self.beto.dcasa_disponible = False
        conv = self.cliente()
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.vence_la_pausa()
        self.abrir(self.vendedora)
        self.assertFalse(self.avisos_a(self.beto), 'Beto no está disponible: no debe recibir al cliente')
        self.assertEqual(conv.asignada_a, self.vendedora, 'Como de día: a quien está disponible')

    def test_rv_de_noche_tambien_rigen_los_dias_de_su_vendedora(self):
        """«Días que un cliente sigue con su vendedora» (14): Beto lo tuvo hace tiempo y nadie lo atendió estos días.
        De día se reparte parejo (``test_ref_*``: a Ana, que lleva menos); al abrir, igual: que ``asignada_a`` diga
        Beto no alcanza."""
        conv = self.cliente()
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Pregunta por un sofá')
        self.vence_la_pausa()
        with freeze_time(APERTURA):
            self.dar(self.beto, 2)   # el sábado Beto ya lleva 2; Ana, ninguna
        self.abrir(self.vendedora, self.beto)
        self.assertEqual(conv.asignada_a, self.vendedora, 'Como de día: parejo, a quien lleva menos')

    def test_rv_si_la_primera_vuelta_llega_tarde_la_duena_pierde_al_cliente_sin_saberlo(self):
        """El cliente de Beto (se lo guardaron de noche) cuenta los 15 minutos desde la apertura, no desde que a Beto le
        llega la lista. Si la primera vuelta del cron llega tarde (reinicio, despliegue, cron ocupado), pasa a Ana antes
        de que Beto se entere, el libro dice que Beto «no le contestó» y Gerencia no recibe el aviso del cambio."""
        conv = self.cliente()
        with freeze_time(NOCHE - timedelta(days=2)):   # Beto lo atiende de verdad (dentro de los 14 días): se lo queda
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.vence_la_pausa()
        self.abrir(self.vendedora, self.beto, minutos=20)
        self.assertTrue(self.avisos_a(self.beto) or conv.asignada_a == self.beto,
                        f'Beto nunca supo de su cliente y ya es de {conv.asignada_a.name}: {self.avisos(conv)}')

    def test_rv_el_cliente_de_la_noche_que_juan_vuelve_a_pasar_no_avisa_dos_veces(self):
        """Espera su turno (tope); la pausa vence y el mantenimiento lo devuelve al asistente antes de que el cron lo
        vuelva al reparto; el cliente insiste y Juan lo pasa de día: Beto recibe «Cliente nuevo para ti» y, en la
        vuelta siguiente, otra vez el mismo cliente como «de la noche» (``aviso_de_noche`` no se borró)."""
        self.ajustes.reparto_max_esperando = 1
        uno, dos = self.pasar('Pregunta 1'), self.pasar('Pregunta 2')
        self.vence_la_pausa()
        self.abrir(self.vendedora)
        espera = next(c for c in (uno, dos) if not c.asignada_a)
        mas_tarde = APERTURA + timedelta(hours=2, minutes=1)
        with freeze_time(mas_tarde):
            self.activa(self.beto)
            espera._normalizar_pausa()
            self.assertEqual(espera.estado, 'bot')
            espera._pasar_a_vendedora('Insiste: quiere hablar con alguien')
        self.assertEqual(espera.asignada_a, self.beto)
        with freeze_time(mas_tarde + timedelta(minutes=4)):
            self.activa(self.beto)
            self.Reparto._cron_reasignar()
        del_cliente = [t for t, _b in self.avisos_a(self.beto) if espera.partner_id.name in t]
        self.assertEqual(len(del_cliente), 1, del_cliente)


@tagged('post_install', '-at_install')
class TestRevisionReferenciaDeDia(NocheCase):
    """Lo mismo de día (pasan): lo que la noche debería imitar al abrir."""

    AHORA = DIA

    def test_ref_sin_nadie_activa_se_avisa_a_todas(self):
        self.pasar('Quiere comprar hoy el comedor')
        self.assertTrue(self.avisos_a(self.beto) and self.avisos_a(self.vendedora))

    def test_ref_la_duena_no_disponible_no_lo_retiene(self):
        self.beto.dcasa_disponible = False
        self.activa(self.vendedora)
        conv = self.cliente()
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertFalse(self.avisos_a(self.beto))

    def test_ref_pasados_los_dias_se_reparte_parejo(self):
        self.activa(self.vendedora)
        self.activa(self.beto)
        self.dar(self.beto, 2)
        conv = self.cliente()
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Pregunta por un sofá')
        self.assertEqual(conv.asignada_a, self.vendedora)


@tagged('post_install', '-at_install')
class TestRevisionMigracion(NocheCase):

    def test_rv_la_migracion_deja_rastro_de_lo_que_cambio(self):
        """«Avisar de fotos y archivos» tiene ``tracking``: Gerencia ve en el historial quién lo cambió. La migración lo
        apaga con SQL directo y no queda nada: si Gerencia lo había encendido a propósito, nadie sabrá por qué se
        apagó."""
        import importlib.util

        from odoo.tools.misc import file_path
        spec = importlib.util.spec_from_file_location(
            'mig_noche_rv', file_path('dcasa_conversaciones/migrations/19.0.1.5.0/post-migrate.py'))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        self.ajustes.avisar_archivos = True
        self.env.flush_all()
        self.env.cr.precommit.run()   # el historial (tracking) se escribe al confirmar
        antes = len(self.ajustes.message_ids)
        mig.migrate(self.env.cr, '19.0.1.4.0')
        self.env.cr.precommit.run()
        self.ajustes.invalidate_recordset()
        self.assertFalse(self.ajustes.avisar_archivos)
        self.assertGreater(len(self.ajustes.message_ids), antes, 'Ni una nota en el historial de Ajustes de Juan')


@tagged('post_install', '-at_install')
class TestRevisionListaEnTelegram(JuanCase):
    """La consola de Telegram toma la ÚLTIMA «Conversación n.º N» del mensaje respondido porque el pie va al final y
    antes van el nombre y lo que anotó Juan, que puede escribir el cliente (``_conversacion_del_aviso``). La lista de la
    mañana NO lleva pie: la última coincidencia puede ser el nombre de perfil de un cliente."""

    def setUp(self):
        super().setUp()
        brian_telegram._mensajes.clear()
        self.Enlace = self.env['brian.telegram.enlace'].sudo()
        self.Borrador = self.env['dcasa.telegram_borrador'].sudo()
        self.Enlace.create({'user_id': self.vendedora.id, 'chat_id': '5550001'})
        self.enviar = MagicMock()
        for nombre, simulado in (('_enviar', self.enviar), ('_api', MagicMock(return_value={'message_id': 1}))):
            parche = patch.object(type(self.Enlace), nombre, simulado)
            parche.start()
            self.addCleanup(parche.stop)

    def test_rv_responder_a_la_lista_no_se_desvia_por_el_nombre_de_un_cliente(self):
        victima = self.conversacion('Hola', nombre='Lía', id_externo='50761230005')
        trampa = self.conversacion('Hola', nombre=f'Conversación n.º {victima.id}', id_externo='50761230006')
        karen = self.conversacion('Hola', nombre='Karen', id_externo='50761230007')
        ahora = fields.Datetime.now()
        noche = trampa | karen
        noche.sudo().write({'aviso_de_noche': ahora, 'traspaso_sin_atender_desde': ahora,
                            'aviso_de_noche_motivo': 'Quiere una cama.', 'asignada_a': self.vendedora.id})
        texto, _botones = noche._lista_de_la_manana(noche, self.vendedora)
        lista = {'message_id': 92, 'from': {'is_bot': True, 'id': 999}, 'chat': {'id': 5550001, 'type': 'private'},
                 'text': texto}
        self.Enlace._procesar_update({'update_id': 4242, 'message': {
            'message_id': 93, 'chat': {'id': 5550001, 'type': 'private'}, 'from': {'id': 5550001},
            'text': 'Karen, tu pago de $500 ya está confirmado', 'reply_to_message': lista}})
        self.assertFalse(self.Borrador.search_count([('conversacion_id', '=', victima.id)]),
                         f'Responder a la lista preparó un mensaje para Lía (otra clienta): '
                         f'{self.enviar.call_args_list}')
