"""El origen «Correo» en la cotización (etapa 2, decisión de la dueña): si el cliente llegó al chat por una campaña de
correo en los últimos 30 días (la misma ventana de las ventas atribuidas), la cotización dice de cuál
(«DCN-0007 · asunto»).

No cambia el «Origen» de siempre (``dcasa_origen``: chatbot, web o vendedora), que dice QUIÉN armó la cotización: el
correo dice POR DÓNDE llegó el cliente, y una cotización puede ser del chatbot y venir del correo a la vez. Es texto (no
un enlace a la campaña): la vendedora lo ve aunque no tenga acceso a Camila. Un error aquí nunca frena la cotización.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from . import reglas as R

_logger = logging.getLogger(__name__)

DIAS_VENTANA = 30


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_camila_correo = fields.Char(
        'Vino del correo', readonly=True, copy=False, index='btree_not_null',
        help='El cliente llegó al chat por esta campaña de correo de novedades en los 30 días antes de la cotización.')

    @api.model_create_multi
    def create(self, vals_list):
        ordenes = super().create(vals_list)
        try:
            with self.env.cr.savepoint():
                ordenes._dcasa_camila_marcar_correo()
        except Exception:   # la cotización sale igual, sin la marca
            _logger.warning('Camila: no se pudo marcar la campaña de correo en la cotización', exc_info=True)
        return ordenes

    def _dcasa_camila_marcar_correo(self):
        Llegada = self.env['dcasa.camila.llegada'].sudo()
        desde = fields.Datetime.now() - timedelta(days=DIAS_VENTANA)
        for orden in self.sudo().filtered(lambda o: o.partner_id and not o.dcasa_camila_correo):
            llegada = Llegada.search([('partner_id', '=', orden.partner_id.commercial_partner_id.id),
                                      ('ts', '>=', desde)], order='ts desc, id desc', limit=1)
            if llegada and llegada.campana_id:
                campana = llegada.campana_id
                orden.write({'dcasa_camila_correo': f'{R.marca(campana.id)} · {R.limpiar(campana.asunto, 80)}'})
