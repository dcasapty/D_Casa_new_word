"""«Ventas de hoy» con el día de Panamá (UI-06).

Un dominio XML con ``context_today()`` compara ``date_order`` (UTC) con la medianoche UTC,
que en Panamá son las 7 p. m. del día anterior: la lista traía las ventas de anoche y no
cuadraba con «Vendido hoy» del Inicio. El menú abre ahora esta acción, que calcula los
límites del día en la hora de quien mira (la de Panamá si no tiene).
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

ZONA_TIENDA = 'America/Panama'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _dcasa_limites_de_hoy(self):
        """Inicio y fin de hoy en la hora de quien mira, en UTC sin zona (como guarda Odoo)."""
        zona = pytz.timezone(self.env.user.tz or ZONA_TIENDA)
        hoy = fields.Date.context_today(self.with_context(tz=zona.zone))
        inicio = zona.localize(datetime.combine(hoy, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return inicio, inicio + timedelta(days=1)

    @api.model
    def _dcasa_accion_ventas_de_hoy(self):
        accion = self.env['ir.actions.act_window']._for_xml_id('dcasa_base.action_dcasa_ventas_hoy')
        inicio, fin = self._dcasa_limites_de_hoy()
        accion['domain'] = [
            ('state', '=', 'sale'),
            ('date_order', '>=', fields.Datetime.to_string(inicio)),
            ('date_order', '<', fields.Datetime.to_string(fin)),
        ]
        return accion
