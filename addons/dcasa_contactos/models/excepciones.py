"""Los flujos de Odoo que crean contactos que enseguida se vinculan (usuario, empleado, empresa) o que unen dos
fichas (fusión) no pasan por el candado: su contacto todavía no tiene su vínculo, o el repetido es justo el que se
va a borrar."""
from odoo import api, models

from .res_partner import SIN_DUPLICADOS


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        usuarios = super(ResUsers, self.with_context(**{SIN_DUPLICADOS: True})).create(vals_list)
        return usuarios.with_env(self.env)


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        empresas = super(ResCompany, self.with_context(**{SIN_DUPLICADOS: True})).create(vals_list)
        return empresas.with_env(self.env)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _create_work_contacts(self):
        return super(HrEmployee, self.with_context(**{SIN_DUPLICADOS: True}))._create_work_contacts()


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        # La ficha que queda llega ya leída por el asistente (sin esta excepción): se le pone también a ella, porque es
        # la que recibe los datos de la que se va mientras esa todavía existe.
        contexto = {SIN_DUPLICADOS: True}
        return super(BasePartnerMergeAutomaticWizard, self.with_context(**contexto))._merge(
            partner_ids, dst_partner=dst_partner.with_context(**contexto) if dst_partner else dst_partner,
            extra_checks=extra_checks)
