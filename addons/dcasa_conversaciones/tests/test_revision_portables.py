"""Revisión adversarial (2026-11-13): escenarios con la regla de la noche APAGADA o de día, escritos solo con ayudas
que ya existían en 570d3c2 (``TomarCase``), para correrlos igual antes y después del cambio. Pasan en 570d3c2 y fallan
en la rama: son cambios de comportamiento. Clientes y vendedoras inventados."""
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from .test_reparto_tomar import TomarCase

PDF = {'tipo': 'documento', 'nombre': 'transferencia.pdf', 'mime': 'application/pdf', 'url': None, 'base64': None,
       'sensible': False, 'clase': None}
CEDULA = {'tipo': 'imagen', 'nombre': 'cedula.jpg', 'mime': 'image/jpeg', 'url': None, 'base64': None,
          'sensible': True, 'clase': 'identidad'}


@tagged('post_install', '-at_install')
class TestRevisionPortable(TomarCase):
    """Viernes 10:00 a. m. en Panamá (abierto), reparto parejo, «recibe solo quien está activa» (30 min)."""

    def textos(self):
        return [c.args[1] for c in self.enviar.call_args_list]

    def test_rv_sin_duena_el_cron_respeta_el_tope_como_antes(self):
        """Interruptor apagado (o de día): un cliente que quedó sin dueña porque nadie estaba activa. Antes, el cron se
        lo daba a la primera activa CON LUGAR (tope). Ahora, con «Parejo», va a su vendedora de siempre aunque esté
        llena, y el libro dice «misma» en vez de «reasignada»."""
        self.ajustes.reparto_max_esperando = 1
        conv = self.cliente()
        with freeze_time(self.AHORA - timedelta(days=2)):   # Beto lo atendió anteayer
            self.Reparto._anotar(conv, self.beto, 'manual', 'Asignada a mano.')
        conv._pasar_a_vendedora('Duda')      # nadie activa: queda sin dueña
        self.assertFalse(conv.asignada_a)
        with freeze_time(self.AHORA + timedelta(minutes=20)):
            self.activa(self.vendedora)
            self.activa(self.beto)
            self.cliente().sudo().write({'estado': 'humano', 'asignada_a': self.beto.id,
                                         'reparto_desde': fields.Datetime.now()})   # Beto ya tiene 1 (el tope)
            self.Reparto._cron_reasignar()
        self.assertEqual(conv.asignada_a, self.vendedora, 'Antes: a la activa con lugar')
        linea = self.Reparto.search([('conversacion_id', '=', conv.id)], order='id desc', limit=1)
        self.assertEqual(linea.regla, 'reasignada')

    def test_rv_la_cedula_avisa_aunque_hace_poco_se_avisara_de_un_pdf(self):
        """Antes la cédula avisaba siempre (sin la pausa de 10 minutos). Ahora, si en el mismo mensaje viene también un
        PDF, gana «documento» y, si hubo un aviso de archivo hace menos de 10 minutos, no sale NADA: ni la cédula."""
        for fotos in (False, True):
            with self.subTest(avisar_archivos=fotos):
                self.enviar.reset_mock()
                self.ajustes.avisar_archivos = fotos
                conv = self.cliente()
                self.registrar('ahí va la transferencia', id_externo=conv.id_externo, adjuntos=[PDF],
                               ts=fields.Datetime.now())
                with freeze_time(self.AHORA + timedelta(minutes=5)):
                    self.registrar('y mi cédula con el otro PDF', id_externo=conv.id_externo, adjuntos=[PDF, CEDULA],
                                   ts=fields.Datetime.now())
                self.assertTrue(any('documento de identidad' in t for t in self.textos()), self.textos())
