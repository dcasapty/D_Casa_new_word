"""Lo contable «de un jefe» no se ve por datos: la Vendedora (y la Caja) solo tocan lo del flujo de venta.

La dueña pidió que quien vende no vea nada de nómina ni de la contabilidad de un jefe. Por el menú ya no lo
ve; este archivo fija que tampoco lo vea por datos (URL, enlace o RPC): facturas y pagos de proveedores,
asientos varios (la nómina se contabiliza ahí), pagos salientes y movimientos bancarios. Y fija lo contrario:
contabilidad, Gerencia y el administrador siguen viendo y haciendo todo, y la venta sigue entera.
Desde 2026-10-16 la Vendedora ve solo lo suyo (sus facturas, notas y cobros); la Caja, lo de clientes de toda la tienda
(el detalle está en test_solo_lo_suyo.py). Reglas: security/dcasa_reglas_contables.xml. Explicación: docs/PERMISOS.md.
"""
import re
from pathlib import Path

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import convert_file

from .test_roles import crear_usuario

CLIENTE = ('out_invoice', 'out_refund', 'out_receipt')
ARCHIVO_REGLAS = 'security/dcasa_reglas_contables.xml'

# Reglas estándar de Odoo que el archivo estrecha, con el dominio que Odoo trae de fábrica.
REGLAS_ESTANDAR = (
    'account.account_move_see_all', 'account.account_move_rule_group_invoice',
    'account.account_move_line_see_all', 'account.account_move_line_rule_group_invoice',
    'account.account_analytic_line_rule_billing_user', 'account.ir_rule_res_partner_bank_billing_officers',
    'sale.account_invoice_report_rule_see_all', 'sale.account_invoice_report_rule_see_personal',
)


