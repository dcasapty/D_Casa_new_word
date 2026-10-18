"""Facturación › Tablero: tarjetas «Facturas de clientes» y «Facturas de proveedores»."""
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

PANEL = 'dcasa.facturas.panel'


@tagged('post_install', '-at_install')
class TestPanelFacturas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env['res.users'])
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE PANEL'})
        cls.proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR PANEL'})
        cls.producto = cls.env['product.product'].create({'name': 'MESA PANEL', 'type': 'consu', 'list_price': 50.0})
        cls.gerencia = crear_usuario(cls.env, 'panel_gerencia', 'dcasa_base.group_gerencia')
        cls.vendedora = crear_usuario(cls.env, 'panel_vendedora', 'dcasa_base.group_vendedora')
        cls.cajero = crear_usuario(cls.env, 'panel_cajero', 'account.group_account_invoice')
        cls.contador = crear_usuario(cls.env, 'panel_contador', 'account.group_account_user')
        cls.lector = crear_usuario(cls.env, 'panel_lector', 'account.group_account_readonly')
        cls.administrador = crear_usuario(cls.env, 'panel_admin_contable', 'account.group_account_manager')

    def _factura(self, tipo, publicar=True, vence_en=0, precio=100.0, vendedora=None):
        """vence_en: días desde hoy (negativo = ya venció). vendedora: de quién es la factura."""
        valores = {
            'move_type': tipo, 'partner_id': (self.cliente if tipo == 'out_invoice' else self.proveedor).id,
            'invoice_date': self.hoy - timedelta(days=60), 'invoice_date_due': self.hoy + timedelta(days=vence_en),
            'invoice_line_ids': [
                Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': precio})]}
        if vendedora:
            valores['invoice_user_id'] = vendedora.id
        factura = self.env['account.move'].create(valores)
        if publicar:
            factura.action_post()
        return factura

    def _pagar(self, factura):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': self.hoy})._create_payments()

    def _filas(self, usuario, tarjeta):
        datos = self.env[PANEL].with_user(usuario).obtener_datos()
        for t in datos['tarjetas']:
            if t['clave'] == tarjeta:
                return {fila['clave']: fila for fila in t['filas']}
        return None

    def _cuentas(self, usuario, tarjeta):
        filas = self._filas(usuario, tarjeta)
        return {clave: fila['cuenta'] for clave, fila in filas.items()} if filas is not None else None

    # --- Qué cuenta cada fila --------------------------------------------------------------

    def test_clientes_cuenta_borradores_por_cobrar_y_vencidas(self):
        antes = self._cuentas(self.gerencia, 'clientes')
        self._factura('out_invoice', publicar=False)             # borrador
        self._factura('out_invoice', vence_en=15)                # por cobrar
        self._factura('out_invoice', vence_en=-5)                # por cobrar y vencida
        self._factura('out_invoice', vence_en=0)                 # vence hoy: por cobrar, aún no vencida
        pagada = self._factura('out_invoice', vence_en=-30)      # pagada: no cuenta
        self._pagar(pagada)
        despues = self._cuentas(self.gerencia, 'clientes')
        self.assertEqual(despues['borradores'] - antes['borradores'], 1)
        self.assertEqual(despues['pendientes'] - antes['pendientes'], 3)
        self.assertEqual(despues['vencidas'] - antes['vencidas'], 1)

    def test_un_pago_parcial_sigue_por_cobrar(self):
        antes = self._cuentas(self.gerencia, 'clientes')
        factura = self._factura('out_invoice', vence_en=-3)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': self.hoy, 'amount': 10.0})._create_payments()
        self.assertEqual(factura.payment_state, 'partial')
        despues = self._cuentas(self.gerencia, 'clientes')
        self.assertEqual(despues['pendientes'] - antes['pendientes'], 1)
        self.assertEqual(despues['vencidas'] - antes['vencidas'], 1)

    def test_proveedores_cuenta_por_pagar_vencidas_y_borradores(self):
        antes = self._cuentas(self.gerencia, 'proveedores')
        self._factura('in_invoice', publicar=False)
        self._factura('in_invoice', vence_en=10)
        self._factura('in_invoice', vence_en=-2)
        despues = self._cuentas(self.gerencia, 'proveedores')
        self.assertEqual(despues['borradores'] - antes['borradores'], 1)
        self.assertEqual(despues['pendientes'] - antes['pendientes'], 2)
        self.assertEqual(despues['vencidas'] - antes['vencidas'], 1)

    def test_los_montos_salen_en_dinero_y_las_vencidas_se_marcan(self):
        antes = self._filas(self.gerencia, 'clientes')
        self._factura('out_invoice', vence_en=-5, precio=123.0)
        filas = self._filas(self.gerencia, 'clientes')
        self.assertIsNone(filas['borradores']['monto'], 'los borradores no tienen saldo')
        self.assertIn('$', filas['pendientes']['monto'])
        self.assertTrue(filas['vencidas']['alerta'])
        self.assertEqual(filas['vencidas']['texto'], 'Vencidas')
        self.assertEqual(filas['pendientes']['texto'], 'Por cobrar')
        self.assertEqual(self._filas(self.gerencia, 'proveedores')['pendientes']['texto'], 'Por pagar')
        self.assertNotEqual(filas['vencidas']['monto'], antes['vencidas']['monto'])

    def test_el_orden_de_las_filas_es_el_que_pidio_la_duena(self):
        datos = self.env[PANEL].with_user(self.gerencia).obtener_datos()
        orden = {t['clave']: [f['clave'] for f in t['filas']] for t in datos['tarjetas']}
        self.assertEqual(orden['clientes'], ['borradores', 'pendientes', 'vencidas'])
        self.assertEqual(orden['proveedores'], ['pendientes', 'vencidas', 'borradores'])
        self.assertEqual([t['titulo'] for t in datos['tarjetas']], ['Facturas de clientes', 'Facturas de proveedores'])

    # --- Cada número abre la misma lista que cuenta ----------------------------------------------

    def test_cada_fila_abre_la_lista_que_cuenta(self):
        borrador = self._factura('out_invoice', publicar=False)
        por_cobrar = self._factura('out_invoice', vence_en=20)
        vencida = self._factura('out_invoice', vence_en=-9)
        pagada = self._factura('out_invoice', vence_en=-9)
        self._pagar(pagada)
        panel = self.env[PANEL].with_user(self.gerencia)
        for fila, esperadas, ausentes in (
                ('borradores', borrador, por_cobrar | vencida | pagada),
                ('pendientes', por_cobrar | vencida, borrador | pagada),
                ('vencidas', vencida, borrador | por_cobrar | pagada)):
            accion = panel.abrir('clientes', fila)
            self.assertEqual(accion['res_model'], 'account.move')
            encontradas = self.env['account.move'].search(accion['domain'])
            self.assertLessEqual(esperadas, encontradas, fila)
            self.assertFalse(encontradas & ausentes, fila)
            # El número y la lista salen del mismo dominio.
            self.assertEqual(len(encontradas), self._cuentas(self.gerencia, 'clientes')[fila], fila)
        todas = panel.abrir('clientes')
        self.assertIn('Facturas de clientes', todas['name'])
        self.assertEqual(todas['display_name'], todas['name'])
        self.assertTrue(self.env['account.move'].search(todas['domain']) >= borrador | por_cobrar)
        self.assertIn('Vencidas', panel.abrir('clientes', 'vencidas')['name'])

    def test_las_listas_de_proveedores_son_de_facturas_de_proveedores(self):
        compra = self._factura('in_invoice', vence_en=5)
        venta = self._factura('out_invoice', vence_en=5)
        accion = self.env[PANEL].with_user(self.gerencia).abrir('proveedores', 'pendientes')
        encontradas = self.env['account.move'].search(accion['domain'])
        self.assertIn(compra, encontradas)
        self.assertNotIn(venta, encontradas)
        self.assertEqual(set(encontradas.mapped('move_type')), {'in_invoice'})

    def test_una_fila_desconocida_abre_todas(self):
        accion = self.env[PANEL].with_user(self.gerencia).abrir('clientes', 'cosa_rara')
        self.assertEqual(accion['domain'], [('move_type', '=', 'out_invoice')])

    # --- Permisos ----------------------------------------------------------------------------------

    def test_quien_cobra_ve_clientes_y_no_proveedores(self):
        for usuario in (self.vendedora, self.cajero):
            datos = self.env[PANEL].with_user(usuario).obtener_datos()
            self.assertEqual([t['clave'] for t in datos['tarjetas']], ['clientes'], usuario.login)
            with self.assertRaises(AccessError, msg=usuario.login):
                self.env[PANEL].with_user(usuario).abrir('proveedores')
            with self.assertRaises(AccessError, msg=usuario.login):
                self.env[PANEL].with_user(usuario).abrir('proveedores', 'pendientes')
            self.assertTrue(self.env[PANEL].with_user(usuario).abrir('clientes'))

    def test_contabilidad_gerencia_y_administradores_ven_las_dos(self):
        for usuario in (self.gerencia, self.contador, self.lector, self.administrador):
            datos = self.env[PANEL].with_user(usuario).obtener_datos()
            self.assertEqual([t['clave'] for t in datos['tarjetas']], ['clientes', 'proveedores'], usuario.login)
            self.assertTrue(self.env[PANEL].with_user(usuario).abrir('proveedores', 'vencidas'))

    def test_la_vendedora_no_cuenta_las_facturas_de_proveedores_ni_por_otra_via(self):
        self._factura('in_invoice', vence_en=-4)
        panel = self.env[PANEL].with_user(self.vendedora)
        self.assertIsNone(self._filas(self.vendedora, 'proveedores'))
        with self.assertRaises(AccessError):
            panel.abrir('proveedores', 'vencidas')
        with self.assertRaises(AccessError):
            panel.abrir('cosa_inventada')

    def test_la_vendedora_ve_tus_facturas_y_cuenta_solo_las_suyas(self):
        """Con «Cada vendedora ve solo sus documentos» encendido, sus cifras no son las de la tienda: la tarjeta se
        titula «Tus facturas de clientes» y cuenta solo las suyas. Caja y Gerencia ven la tarjeta de siempre."""
        caja = crear_usuario(self.env, 'panel_caja', 'dcasa_base.group_caja')
        otra = crear_usuario(self.env, 'panel_otra_vendedora', 'dcasa_base.group_vendedora')
        antes = {u: self._cuentas(u, 'clientes')['pendientes'] for u in (self.vendedora, caja, self.gerencia)}
        self._factura('out_invoice', vence_en=5, vendedora=self.vendedora)
        self._factura('out_invoice', vence_en=5, vendedora=otra)
        despues = {u: self._cuentas(u, 'clientes')['pendientes'] for u in (self.vendedora, caja, self.gerencia)}
        self.assertEqual(despues[self.vendedora] - antes[self.vendedora], 1, 'solo la suya')
        self.assertEqual(despues[caja] - antes[caja], 2)
        self.assertEqual(despues[self.gerencia] - antes[self.gerencia], 2)
        titulo = self.env[PANEL].with_user(self.vendedora).obtener_datos()['tarjetas'][0]['titulo']
        self.assertEqual(titulo, 'Tus facturas de clientes')
        self.assertIn('Tus facturas de clientes', self.env[PANEL].with_user(self.vendedora).abrir('clientes')['name'])
        for usuario in (caja, self.gerencia):
            self.assertEqual(self.env[PANEL].with_user(usuario).obtener_datos()['tarjetas'][0]['titulo'],
                             'Facturas de clientes', usuario.login)
        # Apagado el interruptor, la vendedora vuelve a ver la tarjeta de siempre, con todas.
        self.env['res.users']._dcasa_poner_restriccion(False)
        self.assertEqual(self.env[PANEL].with_user(self.vendedora).obtener_datos()['tarjetas'][0]['titulo'],
                         'Facturas de clientes')
        self.assertEqual(self._cuentas(self.vendedora, 'clientes')['pendientes'], despues[caja])
