from odoo import fields
from odoo.tests import TransactionCase


class DcasaReferralCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.company.write({
            'dcasa_referral_reward_type': 'percent',
            'dcasa_referral_reward_value': 5.0,
            'dcasa_referral_min_amount': 0.0,
            'dcasa_referral_first_purchase_only': False,
        })
        Partner = cls.env['res.partner']
        cls.referrer = Partner.create({'name': 'Ana Referidora', 'phone': '+507 6000-0001'})
        cls.referrer.action_dcasa_generate_referral_code()
        cls.customer = Partner.create({'name': 'Eric Gómez G.', 'vat': '2-723-510'})
        cls.product = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES',
            'type': 'consu',
            'list_price': 329.99,
            'invoice_policy': 'order',
            'taxes_id': [(6, 0, cls.company.account_sale_tax_id.ids)],
        })

    def _sale(self, partner=None, referrer=None, price=329.99):
        order = self.env['sale.order'].create({
            'partner_id': (partner or self.customer).id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': price})],
        })
        if referrer is not None:
            order.dcasa_referrer_id = referrer
        order.action_confirm()
        return order

    def _invoice(self, order):
        invoice = order._create_invoices()
        invoice.invoice_date = fields.Date.today()
        invoice.action_post()
        return invoice

    def _pay(self, invoice):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': invoice.invoice_date})._create_payments()
