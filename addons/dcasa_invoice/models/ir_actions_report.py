from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_html(self, report_ref, docids, data=None):
        # En los documentos impresos los montos van como se escriben en Panamá: $1,070.50.
        return super(IrActionsReport, self.with_context(dcasa_moneda_compacta=True))._render_qweb_html(
            report_ref, docids, data=data)
