"""Inicio según el rol y «vendido» = facturado por completo (pedido de la dueña, 2026-10-14).

* Un borrador, una cotización o un pedido «por facturar» no es una venta; tampoco uno con una factura sin publicar.
* La vendedora ve solo lo que ella vendió hoy y sus cotizaciones abiertas; Gerencia, todo.
* Atajos: Productos · Facturas · Conversaciones · Oportunidades · Resumen contable (este último, solo contabilidad).
* «Mis gastos por reembolsar»: de todo el personal, con ícono propio, sin dejar ver Nómina ni los gastos de otros.
"""
import json
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.safe_eval import safe_eval


def crear_usuario(env, login, grupo):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'password': login, 'tz': 'America/Panama',
        'group_ids': [Command.set([env.ref('base.group_user').id, env.ref(grupo).id])],
    })


class VentasMixin:
    """Usuarios por rol y pedidos de prueba, para las pruebas de servidor y las del navegador."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'vendedora_rol', 'dcasa_base.group_vendedora')
        cls.otra = crear_usuario(cls.env, 'otra_vendedora_rol', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(cls.env, 'gerencia_rol', 'dcasa_base.group_gerencia')
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente inicio por rol'})
        cls.producto = cls.env['product.product'].create({'name': 'SILLA INICIO POR ROL', 'list_price': 50})
        cls.hoy = fields.Date.context_today(cls.env['dcasa.tablero'].with_user(cls.vendedora))

    def pedido(self, vendedor=None, cantidad=1, confirmar=True, producto=None):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'user_id': (vendedor or self.vendedora).id,
            'order_line': [Command.create({'product_id': (producto or self.producto).id, 'product_uom_qty': cantidad})],
        })
        if confirmar:
            orden.action_confirm()
        return orden

    def facturar(self, orden, publicar=True, fecha=None):
        factura = orden._create_invoices()
        if fecha:
            factura.invoice_date = fecha
        if publicar:
            factura.action_post()
        return factura

    def cifras(self, usuario=None):
        tablero = self.env['dcasa.tablero'].with_user(usuario) if usuario else self.env['dcasa.tablero']
        return {c['clave']: c for c in tablero.obtener_datos()['cifras']}


class VentasCommon(VentasMixin, TransactionCase):
    pass


@tagged('post_install', '-at_install')
class TestVendidoEsFacturado(VentasCommon):

    def test_solo_cuenta_lo_facturado_por_completo_y_publicado(self):
        Order = self.env['sale.order']
        antes = Order.search_count(Order._dcasa_dominio_vendido(desde=self.hoy, hasta=self.hoy))
        cotizacion = self.pedido(confirmar=False)
        por_facturar = self.pedido()
        con_borrador = self.pedido()
        self.facturar(con_borrador, publicar=False)
        vendido = self.pedido()
        factura = self.facturar(vendido)
        dominio = Order._dcasa_dominio_vendido(desde=self.hoy, hasta=self.hoy)
        encontradas = Order.search(dominio)
        self.assertIn(vendido, encontradas)
        self.assertEqual(vendido.dcasa_fecha_venta, factura.invoice_date)
        for no_es_venta in (cotizacion, por_facturar, con_borrador):
            self.assertNotIn(no_es_venta, encontradas, no_es_venta.name)
            self.assertFalse(no_es_venta.dcasa_fecha_venta, no_es_venta.name)
        self.assertEqual(Order.search_count(dominio), antes + 1)

    def test_la_factura_en_borrador_no_hace_una_venta_hasta_publicarla(self):
        orden = self.pedido()
        factura = self.facturar(orden, publicar=False)
        self.assertEqual(orden.invoice_status, 'invoiced', 'Odoo ya da por facturado lo que está en un borrador')
        self.assertFalse(orden.dcasa_fecha_venta)
        factura.action_post()
        self.assertEqual(orden.dcasa_fecha_venta, factura.invoice_date)
        factura.button_draft()
        self.assertFalse(orden.dcasa_fecha_venta, 'si la factura vuelve a borrador deja de ser una venta')

    def test_un_pedido_facturado_a_medias_no_es_venta_hasta_facturar_el_resto(self):
        orden = self.pedido(cantidad=4)
        factura = orden._create_invoices()
        factura.invoice_line_ids.quantity = 1      # solo 1 de las 4 unidades
        factura.action_post()
        self.assertEqual(orden.invoice_status, 'to invoice')
        self.assertFalse(orden.dcasa_fecha_venta)
        resto = orden._create_invoices()
        self.assertEqual(sum(resto.invoice_line_ids.mapped('quantity')), 3)
        resto.action_post()
        self.assertEqual(orden.invoice_status, 'invoiced')
        self.assertEqual(orden.dcasa_fecha_venta, max(orden.invoice_ids.mapped('invoice_date')),
                         'el día de la venta es el de la última factura')

    def test_el_dia_de_la_venta_es_el_de_la_factura_no_el_del_pedido(self):
        """Un apartado de hace días que se cobra y se factura hoy se vendió hoy."""
        orden = self.pedido()
        orden.date_order = fields.Datetime.now() - timedelta(days=5)
        self.assertNotIn(orden, self.env['sale.order'].search(
            self.env['sale.order']._dcasa_dominio_vendido(desde=self.hoy, hasta=self.hoy)))
        self.facturar(orden)
        self.assertEqual(orden.dcasa_fecha_venta, self.hoy)
        self.assertIn(orden, self.env['sale.order'].search(
            self.env['sale.order']._dcasa_dominio_vendido(desde=self.hoy, hasta=self.hoy)))

    def test_una_nota_de_credito_que_devuelve_todo_saca_la_venta(self):
        orden = self.pedido()
        factura = self.facturar(orden)
        self.assertTrue(orden.dcasa_fecha_venta)
        reversa = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({'journal_id': factura.journal_id.id})
        reversa.refund_moves()
        nota = orden.invoice_ids.filtered(lambda f: f.move_type == 'out_refund')
        self.assertTrue(nota)
        self.assertFalse(orden.dcasa_fecha_venta, 'la devolución completa la saca de lo vendido (aun en borrador)')
        nota.action_post()
        self.assertFalse(orden.dcasa_fecha_venta)

    def test_cancelar_la_factura_de_un_pedido_lo_regresa_a_por_facturar(self):
        orden = self.pedido()
        factura = self.facturar(orden)
        factura.button_draft()
        factura.button_cancel()
        self.assertEqual(orden.invoice_status, 'to invoice')
        self.assertFalse(orden.dcasa_fecha_venta)

    def test_ventas_de_hoy_del_menu_es_lo_mismo_que_el_inicio(self):
        """Ventas › Hoy › Ventas de hoy (pedidos) y la tarjeta «Vendido hoy» de la vendedora comparten el dominio. La de
        Gerencia cuenta las facturas («Facturado», 2026-10-17): abre las facturas de esos mismos pedidos."""
        por_facturar = self.pedido()
        vendido = self.pedido()
        factura = self.facturar(vendido)
        menu = self.env.ref('dcasa_base.action_dcasa_ventas_hoy_abrir')
        for usuario in (self.gerencia, self.vendedora):
            accion = menu.with_user(usuario).run()
            del_menu = self.env['sale.order'].search(accion['domain'])
            self.assertIn(vendido, del_menu, usuario.login)
            self.assertNotIn(por_facturar, del_menu, usuario.login)
        tarjeta = self.cifras(self.vendedora)['ventas_hoy']['accion']
        del_menu = self.env['sale.order'].search(menu.with_user(self.vendedora).run()['domain'])
        self.assertEqual(self.env['sale.order'].search(tarjeta['domain']), del_menu)
        de_gerencia = self.cifras(self.gerencia)['ventas_hoy']['accion']
        self.assertEqual(de_gerencia['res_model'], 'account.move')
        self.assertIn(factura, self.env['account.move'].search(de_gerencia['domain']))
        self.assertFalse(por_facturar.invoice_ids)

    def test_ventas_de_hoy_del_menu_la_vendedora_ve_solo_las_suyas_y_gerencia_todas(self):
        mia = self.pedido(vendedor=self.vendedora)
        self.facturar(mia)
        ajena = self.pedido(vendedor=self.otra)
        self.facturar(ajena)
        por_facturar = self.pedido(vendedor=self.vendedora)
        contador = crear_usuario(self.env, 'contador_menu_hoy', 'account.group_account_user')
        menu = self.env.ref('dcasa_base.action_dcasa_ventas_hoy_abrir')

        propias = self.env['sale.order'].search(menu.with_user(self.vendedora).run()['domain'])
        self.assertIn(mia, propias)
        self.assertNotIn(ajena, propias, 'la vendedora no ve las ventas de otra en el menú')
        self.assertNotIn(por_facturar, propias)
        self.assertEqual(propias.user_id, self.vendedora)
        otra = self.env['sale.order'].search(menu.with_user(self.otra).run()['domain'])
        self.assertIn(ajena, otra)
        self.assertNotIn(mia, otra)
        for usuario in (self.gerencia, contador, self.env.ref('base.user_admin')):
            todas = self.env['sale.order'].search(menu.with_user(usuario).run()['domain'])
            self.assertTrue((mia | ajena) <= todas, f'{usuario.login} ve las ventas de toda la tienda')
            self.assertNotIn(por_facturar, todas)

    def test_ventas_de_hoy_vacia_conserva_su_ayuda(self):
        menu = self.env.ref('dcasa_base.action_dcasa_ventas_hoy_abrir')
        propia = menu.with_user(self.vendedora).run()['help']
        todas = menu.with_user(self.gerencia).run()['help']
        for ayuda in (propia, todas):
            self.assertIn('o_dcasa_ayuda', ayuda, 'sin esa clase el Inicio de D\'CASA esconde la ayuda')
            self.assertIn('Una venta cuenta cuando su factura ya está publicada.', ayuda)
        self.assertIn('ventas tuyas', propia)
        self.assertNotIn('ventas tuyas', todas)

    def test_la_tarjeta_la_lista_las_barras_y_lo_mas_vendido_dicen_lo_mismo(self):
        producto = self.env['product.product'].create({'name': 'ZZMUY VENDIDO INICIO', 'list_price': 10})
        pendiente = self.pedido(cantidad=40, producto=producto)            # por facturar: no cuenta en nada
        borrador = self.pedido(cantidad=30, producto=producto, confirmar=False)
        con_borrador = self.pedido(cantidad=20, producto=producto)
        self.facturar(con_borrador, publicar=False)
        vendido = self.pedido(cantidad=2, producto=producto)
        self.facturar(vendido)
        datos = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        cifras = {c['clave']: c for c in datos['cifras']}
        # tarjeta y lista: las facturas publicadas de hoy («Facturado»)
        lista = self.env['account.move'].search(cifras['ventas_hoy']['accion']['domain'])
        self.assertIn(vendido.invoice_ids, lista)
        for fuera in (pendiente, borrador, con_borrador):
            self.assertFalse(fuera.invoice_ids & lista, fuera.name)
        self.assertAlmostEqual(cifras['ventas_hoy']['valor'], sum(lista.mapped('amount_untaxed_signed')), places=2)
        self.assertAlmostEqual(cifras['ventas_hoy']['total_con_itbms'], sum(lista.mapped('amount_total_signed')),
                               places=2)
        facturas = len(lista.filtered(lambda f: f.move_type == 'out_invoice'))
        self.assertEqual(cifras['ventas_hoy']['detalle'], f'{facturas} factura' + ('' if facturas == 1 else 's'))
        # barras
        self.assertTrue(datos['semana'][-1]['hoy'])
        self.assertAlmostEqual(datos['semana'][-1]['monto'], cifras['ventas_hoy']['valor'], places=2)
        # lo más vendido: solo las 2 unidades facturadas, no las 40/30/20 que no son venta
        mas_vendido = {p['nombre']: p['cantidad'] for p in datos['top']}
        self.assertEqual(mas_vendido.get('ZZMUY VENDIDO INICIO'), 2)

    def test_las_ventas_de_ayer_no_entran_en_hoy_pero_si_en_la_barra_de_ayer(self):
        orden = self.pedido()
        self.facturar(orden, fecha=self.hoy - timedelta(days=1))
        antes = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        self.assertEqual(orden.dcasa_fecha_venta, self.hoy - timedelta(days=1))
        # La barra de ayer ya la incluye; «hoy» no.
        despues_orden = self.pedido()
        self.facturar(despues_orden, fecha=self.hoy - timedelta(days=1))
        despues = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        self.assertAlmostEqual(despues['semana'][-2]['monto'] - antes['semana'][-2]['monto'],
                               despues_orden.amount_untaxed, places=2)
        self.assertAlmostEqual(despues['semana'][-2]['total'] - antes['semana'][-2]['total'],
                               despues_orden.amount_total, places=2)
        self.assertAlmostEqual(despues['semana'][-1]['monto'], antes['semana'][-1]['monto'], places=2)


@tagged('post_install', '-at_install')
class TestInicioPorRol(VentasCommon):

    def test_la_vendedora_ve_solo_lo_suyo(self):
        mia = self.pedido(vendedor=self.vendedora)
        self.facturar(mia)
        ajena = self.pedido(vendedor=self.otra)
        self.facturar(ajena)
        mia_sin_facturar = self.pedido(vendedor=self.vendedora)
        cotizacion_mia = self.pedido(vendedor=self.vendedora, confirmar=False)
        cotizacion_ajena = self.pedido(vendedor=self.otra, confirmar=False)
        datos = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()
        self.assertEqual(datos['alcance'], 'propio')
        cifras = {c['clave']: c for c in datos['cifras']}
        self.assertEqual(set(cifras), {'ventas_hoy', 'mis_cotizaciones'},
                         'solo lo que ella vendió hoy y sus cotizaciones abiertas')
        # Vendido hoy: solo la suya, facturada
        hoy = cifras['ventas_hoy']
        lista = self.env['sale.order'].with_user(self.vendedora).search(hoy['accion']['domain'])
        self.assertEqual(lista, mia)
        self.assertAlmostEqual(hoy['valor'], mia.amount_untaxed, places=2, msg='el valor es sin ITBMS')
        self.assertAlmostEqual(hoy['total_con_itbms'], mia.amount_total, places=2)
        self.assertAlmostEqual(hoy['itbms'], mia.amount_tax, places=2)
        self.assertEqual(hoy['detalle'], '1 venta tuya')
        self.assertIn(('user_id', '=', self.vendedora.id), hoy['accion']['domain'])
        # Mis cotizaciones: solo las abiertas de ella (la confirmada sin facturar ya no es cotización)
        mis = cifras['mis_cotizaciones']
        self.assertEqual(self.env['sale.order'].with_user(self.vendedora).search(mis['accion']['domain']),
                         cotizacion_mia)
        self.assertEqual(mis['valor'], 1)
        self.assertNotIn(cotizacion_ajena, self.env['sale.order'].search(mis['accion']['domain']))
        self.assertNotIn(mia_sin_facturar, lista)
        # Nada de la tienda
        self.assertFalse(datos['semana'])
        self.assertFalse(datos['top'])
        self.assertFalse(datos['cobros'])

    def test_la_vendedora_no_ve_cobros_ni_por_cobrar_ni_totales_de_la_tienda(self):
        datos = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()
        permisos = datos['permisos']
        self.assertFalse(permisos['completo'])
        self.assertFalse(permisos['cobrar'], 'ni «Registrar cobro» en el Inicio')
        self.assertFalse(permisos['ver_cobros'])
        claves = {c['clave'] for c in datos['cifras']}
        self.assertFalse(claves & {'por_cobrar', 'cotizaciones', 'web', 'entregas', 'socios'}, claves)
        self.assertIsNone(datos['ventas'], 'ni el panel de ventas por periodo, ni la ganancia')
        self.assertFalse(datos['ve_utilidad'])
        # Lo que sí tiene
        self.assertTrue(permisos['facturar'])
        self.assertTrue(permisos['crear_cliente'])

    def test_gerencia_conserva_el_panel_completo(self):
        self.facturar(self.pedido())
        datos = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        self.assertEqual(datos['alcance'], 'tienda')
        self.assertTrue(all(datos['permisos'].values()), datos['permisos'])
        claves = {c['clave'] for c in datos['cifras']}
        self.assertTrue({'ventas_hoy', 'cotizaciones', 'web', 'por_cobrar', 'entregas', 'socios'} <= claves, claves)
        self.assertNotIn('cobrado_hoy', claves, '«Cobrado hoy» salió: Caja de hoy ya lo dice (2026-10-16)')
        self.assertEqual(len(datos['semana']), 7)
        self.assertEqual(datos['ventas']['periodo'], 'hoy')
        self.assertTrue(datos['ve_utilidad'])
        self.assertIsNotNone(datos['cotizaciones'])
        self.assertIsNotNone(datos['entregas'])

    def test_gerencia_ve_lo_cobrado_hoy_por_forma_de_pago_y_la_vendedora_no(self):
        diario = self.env['account.journal'].search([('type', 'in', ('cash', 'bank'))], limit=1)
        if not diario:
            self.skipTest('Sin diarios de caja o banco')
        antes = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        cobrado_antes = antes['total_cobrado']
        self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
            'amount': 12.5, 'journal_id': diario.id}).action_post()
        datos = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        self.assertAlmostEqual(datos['total_cobrado'] - cobrado_antes, 12.5, places=2)
        self.assertIn(diario.display_name, {c['forma'] for c in datos['cobros']})
        propio = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()
        self.assertFalse(propio['cobros'])
        self.assertEqual(propio['total_cobrado'], 0.0)

    def test_caja_cobra_y_ve_la_caja_de_hoy_sin_el_panel_completo(self):
        """Caja (rol D'CASA, 2026-10-17) cobra lo de toda la tienda: tiene «Registrar cobro», «Caja de hoy» y «Por
        cobrar» de todas, pero no el panel completo ni la ganancia. La vendedora sigue igual."""
        caja = crear_usuario(self.env, 'caja_rol', 'dcasa_base.group_caja')
        diario = self.env['account.journal'].search([('type', 'in', ('cash', 'bank'))], limit=1)
        if not diario:
            self.skipTest('Sin diarios de caja o banco')
        factura = self.facturar(self.pedido(vendedor=self.otra))
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'payment_date': self.hoy, 'journal_id': diario.id, 'amount': 12.5})._create_payments()
        datos = self.env['dcasa.tablero'].with_user(caja).obtener_datos()
        permisos = datos['permisos']
        self.assertTrue(permisos['cobrar'])
        self.assertTrue(permisos['ver_cobros'])
        self.assertFalse(permisos['completo'])
        self.assertFalse(datos['ve_utilidad'])
        self.assertIsNone(datos['ventas'])
        de_gerencia = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        self.assertAlmostEqual(datos['total_cobrado'], de_gerencia['total_cobrado'], places=2,
                               msg='la caja de hoy de Caja es la de toda la tienda')
        self.assertGreaterEqual(datos['total_cobrado'], 12.5)
        self.assertIn('por_cobrar', {c['clave'] for c in datos['cifras']})
        propio = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()['permisos']
        self.assertFalse(propio['cobrar'] or propio['ver_cobros'], 'la vendedora sigue sin cobros en su Inicio')

    def test_el_vendido_de_gerencia_incluye_a_todas_las_vendedoras(self):
        mia, ajena = self.pedido(vendedor=self.vendedora), self.pedido(vendedor=self.otra)
        self.facturar(mia)
        self.facturar(ajena)
        lista = self.env['account.move'].search(self.cifras(self.gerencia)['ventas_hoy']['accion']['domain'])
        self.assertTrue((mia.invoice_ids | ajena.invoice_ids) <= lista)

    def test_las_apps_que_no_se_usan_se_vuelven_a_ocultar_en_cada_actualizacion(self):
        """``-u all`` recarga los menús de Odoo con sus grupos de fábrica; el panel los oculta de nuevo."""
        from odoo.addons.dcasa_base import MENUS_OCULTOS
        desarrollador = self.env.ref('base.group_no_one')
        menus = [self.env.ref(x) for x in MENUS_OCULTOS if self.env.ref(x, raise_if_not_found=False)]
        self.assertTrue(menus)
        for menu in menus:
            menu.group_ids = False                      # como los deja una actualización completa de Odoo
        self.env.ref('base.open_module_tree').domain = '[]'
        self.env['dcasa.tablero']._dcasa_configurar_panel()   # lo que corre en cada actualización de dcasa_interfaz
        for menu in menus:
            self.assertEqual(menu.group_ids, desarrollador, menu.complete_name)
        self.assertIn('to_buy', self.env.ref('base.open_module_tree').domain)
        # y la vendedora no ve Discuss, Calendario, Tableros ni Aplicaciones
        visibles = self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids()
        for menu in menus:
            self.assertNotIn(menu.id, visibles, menu.complete_name)

    def test_atajos_de_la_vendedora(self):
        atajos = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()['atajos']
        claves = [a['clave'] for a in atajos]
        self.assertEqual(claves[:2], ['productos', 'facturas'])
        self.assertNotIn('oportunidades', claves, 'Oportunidades es de quien controla la tienda')
        self.assertNotIn('resumen_contable', claves)
        self.assertEqual(set(claves) - {'conversaciones', 'escaner'}, {'productos', 'facturas'})
        facturas = next(a for a in atajos if a['clave'] == 'facturas')
        self.assertEqual(facturas['accion'], 'account.action_move_out_invoice_type')
        self.assertEqual(facturas['vista'], 'list')
        # El atajo abre la misma lista de Facturación › Clientes › Facturas
        self.assertEqual(self.env.ref('dcasa_base.menu_dcasa_ventas_facturas').action,
                         self.env.ref('account.action_move_out_invoice_type'))
        for atajo in atajos:
            self.assertTrue(self.env.ref(atajo['accion'], raise_if_not_found=False), atajo['accion'])

    def test_atajos_de_gerencia_en_el_orden_pedido(self):
        atajos = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()['atajos']
        claves = [a['clave'] for a in atajos]
        esperado = ['productos', 'facturas', 'conversaciones', 'escaner', 'oportunidades', 'resumen_contable']
        # Conversaciones, Oportunidades y el Resumen contable viven en otros módulos: si falta alguno no sale.
        self.assertEqual(claves, [c for c in esperado if c in claves])
        self.assertEqual(claves[:2], ['productos', 'facturas'])
        if 'resumen_contable' in claves:
            self.assertEqual(claves[-1], 'resumen_contable')
            if 'oportunidades' in claves:
                self.assertEqual(claves.index('resumen_contable'), claves.index('oportunidades') + 1,
                                 'el Resumen contable va justo a la derecha de Oportunidades')
            resumen = next(a for a in atajos if a['clave'] == 'resumen_contable')
            self.assertEqual(resumen['accion'], 'dcasa_contabilidad.accion_resumen')
            self.assertIsNone(resumen['vista'])

    def test_el_resumen_contable_es_solo_de_contabilidad_y_gerencia(self):
        if not self.env.ref('dcasa_contabilidad.accion_resumen', raise_if_not_found=False):
            self.skipTest('Sin dcasa_contabilidad')
        contador = crear_usuario(self.env, 'contador_rol', 'account.group_account_user')
        lector = crear_usuario(self.env, 'lector_rol', 'account.group_account_readonly')
        for usuario, ve in ((self.gerencia, True), (contador, True), (lector, True), (self.vendedora, False)):
            claves = {a['clave'] for a in self.env['dcasa.tablero'].with_user(usuario).obtener_datos()['atajos']}
            self.assertEqual('resumen_contable' in claves, ve, usuario.login)

    def test_sin_ventas_el_atajo_de_facturas_no_sale_si_no_hay_permiso(self):
        interno = crear_usuario(self.env, 'interno_sin_facturas', 'base.group_user')
        datos = self.env['dcasa.tablero'].with_user(interno).obtener_datos()
        self.assertEqual(datos['alcance'], 'tienda', 'quien no vende no tiene panel «propio»')
        claves = {a['clave'] for a in datos['atajos']}
        if not self.env['account.move'].with_user(interno).has_access('read'):
            self.assertNotIn('facturas', claves)

    def test_la_plantilla_oculta_a_la_vendedora_lo_que_no_es_suyo(self):
        with open(file_path('dcasa_interfaz/static/src/xml/inicio.xml'), encoding='utf-8') as plantilla:
            xml = plantilla.read()
        # Quien vende cotiza: «Nueva cotización» es de todos y es el botón principal; la factura suelta, sin cotización,
        # solo es de quien controla (no tiene pedido ni nota de entrega).
        self.assertIn('o_dcasa_nueva_cotizacion', xml)
        self.assertIn('<button t-if="d.permisos.cotizar" class="btn btn-primary o_dcasa_nueva_cotizacion"', xml)
        # 2026-10-16: «Nueva factura» y «Ver en el celular» se retiraron; «Ver la tienda» queda solo con ícono.
        self.assertNotIn('o_dcasa_nueva_factura', xml)
        self.assertNotIn('Ver en el celular', xml)
        self.assertIn('<button t-if="d.permisos.completo" class="btn btn-primary o_dcasa_ver_tienda"', xml)
        self.assertIn('<div t-if="d.permisos.completo" class="o_dcasa_inicio_fila">', xml)
        self.assertIn('Así va tu día', xml)


@tagged('post_install', '-at_install')
class TestGastosPorReembolsar(VentasCommon):
    """El menú que la dueña no entendía: «Mis reembolsos» ahora se llama «Mis gastos por reembolsar»."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu = cls.env.ref('dcasa_nomina.menu_mis_reembolsos', raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self.menu:
            self.skipTest('Sin dcasa_nomina')

    def _menus(self, usuario):
        menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
        return {m['xmlid']: m['name'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

    def test_nombre_claro_icono_propio_y_ayuda(self):
        self.assertEqual(self.menu.name, 'Mis gastos por reembolsar')
        self.assertEqual(self.menu.action.name, 'Mis gastos por reembolsar')
        self.assertNotEqual(self.menu.web_icon, self.env.ref('dcasa_nomina.menu_nomina_raiz').web_icon,
                            'con el ícono de Nómina parecía que la vendedora tenía la Nómina habilitada')
        self.assertIn('reembolsos.svg', self.menu.web_icon)
        self.assertTrue(self.menu.web_icon_data)
        self.assertIn('foto del recibo', self.menu.action.help)
        self.assertIn('próxima planilla', self.menu.action.help)

    def test_la_vendedora_ve_ese_menu_pero_no_la_nomina(self):
        visibles = self._menus(self.vendedora)
        self.assertEqual(visibles.get('dcasa_nomina.menu_mis_reembolsos'), 'Mis gastos por reembolsar')
        nomina = {x for x in visibles if x.startswith('dcasa_nomina.')} - {'dcasa_nomina.menu_mis_reembolsos'}
        self.assertFalse(nomina, f'la vendedora no debe ver nada de Nómina: {nomina}')
        self.assertNotIn('Nómina', visibles.values())
        for modelo in ('dcasa.nomina.planilla', 'dcasa.nomina.linea', 'dcasa.nomina.parametros',
                       'dcasa.nomina.liquidacion', 'dcasa.nomina.vacacion', 'dcasa.nomina.config'):
            with self.assertRaises(AccessError, msg=modelo):
                self.env[modelo].with_user(self.vendedora).search([])
        # Gerencia sí: aprueba en Nómina › Reembolsos
        gerencia = self._menus(self.gerencia)
        self.assertIn('dcasa_nomina.menu_reembolsos', gerencia)
        self.assertIn('dcasa_nomina.menu_planillas', gerencia)

    def test_sin_el_menu_empleados_la_vendedora_sigue_usando_sus_gastos(self):
        """«Empleados» ya no es de la vendedora (dcasa_equipo), pero «Mis gastos por reembolsar» es otra app: no cuelga
        de ese menú ni de Nómina, y lo registra y lo ve sin tocar fichas de empleados."""
        raiz = self.env.ref('hr.menu_hr_root')
        self.assertFalse(self.menu.parent_id)
        self.assertNotIn(self.menu.id, raiz.child_id.ids)
        visibles = self._menus(self.vendedora)
        self.assertEqual(visibles.get('dcasa_nomina.menu_mis_reembolsos'), 'Mis gastos por reembolsar')
        equipo = self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'dcasa_equipo'), ('state', '=', 'installed')])
        if equipo:
            self.assertNotIn('hr.menu_hr_root', visibles)
        ficha = self.env['hr.employee'].create({'name': 'Ficha de la vendedora gastos', 'user_id': self.vendedora.id})
        Reembolso = self.env['dcasa.nomina.reembolso'].with_user(self.vendedora)
        gasto = Reembolso.create({'empleado_id': ficha.id, 'concepto': 'Taxi a la bodega', 'monto': 6.5})
        self.assertEqual(gasto.estado, 'borrador')
        # la lista del menú (su dominio, con ``uid`` de ella) trae su gasto
        dominio = safe_eval(self.menu.action.domain, {'uid': self.vendedora.id})
        self.assertEqual(Reembolso.search(dominio), gasto)
        self.assertEqual(Reembolso.default_get(['empleado_id'])['empleado_id'], ficha.id)

    def test_cada_quien_ve_solo_sus_gastos(self):
        Empleado = self.env['hr.employee']
        mio = Empleado.create({'name': 'Ficha de la vendedora', 'user_id': self.vendedora.id})
        ajeno = Empleado.create({'name': 'Ficha de la otra', 'user_id': self.otra.id})
        Reembolso = self.env['dcasa.nomina.reembolso']
        suyo = Reembolso.create({'empleado_id': mio.id, 'concepto': 'Taxi de la vendedora', 'monto': 5.0})
        de_otra = Reembolso.create({'empleado_id': ajeno.id, 'concepto': 'Bolsas de la otra', 'monto': 7.0})
        visibles = Reembolso.with_user(self.vendedora).search([('id', 'in', (suyo | de_otra).ids)])
        self.assertEqual(visibles, suyo)
        # y la lista del menú (su dominio) tampoco trae los de otras
        accion = self.menu.action
        self.assertEqual(Reembolso.with_user(self.vendedora).search(
            [('id', 'in', (suyo | de_otra).ids)] + [('empleado_id.user_id', '=', self.vendedora.id)]), suyo)
        self.assertIn('empleado_id.user_id', accion.domain)
        with self.assertRaises(AccessError):
            de_otra.with_user(self.vendedora).read(['monto'])
        # Gerencia ve los dos
        self.assertEqual(Reembolso.with_user(self.gerencia).search([('id', 'in', (suyo | de_otra).ids)]),
                         suyo | de_otra)


