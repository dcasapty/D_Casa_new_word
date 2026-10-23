from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


def menus_visibles(env, usuario):
    """Ids externos de los menús con pantalla que el usuario ve de verdad: él y todos sus menús padre."""
    menu = env['ir.ui.menu'].with_user(usuario)
    visibles = menu._visible_menu_ids()
    resultado = set()
    for m in env['ir.ui.menu'].sudo().browse(sorted(visibles)):
        if not m.action:
            continue
        padre, ok = m, True
        while padre:
            if padre.id not in visibles:
                ok = False
                break
            padre = padre.parent_id
        if ok:
            xmlid = m.get_external_id().get(m.id)
            if xmlid:
                resultado.add(xmlid)
    return resultado


@tagged('post_install', '-at_install')
class TestPermisosVendedora(TransactionCase):
    """Lo que la dueña pidió del rol Vendedora: atiende, factura, ve y edita productos; nada de nómina ni de la
    contabilidad de un jefe. Los menús que no existen (módulo no instalado) no cuentan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interfaz_instalada = bool(cls.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'dcasa_interfaz'), ('state', '=', 'installed')]))
        cls.vendedora = crear_usuario(cls.env, 'perm_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'perm_gerencia', 'dcasa_base.group_gerencia')
        cls.visibles = menus_visibles(cls.env, cls.vendedora)
        cls.visibles_gerencia = menus_visibles(cls.env, cls.gerencia)

    def _existe(self, xmlid):
        return bool(self.env.ref(xmlid, raise_if_not_found=False))

    def test_la_vendedora_ve_lo_que_necesita_para_vender(self):
        necesarios = (
            'dcasa_interfaz.menu_dcasa_inicio', 'dcasa_guia.menu_guia',
            'dcasa_conversaciones.menu_dcasa_panel_conversaciones',
            'contacts.res_partner_menu_contacts', 'sale.menu_sale_quotations', 'sale.menu_sale_order',
            'sale.menu_product_template_action', 'dcasa_base.menu_dcasa_ventas_facturas',
            'account.menu_action_move_out_invoice_type', 'account.menu_action_move_out_refund_type',
            'account.menu_action_account_payments_receivable', 'stock.menu_product_variant_config_stock',
            'dcasa_barras.menu_dcasa_escaner', 'dcasa_barras.menu_dcasa_bodega',
            'dcasa_brian.menu_brian_conversaciones',
        )
        for xmlid in necesarios:
            if self._existe(xmlid):
                self.assertIn(xmlid, self.visibles, f'La vendedora debe ver {xmlid}')

    def test_la_vendedora_no_ve_nomina_ni_contabilidad_de_jefe(self):
        if not self.interfaz_instalada:
            self.skipTest('Los menús contables los oculta dcasa_interfaz (no instalado en esta corrida)')
        prohibidos = (
            # nómina: ni la app ni ninguna de sus pantallas
            'dcasa_nomina.menu_planillas', 'dcasa_nomina.menu_decimo', 'dcasa_nomina.menu_colaboradores',
            'dcasa_nomina.menu_vacaciones', 'dcasa_nomina.menu_liquidaciones', 'dcasa_nomina.menu_reembolsos',
            'dcasa_nomina.menu_parametros', 'dcasa_nomina.menu_config_cuentas',
            # contabilidad de un jefe: reportes, asientos, proveedores, bancos y configuración
            'account.menu_action_move_in_invoice_type', 'account.menu_action_account_moves_all',
            'account.menu_action_account_payments_payable', 'account.menu_action_account_form',
            'account.menu_action_account_journal_form', 'account.menu_action_tax_form',
            'dcasa_contabilidad.menu_resumen', 'dcasa_contabilidad.menu_estado_resultados',
            'dcasa_contabilidad.menu_balance_general', 'dcasa_contabilidad.menu_libro_mayor',
            'dcasa_contabilidad.menu_conciliacion', 'dcasa_contabilidad.menu_cierre_mes',
            'dcasa_contabilidad.menu_itbms', 'dcasa_contabilidad.menu_por_cobrar',
            'dcasa_contabilidad.menu_por_pagar', 'dcasa_contabilidad.menu_flujo_efectivo',
            # lo de gestión del CRM y las importaciones de Brian
            'crm.crm_menu_forecast', 'crm.crm_opportunity_report_menu', 'crm.crm_activity_report_menu',
            'crm.sales_team_menu_team_pipeline', 'dcasa_brian.menu_brian_importaciones',
            'dcasa_brian.menu_brian_acciones', 'dcasa_brian.menu_brian_ajustes',
        )
        for xmlid in prohibidos:
            if self._existe(xmlid):
                self.assertNotIn(xmlid, self.visibles, f'La vendedora no debe ver {xmlid}')

    def test_en_facturacion_la_vendedora_solo_ve_el_lado_de_clientes(self):
        if not self.interfaz_instalada:
            self.skipTest('Los menús contables los oculta dcasa_interfaz (no instalado en esta corrida)')
        raiz = self.env.ref('account.menu_finance', raise_if_not_found=False)
        if not raiz:
            self.skipTest('Sin la app de Facturación')
        permitidos = {
            'account.menu_account_customer', 'account.menu_action_move_out_invoice_type',
            'account.menu_action_move_out_refund_type', 'account.menu_action_account_payments_receivable',
            'account.product_product_menu_sellable', 'dcasa_fe_pa.menu_dcasa_fe_documento',
        }
        for xmlid in self.visibles:
            menu = self.env.ref(xmlid)
            if raiz.id in [int(i) for i in menu.parent_path.split('/') if i]:
                self.assertIn(xmlid, permitidos, f'«{menu.complete_name}» no es del lado de clientes')

    def test_cobros_de_hoy_es_de_caja_no_de_la_vendedora(self):
        """«Cobros de hoy (caja)» es la caja de toda la tienda: con «Cada vendedora ve solo sus documentos» encendido,
        la vendedora vería solo sus cobros (una cifra parcial con nombre de caja), así que no lo ve; Caja y Gerencia
        sí. Apagado, la vendedora lo vuelve a ver, como antes (test_solo_lo_suyo.py)."""
        caja = crear_usuario(self.env, 'perm_caja', 'dcasa_base.group_caja')
        self.assertNotIn('dcasa_base.menu_dcasa_cobros_hoy', self.visibles)
        self.assertIn('dcasa_base.menu_dcasa_cobros_hoy', menus_visibles(self.env, caja))
        self.assertIn('dcasa_base.menu_dcasa_cobros_hoy', self.visibles_gerencia)
        self.assertIn('dcasa_base.menu_dcasa_ventas_hoy', self.visibles, '«Ventas de hoy» (las suyas) sí la ve')

    def test_gerencia_sigue_viendo_todo_lo_suyo(self):
        for xmlid in ('dcasa_nomina.menu_planillas', 'dcasa_nomina.menu_reembolsos', 'crm.crm_menu_forecast',
                      'dcasa_brian.menu_brian_importaciones', 'dcasa_contabilidad.menu_estado_resultados',
                      'dcasa_contabilidad.menu_conciliacion', 'account.menu_action_account_moves_all'):
            if self._existe(xmlid):
                self.assertIn(xmlid, self.visibles_gerencia, f'Gerencia debe ver {xmlid}')

    def test_mis_reembolsos_es_de_todos_y_no_cuelga_de_nomina(self):
        menu = self.env.ref('dcasa_nomina.menu_mis_reembolsos', raise_if_not_found=False)
        if not menu:
            self.skipTest('Sin dcasa_nomina')
        self.assertFalse(menu.parent_id, '«Mis reembolsos» es su propia app, no está dentro de «Nómina»')
        self.assertIn('dcasa_nomina.menu_mis_reembolsos', self.visibles)
        raiz = self.env.ref('dcasa_nomina.menu_nomina_raiz')
        self.assertNotIn(raiz.id, self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids())
        # Y por datos: ninguna planilla ni sueldo para ella
        for modelo in ('dcasa.nomina.planilla', 'dcasa.nomina.parametros', 'dcasa.nomina.liquidacion'):
            if modelo in self.env:
                self.assertFalse(self.env[modelo].with_user(self.vendedora).has_access('read'), modelo)

    def test_la_vendedora_edita_productos_pero_no_precios_ni_costos(self):
        producto = self.env['product.template'].create({'name': 'Cama prueba permisos', 'list_price': 100.0})
        como_vendedora = producto.with_user(self.vendedora)
        como_vendedora.write({'name': 'Cama prueba permisos (editada)', 'description_sale': 'Con colchón'})
        self.assertEqual(producto.name, 'Cama prueba permisos (editada)')
        for vals in ({'list_price': 1.0}, {'standard_price': 1.0}):
            with self.assertRaises(AccessError):
                como_vendedora.write(vals)
        variante = producto.product_variant_id.with_user(self.vendedora)
        with self.assertRaises(AccessError):
            variante.write({'lst_price': 1.0})
        self.assertEqual(producto.list_price, 100.0)
        # Crear o borrar productos sigue siendo de Gerencia
        self.assertFalse(self.env['product.template'].with_user(self.vendedora).has_access('create'))
        self.assertFalse(self.env['product.template'].with_user(self.vendedora).has_access('unlink'))

    def test_gerencia_cambia_precios(self):
        producto = self.env['product.template'].create({'name': 'Sofá prueba permisos', 'list_price': 100.0})
        producto.with_user(self.gerencia).write({'list_price': 120.0, 'standard_price': 60.0})
        self.assertEqual(producto.list_price, 120.0)

    def test_recibir_mercancia_con_costo_promedio_no_se_traba_por_el_costo(self):
        """El costo promedio se actualiza solo al recibir (con permisos internos): la vendedora que recibe no recibe
        un error de «solo Gerencia cambia los costos»."""
        categoria = self.env['product.category'].create(
            {'name': 'Promedio permisos', 'property_cost_method': 'average'})
        producto = self.env['product.product'].create({
            'name': 'Silla costo promedio', 'is_storable': True, 'categ_id': categoria.id, 'standard_price': 10.0,
        })
        almacen = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        proveedores = self.env.ref('stock.stock_location_suppliers')
        recepcion = self.env['stock.picking'].create({
            'picking_type_id': almacen.in_type_id.id,
            'location_id': proveedores.id, 'location_dest_id': almacen.lot_stock_id.id,
            'move_ids': [Command.create({
                'product_id': producto.id, 'product_uom_qty': 5, 'location_id': proveedores.id,
                'location_dest_id': almacen.lot_stock_id.id,
            })],
        })
        recepcion.action_confirm()
        recepcion.move_ids.quantity = 5
        recepcion.with_user(self.vendedora).button_validate()
        self.assertEqual(recepcion.state, 'done')
        self.assertEqual(producto.qty_available, 5)
