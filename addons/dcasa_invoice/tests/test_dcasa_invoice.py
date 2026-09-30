from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDcasaInvoice(TransactionCase):
    """Reproduce la factura real INV/2026/00821 (combo cama + colchón)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        # ITBMS que se suma al precio (como en la factura real): el de la tienda ya lo incluye.
        cls.itbms = cls.env['account.tax'].search([
            ('company_id', '=', cls.company.id), ('type_tax_use', '=', 'sale'),
            ('amount', '=', 7), ('price_include', '=', False)], limit=1)
        cls.customer = cls.env['res.partner'].create({
            'name': 'ERIC GOMEZ G.',
            'street': 'P. Oeste, La Chorrera, Corregimiento Herrera',
            'city': 'La Chorrera',
            'country_id': cls.env.ref('base.pa').id,
            'vat': '2-723-510',
        })
        product_vals = {'type': 'consu', 'taxes_id': [(6, 0, cls.itbms.ids)]}
        cls.colchon = cls.env['product.product'].create({
            **product_vals, 'name': 'COLCHON DULCESUENOS SEMI RESORTE Q (A)', 'default_code': 'DSRSOQ',
        })
        cls.cama = cls.env['product.product'].create({
            **product_vals, 'name': 'CAMA QUEEN GREY CON ESTANTES', 'default_code': '1062010735N',
        })

    def _create_invoice(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {'product_id': self.colchon.id, 'quantity': 1, 'price_unit': 171.97}),
                (0, 0, {'product_id': self.cama.id, 'quantity': 1, 'price_unit': 158.02}),
            ],
        })
        invoice.action_post()
        return invoice

    def _pay(self, invoice):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': invoice.invoice_date})._create_payments()

    def _render(self, invoice):
        html, _fmt = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', invoice.ids)
        return html.decode()

    def test_totals_match_real_invoice(self):
        invoice = self._create_invoice()
        self.assertAlmostEqual(invoice.amount_untaxed, 329.99)
        self.assertAlmostEqual(invoice.amount_tax, 23.10)
        self.assertAlmostEqual(invoice.amount_total, 353.09)

    def test_company_uses_dcasa_layout(self):
        self.assertEqual(self.company.external_report_layout_id, self.env.ref('dcasa_invoice.external_layout_dcasa'))
        self.assertTrue(self.company.display_invoice_amount_total_words)

    def test_unpaid_invoice_has_no_stamp(self):
        invoice = self._create_invoice()
        self.assertFalse(invoice._dcasa_is_paid())
        self.assertNotIn('o_dcasa_pago', self._render(invoice))

    def test_paid_invoice_shows_stamp_and_ruc(self):
        invoice = self._create_invoice()
        self._pay(invoice)
        self.assertTrue(invoice._dcasa_is_paid())
        self.assertEqual(invoice._dcasa_last_payment_date(), invoice.invoice_date)

        html = self._render(invoice)
        # Sin sello que imite el de goma: lo que pasó, con fecha, forma de pago y saldo.
        self.assertNotIn('o_dcasa_paid_stamp', html)
        self.assertNotIn('PAGADO', html)
        self.assertIn('o_dcasa_pago', html)
        self.assertIn('Pagada el', html)
        self.assertIn('Saldo', html)
        self.assertIn('2-723-510', html)
        self.assertIn('155779346-2-2026 DV7', html)
        self.assertIn('Tu casa, bien amueblada.', html)

    def test_factura_en_espanol_y_con_formato_de_panama(self):
        invoice = self._create_invoice()
        html = self._render(invoice.with_context(lang='en_US'))
        for etiqueta in ('Factura', 'Descripción', 'Cantidad', 'Precio unitario', 'Importe'):
            self.assertIn(etiqueta, html)
        self.assertNotIn('Unit Price', html)
        self.assertIn('Dólares', html)
        self.assertNotIn('Dollars', html)
        self.assertNotIn('$\N{NO-BREAK SPACE}', html)
        self.assertNotIn('localhost', html.split('<body', 1)[1].replace('web-base-url', ''))

    def test_customer_dv_printed_with_ruc(self):
        self.customer.l10n_pa_dv = '12'
        html = self._render(self._create_invoice())
        self.assertIn('2-723-510 DV12', html)
