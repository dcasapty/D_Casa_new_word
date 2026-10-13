"""El PDF sale con el diseño de D'CASA aunque la URL pública no se alcance desde el contenedor.

wkhtmltopdf pide los estilos y las fuentes por HTTP. Si los pide a la URL pública (web.base.url),
desde dentro del contenedor no llegan y la factura sale como texto suelto, sin cuadros ni marca:
así se vio en staging. Los pide siempre al propio Odoo (127.0.0.1).
"""
import shutil
from unittest import skipUnless

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tools import config


@tagged('post_install', '-at_install')
class TestPdfConEstilos(HttpCase):

    def setUp(self):
        super().setUp()
        parametros = self.env['ir.config_parameter'].sudo()
        # Una URL pública que desde aquí no responde, como la de Cloudflare vista desde el contenedor.
        parametros.set_param('web.base.url', 'https://dcasa-no-alcanzable.invalid')
        parametros.set_param('web.base.url.freeze', True)
        parametros.set_param('report.url', False)

    def test_los_estilos_se_piden_al_propio_odoo(self):
        url = self.env['ir.actions.report']._get_report_url()
        self.assertEqual(url, f"http://127.0.0.1:{config['http_port']}")

    def test_report_url_explicito_manda(self):
        self.env['ir.config_parameter'].sudo().set_param('report.url', 'http://interno:9000')
        self.assertEqual(self.env['ir.actions.report']._get_report_url(), 'http://interno:9000')

    @skipUnless(shutil.which('wkhtmltopdf'), 'sin wkhtmltopdf (la imagen Docker lo comprueba en CI)')
    def test_la_factura_en_pdf_lleva_las_fuentes_de_marca(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente PDF'})
        producto = self.env['product.product'].create({'name': 'Mesa PDF', 'type': 'consu'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {'product_id': producto.id, 'quantity': 1, 'price_unit': 99.0})],
        })
        factura.action_post()
        pdf, _tipo = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            'account.account_invoices', factura.ids)
        self.assertTrue(pdf.startswith(b'%PDF'))
        # Las fuentes de marca solo llegan si wkhtmltopdf pudo cargar la hoja de estilos.
        self.assertIn(b'Anton', pdf, 'La factura salió sin estilos (wkhtmltopdf no cargó el CSS)')
        self.assertIn(b'Inter', pdf)
