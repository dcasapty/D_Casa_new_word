"""A quién le toca una conversación que Juan pasa a una persona (el reparto de Ajustes de Juan).

La regla de verdad vive en ``reparto.py``; aquí está lo que hace cada conversación con ella. ``_repartir`` lo llama
``_pasar_a_vendedora`` y es lo único que cambia quién atiende: nunca falla una conversación por culpa del reparto
(si no hay nadie, queda como siempre: el responsable por defecto y el aviso a todo el equipo).
"""
from odoo import models

from .reparto import Decision


class DcasaConversacionReparto(models.Model):
    _inherit = 'dcasa.conversacion'

    def _repartir(self):
        """Según «Reparto de conversaciones» en Ajustes de Juan, le asigna esta conversación a una persona.

        * ``manual``: a nadie (la toma quien quiera).
        * ``turnos``: a quien lleva más tiempo sin recibir una (el reparto de siempre).
        * ``parejo``: su vendedora de siempre o, si no, a quien lleva menos hoy.

        Devuelve una ``Decision``: a quién (vacío = a nadie), por qué (frase para el hilo) y si faltó gente disponible.
        """
        self.ensure_one()
        vacio = self.env['res.users']
        modo = self.env['dcasa.juan.ajustes'].obtener().reparto_modo
        if modo == 'parejo':
            return self._repartir_parejo()
        if modo == 'turnos' and not self.asignada_a:
            elegida = self._asignar_por_turno()
            if not elegida:
                return Decision(vacio, sin_nadie=True)
            self.env['dcasa.reparto']._anotar(self, elegida, 'turno')
            return Decision(elegida, self.env._('Le tocó a %s por turno.', elegida.name), 'turno')
        return Decision(vacio)

    def _repartir_parejo(self):
        Reparto = self.env['dcasa.reparto']
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        hoy = Reparto._hoy()
        candidatas = Reparto._disponibles(hoy)
        if not candidatas:
            return Decision(self.env['res.users'], sin_nadie=True)
        # 1) Su vendedora de siempre, si está disponible.
        elegida, momento = Reparto._vendedora_de_siempre(self, candidatas, ajustes.reparto_dias_misma_vendedora)
        if elegida:
            regla = 'misma'
            razon = self.env._('Sigue con %(quien)s: ya atendió a este cliente %(cuando)s.',
                               quien=elegida.name, cuando=Reparto._hace_cuanto(momento))
        else:
            # 2) Quien lleva menos hoy.
            cuentas = Reparto._cuentas(candidatas, hoy, hoy, excepto=self)
            ordenadas = Reparto._ordenar(candidatas, cuentas)
            elegida, regla = ordenadas[0], 'parejo'
            razon = self.env._('Le tocó a %(quien)s. %(por_que)s', quien=elegida.name,
                               por_que=Reparto._por_que_le_toco(ordenadas, cuentas))
        antes = self.asignada_a
        if antes and antes != elegida:
            razon = f"{razon} {self.env._('Antes la tenía %s.', antes.name)}"
        self.sudo().asignada_a = elegida
        if Reparto._anotar(self, elegida, regla, razon, hoy):
            # El turno también se gasta aquí: es el último desempate, y así quien acaba de recibir pasa al final de la
            # fila. (Escribirlo además frena a dos conversaciones que eligieran a la misma persona al mismo tiempo: la
            # segunda espera, vuelve a empezar y ya ve la cuenta al día.)
            elegida.dcasa_turno = max(Reparto._equipo(hoy).mapped('dcasa_turno') or [0]) + 1
        return Decision(elegida, razon, regla)

    def _registrar_asignacion_a_mano(self, usuario):
        """Una persona de Gerencia o de ventas eligió a quién atiende: queda anotado (sirve para «su vendedora de
        siempre») pero no cuenta como una conversación que Juan pasó."""
        self.ensure_one()
        if usuario:
            self.env['dcasa.reparto']._anotar(self, usuario, 'manual', self.env._('Asignada a mano.'))
