"""Reglas contables de la gerencia (17 oct 2026, docs/DECISIONES_CONTABLES.md), una prueba por regla y por camino.

* A5 · El cobro solo en Caja: la Vendedora ya no registra cobros por el asistente «Pagar», el botón, un cobro suelto,
  aplicando un cobro que ya estaba ni por RPC (crear, publicar, conciliar), con el interruptor «Cada vendedora ve solo
  sus documentos» encendido o apagado. Sigue facturando. Caja, Gerencia y contabilidad cobran.
* A6 · Pasar a borrador o anular una factura de cliente publicada: solo Gerencia (y administradores).
* A7 · Notas de crédito, devolverle dinero a un cliente y dejarle saldo a favor: solo Gerencia (y administradores).
* C1 · Tafi y Crediviva como formas de pago de clientes, una vez por base y sin pisar lo que exista.

El primer abono mínimo y el plazo de 30 días están en dcasa_invoice (test_primer_abono.py, test_estado_abono.py).
"""
from contextlib import contextmanager

from odoo import Command, fields
from odoo.addons.dcasa_base import (
    DIARIOS_FINANCIAMIENTO,
    PARAMETRO_FINANCIAMIENTO,
    crear_diarios_financiamiento,
)
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from .test_roles import crear_usuario


@contextmanager
def negado(prueba, excepcion, texto):
    """``assertRaisesRegex`` con el savepoint de Odoo (``assertRaises``): lo que se escribió antes del error se deshace,
    como en una llamada real."""
    with prueba.assertRaises(excepcion) as contexto:
        yield contexto
    prueba.assertRegex(str(contexto.exception), texto)


COBRO = 'Los cobros los registra Caja'
GERENCIA = 'solo Gerencia'


