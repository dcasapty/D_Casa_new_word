from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_pa_dv = fields.Char(
        string='DV',
        size=2,
        help='Dígito Verificador del RUC (Panamá). Se imprime junto al RUC en la factura.',
    )
    dcasa_ruc_display = fields.Char(
        string='RUC completo',
        compute='_compute_dcasa_ruc_display',
        help='RUC tal como se imprime en documentos: "<RUC> DV<dígito>".',
    )

    @api.depends('vat', 'l10n_pa_dv')
    def _compute_dcasa_ruc_display(self):
        for partner in self:
            parts = [partner.vat or '']
            if partner.vat and partner.l10n_pa_dv:
                parts.append(f'DV{partner.l10n_pa_dv}')
            partner.dcasa_ruc_display = ' '.join(parts).strip()

    @api.constrains('l10n_pa_dv')
    def _check_l10n_pa_dv(self):
        for partner in self:
            if partner.l10n_pa_dv and not partner.l10n_pa_dv.isdigit():
                raise ValidationError(self.env._('El DV del RUC solo puede contener dígitos.'))

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ['l10n_pa_dv']
