from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDcasaBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')

    def test_company_is_configured_for_panama(self):
        self.assertEqual(self.company.country_id, self.env.ref('base.pa'))
        self.assertEqual(self.company.chart_template, 'pa')
        self.assertEqual(self.company.currency_id, self.env.ref('base.USD'))

    def test_sales_are_in_usd(self):
        """El plan contable de Panamá deja PAB; ventas y listas de precios deben quedar en USD."""
        usd = self.env.ref('base.USD')
        pricelists = self.env['product.pricelist'].search([('company_id', 'in', [self.company.id, False])])
        self.assertEqual(pricelists.currency_id, usd)
        order = self.env['sale.order'].create({'partner_id': self.env['res.partner'].create({'name': 'X'}).id})
        self.assertEqual(order.currency_id, usd)

    def test_company_ruc_with_dv(self):
        self.assertEqual(self.company.vat, '155779346-2-2026')
        self.assertEqual(self.company.partner_id.dcasa_ruc_display, '155779346-2-2026 DV7')

    def test_company_real_address(self):
        self.assertEqual(self.company.street, 'Frente al Parque Libertadores')
        self.assertEqual(self.company.street2, 'Diagonal a la Discoteca Seven')
        self.assertEqual(self.company.city, 'La Chorrera')

    def test_address_migration_only_replaces_old_address(self):
        import importlib.util

        from odoo.tools.misc import file_path
        spec = importlib.util.spec_from_file_location(
            'mig', file_path('dcasa_base/migrations/19.0.1.7.0/post-migrate.py'))
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        self.company.write({'street': mig.VIEJA, 'street2': 'Local 4550 PB-1'})
        mig.migrate(self.env.cr, '19.0.1.6.0')
        self.company.invalidate_recordset()
        self.assertEqual(self.company.street, 'Frente al Parque Libertadores')
        self.company.write({'street': 'Editada por la dueña'})
        mig.migrate(self.env.cr, '19.0.1.6.0')
        self.company.invalidate_recordset()
        self.assertEqual(self.company.street, 'Editada por la dueña', 'No pisa una dirección editada')

    def test_default_sale_tax_is_itbms_7(self):
        tax = self.company.account_sale_tax_id
        self.assertEqual(tax.amount, 7.0)
        self.assertEqual(tax.type_tax_use, 'sale')

    def test_attachments_stored_in_database(self):
        location = self.env['ir.config_parameter'].sudo().get_param('ir_attachment.location')
        self.assertEqual(location, 'db')

    def test_ruc_display_without_dv(self):
        partner = self.env['res.partner'].create({'name': 'Eric Gómez G.', 'vat': '2-723-510'})
        self.assertEqual(partner.dcasa_ruc_display, '2-723-510')

    def test_dv_must_be_numeric(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({'name': 'Cliente', 'vat': '8-1-1', 'l10n_pa_dv': 'X'})

    def test_dv_is_commercial_field(self):
        company = self.env['res.partner'].create({
            'name': 'Hotel Cliente S.A.', 'is_company': True, 'vat': '1557-1-2026', 'l10n_pa_dv': '45',
        })
        contact = self.env['res.partner'].create({'name': 'Compras', 'parent_id': company.id})
        self.assertEqual(contact.l10n_pa_dv, '45')

    def test_numbers_use_panama_format(self):
        lang = self.env['res.lang']._lang_get('es_419')
        self.assertEqual((lang.decimal_point, lang.thousands_sep), ('.', ','))
