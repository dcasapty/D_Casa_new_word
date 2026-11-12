"""Revisión adversarial del 2026-11-12 (I7): los lugares que agregó alguien del equipo que no es Gerencia quedan «Por
revisar» (la columna nueva nace encendida para los del archivo y los de Gerencia)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Lugar = env['dcasa.envio.lugar'].with_context(active_test=False)
    sin_revisar = Lugar.search([('origen', '=', 'mano')]).filtered(
        lambda lugar: not (lugar.agregado_por and lugar.agregado_por._dcasa_es_gerencia()))
    if sin_revisar:
        cr.execute('UPDATE dcasa_envio_lugar SET revisado = FALSE, revisado_por = NULL, revisado_el = NULL '
                   'WHERE id IN %s', [tuple(sin_revisar.ids)])
        Lugar.invalidate_model(['revisado', 'revisado_por', 'revisado_el'])
