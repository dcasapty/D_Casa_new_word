from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from ..models.res_partner import CODE_ALPHABET, CODE_LENGTH, CODE_PREFIX
from .common import DcasaReferralCommon


@tagged('post_install', '-at_install')
class TestReferralFlow(DcasaReferralCommon):

    # --- Códigos -----------------------------------------------------------

    def test_generated_code_format(self):
        code = self.referrer.dcasa_referral_code
        self.assertTrue(code.startswith(CODE_PREFIX))
        self.assertEqual(len(code), len(CODE_PREFIX) + CODE_LENGTH)
        self.assertTrue(set(code[len(CODE_PREFIX):]) <= set(CODE_ALPHABET))
        self.assertTrue(self.referrer.dcasa_referral_url.endswith(f'/r/{code}'))

    def test_generating_twice_keeps_code(self):
        code = self.referrer.dcasa_referral_code
        self.referrer.action_dcasa_generate_referral_code()
        self.assertEqual(self.referrer.dcasa_referral_code, code)

    def test_find_referrer_by_code_in_many2one(self):
        code = self.referrer.dcasa_referral_code
        self.assertIn(self.referrer, self.env['res.partner'].search([('display_name', 'ilike', code)]))
        self.assertEqual(self.env['res.partner']._dcasa_find_by_referral_code(f'  {code.lower()} '), self.referrer)

    def test_no_self_or_mutual_referral(self):
        with self.assertRaises(ValidationError):
            self.referrer.dcasa_referrer_id = self.referrer
        self.customer.action_dcasa_generate_referral_code()
        self.customer.dcasa_referrer_id = self.referrer
        with self.assertRaises(ValidationError):
            self.referrer.dcasa_referrer_id = self.customer

    # --- Flujo de venta ----------------------------------------------------

    def test_full_flow_pending_earned_paid(self):
        order = self._sale(referrer=self.referrer)
        self.assertEqual(self.customer.dcasa_referrer_id, self.referrer, 'La venta fija el referidor del cliente')

        invoice = self._invoice(order)
        self.assertEqual(invoice.dcasa_referrer_id, self.referrer)
        reward = invoice.dcasa_referral_reward_ids
        self.assertEqual(len(reward), 1)
        self.assertEqual(reward.state, 'pending')
        self.assertEqual(reward.referred_partner_id, self.customer)
        self.assertAlmostEqual(reward.base_amount, 329.99)
        self.assertAlmostEqual(reward.amount, 16.50)  # 5% de 329.99, sin ITBMS
        self.assertEqual(reward.sale_order_ids, order)
        with self.assertRaises(UserError):
            reward.action_mark_paid()

        self._pay(invoice)
        self.assertEqual(reward.state, 'earned')
        self.assertAlmostEqual(self.referrer.dcasa_referral_balance, 16.50)

        reward.action_mark_paid()
        self.assertEqual(reward.state, 'paid')
        self.assertTrue(reward.payout_date)
        self.assertAlmostEqual(self.referrer.dcasa_referral_balance, 0.0)

        reward.action_undo_payout()
        self.assertEqual(reward.state, 'earned')

    def test_next_sale_inherits_referrer(self):
        self._sale(referrer=self.referrer)
        second = self._sale()
        self.assertEqual(second.dcasa_referrer_id, self.referrer)

    def test_direct_invoice_uses_customer_referrer(self):
        self.customer.dcasa_referrer_id = self.referrer
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.product.id, 'price_unit': 100.0})],
        })
        self.assertEqual(invoice.dcasa_referrer_id, self.referrer)
        invoice.action_post()
        self.assertAlmostEqual(invoice.dcasa_referral_reward_ids.amount, 5.0)

    def test_sale_without_referrer_creates_nothing(self):
        invoice = self._invoice(self._sale())
        self.assertFalse(invoice.dcasa_referral_reward_ids)

    def test_self_referral_on_order_is_ignored(self):
        self.customer.action_dcasa_generate_referral_code()
        invoice = self._invoice(self._sale(referrer=self.customer))
        self.assertFalse(self.customer.dcasa_referrer_id)
        self.assertFalse(invoice.dcasa_referral_reward_ids)

    def test_credit_note_cancels_reward(self):
        invoice = self._invoice(self._sale(referrer=self.referrer))
        reward = invoice.dcasa_referral_reward_ids
        # Nota de crédito total, publicada y conciliada: la factura queda "revertida".
        credit_note = invoice._reverse_moves([{'ref': 'Devolución'}], cancel=True)
        self.assertEqual(invoice.payment_state, 'reversed')
        self.assertEqual(reward.state, 'cancelled')
        self.assertFalse(credit_note.dcasa_referral_reward_ids, 'Las notas de crédito no generan recompensa')

    def test_cancelled_invoice_cancels_reward(self):
        invoice = self._invoice(self._sale(referrer=self.referrer))
        reward = invoice.dcasa_referral_reward_ids
        invoice.button_draft()
        self.assertEqual(reward.state, 'pending')
        invoice.button_cancel()
        self.assertEqual(reward.state, 'cancelled')

    def test_repost_does_not_duplicate_reward(self):
        invoice = self._invoice(self._sale(referrer=self.referrer))
        invoice.button_draft()
        invoice.action_post()
        self.assertEqual(len(invoice.dcasa_referral_reward_ids), 1)

    # --- Configuración -----------------------------------------------------

    def test_fixed_reward(self):
        self.company.write({'dcasa_referral_reward_type': 'fixed', 'dcasa_referral_reward_value': 10.0})
        invoice = self._invoice(self._sale(referrer=self.referrer))
        self.assertAlmostEqual(invoice.dcasa_referral_reward_ids.amount, 10.0)

    def test_min_amount(self):
        self.company.dcasa_referral_min_amount = 500.0
        invoice = self._invoice(self._sale(referrer=self.referrer))
        self.assertFalse(invoice.dcasa_referral_reward_ids)

    def test_first_purchase_only(self):
        self.company.dcasa_referral_first_purchase_only = True
        first = self._invoice(self._sale(referrer=self.referrer))
        second = self._invoice(self._sale())
        self.assertTrue(first.dcasa_referral_reward_ids)
        self.assertFalse(second.dcasa_referral_reward_ids)

    @mute_logger('odoo.sql_db')
    def test_negative_reward_value_rejected(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.company.dcasa_referral_reward_value = -1
            self.company.flush_recordset()
