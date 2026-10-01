from odoo import Command
from odoo.tests import tagged

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestRolesSocios(SociosCommon):
    """UI-03: el control antifraude y el pasivo son de Gerencia, no de la vendedora."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)
        cls.vendedora = Usuarios.create({
            'name': 'Vendedora Socios', 'login': 'socios_vendedora',
            'group_ids': [Command.set([cls.env.ref('dcasa_base.group_vendedora').id])]})
        cls.gerencia = Usuarios.create({
            'name': 'Gerencia Socios', 'login': 'socios_gerencia',
            'group_ids': [Command.set([cls.env.ref('dcasa_base.group_gerencia').id])]})
        cls.reportes = (cls.env.ref('dcasa_socios.menu_dcasa_reportes')
                        | cls.env.ref('dcasa_socios.menu_dcasa_reporte_vendedoras')
                        | cls.env.ref('dcasa_socios.menu_dcasa_pasivo'))

    def _menus_visibles(self, usuario):
        return self.env['ir.ui.menu'].with_user(usuario)._visible_menu_ids()

    def test_vendedora_no_ve_reportes_antifraude(self):
        visibles = self._menus_visibles(self.vendedora)
        self.assertIn(self.env.ref('dcasa_socios.menu_dcasa_socios').id, visibles)
        self.assertIn(self.env.ref('dcasa_socios.menu_dcasa_canjes').id, visibles)
        for menu in self.reportes:
            self.assertNotIn(menu.id, visibles, menu.name)

    def test_gerencia_ve_reportes_antifraude(self):
        visibles = self._menus_visibles(self.gerencia)
        for menu in self.reportes:
            self.assertIn(menu.id, visibles, menu.name)

    def test_acciones_de_reportes_solo_para_gerencia(self):
        gerente = self.env.ref('sales_team.group_sale_manager')
        for xmlid in ('dcasa_socios.action_dcasa_reporte_vendedoras', 'dcasa_socios.action_dcasa_pasivo'):
            self.assertEqual(self.env.ref(xmlid).group_ids, gerente, xmlid)

    def test_vendedora_cobra_premio_aunque_la_linea_sea_negativa(self):
        """El premio rebaja más que el tope de descuento, pero lo pagan los puntos: no cuenta."""
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_10'))
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.padrino.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        self.env['dcasa.cobrar.premio.wizard'].with_user(self.vendedora).create({
            'order_id': orden.id, 'codigo': canje.codigo}).action_confirmar()
        self.assertTrue(orden.order_line.filtered('dcasa_canje_id'))
        self.assertAlmostEqual(orden.amount_total, 107.0 - 10.0)
