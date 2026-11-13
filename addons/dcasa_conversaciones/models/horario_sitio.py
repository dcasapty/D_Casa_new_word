"""El horario de la tienda en el sitio (Visítanos y el pie) sale de UN solo lugar: los Ajustes de Juan.

``website_dcasa`` deja el gancho ``website._dcasa_horario_tienda`` (models/horario_tienda.py) y aquí se llena con
``horario_inicio``, ``horario_fin``, ``horario_fin_domingo`` y los días. Al cambiar el horario en los ajustes, la
tienda guardada en el borde se renueva entera (el pie sale en todas las páginas): la marca de ``dcasa_tienda_borde``,
si está instalado.
"""
from odoo import models
from odoo.addons.website_dcasa.models.horario_tienda import filas_horario

from .ajustes import DIAS_CAMPOS

CAMPOS_HORARIO = frozenset({'horario_inicio', 'horario_fin', 'horario_fin_domingo', *(c for c, _d in DIAS_CAMPOS)})


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_horario_tienda(self):
        ajustes = self.env['dcasa.juan.ajustes'].sudo().search([], limit=1)
        if not ajustes:
            return super()._dcasa_horario_tienda()
        return filas_horario(ajustes.horario_inicio, ajustes.horario_fin, ajustes._dias(),
                             ajustes.horario_fin_domingo or None)


class DcasaJuanAjustes(models.Model):
    _inherit = 'dcasa.juan.ajustes'

    def write(self, vals):
        resultado = super().write(vals)
        if CAMPOS_HORARIO.intersection(vals) and 'dcasa.tienda.pendiente' in self.env:
            self.env['dcasa.tienda.pendiente']._dcasa_marcar([0], 'horario de la tienda')
        return resultado