class PermisosContablesCommon(TransactionCase):
    """Un negocio de prueba con lo de cliente y lo «de jefe», y una persona de cada rol."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.ref('base.main_company')
        # Personas
        cls.vendedora = crear_usuario(env, 'perm_cont_vendedora', 'dcasa_base.group_vendedora')
        cls.cajero = crear_usuario(env, 'perm_cont_cajero', 'dcasa_base.group_caja')  # el rol «Caja» (y de Brian)
        cls.otra_vendedora = crear_usuario(env, 'perm_cont_otra_vendedora', 'dcasa_base.group_vendedora')
        cls.gerencia = crear_usuario(env, 'perm_cont_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(env, 'perm_cont_contador', 'account.group_account_user')
        cls.gerente_contable = crear_usuario(env, 'perm_cont_gerente_cont', 'account.group_account_manager')
        cls.lector = crear_usuario(env, 'perm_cont_lector', 'account.group_account_readonly')
        cls.admin = env.ref('base.user_admin')
        cls.con_contabilidad = (cls.gerencia, cls.contador, cls.gerente_contable, cls.admin)
        cls.sin_contabilidad = (cls.vendedora, cls.cajero)

        # Negocio
        # Con celular y correo: sin ellos no se publica la factura (dcasa_contactos, 2026-10-16).
        cls.cliente = env['res.partner'].create({'name': 'Cliente Prueba Permisos', 'phone': '6000-0011',
                                                 'email': 'cliente.permisos@example.com'})
        cls.proveedor = env['res.partner'].create({'name': 'Proveedor Prueba Permisos'})
        cls.producto = env['product.product'].create({'name': 'Mueble Prueba Permisos', 'list_price': 100.0})
        Diario = env['account.journal']
        cls.banco = Diario.search([('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1)
        cls.efectivo = Diario.search([('type', '=', 'cash'), ('company_id', '=', cls.company.id)], limit=1)
        cls.varios = Diario.search([('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        cls.compras = Diario.search([('type', '=', 'purchase'), ('company_id', '=', cls.company.id)], limit=1)
        plan = env['account.analytic.plan'].create({'name': 'Plan Prueba Permisos'})
        cls.cuenta_analitica = env['account.analytic.account'].create(
            {'name': 'Canal Prueba Permisos', 'plan_id': plan.id})

        # Lo de CLIENTE de la vendedora (lo ve y lo usa). Se crea como superusuario, a nombre de ella: si no, la
        # factura quedaría a nombre del superusuario y ella ya no la vería (solo ve lo suyo).
        cls.factura_cliente = cls._factura('out_invoice', cls.cliente, 100.0, analitica=True, vendedora=cls.vendedora)
        cls.cobro_cliente = cls._pagar(cls.factura_cliente, cls.efectivo)
        # Lo de cliente de OTRA vendedora: la Caja lo ve; la vendedora no.
        cls.factura_de_otra = cls._factura('out_invoice', cls.cliente, 70.0, analitica=True,
                                           vendedora=cls.otra_vendedora)
        cls.cobro_de_otra = cls._pagar(cls.factura_de_otra, cls.efectivo)
        # Lo «de un jefe» (la vendedora no lo ve)
        cls.factura_proveedor = cls._factura('in_invoice', cls.proveedor, 200.0, analitica=True)
        cls.nota_proveedor = cls._factura('in_refund', cls.proveedor, 30.0)
        cls.pago_proveedor = cls._pagar(cls.factura_proveedor, cls.efectivo, monto=50.0)
        cls.asiento_vario = cls._asiento_vario('Contabilización de nómina de prueba', 80.0)
        cls.movimiento_banco = env['account.bank.statement.line'].create({
            'journal_id': cls.banco.id, 'date': fields.Date.today(), 'amount': 500.0,
            'payment_ref': 'Depósito de prueba',
        })
        cls.extracto = cls.movimiento_banco.statement_id
        if not cls.extracto:
            cls.extracto = env['account.bank.statement'].create({
                'name': 'Extracto prueba permisos', 'journal_id': cls.banco.id,
                'line_ids': [Command.set(cls.movimiento_banco.ids)],
            })
        cls.cosas_de_jefe = cls._armar_cosas_de_jefe()

    # --- ayudas de datos (siempre como superusuario) -------------------------------------------------------
    @classmethod
    def _factura(cls, tipo, socio, monto, analitica=False, vendedora=None):
        compra = tipo.startswith('in_')
        linea = {'product_id': cls.producto.id, 'quantity': 1, 'price_unit': monto}
        if compra:
            linea['tax_ids'] = [Command.clear()]
        if analitica:
            linea['analytic_distribution'] = {str(cls.cuenta_analitica.id): 100}
        valores = {
            'move_type': tipo, 'partner_id': socio.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create(linea)],
        }
        if vendedora:
            valores['invoice_user_id'] = vendedora.id
        factura = cls.env['account.move'].create(valores)
        factura.action_post()
        return factura

    @classmethod
    def _pagar(cls, factura, diario, monto=None):
        valores = {'payment_date': fields.Date.today(), 'journal_id': diario.id}
        if monto:
            valores['amount'] = monto
        registro = cls.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(valores)
        return registro._create_payments()

    @classmethod
    def _asiento_vario(cls, texto, monto):
        Cuenta = cls.env['account.account']
        gasto = Cuenta.search([('account_type', '=', 'expense')], limit=1)
        efectivo = Cuenta.search([('account_type', '=', 'asset_cash')], limit=1)
        asiento = cls.env['account.move'].create({
            'move_type': 'entry', 'journal_id': cls.varios.id, 'date': fields.Date.today(), 'ref': texto,
            'line_ids': [
                Command.create({'account_id': gasto.id, 'debit': monto, 'name': texto}),
                Command.create({'account_id': efectivo.id, 'credit': monto, 'name': texto}),
            ],
        })
        asiento.action_post()
        return asiento

    @classmethod
    def _armar_cosas_de_jefe(cls):
        """Todo lo que la vendedora NO debe poder ver ni tocar, como (nombre, registros)."""
        asientos = (cls.factura_proveedor | cls.nota_proveedor | cls.asiento_vario
                    | cls.pago_proveedor.move_id | cls.movimiento_banco.move_id)
        apuntes = asientos.line_ids
        conciliaciones = apuntes.matched_debit_ids | apuntes.matched_credit_ids
        analiticas = cls.env['account.analytic.line'].search(
            [('move_line_id', 'in', cls.factura_proveedor.line_ids.ids)])
        return (
            ('facturas de proveedor, asientos varios y de pagos salientes y del banco', asientos),
            ('apuntes de esos asientos', apuntes),
            ('pagos salientes', cls.pago_proveedor),
            ('movimientos bancarios', cls.movimiento_banco),
            ('extractos bancarios', cls.extracto),
            ('conciliaciones de proveedor', conciliaciones),
            ('líneas analíticas de gastos', analiticas),
        )

    # --- el mismo recorrido para cada modelo --------------------------------------------------------------
    def _cerrado(self, registros, usuario, etiqueta=''):
        """Para ``usuario`` esos registros no existen: ni se buscan, ni se cuentan, ni se leen, ni se tocan."""
        self.assertTrue(registros, f'{etiqueta}: el dato de prueba no se creó')
        dominio = [('id', 'in', registros.ids)]
        Modelo = registros.browse().with_user(usuario)
        self.assertFalse(Modelo.search(dominio), f'{etiqueta}: aparece en search')
        self.assertEqual(Modelo.search_count(dominio), 0, f'{etiqueta}: cuenta en search_count')
        self.assertFalse(Modelo.search_read(dominio, ['id']), f'{etiqueta}: aparece en search_read')
        self.assertEqual(Modelo._read_group(dominio, [], ['__count']), [(0,)], f'{etiqueta}: cuenta en read_group')
        propios = registros.with_user(usuario)
        with self.assertRaises(AccessError, msg=f'{etiqueta}: se puede leer'):
            propios.read(['display_name'])
        for operacion in ('read', 'write', 'unlink'):
            with self.assertRaises(AccessError, msg=f'{etiqueta}: {operacion} permitido'):
                propios.check_access(operacion)

    def _igual_que_el_permiso_del_modelo(self, registros, usuario, etiqueta=''):
        """Contabilidad no pierde nada: lo que el permiso del modelo da, las reglas lo dejan sobre todo registro."""
        Modelo = registros.browse().with_user(usuario)
        propios = registros.with_user(usuario)
        dominio = [('id', 'in', registros.ids)]
        for operacion in ('read', 'write', 'unlink'):
            if Modelo.has_access(operacion):
                propios.check_access(operacion)  # no debe lanzar AccessError
            else:
                with self.assertRaises(AccessError, msg=f'{etiqueta}: {operacion} no debería'):
                    propios.check_access(operacion)
        if Modelo.has_access('read'):
            self.assertEqual(Modelo.search(dominio), registros, f'{etiqueta}: {usuario.login} debe ver todo')
            self.assertEqual(Modelo.search_count(dominio), len(registros))


@tagged('post_install', '-at_install')
class TestVendedoraVendeYCobra(PermisosContablesCommon):
    """Lo que SÍ sigue pudiendo la vendedora (y la Caja): todo el flujo de venta."""

    def _facturar(self, usuario):
        factura = self.env['account.move'].with_user(usuario).create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 2, 'price_unit': 100.0})],
        })
        factura.action_post()
        return factura

    def _cobrar(self, usuario, factura, **valores):
        registro = self.env['account.payment.register'].with_user(usuario).with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'payment_date': fields.Date.today(), 'journal_id': self.efectivo.id, **valores})
        return registro._create_payments()

    def test_factura_cobro_y_conciliacion(self):
        # Efectivo (caja) y banco (Yappy, tarjeta): las dos formas de cobro de la tienda.
        for usuario, diario in [(u, d) for u in self.sin_contabilidad for d in (self.efectivo, self.banco)]:
            with self.subTest(usuario=usuario.login, diario=diario.name):
                factura = self._facturar(usuario)
                self.assertEqual(factura.state, 'posted')
                self.assertAlmostEqual(factura.amount_total, 214.0)
                pago = self._cobrar(usuario, factura, journal_id=diario.id)
                self.assertEqual(pago.payment_type, 'inbound')
                self.assertIn(factura.payment_state, ('paid', 'in_payment'))
                # El asiento del cobro y su conciliación con la factura son visibles para ella.
                asiento = pago.with_user(usuario).move_id
                self.assertEqual(asiento.origin_payment_id, pago)
                self.assertTrue(asiento.line_ids.with_user(usuario).mapped('account_id'))
                por_cobrar = factura.with_user(usuario).line_ids.filtered(
                    lambda linea: linea.account_id.account_type == 'asset_receivable')
                conciliaciones = por_cobrar.matched_credit_ids | por_cobrar.matched_debit_ids
                self.assertTrue(conciliaciones, 'la conciliación con el cobro debe verse')
                self.assertEqual(conciliaciones.with_user(usuario).search_count([('id', 'in', conciliaciones.ids)]),
                                 len(conciliaciones))
                self.assertTrue(factura.with_user(usuario).invoice_payments_widget)
                self.assertTrue(pago.with_user(usuario).read(['name', 'amount', 'state']))

    def test_cobro_parcial_y_nota_de_credito(self):
        for usuario in self.sin_contabilidad:
            with self.subTest(usuario=usuario.login):
                factura = self._facturar(usuario)
                self._cobrar(usuario, factura, amount=100.0)
                self.assertEqual(factura.payment_state, 'partial')
                reversa = self.env['account.move.reversal'].with_user(usuario).with_context(
                    active_model='account.move', active_ids=factura.ids).create(
                    {'reason': 'Devolución de prueba', 'journal_id': factura.journal_id.id})
                nota = self.env['account.move'].with_user(usuario).browse(reversa.refund_moves()['res_id'])
                self.assertEqual(nota.move_type, 'out_refund')
                nota.action_post()
                self.assertEqual(nota.state, 'posted')
                self.assertTrue(nota.line_ids)

    def test_facturar_desde_una_orden_de_venta(self):
        for usuario in self.sin_contabilidad:
            with self.subTest(usuario=usuario.login):
                orden = self.env['sale.order'].with_user(usuario).create({
                    'partner_id': self.cliente.id,
                    'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
                })
                orden.action_confirm()
                factura = orden._create_invoices()
                factura.with_user(usuario).action_post()
                self.assertEqual(factura.move_type, 'out_invoice')
                self.assertEqual(factura.with_user(usuario).search_count([('id', '=', factura.id)]), 1)

    def test_imprimir_y_enviar_la_factura(self):
        factura = self._facturar(self.vendedora)
        self._cobrar(self.vendedora, factura)
        html, _formato = self.env['ir.actions.report'].with_user(self.vendedora)._render_qweb_html(
            'account.report_invoice', factura.ids)
        self.assertIn(factura.name, html.decode())
        asistente = self.env['account.move.send.wizard'].with_user(self.vendedora).with_context(
            active_model='account.move', active_ids=factura.ids).create({'move_id': factura.id})
        self.assertEqual(asistente.move_id, factura)
        self.assertTrue(asistente.with_user(self.vendedora).read(['display_name']))

    def test_lee_lo_suyo_de_cliente(self):
        for usuario in self.sin_contabilidad:
            with self.subTest(usuario=usuario.login):
                visibles = self.env['account.move'].with_user(usuario).search([])
                self.assertIn(self.factura_cliente, visibles)
                self.assertIn(self.cobro_cliente.move_id, visibles, 'el asiento del cobro de cliente')
                self.assertTrue(self.factura_cliente.line_ids.with_user(usuario).read(['name', 'debit', 'credit']))
                self.assertIn(self.cobro_cliente, self.env['account.payment'].with_user(usuario).search([]))
                # Lo de la otra vendedora: la Caja sí lo ve; la vendedora no (solo lo suyo).
                ajeno = (self.factura_de_otra, self.cobro_de_otra.move_id)
                for registro in ajeno:
                    if usuario == self.cajero:
                        self.assertIn(registro, visibles)
                    else:
                        self.assertNotIn(registro, visibles)
                pagos_visibles = self.env['account.payment'].with_user(usuario).search([])
                self.assertEqual(self.cobro_de_otra in pagos_visibles, usuario == self.cajero)
                # Y todo lo que ve es de cliente o cobro de cliente: nada más se cuela.
                ajenos = visibles.filtered(lambda m: m.move_type not in CLIENTE and not (
                    m.move_type == 'entry' and m.origin_payment_id.payment_type == 'inbound'))
                self.assertFalse(ajenos, f've asientos que no son de cliente: {ajenos.mapped("display_name")}')
                apuntes = self.env['account.move.line'].with_user(usuario).search([])
                self.assertFalse(apuntes.filtered(lambda a: a.move_id.move_type not in CLIENTE and not (
                    a.move_id.move_type == 'entry' and a.move_id.origin_payment_id.payment_type == 'inbound')))
                pagos = self.env['account.payment'].with_user(usuario).search([])
                self.assertEqual(set(pagos.mapped('payment_type')), {'inbound'})

    def test_ve_sus_lineas_analiticas_de_cliente(self):
        Analitica = self.env['account.analytic.line']
        propias = Analitica.search([('move_line_id', 'in', self.factura_cliente.line_ids.ids)])
        de_otra = Analitica.search([('move_line_id', 'in', self.factura_de_otra.line_ids.ids)])
        self.assertTrue(propias and de_otra, 'la factura de cliente con canal debe dejar su línea analítica')
        self.assertEqual(Analitica.with_user(self.vendedora).search([('id', 'in', (propias | de_otra).ids)]), propias)
        # La Caja y el lector contable ven las de toda la tienda (de clientes).
        for usuario in (self.cajero, self.lector):
            self.assertEqual(Analitica.with_user(usuario).search([('id', 'in', (propias | de_otra).ids)]),
                             propias | de_otra, usuario.login)

    def test_reportes_de_ventas_de_clientes(self):
        informe = self.env['account.invoice.report']
        como_vendedora = informe.with_user(self.vendedora).search([('move_id', '=', self.factura_cliente.id)])
        self.assertTrue(como_vendedora, 'el análisis de facturas de CLIENTE sigue disponible')

    def test_clientes_se_crean_y_editan(self):
        cliente = self.env['res.partner'].with_user(self.vendedora).create({'name': 'Cliente nuevo permisos'})
        cliente.write({'phone': '+507 6000-0000'})
        self.assertEqual(cliente.phone, '+507 6000-0000')
        banco = self.env['res.partner.bank'].create({'acc_number': 'PRUEBA-0001', 'partner_id': cliente.id})
        self.assertEqual(self.env['res.partner.bank'].with_user(self.vendedora).search([('id', '=', banco.id)]), banco)


@tagged('post_install', '-at_install')
class TestVendedoraNoVeLoContable(PermisosContablesCommon):
    """Lo que la vendedora (y la Caja) NO pueden ver ni tocar por datos."""

    def test_nada_de_proveedores_ni_asientos_varios_ni_bancos(self):
        for usuario in self.sin_contabilidad:
            for etiqueta, registros in self.cosas_de_jefe:
                with self.subTest(usuario=usuario.login, que=etiqueta):
                    self._cerrado(registros, usuario, etiqueta)

    def test_ni_siquiera_los_totales(self):
        """Ni sumas ni conteos agrupados dejan ver los números de proveedores."""
        for usuario in self.sin_contabilidad:
            Apunte = self.env['account.move.line'].with_user(usuario)
            dominio = [('move_id', 'in', (self.factura_proveedor | self.asiento_vario).ids)]
            self.assertEqual(Apunte.search_count(dominio), 0)
            self.assertFalse(Apunte._read_group(dominio, ['account_id'], ['balance:sum']))
            Pago = self.env['account.payment'].with_user(usuario)
            self.assertFalse(Pago._read_group([('payment_type', '=', 'outbound')], ['journal_id'], ['amount:sum']))
            Informe = self.env['account.invoice.report'].with_user(usuario)
            self.assertFalse(Informe.search([('move_type', 'in', ('in_invoice', 'in_refund'))]))
            self.assertFalse(Informe.search([('move_id', '=', self.factura_proveedor.id)]))

    def test_no_puede_crear_lo_que_no_es_suyo(self):
        for usuario in self.sin_contabilidad:
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError, msg='factura de proveedor'):
                    self.env['account.move'].with_user(usuario).create({
                        'move_type': 'in_invoice', 'partner_id': self.proveedor.id, 'invoice_date': fields.Date.today(),
                        'invoice_line_ids': [Command.create({'name': 'Falsa', 'quantity': 1, 'price_unit': 1.0})],
                    })
                cuentas = self.env['account.account'].search(
                    [('account_type', 'in', ('expense', 'asset_cash'))], limit=2)
                with self.assertRaises(AccessError, msg='asiento vario'):
                    self.env['account.move'].with_user(usuario).create({
                        'move_type': 'entry', 'journal_id': self.varios.id,
                        'line_ids': [Command.create({'account_id': cuentas[0].id, 'debit': 1.0}),
                                     Command.create({'account_id': cuentas[1].id, 'credit': 1.0})],
                    })
                with self.assertRaises(AccessError, msg='pago saliente'):
                    self.env['account.payment'].with_user(usuario).create({
                        'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.proveedor.id,
                        'amount': 10.0, 'journal_id': self.efectivo.id,
                    })
                with self.assertRaises(AccessError, msg='movimiento bancario'):
                    self.env['account.bank.statement.line'].with_user(usuario).create({
                        'journal_id': self.banco.id, 'amount': 10.0, 'payment_ref': 'Falso'})

    def test_no_puede_pagar_a_proveedores_ni_desconciliar(self):
        """Pagar una factura de proveedor, o deshacer el pago que ya se hizo, es de contabilidad."""
        factura = self._factura('in_invoice', self.proveedor, 60.0)
        with self.assertRaises(AccessError):
            self.env['account.payment.register'].with_user(self.vendedora).with_context(
                active_model='account.move', active_ids=factura.ids).create(
                {'payment_date': fields.Date.today(), 'journal_id': self.efectivo.id})._create_payments()
        conciliaciones = self.pago_proveedor.move_id.line_ids.matched_debit_ids \
            | self.pago_proveedor.move_id.line_ids.matched_credit_ids
        self.assertTrue(conciliaciones)
        with self.assertRaises(AccessError):
            conciliaciones.with_user(self.vendedora).unlink()
        with self.assertRaises(AccessError):
            self.pago_proveedor.with_user(self.vendedora).action_draft()

    def test_no_edita_ni_borra_lo_ajeno_aunque_conozca_el_id(self):
        for usuario in self.sin_contabilidad:
            with self.assertRaises(AccessError):
                self.factura_proveedor.with_user(usuario).write({'narration': 'cambio'})
            with self.assertRaises(AccessError):
                self.asiento_vario.with_user(usuario).write({'ref': 'cambio'})
            with self.assertRaises(AccessError):
                self.pago_proveedor.with_user(usuario).write({'memo': 'cambio'})
            with self.assertRaises(AccessError):
                self.asiento_vario.line_ids.with_user(usuario).write({'name': 'cambio'})
            with self.assertRaises(AccessError):
                self.factura_proveedor.with_user(usuario).unlink()

    def test_no_ve_las_cuentas_bancarias_de_empleados(self):
        if 'hr.employee' not in self.env:
            self.skipTest('Sin Recursos Humanos instalado no hay cuentas de empleados.')
        empleado = self.env['hr.employee'].create({'name': 'Empleada Prueba Permisos'})
        cuenta_empleado = self.env['res.partner.bank'].create(
            {'acc_number': 'PRUEBA-EMPLEADO', 'partner_id': empleado.work_contact_id.id})
        cuenta_cliente = self.env['res.partner.bank'].create(
            {'acc_number': 'PRUEBA-CLIENTE', 'partner_id': self.cliente.id})
        for usuario in self.sin_contabilidad:
            Banco = self.env['res.partner.bank'].with_user(usuario)
            self.assertFalse(Banco.search([('id', '=', cuenta_empleado.id)]), 'cuenta de una empleada (nómina)')
            self.assertEqual(Banco.search([('id', '=', cuenta_cliente.id)]), cuenta_cliente)
        for usuario in (self.gerencia, self.contador, self.gerente_contable, self.admin):
            self.assertEqual(self.env['res.partner.bank'].with_user(usuario).search(
                [('id', '=', cuenta_empleado.id)]), cuenta_empleado, usuario.login)

    def test_ninguna_pantalla_de_nomina(self):
        for modelo in ('dcasa.nomina.planilla', 'dcasa.nomina.linea', 'dcasa.nomina.parametros',
                       'dcasa.nomina.liquidacion', 'dcasa.nomina.vacacion', 'dcasa.nomina.config'):
            if modelo in self.env:
                for usuario in self.sin_contabilidad:
                    self.assertFalse(
                        self.env[modelo].with_user(usuario).has_access('read'), f'{usuario.login}: {modelo}')

    def test_no_ve_lo_que_se_le_debe_a_proveedores_ni_el_tablero_del_banco(self):
        """Campos que Odoo calcula con SQL directo (saltan las reglas): se frenan por grupo del campo."""
        self.assertTrue(self.proveedor.debit, 'el dato de prueba: algo se le debe al proveedor')
        for usuario in self.sin_contabilidad:
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError, msg='lo que se le debe a un proveedor'):
                    self.proveedor.with_user(usuario).read(['debit'])
                for diario in (self.compras, self.banco, self.efectivo):
                    for campo in ('kanban_dashboard', 'kanban_dashboard_graph'):
                        with self.assertRaises(AccessError, msg=f'{campo} de {diario.name}'):
                            diario.with_user(usuario).read([campo])
                # Lo del lado de clientes sí.
                self.assertTrue(self.cliente.with_user(usuario).read(['credit', 'total_invoiced']))

    def test_el_codigo_propio_no_se_cuela_por_sudo(self):
        """Ningún ``env['account.*'].sudo()`` de los módulos propios mira asientos sin filtrar a facturas de cliente.

        Un ``sudo()`` salta las reglas: si una pantalla devolviera lo que encuentra con él, la vendedora vería
        facturas de proveedor aunque las reglas estén bien. Hoy todos filtran ``out_invoice``/``out_refund``; si
        agregas uno nuevo, filtra por tipo (o no devuelvas el resultado a quien vende).
        """
        raiz = Path(__file__).resolve().parents[2]
        patron = re.compile(
            r"env\[['\"]account\.(move|move\.line|payment|bank\.statement|bank\.statement\.line)['\"]\]\.sudo\(\)")
        encontrados = 0
        for archivo in sorted(raiz.glob('*/**/*.py')):
            if 'tests' in archivo.parts:
                continue
            lineas = archivo.read_text(encoding='utf-8').splitlines()
            for numero, linea in enumerate(lineas):
                if patron.search(linea):
                    encontrados += 1
                    contexto = '\n'.join(lineas[max(0, numero - 12):numero + 8])
                    self.assertRegex(
                        contexto, r'out_invoice|out_refund',
                        f'{archivo.relative_to(raiz)}:{numero + 1} usa sudo() sobre asientos sin filtrar a clientes')
        self.assertGreater(encontrados, 0, 'el patrón del test ya no encuentra nada: revísalo')


@tagged('post_install', '-at_install')
class TestContabilidadSigueViendoTodo(PermisosContablesCommon):
    """Contabilidad, Gerencia y el administrador siguen igual que antes: ven y hacen todo."""

    def test_ven_todo_y_les_dejan_tocarlo(self):
        for usuario in self.con_contabilidad:
            for etiqueta, registros in self.cosas_de_jefe:
                with self.subTest(usuario=usuario.login, que=etiqueta):
                    self.assertTrue(registros)
                    self._igual_que_el_permiso_del_modelo(registros, usuario, etiqueta)

    def test_siguen_viendo_lo_que_se_debe_a_proveedores_y_el_tablero_del_banco(self):
        for usuario in self.con_contabilidad + (self.lector,):
            with self.subTest(usuario=usuario.login):
                self.assertEqual(self.proveedor.with_user(usuario).debit, self.proveedor.debit)
                for diario in (self.compras, self.banco):
                    self.assertTrue(diario.with_user(usuario).kanban_dashboard)
                    self.assertTrue(diario.with_user(usuario).kanban_dashboard_graph)

    def test_ven_tambien_lo_de_cliente(self):
        cliente = (self.factura_cliente, self.cobro_cliente, self.cobro_cliente.move_id, self.factura_cliente.line_ids)
        for usuario in self.con_contabilidad + (self.lector,):
            for registros in cliente:
                self.assertEqual(registros.with_user(usuario).exists(), registros)
                self.assertEqual(
                    registros.browse().with_user(usuario).search([('id', 'in', registros.ids)]), registros,
                    usuario.login)

    def test_el_lector_solo_lee_pero_lo_lee_todo(self):
        for etiqueta, registros in self.cosas_de_jefe:
            with self.subTest(que=etiqueta):
                propios = registros.with_user(self.lector)
                self.assertEqual(registros.browse().with_user(self.lector).search([('id', 'in', registros.ids)]),
                                 registros, 'el lector contable lo ve todo')
                self.assertTrue(propios.read(['display_name']))
                for operacion in ('write', 'unlink'):
                    with self.assertRaises(AccessError, msg=f'{etiqueta}: el lector no debe poder {operacion}'):
                        propios.check_access(operacion)

    def test_contabilidad_registra_pagos_asientos_y_extractos(self):
        """Lo que hacen Nómina y Contabilidad (pagos salientes, asientos, extractos) sigue funcionando."""
        for usuario in (self.gerencia, self.contador, self.gerente_contable, self.admin):
            with self.subTest(usuario=usuario.login):
                Cuenta = self.env['account.account']
                gasto = Cuenta.search([('account_type', '=', 'expense')], limit=1)
                caja = Cuenta.search([('account_type', '=', 'asset_cash')], limit=1)
                asiento = self.env['account.move'].with_user(usuario).create({
                    'move_type': 'entry', 'journal_id': self.varios.id, 'date': fields.Date.today(),
                    'line_ids': [Command.create({'account_id': gasto.id, 'debit': 5.0}),
                                 Command.create({'account_id': caja.id, 'credit': 5.0})],
                })
                asiento.action_post()
                self.assertEqual(asiento.state, 'posted')
                factura = self.env['account.move'].with_user(usuario).create({
                    'move_type': 'in_invoice', 'partner_id': self.proveedor.id, 'invoice_date': fields.Date.today(),
                    'invoice_line_ids': [Command.create({'name': 'Compra', 'quantity': 1, 'price_unit': 20.0})],
                })
                factura.action_post()
                pago = self.env['account.payment.register'].with_user(usuario).with_context(
                    active_model='account.move', active_ids=factura.ids).create(
                    {'payment_date': fields.Date.today(), 'journal_id': self.efectivo.id})._create_payments()
                self.assertEqual(pago.payment_type, 'outbound')
                self.assertIn(factura.payment_state, ('paid', 'in_payment'))
                creados = [asiento, factura, pago]
                Linea = self.env['account.bank.statement.line'].with_user(usuario)
                if Linea.has_access('create'):  # el permiso del modelo lo da «Basic» (contador), no el gerente solo
                    linea = Linea.create({'journal_id': self.banco.id, 'amount': 7.0, 'payment_ref': 'Depósito'})
                    self.assertTrue(linea.move_id)
                    creados += [linea, linea.move_id]
                # Y la vendedora no ve nada de lo que acaban de crear.
                for registros in creados:
                    self._cerrado(registros, self.vendedora)

    def test_los_reportes_contables_siguen_completos(self):
        for usuario in (self.gerencia, self.contador, self.gerente_contable, self.admin, self.lector):
            Informe = self.env['account.invoice.report'].with_user(usuario)
            self.assertTrue(Informe.search([('move_id', '=', self.factura_proveedor.id)]),
                            f'{usuario.login}: el análisis de facturas incluye compras')
            self.assertTrue(Informe.search([('move_id', '=', self.factura_cliente.id)]))

    def test_gerencia_ve_los_apuntes_de_nomina(self):
        """Los asientos de nómina son asientos varios: Gerencia (grupo Nómina incluido) los ve."""
        apuntes = self.asiento_vario.line_ids
        self.assertEqual(self.env['account.move.line'].with_user(self.gerencia).search(
            [('id', 'in', apuntes.ids)]), apuntes)


@tagged('post_install', '-at_install')
class TestReglasContables(PermisosContablesCommon):
    """Las reglas están como las dejamos, sobreviven a una actualización del módulo y respetan lo demás."""

    def _dominios(self):
        return {xmlid: self.env.ref(xmlid).domain_force for xmlid in REGLAS_ESTANDAR}

    def test_las_reglas_estandar_ya_no_abren_todo(self):
        for xmlid, dominio in self._dominios().items():
            self.assertNotEqual(dominio.replace(' ', ''), "[(1,'=',1)]", xmlid)

    def test_las_reglas_sobreviven_a_actualizar_dcasa_base(self):
        """Una base ya existente trae las reglas de fábrica (``noupdate``): al actualizar el módulo se estrechan."""
        esperado = self._dominios()
        for xmlid in REGLAS_ESTANDAR:
            self.env.ref(xmlid).write({'domain_force': "[(1, '=', 1)]"})
        for _ in range(2):  # y repetir la actualización no cambia nada
            convert_file(self.env, 'dcasa_base', ARCHIVO_REGLAS, {}, mode='update', noupdate=False)
            self.env.registry.clear_cache()
            self.assertEqual(self._dominios(), esperado)
        # Con las reglas de vuelta, la vendedora sigue sin ver lo de proveedores.
        self._cerrado(self.factura_proveedor, self.vendedora)
        self._cerrado(self.pago_proveedor, self.vendedora)

    def test_las_reglas_propias_estan_en_la_base(self):
        for nombre in ('regla_asientos_contabilidad', 'regla_apuntes_contabilidad', 'regla_pagos_contabilidad',
                       'regla_extractos_contabilidad', 'regla_lineas_extracto_contabilidad',
                       'regla_pagos_facturacion', 'regla_extractos_facturacion', 'regla_lineas_extracto_facturacion',
                       'regla_conciliaciones_facturacion', 'regla_analitica_empleados',
                       'regla_asientos_toda_la_tienda', 'regla_apuntes_toda_la_tienda', 'regla_pagos_toda_la_tienda',
                       'regla_conciliaciones_toda_la_tienda', 'regla_analitica_toda_la_tienda'):
            regla = self.env.ref(f'dcasa_base.{nombre}')
            self.assertTrue(regla.active, nombre)
            self.assertTrue(regla.groups, f'{nombre} es de grupo, no global')

    def test_contabilidad_tiene_su_regla_de_todo(self):
        user = self.env.ref('account.group_account_user')
        manager = self.env.ref('account.group_account_manager')
        for nombre in ('regla_asientos_contabilidad', 'regla_apuntes_contabilidad', 'regla_pagos_contabilidad',
                       'regla_extractos_contabilidad', 'regla_lineas_extracto_contabilidad',
                       'regla_conciliaciones_contabilidad', 'regla_analitica_contabilidad'):
            regla = self.env.ref(f'dcasa_base.{nombre}')
            self.assertEqual(regla.groups, user | manager, nombre)
            self.assertEqual(regla.domain_force.replace(' ', ''), "[(1,'=',1)]", nombre)
            self.assertTrue(regla.perm_read and regla.perm_write and regla.perm_create and regla.perm_unlink, nombre)

    def test_siguen_las_reglas_de_varias_empresas_y_las_de_otros_grupos(self):
        for xmlid in ('account.account_move_comp_rule', 'account.account_move_line_comp_rule',
                      'account.account_payment_comp_rule', 'account.account_bank_statement_comp_rule',
                      'account.account_bank_statement_line_comp_rule', 'analytic.analytic_line_comp_rule'):
            regla = self.env.ref(xmlid)
            self.assertIn('company_id', regla.domain_force, xmlid)
            self.assertFalse(regla.groups, f'{xmlid} debe seguir siendo global')
        # Compras sigue viendo las facturas de proveedor con su propia regla.
        compras = self.env.ref('purchase.purchase_user_account_move_rule')
        self.assertIn('in_invoice', compras.domain_force)
        # Y la de «facturas de venta» de Ventas no cambió.
        self.assertEqual(self.env.ref('sale.account_invoice_rule_see_all').domain_force,
                         "[('move_type', 'in', ('out_invoice', 'out_refund'))]")
        # La regla de solo lectura de Odoo para el lector contable sigue ahí.
        lector = self.env.ref('account.account_move_rule_group_readonly')
        self.assertEqual(lector.domain_force.replace(' ', ''), "[(1,'=',1)]")
        self.assertFalse(lector.perm_write)

    def test_compras_sigue_viendo_facturas_de_proveedor(self):
        """Quien tiene Compras y Facturación junto suma sus reglas: la de Compras sigue abriendo lo de proveedores."""
        compras = crear_usuario(self.env, 'perm_cont_compras', 'purchase.group_purchase_user',
                                'account.group_account_invoice')
        visibles = self.env['account.move'].with_user(compras).search([('id', '=', self.factura_proveedor.id)])
        self.assertEqual(visibles, self.factura_proveedor)
        # ...pero sus asientos varios y pagos salientes tampoco.
        self._cerrado(self.asiento_vario, compras)
        self._cerrado(self.pago_proveedor, compras)
