"""El sitio se edita por código (docs/OPERACION.md, «El sitio se edita por código»).

La política la aplica ``dcasa_interfaz`` (``dcasa.sitio._sitio_por_codigo``, que corre en cada
actualización y retira los grupos de editor/diseñador a todos, también la implicación que
``security/dcasa_roles_website.xml`` de este módulo le pone a Gerencia). Aquí se comprueba el
resultado final sobre los roles de D'CASA.
"""
from odoo.tests import TransactionCase, tagged

GRUPOS_EDITOR = ('website.group_website_designer', 'website.group_website_restricted_editor')


@tagged('post_install', '-at_install')
class TestRolesSitio(TransactionCase):

    def _grupos_editor(self):
        return self.env['res.groups'].browse([self.env.ref(x).id for x in GRUPOS_EDITOR])

    def test_la_vendedora_nunca_edita_el_sitio(self):
        vendedora = self.env.ref('dcasa_base.group_vendedora')
        self.assertFalse(vendedora.all_implied_ids & self._grupos_editor())

    def test_nadie_edita_el_sitio_desde_el_panel(self):
        """Con ``dcasa_interfaz`` instalado, ni Gerencia ni nadie tiene el constructor de Odoo."""
        interfaz = self.env['ir.module.module'].search([('name', '=', 'dcasa_interfaz')], limit=1)
        if interfaz.state != 'installed':
            self.skipTest('La política «el sitio se edita por código» la aplica dcasa_interfaz.')
        grupos = self._grupos_editor()
        for xmlid in ('dcasa_base.group_gerencia', 'dcasa_base.group_vendedora', 'base.group_system'):
            self.assertFalse(self.env.ref(xmlid).all_implied_ids & grupos, xmlid)
        internos = self.env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        con_grupo = internos.filtered(lambda u: u.all_group_ids & grupos)
        self.assertFalse(con_grupo, con_grupo.mapped('login'))
