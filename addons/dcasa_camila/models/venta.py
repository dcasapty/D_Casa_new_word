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
CAMPO = 'dcasa_camila_correo'
# Solo el código de Camila escribe «Vino del correo»: la marca del contexto es un objeto de Python, que no se puede
# mandar por RPC (un contexto de RPC es JSON) ni con ``sudo`` desde otro módulo sin importarlo de aquí.
MARCA_DE_CAMILA = object()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_camila_correo = fields.Char(
        'Vino del correo', readonly=True, copy=False, index='btree_not_null',
        help='El cliente llegó al chat por esta campaña de correo de novedades en los 30 días antes de la cotización.')

    @api.model
    def _sin_vino_del_correo(self, vals):
        """Quita «Vino del correo» de lo que se escribe, salvo que lo escriba Camila (``MARCA_DE_CAMILA``)."""
        if CAMPO in vals and self.env.context.get('dcasa_camila_marca') is not MARCA_DE_CAMILA:
            vals = {clave: valor for clave, valor in vals.items() if clave != CAMPO}
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._sin_vino_del_correo(vals) for vals in vals_list]
        ordenes = super().create(vals_list)
        self.env.cr.flush()   # lo pendiente de la cotización, AFUERA del try: un error suyo no se traga
        try:
            with self.env.cr.savepoint():
                ordenes._dcasa_camila_marcar_correo()
        except Exception:   # la cotización sale igual, sin la marca
            _logger.warning('Camila: no se pudo marcar la campaña de correo en la cotización', exc_info=True)
        return ordenes

    def write(self, vals):
        return super().write(self._sin_vino_del_correo(vals))

    def _dcasa_camila_marcar_correo(self):
        Llegada = self.env['dcasa.camila.llegada'].sudo()
        desde = fields.Datetime.now() - timedelta(days=DIAS_VENTANA)
        for orden in self.sudo().filtered(lambda o: o.partner_id and not o.dcasa_camila_correo):
            llegada = Llegada.search([('partner_id', '=', orden.partner_id.commercial_partner_id.id),
                                      ('ts', '>=', desde)], order='ts desc, id desc', limit=1)
            if llegada and llegada.campana_id:
                campana = llegada.campana_id
                orden.with_context(dcasa_camila_marca=MARCA_DE_CAMILA).write(
                    {CAMPO: f'{R.marca(campana.id)} · {R.limpiar(campana.asunto, 80)}'})
