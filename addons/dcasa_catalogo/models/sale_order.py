from urllib.parse import quote

from odoo import models
from odoo.addons.dcasa_socios.models import reglas
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_dcasa_whatsapp(self):
        """Abre WhatsApp con la cotización lista para enviar al celular del cliente.

        El mensaje lleva el total y el enlace del portal, donde el cliente la ve, la firma o la paga.
        """
        self.ensure_one()
        celular = reglas.celular_normal(self.partner_id.phone or self.partner_id.dcasa_celular)
        if not reglas.celular_valido(celular):
            raise UserError(self.env._(
                '%s no tiene un celular de Panamá anotado. Escríbelo en el contacto (8 números, como 6123-4567).',
                self.partner_id.display_name))
        tipo = self.env._('cotización') if self.state in ('draft', 'sent') else self.env._('orden')
        texto = self.env._(
            "Hola %(nombre)s, te comparto tu %(tipo)s %(numero)s de D'CASA por %(total)s: %(enlace)s",
            nombre=self.partner_id.name.split()[0], tipo=tipo, numero=self.name,
            total=formatLang(self.env, self.amount_total, currency_obj=self.currency_id),
            enlace=self.get_base_url() + self.get_portal_url())
        if self.state == 'draft':
            self.action_quotation_sent()
        return {'type': 'ir.actions.act_url', 'url': f'https://wa.me/507{celular}?text={quote(texto)}', 'target': 'new'}
