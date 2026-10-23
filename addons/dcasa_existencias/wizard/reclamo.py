"""Reclamo al proveedor: la lista en PDF (con la marca) de las mermas y daños de su mercancía en un periodo, para
mandársela y pedirle la reposición o la nota de crédito. Después se marcan como reclamadas."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.bitacora import GRUPO_AJUSTA
from ..models.merma import RECLAMABLES


class DcasaMermaReclamo(models.TransientModel):
    _name = 'dcasa.merma.reclamo'
    _description = 'Reclamo de mermas a un proveedor'

    proveedor_id = fields.Many2one('res.partner', 'Proveedor', required=True)
    desde = fields.Date('Desde', required=True,
                        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    hasta = fields.Date('Hasta', required=True, default=fields.Date.context_today)
    solo_por_reclamar = fields.Boolean('Solo las que falta reclamar', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    merma_ids = fields.Many2many('stock.scrap', compute='_compute_mermas', string='Mermas y daños')
    total = fields.Monetary('Total a costo', compute='_compute_mermas')

    @api.depends('proveedor_id', 'desde', 'hasta', 'solo_por_reclamar', 'company_id')
    def _compute_mermas(self):
        for reclamo in self:
            reclamo.merma_ids = reclamo._buscar()
            reclamo.total = round(sum(reclamo.merma_ids.mapped('dcasa_costo')), 2)

    def _buscar(self):
        self.ensure_one()
        if not (self.proveedor_id and self.desde and self.hasta):
            return self.env['stock.scrap']
        inicio, _ = self._limites_dia(self.desde)
        _ini, fin = self._limites_dia(self.hasta)
        dominio = [('company_id', '=', self.company_id.id), ('state', '=', 'done'),
                   ('dcasa_motivo', 'in', RECLAMABLES), ('dcasa_proveedor_id', '=', self.proveedor_id.id),
                   ('date_done', '>=', inicio), ('date_done', '<', fin)]
        if self.solo_por_reclamar:
            dominio.append(('dcasa_reclamo', '=', 'por_reclamar'))
        return self.env['stock.scrap'].sudo().search(dominio, order='date_done, id')

    def _limites_dia(self, dia):
        return self.env['dcasa.tablero']._limites_del_dia(dia)

    def _exigir(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_AJUSTA):
            raise AccessError(self.env._('Las mermas las ve Gerencia.'))

    def action_imprimir(self):
        self._exigir()
        self.ensure_one()
        if not self.merma_ids:
            raise UserError(self.env._('No hay mermas ni daños de ese proveedor en ese periodo.'))
        return self.env.ref('dcasa_existencias.accion_reclamo_pdf').report_action(self)

    def action_marcar_reclamadas(self):
        self._exigir()
        self.ensure_one()
        if not self.merma_ids:
            raise UserError(self.env._('No hay mermas ni daños de ese proveedor en ese periodo.'))
        for scrap in self.merma_ids:
            scrap.sudo().dcasa_reclamo = 'reclamado'
            scrap.message_post(body=self.env._('Reclamada al proveedor %(prov)s por %(quien)s.',
                                               prov=self.proveedor_id.name, quien=self.env.user.name))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': self.env._('Reclamo'), 'type': 'success',
                           'message': self.env._('%s merma(s) marcadas como reclamadas.', len(self.merma_ids)),
                           'next': {'type': 'ir.actions.act_window_close'}}}
