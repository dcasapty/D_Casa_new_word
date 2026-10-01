from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRolesSitio(TransactionCase):

    def test_gerencia_edita_el_sitio_y_la_vendedora_no(self):
        disenador = self.env.ref('website.group_website_designer')
        self.assertIn(disenador, self.env.ref('dcasa_base.group_gerencia').all_implied_ids)
        self.assertNotIn(disenador, self.env.ref('dcasa_base.group_vendedora').all_implied_ids)
        self.assertNotIn(self.env.ref('website.group_website_restricted_editor'),
                         self.env.ref('dcasa_base.group_vendedora').all_implied_ids)