ESPERAR_JS = """
    const esperar = async (fn, que, intentos = 150) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    const textos = (selector) => [...document.querySelectorAll(selector)]
        .map((e) => e.textContent.trim().replace(/\\s+/g, ' '));
    const igual = (visto, esperado, que) => {
        if (JSON.stringify(visto) !== JSON.stringify(esperado)) {
            throw new Error(`${que}: se vio ${JSON.stringify(visto)} y se esperaba ${JSON.stringify(esperado)}`);
        }
    };
"""


@tagged('post_install', '-at_install')
class TestInicioEnElNavegador(VentasMixin, HttpCase):
    """Lo que de verdad se ve en pantalla: la vendedora y Gerencia, y la lista que abre «Vendido hoy»."""

    def probar(self, login, cuerpo):
        codigo = '(async () => {' + ESPERAR_JS + cuerpo + "console.log('test successful'); })();"
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login=login)

    def test_la_vendedora_ve_solo_sus_herramientas_y_lo_que_vendio(self):
        mia = self.pedido(vendedor=self.vendedora)
        self.facturar(mia)
        ajena = self.pedido(vendedor=self.otra)
        self.facturar(ajena)
        por_facturar = self.pedido(vendedor=self.vendedora)
        borrador = self.pedido(vendedor=self.vendedora)
        self.facturar(borrador, publicar=False)
        self.probar('vendedora_rol', """
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_cifra'), 'las cifras');
            igual(textos('.o_dcasa_cifra .o_dcasa_cifra_titulo'), ['Vendido hoy', 'Mis cotizaciones'], 'cifras');
            const atajos = textos('.o_dcasa_atajo strong');
            igual(atajos.slice(0, 2), ['Productos', 'Facturas'], 'los primeros atajos');
            for (const fuera of ['Oportunidades', 'Resumen contable']) {
                if (atajos.includes(fuera)) { throw new Error('la vendedora no debe ver el atajo ' + fuera); }
            }
            const botones = textos('.o_dcasa_inicio_accesos .btn');
            for (const dentro of ['Nueva cotización', 'Nuevo cliente']) {
                if (!botones.includes(dentro)) { throw new Error('falta el botón ' + dentro); }
            }
            for (const fuera of ['Nueva factura', 'Registrar cobro', 'Ver la tienda', 'Ver en el celular']) {
                if (botones.includes(fuera)) { throw new Error('la vendedora no debe ver el botón ' + fuera); }
            }
            // El botón principal (azul) es el de cotizar.
            const principal = document.querySelector('.o_dcasa_inicio_accesos .btn-primary');
            if (!principal || !principal.textContent.includes('Nueva cotización')) {
                throw new Error('el botón principal de la vendedora debe ser «Nueva cotización»');
            }
            if (document.querySelector('.o_dcasa_panel')) { throw new Error('sin barras ni paneles de la tienda'); }
            // Ni el interruptor, ni el selector de vendedora, ni «Comparar», ni los ⓘ, ni «N de M salieron de un
            // pedido»: su Inicio no cambia (2026-10-17).
            for (const fuera of ['.o_dcasa_interruptor', '.o_dcasa_vendedora_select', '.o_dcasa_comparar',
                                 '.o_dcasa_ayuda_boton', '.o_dcasa_de_pedido', '.o_dcasa_ventas']) {
                if (document.querySelector(fuera)) { throw new Error('la vendedora no debe ver ' + fuera); }
            }
            if (document.body.innerText.includes('Cobrado hoy') || document.body.innerText.includes('Por cobrar')) {
                throw new Error('la vendedora no ve lo cobrado ni lo por cobrar');
            }
            // Tocar «Vendido hoy»: solo lo suyo y facturado por completo.
            document.querySelector('.o_dcasa_cifra_ventas_hoy').click();
            await esperar(() => document.querySelector('.o_list_view .o_data_row'), 'la lista de ventas');
            const nombres = textos('.o_list_view .o_data_row td[name="name"]');
            igual(nombres, [__MIA__], 'la lista de Vendido hoy');
        """.replace('__MIA__', json.dumps(mia.name)))
        self.assertNotIn(ajena.name, [mia.name])
        self.assertTrue(por_facturar and borrador)

    def test_gerencia_ve_el_panel_completo_con_los_atajos_en_su_orden(self):
        self.probar('gerencia_rol', """
            await esperar(() => document.querySelector('.o_dcasa_inicio .o_dcasa_cifra'), 'las cifras');
            const orden = ['Productos', 'Facturas', 'Conversaciones', 'Escáner', 'Oportunidades', 'Resumen contable'];
            const atajos = textos('.o_dcasa_atajo strong');
            igual(atajos, orden.filter((t) => atajos.includes(t)), 'orden de los atajos');
            const titulos = textos('.o_dcasa_cifra .o_dcasa_cifra_titulo');
            if (!titulos.includes('Por cobrar')) { throw new Error('Gerencia debe ver Por cobrar'); }
            for (const fuera of ['Cobrado hoy', 'Vendido hoy', 'Cotizaciones abiertas', 'Entregas pendientes']) {
                if (titulos.includes(fuera)) { throw new Error('esa cifra ahora va en su panel: ' + fuera); }
            }
            await esperar(() => document.querySelector('.o_dcasa_ventas'), 'el panel de ventas');
            await esperar(() => document.querySelector('.o_dcasa_lista_cotizaciones'), 'las cotizaciones abiertas');
            await esperar(() => document.querySelector('.o_dcasa_lista_entregas'), 'las entregas pendientes');
            // Cotizaciones y entregas, justo debajo de los accesos azules y con cabecera de acento (2026-10-16).
            const listas = document.querySelector('.o_dcasa_listas');
            if (document.querySelector('.o_dcasa_atajos').nextElementSibling !== listas) {
                throw new Error('las cotizaciones y las entregas van justo debajo de los accesos azules');
            }
            const fondo = getComputedStyle(listas.querySelector('.o_dcasa_lista_cabeza')).backgroundColor;
            igual(fondo, 'rgb(14, 42, 107)', 'la cabecera de las listas va en azul marino');
            const numero = getComputedStyle(listas.querySelector('.o_dcasa_lista_numero')).backgroundColor;
            igual(numero, 'rgb(254, 208, 15)', 'el número va en amarillo, sobre el azul');
            igual(textos('.o_dcasa_ganancia .o_dcasa_ventas_etiqueta'), ['Ganancia bruta'], 'el nombre de la ganancia');
            await esperar(() => document.querySelector('.o_dcasa_semana'), 'las barras de la semana');
            const botones = textos('.o_dcasa_inicio_accesos .btn');
            for (const dentro of ['Nueva cotización', 'Nuevo cliente', 'Registrar cobro']) {
                if (!botones.includes(dentro)) { throw new Error('falta el botón ' + dentro); }
            }
            for (const fuera of ['Nueva factura', 'Ver en el celular']) {
                if (botones.includes(fuera)) { throw new Error('ya no debe estar el botón ' + fuera); }
            }
            if (!document.querySelector('.o_dcasa_ver_tienda[aria-label="Ver la tienda"]')) {
                throw new Error('falta «Ver la tienda» (solo con ícono)');
            }
            // Los periodos de las ventas: Hoy ya está activo; Esta semana cambia la etiqueta.
            if (!document.querySelector('.o_dcasa_periodo_hoy.o_activo')) { throw new Error('Hoy debe estar activo'); }
            // Las frases de comparación se reemplazaron por el bloque «Comparar» (jefe, 2026-10-17) y el interruptor
            // «Facturado» · «Con abonos» · «Completadas» abre en «Facturado» (las facturas, como Contabilidad).
            if (document.querySelector('.o_dcasa_comparacion')) { throw new Error('ya no hay frases de comparación'); }
            igual(textos('.o_dcasa_interruptor_opcion'), ['Facturado', 'Con abonos', 'Completadas'], 'el interruptor');
            if (!document.querySelector('.o_dcasa_base_facturado.o_activo')) {
                throw new Error('el Inicio abre en «Facturado»');
            }
            igual(textos('.o_dcasa_chip').length, 6, 'los botones de Comparar');
            document.querySelector('.o_dcasa_periodo_semana').click();
            await esperar(() => document.querySelector('.o_dcasa_periodo_semana.o_activo'), 'la semana activa');
            await esperar(
                () => document.querySelector('.o_dcasa_ventas_etiqueta')?.textContent === 'Esta semana', 'la etiqueta');
            // El Inicio baja con scroll (regla fuerte de interfaz.scss).
            const accion = document.querySelector('.o_dcasa_inicio');
            if (getComputedStyle(accion).overflowY !== 'auto') { throw new Error('el Inicio debe tener scroll'); }
        """)

    def test_ayuda_propia_en_la_lista_vacia_de_gastos_por_reembolsar(self):
        if not self.env.ref('dcasa_nomina.accion_mis_reembolsos', raise_if_not_found=False):
            self.skipTest('Sin dcasa_nomina')
        codigo = '(async () => {' + ESPERAR_JS + """
            const ayuda = await esperar(() => document.querySelector('.o_view_nocontent'), 'la ayuda de la lista');
            const texto = ayuda.textContent.replace(/\\s+/g, ' ');
            if (!texto.includes('regístralo aquí con la foto del recibo')) {
                throw new Error('Se esperaba la ayuda propia y se vio: ' + texto);
            }
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/action-dcasa_nomina.accion_mis_reembolsos', codigo, login='vendedora_rol')