class ReglasGerenciaComun(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.ref('base.main_company')
        cls.vendedora = crear_usuario(env, 'rg_vendedora', 'dcasa_base.group_vendedora')
        cls.caja = crear_usuario(env, 'rg_caja', 'dcasa_base.group_caja')
        cls.gerencia = crear_usuario(env, 'rg_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(env, 'rg_contador', 'account.group_account_user')
        cls.admin = env.ref('base.user_admin')
        cls.cliente = env['res.partner'].create({
            'name': 'Cliente Reglas Gerencia', 'phone': '+507 6555-0201', 'email': 'cliente.reglas@example.com'})
        cls.producto = env['product.product'].create({
            'name': 'Sofá Reglas Gerencia', 'type': 'consu', 'list_price': 100.0, 'taxes_id': [Command.clear()]})
        Diario = env['account.journal']
        cls.efectivo = Diario.search([('type', '=', 'cash'), ('company_id', '=', cls.company.id)], limit=1)
        cls.banco = Diario.search([('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1)

    # --- ayudas ---------------------------------------------------------------------------------------------
    def _factura(self, usuario=None, monto=200.0, vendedora=None):
        """Una factura de cliente publicada de ``monto`` (sin ITBMS), creada y publicada por ``usuario``."""
        Move = self.env['account.move'].with_user(usuario) if usuario else self.env['account.move']
        factura = Move.create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_user_id': (vendedora or usuario or self.vendedora).id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': monto,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def _asistente(self, usuario, facturas, **valores):
        return self.env['account.payment.register'].with_user(usuario).with_context(
            active_model='account.move', active_ids=facturas.ids).create(
            {'payment_date': fields.Date.today(), 'journal_id': self.efectivo.id, **valores})

    def _cobrar(self, usuario, factura, **valores):
        return self._asistente(usuario, factura, **valores)._create_payments()

    def _nota(self, usuario, factura):
        reversa = self.env['account.move.reversal'].with_user(usuario).with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'reason': 'Devolución de prueba', 'journal_id': factura.journal_id.id})
        nota = self.env['account.move'].with_user(usuario).browse(reversa.refund_moves()['res_id'])
        nota.action_post()
        return nota

    def _cobro_suelto(self, usuario, monto=50.0):
        return self.env['account.payment'].with_user(usuario).create({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
            'amount': monto, 'journal_id': self.efectivo.id})

    def _apagar_interruptor(self):
        self.env['res.users']._dcasa_poner_restriccion(False)
        self.assertFalse(self.env['res.users']._dcasa_restriccion_activa())


@tagged('post_install', '-at_install')
class TestElCobroSoloEnCaja(ReglasGerenciaComun):
    """A5: la Vendedora factura, pero no cobra por ningún camino; Caja, Gerencia y contabilidad sí."""

    def test_quien_cobra(self):
        self.assertFalse(self.vendedora._dcasa_puede_cobrar())
        for usuario in (self.caja, self.gerencia, self.contador, self.admin):
            self.assertTrue(usuario._dcasa_puede_cobrar(), usuario.login)

    def test_la_vendedora_sigue_facturando(self):
        factura = self._factura(self.vendedora)
        self.assertEqual((factura.state, factura.invoice_user_id), ('posted', self.vendedora))

    def test_vendedora_no_cobra_por_el_asistente(self):
        factura = self._factura(self.vendedora)
        with negado(self, AccessError, COBRO):
            self._cobrar(self.vendedora, factura)
        with negado(self, AccessError, COBRO):
            self._asistente(self.vendedora, factura).action_create_payments()
        self.assertEqual(factura.payment_state, 'not_paid')

    def test_vendedora_no_abre_pagar(self):
        """El botón «Pagar» (y el de la lista) avisan antes de abrir el asistente."""
        factura = self._factura(self.vendedora)
        with negado(self, AccessError, COBRO):
            factura.with_user(self.vendedora).action_register_payment()
        with negado(self, AccessError, COBRO):
            factura.with_user(self.vendedora).action_force_register_payment()
        with negado(self, AccessError, COBRO):
            factura.with_user(self.vendedora).line_ids.action_register_payment()

    def test_vendedora_no_cobra_por_rpc(self):
        """Crear un cobro suelto, publicar uno que dejó Caja en borrador o cruzarlo a mano con su factura."""
        with negado(self, AccessError, COBRO):
            self._cobro_suelto(self.vendedora)
        borrador = self._cobro_suelto(self.caja)
        self.assertEqual(borrador.state, 'draft')
        with negado(self, AccessError, COBRO):
            borrador.with_user(self.vendedora).action_post()
        borrador.with_user(self.caja).action_post()
        # Un cobro que ya estaba (saldo del cliente), cruzado por ella con su factura: tampoco.
        factura = self._factura(self.vendedora, monto=50.0)
        cobro = borrador.move_id.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        por_cobrar = factura.line_ids.filtered(lambda ln: ln.account_id.account_type == 'asset_receivable')
        with negado(self, AccessError, COBRO):
            factura.with_user(self.vendedora).js_assign_outstanding_line(cobro.id)
        with negado(self, AccessError, COBRO):
            (cobro | por_cobrar).with_user(self.vendedora).reconcile()
        with self.assertRaises(AccessError):
            self.env['account.partial.reconcile'].with_user(self.vendedora).create({
                'debit_move_id': por_cobrar.id, 'credit_move_id': cobro.id,
                'amount': 50.0, 'debit_amount_currency': 50.0, 'credit_amount_currency': 50.0})
        self.assertEqual(factura.payment_state, 'not_paid')
        # Caja sí lo aplica.
        factura.with_user(self.caja).js_assign_outstanding_line(cobro.id)
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        # Y deshacerlo tampoco es de la vendedora.
        parcial = por_cobrar.matched_credit_ids
        with negado(self, AccessError, COBRO):
            factura.with_user(self.vendedora).js_remove_outstanding_partial(parcial.id)
        with self.assertRaises(AccessError):
            parcial.with_user(self.vendedora).unlink()

    def test_vendedora_no_toca_un_cobro_hecho(self):
        factura = self._factura(self.vendedora)
        pago = self._cobrar(self.caja, factura)
        for accion in ('action_draft', 'action_cancel'):
            with self.subTest(accion), negado(self, AccessError, COBRO):
                getattr(pago.with_user(self.vendedora), accion)()
        with negado(self, AccessError, COBRO):
            pago.with_user(self.vendedora).write({'amount': 1.0})
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    def test_con_el_interruptor_apagado_tampoco_cobra(self):
        """«Ver solo lo suyo» apagado le devuelve ver todo, no cobrar: Caja es su propio rol."""
        self._apagar_interruptor()
        self.assertFalse(self.vendedora._dcasa_solo_lo_suyo())
        self.assertFalse(self.vendedora._dcasa_puede_cobrar())
        factura = self._factura(self.vendedora)
        with negado(self, AccessError, COBRO):
            self._cobrar(self.vendedora, factura)
        with negado(self, AccessError, COBRO):
            self._cobro_suelto(self.vendedora)

    def test_caja_gerencia_y_contabilidad_cobran(self):
        for usuario in (self.caja, self.gerencia, self.contador, self.admin):
            with self.subTest(usuario.login):
                factura = self._factura(monto=100.0)
                pago = self._cobrar(usuario, factura, journal_id=self.banco.id)
                self.assertEqual((pago.payment_type, pago.partner_type), ('inbound', 'customer'))
                self.assertIn(factura.payment_state, ('paid', 'in_payment'))
                self.assertTrue(self._cobro_suelto(usuario, 5.0))

    def test_la_factura_dice_donde_se_cobra(self):
        """La pantalla: a la vendedora no le sale «Pagar» y la factura dice que el cobro es en Caja."""
        factura = self._factura(self.vendedora)
        self.assertFalse(factura.with_user(self.vendedora).dcasa_puede_cobrar)
        self.assertTrue(factura.with_user(self.caja).dcasa_puede_cobrar)
        vista = self.env['account.move'].with_user(self.vendedora).get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('o_dcasa_cobro_en_caja', vista)
        self.assertIn('lo registra <b>Caja</b>', vista)
        self.assertIn('not dcasa_puede_cobrar', vista)

    def test_proveedores_siguen_igual_para_contabilidad(self):
        factura = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'name': 'Compra', 'quantity': 1, 'price_unit': 30.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        pago = self._cobrar(self.contador, factura)
        self.assertEqual(pago.payment_type, 'outbound')
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))


@tagged('post_install', '-at_install')
class TestDeshacerYDevolverEsDeGerencia(ReglasGerenciaComun):
    """A6 y A7: pasar a borrador o anular, notas de crédito, devoluciones y saldo a favor."""

    def test_pasar_a_borrador_o_anular_negado_a_caja_y_vendedora(self):
        for usuario in (self.vendedora, self.caja, self.contador):
            factura = self._factura(self.vendedora)
            for intento in (lambda f: f.button_draft(), lambda f: f.button_cancel(),
                            lambda f: f.write({'state': 'draft'}), lambda f: f.write({'state': 'cancel'})):
                with self.subTest(usuario=usuario.login), negado(self, AccessError, GERENCIA):
                    intento(factura.with_user(usuario))
            self.assertEqual(factura.state, 'posted')

    def test_el_mensaje_dice_a_quien_pedirselo(self):
        factura = self._factura(self.vendedora)
        with self.assertRaises(AccessError) as error:
            factura.with_user(self.caja).button_draft()
        mensaje = str(error.exception)
        self.assertIn(factura.name, mensaje)
        self.assertIn('pasarla a borrador o anularla lo hace solo Gerencia', mensaje)
        self.assertIn('Pídeselo a Gerencia', mensaje)

    def test_gerencia_y_administrador_pasan_a_borrador_y_anulan(self):
        for usuario in (self.gerencia, self.admin):
            with self.subTest(usuario.login):
                factura = self._factura(self.vendedora)
                factura.with_user(usuario).button_draft()
                self.assertEqual(factura.state, 'draft')
                factura.with_user(usuario).action_post()
                factura.with_user(usuario).button_cancel()
                self.assertEqual(factura.state, 'cancel')

    def test_un_borrador_lo_cancela_quien_factura(self):
        """La regla es para lo publicado: un borrador que nunca se publicó lo cancela quien lo hizo."""
        borrador = self.env['account.move'].with_user(self.vendedora).create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1})]})
        borrador.button_cancel()
        self.assertEqual(borrador.state, 'cancel')

    def test_nota_de_credito_negada_a_caja_y_vendedora(self):
        factura = self._factura(self.vendedora)
        for usuario in (self.vendedora, self.caja):
            with self.subTest(usuario.login):
                with negado(self, AccessError, 'notas de crédito'):
                    factura.with_user(usuario).action_reverse()
                with negado(self, AccessError, 'notas de crédito'):
                    self._nota(usuario, factura)
                with negado(self, AccessError, 'notas de crédito'):
                    self.env['account.move'].with_user(usuario).create({
                        'move_type': 'out_refund', 'partner_id': self.cliente.id,
                        'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1})]})
        # Una nota que quedó en borrador por otro camino (con sudo) tampoco la publican.
        borrador = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_user_id': self.vendedora.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1})]})
        for usuario in (self.vendedora, self.caja):
            with self.subTest(usuario.login), negado(self, AccessError, 'notas de crédito'):
                borrador.with_user(usuario).action_post()
        self.assertEqual(borrador.state, 'draft')
        self.assertFalse(factura.reversal_move_ids)

    def test_gerencia_hace_la_nota_de_credito(self):
        factura = self._factura(self.vendedora)
        nota = self._nota(self.gerencia, factura)
        self.assertEqual((nota.move_type, nota.state, nota.invoice_user_id),
                         ('out_refund', 'posted', self.vendedora), 'sigue siendo de la vendedora')

    def test_devolver_dinero_es_de_gerencia(self):
        factura = self._factura(self.vendedora)
        self._cobrar(self.caja, factura)
        nota = self._nota(self.gerencia, factura)
        for usuario in (self.caja, self.vendedora):
            with self.subTest(usuario.login):
                with negado(self, AccessError, 'Devolverle dinero'):
                    self._cobrar(usuario, nota)
                with negado(self, AccessError, 'Devolverle dinero'):
                    self.env['account.payment'].with_user(usuario).create({
                        'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                        'amount': 10.0, 'journal_id': self.efectivo.id})
        devolucion = self._cobrar(self.gerencia, nota)
        self.assertEqual((devolucion.payment_type, devolucion.partner_type), ('outbound', 'customer'))
        self.assertIn(nota.payment_state, ('paid', 'in_payment'))

    def test_saldo_a_favor_o_dar_por_pagada_con_diferencia_es_de_gerencia(self):
        factura = self._factura(monto=100.0)
        de_mas = self._asistente(self.caja, factura, amount=150.0, payment_difference_handling='open')
        with negado(self, AccessError, 'saldo a favor'):
            de_mas._create_payments()
        castigo = self._asistente(self.caja, factura, amount=95.0, payment_difference_handling='reconcile',
                                  writeoff_account_id=self.env['account.account'].search(
                                      [('account_type', '=', 'expense')], limit=1).id,
                                  writeoff_label='Diferencia')
        with negado(self, AccessError, 'con una diferencia'):
            castigo._create_payments()
        self.assertEqual(factura.payment_state, 'not_paid')
        self._asistente(self.gerencia, factura, amount=150.0, payment_difference_handling='open')._create_payments()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))
        self.assertLess(self.cliente.credit, 0, 'el cliente quedó con saldo a favor')

    def test_quien_es_gerencia(self):
        for usuario in (self.vendedora, self.caja, self.contador):
            self.assertFalse(usuario._dcasa_es_gerencia(), usuario.login)
        for usuario in (self.gerencia, self.admin):
            self.assertTrue(usuario._dcasa_es_gerencia(), usuario.login)


@tagged('post_install', '-at_install')
class TestTafiYCrediviva(ReglasGerenciaComun):
    """C1: las financieras como formas de pago de clientes."""

    def _diario(self, codigo):
        return self.env['account.journal'].with_context(active_test=False).search(
            [('company_id', '=', self.company.id), ('code', '=', codigo)])

    def test_estan_activas_y_salen_en_pagar(self):
        factura = self._factura(monto=100.0)
        asistente = self._asistente(self.caja, factura)
        for codigo, nombre, _palabra in DIARIOS_FINANCIAMIENTO:
            with self.subTest(nombre):
                diario = self._diario(codigo)
                self.assertEqual((diario.name, diario.type, diario.active), (nombre, 'bank', True))
                self.assertTrue(diario.inbound_payment_method_line_ids, 'se puede cobrar con ella')
                self.assertIn(diario, asistente.available_journal_ids)
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_param(PARAMETRO_FINANCIAMIENTO))
        nombres = {d.name for d in asistente.available_journal_ids}
        self.assertTrue({'Tafi (financiamiento)', 'Crediviva (financiamiento)'} <= nombres)

    def test_caja_cobra_con_tafi(self):
        factura = self._factura(monto=100.0)
        pago = self._cobrar(self.caja, factura, journal_id=self._diario('TAFI').id)
        self.assertEqual(pago.journal_id.name, 'Tafi (financiamiento)')
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    def test_una_sola_vez_por_base_y_sin_pisar(self):
        icp = self.env['ir.config_parameter'].sudo()
        # Ya se crearon: no se repiten.
        self.assertFalse(crear_diarios_financiamiento(self.env))
        # Una base de antes (sin la marca), donde alguien ya había hecho «Tafi» a mano y nadie Crediviva.
        tafi, crediviva = self._diario('TAFI'), self._diario('CRVIV')
        crediviva.unlink()
        tafi.write({'name': 'TAFI Panamá', 'code': 'TF'})
        icp.set_param(PARAMETRO_FINANCIAMIENTO, False)
        creados = crear_diarios_financiamiento(self.env)
        self.assertEqual(creados.mapped('code'), ['CRVIV'], 'solo la que faltaba')
        self.assertEqual((tafi.name, tafi.code), ('TAFI Panamá', 'TF'), 'la de a mano no se toca')
        # Si después alguien la archiva, no vuelve.
        creados.active = False
        self.assertFalse(crear_diarios_financiamiento(self.env))
        self.assertFalse(self._diario('CRVIV').active)

    def test_la_migracion_las_crea(self):
        import importlib.util

        from odoo.tools.misc import file_path
        spec = importlib.util.spec_from_file_location(
            'mig_financiamiento', file_path('dcasa_base/migrations/19.0.1.9.0/post-migrate.py'))
        migracion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migracion)
        self._diario('TAFI').unlink()
        self._diario('CRVIV').unlink()
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_FINANCIAMIENTO, False)
        migracion.migrate(self.env.cr, '19.0.1.8.0')
        self.assertTrue(self._diario('TAFI') and self._diario('CRVIV'))
        migracion.migrate(self.env.cr, '19.0.1.8.0')
        self.assertEqual(len(self._diario('TAFI')), 1, 'repetirla no duplica')
