"""Revisión adversarial, segunda vuelta (2026-11-13), sobre 9fdbaa1. ``test_rv2_*``: escenarios que fallaban en la rama
(ya arreglados, adaptados a lo que decidió el coordinador); ``test_ref2_*``: lo mismo de día (pasa). Clientes y
vendedoras inventados."""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.tests import tagged

from ..models import conversacion_noche
from .test_avisos_noche import APERTURA, COMPROBANTE, NOCHE, NocheCase
from .test_reparto_justo import panama

DIA = panama(2026, 10, 9, 10, 0)          # viernes 10:00 a. m. (abierto)
SIN_LEER = {'tipo': 'imagen', 'nombre': 'IMG_2031.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None}
# Lo que manda el Juan nuevo cuando el lector está apagado (o sin cupo): «sin_leer» con su porqué.
SIN_LEER_APAGADO = {**SIN_LEER, 'clase': 'sin_leer', 'sin_leer': 'apagado'}
SIN_LEER_TOPE = {**SIN_LEER, 'clase': 'sin_leer', 'sin_leer': 'tope'}
# Lo que manda HOY el Juan de producción por un sticker de WhatsApp (sin clase); el nuevo lo manda como «otra».
STICKER_VIEJO = {'tipo': 'imagen', 'nombre': 'sticker.webp', 'mime': 'image/webp', 'url': None, 'base64': None}
STICKER_NUEVO = {**STICKER_VIEJO, 'clase': 'otra'}


@tagged('post_install', '-at_install')
class TestRevision2DeDia(NocheCase):

    AHORA = DIA

    def setUp(self):
        super().setUp()
        self.ajustes.avisar_archivos = False   # como lo deja la migración

    def test_rv2_con_el_lector_caido_cada_captura_avisa_como_posible_comprobante(self):
        """Con el lector apagado (RECONOCER_IMAGENES) o sin cupo, o con el cliente en «descanso» del anti-spam, TODA
        imagen llega sin leer. Juan dice por qué («apagado», «tope») y, si el cliente no habla de pago, a lo más un
        aviso por conversación al día (antes: uno cada 10 minutos). Gerencia se entera, una vez al día, de que el lector
        no está leyendo."""
        del_lector = []
        for adjunto in (SIN_LEER_APAGADO, SIN_LEER_TOPE):
            with self.subTest(sin_leer=adjunto['sin_leer']):
                self.enviar.reset_mock()
                conv = self.cliente()
                for n in range(6):
                    with freeze_time(DIA + timedelta(minutes=11 * n)):
                        self.mandar(conv, {**adjunto, 'nombre': f'captura{n}.jpg'}, f'¿y esta la tienen? {n}')
                a_ana = self.avisos_a(self.vendedora)
                self.assertLessEqual(len(a_ana), 1, f'{len(a_ana)} avisos en una hora: {a_ana[:1]}')
                del_lector += [t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo las fotos' in t]
        self.assertEqual(len(del_lector), 1, 'Gerencia sabe (una vez al día) que el lector no está leyendo')

    def test_rv2_odoo_nuevo_con_el_juan_de_produccion_un_sticker_avisa(self):
        """El Juan nuevo manda el sticker como «otra»: no avisa. (En esta entrega Juan sale ANTES que Odoo: la ventana
        «Odoo nuevo con el Juan de hoy» no se da. Si se diera, una imagen sin clase ni porqué se toma como «fallo» y
        avisa, uno cada 10 minutos por conversación: lo decidió el coordinador.)"""
        conv = self.cliente()
        self.mandar(conv, STICKER_NUEVO, '(el cliente mandó un sticker)')
        self.assertFalse(self.textos(), self.textos())

    def test_ref2_de_dia_sin_nadie_activa_se_recuerda_al_que_espera(self):
        conv = self.pasar('Quiere comprar hoy el comedor')        # nadie activa: aviso a todas
        self.registrar('¿Hola? ¿Alguien?', id_externo=conv.id_externo, ts=DIA + timedelta(minutes=5))
        self.enviar.reset_mock()
        with freeze_time(DIA + timedelta(minutes=20)):
            self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1)

    def test_ref2_de_dia_lo_asignado_a_mano_no_lo_mueve_el_reparto(self):
        self.activa(self.vendedora)
        conv = self.pasar('Duda')
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.Conversacion.with_user(self.gerente).asignar(conv.id, self.carla.id)
        with freeze_time(DIA + timedelta(minutes=40)):
            self.activa(self.vendedora)
            self.Reparto._cron_reasignar()
        self.assertEqual(conv.asignada_a, self.carla)

    def test_ref2_de_dia_la_que_no_vino_no_recibe(self):
        conv = self.cliente()
        with freeze_time(DIA - timedelta(days=2)):
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        self.activa(self.vendedora)        # Beto no vino hoy (no usó Odoo), pero nadie lo marcó «No disponible»
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.assertEqual(conv.asignada_a, self.vendedora)
        self.assertFalse(self.avisos_a(self.beto))


@tagged('post_install', '-at_install')
class TestRevision2Noche(NocheCase):

    def test_rv2_sin_nadie_al_abrir_no_vuelve_a_sonar_aunque_el_cliente_insista(self):
        """De día (``test_ref2_*``), el que espera sin dueña recibe «un cliente espera respuesta» si nadie le contesta.
        El de la noche sin nadie disponible recibe UN aviso a todas al abrir y después nada en todo el día, aunque
        escriba otra vez: ``aviso_de_noche`` lo saca del aviso de espera."""
        conv = self.pasar('Quiere comprar hoy el comedor')
        self.vence_la_pausa()
        self.abrir(minutos=31)                         # pasado el plazo y nadie activa: un aviso a todas
        self.assertTrue(conv.aviso_de_noche_a_todas)
        self.registrar('¿Hola? ¿Alguien?', id_externo=conv.id_externo, ts=APERTURA + timedelta(hours=1))
        self.enviar.reset_mock()
        with freeze_time(APERTURA + timedelta(hours=1, minutes=20)):
            self.assertEqual(self.Conversacion._avisar_clientes_esperando(), 1,
                             'Escribió otra vez y nadie le contesta: como de día, se recuerda')

    def test_rv2_lo_que_gerencia_asigna_a_mano_no_lo_mueve_el_reparto(self):
        """«``reparto_desde`` se borra en cuanto alguien del equipo [...] la asigna [...] a mano: desde ahí es de una
        persona y «pasar a otra si no contesta» no la toca» (revisión 2026-11-03). Con el cliente de la noche, el cron
        le vuelve a poner ``reparto_desde`` (``_volver_al_reparto_lo_de_la_noche``) y a los 15 minutos se lo pasa a
        otra; si Gerencia se lo asignó a alguien «No disponible» o a sí misma, ``_soltar_lo_de_la_noche_ajeno`` se lo
        quita en la vuelta siguiente."""
        conv = self.pasar('Quiere una cotización')
        self.vence_la_pausa()
        self.abrir()                                   # nadie activa todavía
        with freeze_time(APERTURA + timedelta(minutes=7)):
            self.Conversacion.with_user(self.gerente).asignar(conv.id, self.carla.id)
        self.assertEqual(conv.asignada_a, self.carla)
        for minutos in (10, 40):
            self.abrir(self.vendedora, minutos=minutos)
        self.assertEqual(conv.asignada_a, self.carla, self.avisos(conv))

    def test_rv2_la_duena_que_no_vino_no_recibe_al_abrir(self):
        """Regla de la dueña (2026-11-03, «Recibe solo quien usó el sistema hace poco»): «si no vino, no entró al
        sistema y no recibe, aunque nadie la haya marcado No disponible (los turnos rotan)». Al abrir, Beto (su
        vendedora de estos días, «Disponible» pero hoy no vino) se queda con el cliente y le llega el Telegram en su día
        libre; de día (``test_ref2_*``) iría a Ana, que sí está."""
        conv = self.cliente()
        with freeze_time(NOCHE - timedelta(days=2)):
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.vence_la_pausa()
        self.abrir(self.vendedora)                     # solo Ana usa Odoo
        self.assertFalse(self.avisos_a(self.beto), 'Beto no vino hoy: no debe recibir nada')

    def test_rv2_un_segundo_comprobante_de_noche_tambien_se_avisa(self):
        """El cliente espera su turno de un día para otro (nadie disponible). El primer comprobante se avisó a las de
        siempre (``archivo_de_noche_avisado``). La noche siguiente manda OTRO comprobante: como la prioridad es la
        misma, ``_anotar_archivo_de_noche`` no lo vuelve a marcar y no le llega a nadie."""
        conv = self.cliente()
        self.mandar(conv, COMPROBANTE, 'abono de la cama')
        conv._pasar_a_vendedora('Abonó y quiere saber el saldo')
        self.vence_la_pausa()
        self.abrir()                                   # sábado: nadie disponible; aviso a todas (con el comprobante)
        avisos_de_pago = lambda: [t for t, _b in self.avisos_a(self.gerente) if 'comprobante' in t]   # noqa: E731
        self.assertEqual(len(avisos_de_pago()), 1)
        with freeze_time(panama(2026, 10, 10, 23, 0)):  # sábado 11 p. m.: la pausa venció, manda el segundo abono
            conv._normalizar_pausa()
            self.mandar(conv, COMPROBANTE, 'segundo abono')
        with freeze_time(panama(2026, 10, 11, 8, 0)):   # domingo, abre
            self.Reparto._cron_reasignar()
        self.assertEqual(len(avisos_de_pago()), 2, 'El segundo comprobante no le llegó a nadie')

    def test_rv2_con_mas_de_un_lote_el_cliente_de_su_vendedora_se_queda_esperando(self):
        """El cron ya no le pasa a otra al cliente de su vendedora mientras ``aviso_de_noche`` siga puesto, y ese aviso
        solo lo manda ``_avisar_lo_de_la_noche``, que mira las primeras ``LOTE_DE_LA_MANANA`` (200) por id. Con más
        pendientes que eso (los que esperan turno se quedan en la lista), el de Beto nunca entra: ni aviso, ni pasar a
        otra. Aquí el lote es 2 para no crear 200 clientes."""
        self.ajustes.reparto_max_esperando = 1
        esperan = [self.pasar(f'Pregunta {n}') for n in range(3)]
        de_beto = self.cliente()
        with freeze_time(NOCHE - timedelta(days=2)):
            self.Reparto._anotar(de_beto, self.beto, 'manual', 'Asignada a mano.')
        de_beto.sudo().asignada_a = self.beto
        de_beto._pasar_a_vendedora('Es cliente de Beto')
        self.vence_la_pausa()
        with patch.object(conversacion_noche, 'LOTE_DE_LA_MANANA', 2):
            for minutos in (0, 30, 60, 120):
                self.abrir(self.vendedora, minutos=minutos)   # Ana atiende; Beto llega más tarde
        self.assertTrue(any(c.asignada_a for c in esperan))
        de_su_cliente = [t for t, _b in self.textos_con(de_beto)]
        self.assertTrue(de_su_cliente or de_beto.asignada_a != self.beto,
                        f'Dos horas después nadie sabe del cliente de Beto (estado {de_beto.estado}) y nadie más lo '
                        f'tiene')

    def textos_con(self, conv):
        return [(c.args[1], c.kwargs.get('botones')) for c in self.enviar.call_args_list
                if conv.partner_id.name in c.args[1]]


@tagged('post_install', '-at_install')
class TestRevision2Migracion(NocheCase):

    def test_rv2_la_nota_de_la_migracion_dice_que_se_encendio_lo_de_la_noche(self):
        """Al actualizar, Odoo crea la columna nueva y la llena con su valor de fábrica (``_init_column``: True) ANTES
        del post-migrate: la migración ve el interruptor ya encendido, no escribe nada y su nota solo habla de las
        fotos. En el historial de Ajustes nadie verá que «De noche nadie recibe clientes» se encendió en producción."""
        import importlib.util

        from odoo.tools.misc import file_path
        self.env.cr.execute('UPDATE dcasa_juan_ajustes SET reparto_nadie_de_noche = NULL, avisar_archivos = TRUE')
        self.env['dcasa.juan.ajustes']._init_column('reparto_nadie_de_noche')   # lo que hace Odoo al crear la columna
        self.env.invalidate_all()
        spec = importlib.util.spec_from_file_location(
            'mig_noche_rv2', file_path('dcasa_conversaciones/migrations/19.0.1.5.0/post-migrate.py'))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        mig.migrate(self.env.cr, '19.0.1.4.0')
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()
        historial = ' '.join(str(b) for b in self.ajustes.message_ids.mapped('body'))
        self.assertIn('De noche nadie recibe clientes', historial)


@tagged('post_install', '-at_install')
class TestRevision2Rescate(NocheCase):

    def test_rv2_si_el_aviso_de_la_manana_falla_el_cliente_de_su_vendedora_no_se_rescata(self):
        """Antes, si el aviso de la mañana fallaba (cualquier excepción: queda en el log y el savepoint la tapa), «pasar
        a otra» rescataba al cliente a los 15 minutos. Ahora el cron lo salta mientras ``aviso_de_noche`` siga puesto:
        sin aviso y sin rescate, para siempre."""
        conv = self.cliente()
        with freeze_time(NOCHE - timedelta(days=2)):
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Es cliente de Beto')
        self.vence_la_pausa()
        with patch.object(type(self.Conversacion), '_avisar_lo_de_la_noche', side_effect=RuntimeError('falla')):
            for minutos in (0, 30, 60, 120):
                self.abrir(self.vendedora, self.beto, minutos=minutos)
        self.assertNotEqual(conv.asignada_a, self.beto, 'Dos horas sin aviso a nadie y nadie lo rescató')


@tagged('post_install', '-at_install')
class TestRevision2MananaNormal(NocheCase):

    def test_rv2_una_manana_normal_no_es_un_aviso_a_todas(self):
        """«Recibe solo quien usó el sistema hace poco» mide el uso de Odoo: a la primera vuelta tras abrir (8:00) casi
        nunca hay nadie activa todavía. El respaldo «no hay ninguna vendedora: avisar a las de siempre» salta entonces
        CADA mañana: a las 8:00 la lista de la noche le llega a todas (también a la que libra y a Gerencia) y a los
        cinco minutos, cuando entra Ana, le llega otra vez a ella. La dueña pidió un solo aviso por vendedora."""
        clientes = [self.pasar(f'Pregunta {n}') for n in range(2)]
        self.vence_la_pausa()
        self.abrir()                                   # 8:00: nadie ha abierto Odoo todavía
        self.abrir(self.vendedora, minutos=5)          # 8:05: entra Ana
        self.assertTrue(all(c.asignada_a == self.vendedora for c in clientes))
        self.assertFalse(self.avisos_a(self.beto), f'A Beto (no vino) le llegó: {self.avisos_a(self.beto)}')
        self.assertFalse(self.avisos_a(self.gerente), 'A Gerencia le llegó la lista de la noche')
        self.assertEqual(len(self.avisos_a(self.vendedora)), 1, 'A Ana: un solo aviso con su lista')
