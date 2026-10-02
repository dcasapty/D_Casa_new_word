from odoo import fields
from odoo.addons.dcasa_fe_pa.models import pac as P
from odoo.tests import TransactionCase

UBICACION = {'l10n_pa_cod_ubicacion': '8-8-8', 'l10n_pa_corregimiento': 'Barrio Colón',
             'l10n_pa_distrito': 'La Chorrera', 'l10n_pa_provincia': 'Panamá Oeste'}


class FeComun(TransactionCase):
    """Empresa D'CASA, un cliente contribuyente, un consumidor final y la cama del catálogo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.company.partner_id.write(UBICACION)
        cls.diario = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
        cls.contribuyente = cls.env['res.partner'].create({
            'name': 'MUEBLES DEL OESTE, S.A.', 'is_company': True, 'vat': '8-NT-1-12345', 'l10n_pa_dv': '45',
            'street': 'Calle 1, Barrio Colón', 'city': 'La Chorrera', 'country_id': cls.env.ref('base.pa').id,
            'phone': '+507 6123-4567', 'email': 'compras@example.com', **UBICACION,
        })
        cls.consumidor = cls.env['res.partner'].create({'name': 'Ana Gómez', 'country_id': cls.env.ref('base.pa').id})
        cls.cama = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES', 'default_code': '1062010735N', 'type': 'consu',
        })
        cls.admin = cls.env.ref('base.user_admin')

    def _activar(self, modo='autorizar', **extra):
        self.company.write({'l10n_pa_fe_activo': True, 'l10n_pa_fe_adaptador': 'simulado', **extra})
        self._modo(modo)

    def _modo(self, modo):
        self.env['ir.config_parameter'].sudo().set_param(P.PARAM_MODO_SIMULADO, modo)

    def _factura(self, cliente=None, precio=158.02, cantidad=1, publicar=True, **valores):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': (cliente or self.consumidor).id,
            'invoice_date': fields.Date.today(), 'journal_id': self.diario.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.cama.id, 'quantity': cantidad, 'price_unit': precio})],
            **valores,
        })
        if publicar:
            factura.action_post()
        return factura

    def _render(self, factura):
        html, _fmt = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', factura.ids)
        return html.decode()
