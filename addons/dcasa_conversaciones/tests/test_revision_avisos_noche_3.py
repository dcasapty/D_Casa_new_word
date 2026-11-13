"""Revisión adversarial, tercera vuelta (2026-11-13), sobre a57dec6. ``test_rv3_*``: escenarios que fallaban en la rama
(ya arreglados). Clientes y vendedoras inventados."""
from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .test_avisos_noche import NOCHE, NocheCase
from .test_reparto_justo import panama

DIA = panama(2026, 10, 9, 10, 0)          # viernes 10:00 a. m. (abierto)
IMAGEN = {'tipo': 'imagen', 'nombre': 'foto.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None}
# Lo que manda el Juan nuevo por una foto de Messenger o Instagram: Meta da solo la URL, Juan no la baja ni la lee y la
# marca «sin_bajar» (antes de este arreglo, «fallo»; ver juan/test/revision/revision_ronda3.test.ts).
FOTO_DE_INSTAGRAM = {**IMAGEN, 'clase': 'sin_leer', 'sin_leer': 'sin_bajar'}
TOPE = {**IMAGEN, 'clase': 'sin_leer', 'sin_leer': 'tope'}


@tagged('post_install', '-at_install')
class TestRevision3DeDia(NocheCase):

    AHORA = DIA

    def setUp(self):
        super().setUp()
        self.ajustes.avisar_archivos = False

    def test_rv3_las_fotos_de_instagram_avisan_cada_10_minutos_y_alarman_a_gerencia(self):
        """Por Messenger e Instagram el lector nunca lee (Meta da solo la URL), pero Juan las marca «fallo»: cada foto
        de una conversación avisa «puede ser un comprobante» cada 10 minutos, y tres mensajes así en una hora (de
        cualquier cliente) le dicen a Gerencia que «el lector de imágenes está fallando», aunque funciona."""
        conv = self.cliente()
        for n in range(6):
            with freeze_time(DIA + timedelta(minutes=11 * n)):
                self.mandar(conv, {**FOTO_DE_INSTAGRAM, 'nombre': f'ig{n}.jpg'}, f'¿y esta? {n}')
        alarma = [t for t, _b in self.avisos_a(self.gerente) if 'Juan no está leyendo las fotos' in t]
        self.assertFalse(alarma, f'Alarma falsa a Gerencia: {alarma[:1]}')
        self.assertLessEqual(len(self.avisos_a(self.vendedora)), 1, 'Seis capturas de Instagram, seis avisos')

    def test_rv3_como_se_dice_aqui_que_ya_se_pago(self):
        """Con «tope» o «apagado», el segundo aviso del día solo sale si el cliente habla de pago. Formas de decirlo en
        Panamá que la lista no reconoce: cada una se queda sin aviso."""
        for texto in ('listo, ya te yapié', 'ya cancelé la cama', 'la cuota ya está pagada', 'ahí te envié la plata'):
            with self.subTest(texto=texto):
                self.enviar.reset_mock()
                conv = self.cliente()
                self.mandar(conv, TOPE, 'mira esta')                       # gasta el aviso del día
                with freeze_time(DIA + timedelta(minutes=15)):
                    self.mandar(conv, {**TOPE, 'nombre': 'pago.jpg'}, texto)
                self.assertEqual(len(self.avisos_a(self.vendedora)), 2, self.avisos_a(self.vendedora))

    def test_rv3_preguntar_por_el_deposito_no_es_hablar_de_pago(self):
        """«Depósito» también es la bodega: «¿lo tienen en depósito?» cuenta como hablar de pago."""
        conv = self.cliente()
        self.mandar(conv, TOPE, 'mira esta')
        with freeze_time(DIA + timedelta(minutes=15)):
            self.mandar(conv, {**TOPE, 'nombre': 'otra.jpg'}, '¿y esta la tienen en depósito?')
        self.assertEqual(len(self.avisos_a(self.vendedora)), 1, self.avisos_a(self.vendedora))


@tagged('post_install', '-at_install')
class TestRevision3Rescate(NocheCase):

    def de_beto(self):
        conv = self.cliente()
        with freeze_time(NOCHE - timedelta(days=2)):   # Beto lo atendió anteayer: es su vendedora de estos días
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv.sudo().asignada_a = self.beto
        conv._pasar_a_vendedora('Quiere saber cuándo le llega')
        self.vence_la_pausa()
        return conv

    def test_rv3_el_rescate_no_acusa_a_la_que_todavia_puede_llegar(self):
        """«Pasar a otra» en 10 minutos (Ajustes) y «Recibe solo quien usó el sistema» en 30: el cliente espera a Beto
        hasta las 8:30 (``_soltar_lo_de_la_noche_ajeno``), pero el rescate (``apertura + 2 × 10``) se lo pasa a Ana a
        las 8:20 diciendo que Beto «no le contestó» (nunca le llegó nada) y avisa a Gerencia de un cambio de
        vendedora."""
        self.ajustes.reparto_reasignar_minutos = 10
        conv = self.de_beto()
        for minutos in (0, 10, 20, 25):
            self.abrir(self.vendedora, minutos=minutos)
        self.assertNotIn('Beto Vendedor no le contestó', self.avisos(conv))
        self.assertFalse([t for t, _b in self.avisos_a(self.gerente) if 'cambió de vendedora' in t])

    def test_rv3_si_la_primera_vuelta_llega_muy_tarde_la_duena_pierde_al_cliente_sin_saberlo(self):
        """Si la primera vuelta tras abrir llega pasados ``2 × reparto_reasignar_minutos`` (reinicio, despliegue), el
        rescate corre ANTES que el aviso de la mañana en la misma vuelta: Beto (activa) nunca recibe la lista y el libro
        dice que «no le contestó»."""
        conv = self.de_beto()
        self.abrir(self.vendedora, self.beto, minutos=35)
        self.assertTrue([t for t, _b in self.avisos_a(self.beto) if conv.partner_id.name in t]
                        or conv.asignada_a == self.beto, self.avisos(conv))
