"""«Ventas de hoy» con el día de Panamá (UI-06) y la dueña de la cotización (solo lo suyo, 2026-10-16).

Un dominio XML con ``context_today()`` compara ``date_order`` (UTC) con la medianoche UTC,
que en Panamá son las 7 p. m. del día anterior: la lista traía las ventas de anoche y no
cuadraba con «Vendido hoy» del Inicio. El menú abre ahora esta acción, que calcula los
límites del día en la hora de quien mira (la de Panamá si no tiene).

Dueña del documento: quien solo ve lo suyo (la Vendedora, ``res.users._dcasa_solo_lo_suyo``) queda siempre como
vendedora de lo que crea y de lo sin dueña que confirma. Si no, Odoo pondría a la vendedora de la ficha del cliente
(o la de ``default_user_id``, p. ej. «Nueva cotización» desde la oportunidad de otra) y la creación fallaría por
permisos: no podría ver lo que acaba de crear. Juan, la web, los procesos automáticos y Caja no cambian (corren
con ``sudo`` o ven todo).
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

    # ------------------------------------------------------------------
    # Dueña del documento (solo lo suyo)
    # ------------------------------------------------------------------

    def _dcasa_crea_para_si(self):
        """Quien crea o confirma solo ve lo suyo: el documento tiene que quedar a su nombre."""
        return not self.env.su and self.env.user._dcasa_solo_lo_suyo()

    def _compute_user_id(self):
        # Mismo criterio que Odoo para recalcular (pedido nuevo o sin vendedora), pero a nombre de quien lo hace y
        # no de la vendedora de la ficha. El cálculo corre con sudo (campo guardado): se pregunta por la persona.
        tomar = self.browse()
        if self.env.user._dcasa_solo_lo_suyo():
            tomar = self.filtered(lambda o: o.partner_id and not (o._origin.id and o.user_id))
        super()._compute_user_id()
        for orden in tomar:
            orden.user_id = self.env.user

    @api.model_create_multi
    def create(self, vals_list):
        if self._dcasa_crea_para_si():
            vals_list = [dict(vals, user_id=self.env.uid) for vals in vals_list]
        return super().create(vals_list)

    def _prepare_confirmation_values(self):
        valores = super()._prepare_confirmation_values()
        if self._dcasa_crea_para_si():
            # Solo puede confirmar lo suyo o lo que no tiene vendedora: confirmar es «tomarlo».
            valores['user_id'] = self.env.uid
        return valores
