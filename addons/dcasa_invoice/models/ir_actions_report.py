from odoo import models
from odoo.tools import config


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_html(self, report_ref, docids, data=None):
        # En los documentos impresos los montos van como se escriben en Panamá: $1,070.50.
        return super(IrActionsReport, self.with_context(dcasa_moneda_compacta=True))._render_qweb_html(
            report_ref, docids, data=data)

    def _get_report_url(self, layout=None):
        """wkhtmltopdf pide estilos y fuentes al propio Odoo, nunca a la URL pública.

        Con ``web.base.url`` (la dirección de Cloudflare) el contenedor no alcanza los estilos y
        el PDF sale como texto suelto, sin cuadros ni marca. ``report.url``, si se fija, manda.
        """
        if self.env['ir.config_parameter'].sudo().get_param('report.url'):
            return super()._get_report_url(layout=layout)
        interfaz = config.get('http_interface') or ''
        if interfaz in ('', '0.0.0.0', '::'):
            interfaz = '127.0.0.1'
        return f"http://{interfaz}:{config['http_port']}"
