"""Reglas contables de la gerencia (17 oct 2026, docs/DECISIONES_CONTABLES.md), una prueba por regla y por camino.

* A5 · El cobro solo en Caja: la Vendedora ya no registra cobros por el asistente «Pagar», el botón, un cobro suelto,
  aplicando un cobro que ya estaba ni por RPC (crear, publicar, conciliar), con el interruptor «Cada vendedora ve solo
  sus documentos» encendido o apagado. Sigue facturando. Caja, Gerencia y contabilidad cobran.
* A6 · Pasar a borrador o anular una factura de cliente publicada: solo Gerencia (y administradores).
* A7 · Notas de crédito, devolverle dinero a un cliente y dejarle saldo a favor: solo Gerencia (y administradores).
* C1 · Tafi y Crediviva como formas de pago de clientes, una vez por base y sin pisar lo que exista.
* La pantalla: a quien no puede usar un botón no se le ofrece (la factura, la lista, el menú «Acción», el pago, el
  asistente «Pagar» y el globito del pago); el servidor lo sigue negando por RPC.

El primer abono mínimo y el plazo de 30 días están en dcasa_invoice (test_primer_abono.py, test_estado_abono.py).
"""
from contextlib import contextmanager

from lxml import etree

from odoo import Command, fields
from odoo.addons.dcasa_base import (
    DIARIOS_FINANCIAMIENTO,
    PARAMETRO_FINANCIAMIENTO,
    crear_diarios_financiamiento,
)
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval
from odoo.tools.view_validation import get_expression_field_names

from .test_roles import crear_usuario


@contextmanager
def negado(prueba, excepcion, texto):
    """``assertRaisesRegex`` con el savepoint de Odoo (``assertRaises``): lo que se escribió antes del error se deshace,
    como en una llamada real."""
    with prueba.assertRaises(excepcion) as contexto:
        yield contexto
    prueba.assertRegex(str(contexto.exception), texto)


COBRO = 'Los cobros los registra Caja'
COTIZAR = 'Las ventas se hacen como cotización: Ventas › Nueva cotización'
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
        # La factura de una vendedora sale de su pedido, y Odoo la crea con sudo (TestFacturasSueltas): aquí, igual.
        factura = Move.sudo().create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_user_id': (vendedora or usuario or self.vendedora).id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': monto,
                                                 'tax_ids': [Command.clear()]})]}).sudo(False)
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
        borrador = self.env['account.move'].with_user(self.vendedora).sudo().create({   # como sale del pedido
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1})]}).sudo(False)
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


@tagged('post_install', '-at_install')
class TestBotonesSoloAQuienPuede(ReglasGerenciaComun):
    """La pantalla no ofrece lo que solo daría error: a quien no es Gerencia (Caja incluida) no le salen «Nota de
    crédito» ni «Restablecer a borrador» en una factura de cliente publicada, y a la Vendedora tampoco «Pagar». Se mira
    como el navegador: el botón tiene que llegarle (``groups``) y ni él ni lo que lo contiene pueden estar invisibles
    con los valores de esa factura vista por ese usuario. El servidor lo sigue negando por RPC."""

    NOTA = "//header/button[@name='action_reverse']"
    BORRADOR = "//header/button[@name='button_draft']"
    PAGAR = "//header/button[@name='action_register_payment']"
    REVERTIR = "//header/button[@data-hotkey='z']"

    # --- ayudas ---------------------------------------------------------------------------------------------
    def _arch(self, usuario, modelo, tipo='form', vista=None, contexto=None):
        Modelo = self.env[modelo].with_user(usuario).with_context(**(contexto or {}))
        return etree.fromstring(Modelo.get_views([(vista, tipo)])['views'][tipo]['arch'])

    def _vale(self, registro, expresion, contexto):
        valores = {'context': dict(contexto), 'id': registro.id, 'uid': registro.env.uid}
        for nombre in get_expression_field_names(expresion):
            if nombre in registro._fields and nombre not in valores:
                campo, valor = registro._fields[nombre], registro[nombre]
                if campo.type == 'many2one':
                    valor = valor.id
                elif campo.type in ('one2many', 'many2many'):
                    valor = valor.ids
                valores[nombre] = valor
        return bool(safe_eval(expresion, valores))

    def _se_ve(self, usuario, registro, xpath, tipo='form', vista=None, contexto=None):
        """¿Le sale a ``usuario`` algún nodo ``xpath`` de la vista de ``registro``? (Vacío: la lista, solo contexto.)"""
        contexto = contexto or {}
        registro = registro.with_user(usuario).with_context(**contexto)
        for nodo in self._arch(usuario, registro._name, tipo, vista, contexto).xpath(xpath):
            condiciones = [n.get('invisible') for n in (nodo, *nodo.iterancestors()) if n.get('invisible')]
            if not any(self._vale(registro, condicion, contexto) for condicion in condiciones):
                return True
        return False

    def _cobros_con_asiento(self):
        """Como en la base de D'CASA: el efectivo lleva su cuenta de cobros por depositar, así un cobro deja asiento
        (un cobro suelto queda como crédito pendiente) y el asistente muestra la diferencia."""
        cuenta = self.env['account.account'].create({
            'name': 'Cobros por depositar (prueba)', 'code': 'PRB1010', 'account_type': 'asset_current',
            'reconcile': True})
        self.efectivo.inbound_payment_method_line_ids.payment_account_id = cuenta

    def _por_rpc(self, usuario, modelo, metodo, ids, *args):
        return call_kw(self.env[modelo].with_user(usuario), metodo, [ids, *args], {})

    # --- la factura publicada -------------------------------------------------------------------------------
    def test_factura_publicada_solo_gerencia_ve_nota_y_borrador(self):
        factura = self._factura(self.vendedora)
        for usuario in (self.vendedora, self.caja, self.contador):
            with self.subTest(usuario.login):
                self.assertFalse(self._se_ve(usuario, factura, self.NOTA), 'sin «Nota de crédito»')
                self.assertFalse(self._se_ve(usuario, factura, self.BORRADOR), 'sin «Restablecer a borrador»')
        for usuario in (self.gerencia, self.admin):
            with self.subTest(usuario.login):
                self.assertTrue(self._se_ve(usuario, factura, self.NOTA))
                self.assertTrue(self._se_ve(usuario, factura, self.BORRADOR))
                self.assertTrue(self._se_ve(usuario, factura, self.PAGAR))

    def test_pagar_sigue_escondido_para_la_vendedora(self):
        factura = self._factura(self.vendedora)
        self.assertFalse(self._se_ve(self.vendedora, factura, self.PAGAR))
        self.assertTrue(self._se_ve(self.vendedora, factura, "//div[contains(@class, 'o_dcasa_cobro_en_caja')]"),
                        'la factura le dice que el cobro es en Caja')
        for usuario in (self.caja, self.contador):
            with self.subTest(usuario.login):
                self.assertTrue(self._se_ve(usuario, factura, self.PAGAR), 'Caja cobra')
                self.assertFalse(self._se_ve(usuario, factura, "//div[contains(@class, 'o_dcasa_cobro_en_caja')]"))
        # Con un cobro que ya estaba («Créditos pendientes: Agregar») tampoco se lo ofrece. Con el interruptor
        # apagado, para que la vendedora vea ese cobro (encendido, ni siquiera lo ve).
        self._apagar_interruptor()
        self._cobros_con_asiento()
        self._cobro_suelto(self.caja).action_post()
        factura.invalidate_recordset()
        self.assertTrue(factura.with_user(self.vendedora).invoice_has_outstanding)
        pendientes = "//field[@name='invoice_outstanding_credits_debits_widget']"
        self.assertFalse(self._se_ve(self.vendedora, factura, pendientes))
        self.assertFalse(self._se_ve(self.vendedora, factura, self.PAGAR))
        self.assertTrue(self._se_ve(self.caja, factura, pendientes))
        self.assertTrue(self._se_ve(self.caja, factura, self.PAGAR))

    def test_nota_de_credito_publicada(self):
        """En una nota, «Pagar» es devolver dinero y «Restablecer a borrador» deshacerla: solo Gerencia."""
        factura = self._factura(self.vendedora)
        self._cobrar(self.caja, factura)
        nota = self._nota(self.gerencia, factura)
        for usuario in (self.vendedora, self.caja):
            with self.subTest(usuario.login):
                self.assertFalse(self._se_ve(usuario, nota, self.PAGAR))
                self.assertFalse(self._se_ve(usuario, nota, self.BORRADOR))
        self.assertTrue(self._se_ve(self.gerencia, nota, self.PAGAR))
        self.assertTrue(self._se_ve(self.gerencia, nota, self.BORRADOR))

    def test_lo_que_no_es_de_gerencia_sigue_a_la_vista(self):
        """Se esconde exactamente lo que el servidor niega: una factura cancelada vuelve a borrador con Caja, y en un
        borrador «Cancelar» le sigue saliendo a quien factura."""
        cancelada = self._factura(self.vendedora)
        cancelada.with_user(self.gerencia).button_cancel()
        self.assertTrue(self._se_ve(self.caja, cancelada, self.BORRADOR))
        cancelada.with_user(self.caja).button_draft()
        self.assertEqual(cancelada.state, 'draft')
        self.assertTrue(self._se_ve(self.vendedora, cancelada, "//header/button[@name='button_cancel']"))

    def test_revertir_un_asiento_no_le_llega(self):
        for usuario in (self.vendedora, self.caja):
            with self.subTest(usuario.login):
                self.assertFalse(self._arch(usuario, 'account.move').xpath(self.REVERTIR))
        for usuario in (self.gerencia, self.contador, self.admin):
            with self.subTest(usuario.login):
                self.assertTrue(self._arch(usuario, 'account.move').xpath(self.REVERTIR))

    # --- la lista y el menú «Acción» -------------------------------------------------------------------------
    def test_lista_pagar_solo_a_quien_puede(self):
        Move = self.env['account.move']
        facturas = self.env.ref('account.view_out_invoice_tree').id
        notas = self.env.ref('account.view_out_credit_note_tree').id
        pagar = "//header/button[@name='action_force_register_payment']"
        en_facturas = {'default_move_type': 'out_invoice'}
        en_notas = {'default_move_type': 'out_refund'}
        self.assertFalse(self._se_ve(self.vendedora, Move, pagar, 'list', facturas, en_facturas))
        self.assertFalse(self._se_ve(self.vendedora, Move, pagar, 'list', notas, en_notas))
        self.assertTrue(self._se_ve(self.caja, Move, pagar, 'list', facturas, en_facturas))
        self.assertFalse(self._se_ve(self.caja, Move, pagar, 'list', notas, en_notas), 'devolver dinero')
        self.assertTrue(self._se_ve(self.gerencia, Move, pagar, 'list', facturas, en_facturas))
        self.assertTrue(self._se_ve(self.gerencia, Move, pagar, 'list', notas, en_notas))

    def test_menu_accion_sin_lo_de_gerencia(self):
        de_gerencia = {self.env.ref(x).id for x in (
            'account.action_move_force_register_payment', 'account.action_view_account_move_reversal',
            'account.action_move_switch_move_type')}
        for usuario, las_ve in ((self.vendedora, False), (self.caja, False), (self.gerencia, True),
                                (self.contador, True), (self.admin, True)):
            with self.subTest(usuario.login):
                enlaces = self.env['ir.actions.actions'].with_user(usuario).get_bindings('account.move')
                ids = {accion['id'] for accion in enlaces.get('action', ())}
                if las_ve:
                    self.assertLessEqual(de_gerencia, ids)
                else:
                    self.assertFalse(de_gerencia & ids)

    # --- el pago y el asistente «Pagar» ------------------------------------------------------------------------
    def test_pagos_sin_nuevo_ni_botones_para_quien_no_cobra(self):
        self._apagar_interruptor()  # para que la vendedora pueda abrir el cobro y ver qué le sale
        for tipo in ('list', 'form', 'kanban'):
            with self.subTest(tipo):
                self.assertEqual(self._arch(self.vendedora, 'account.payment', tipo).get('create'), '0')
        for tipo in ('list', 'form'):  # el kanban (celular) ya viene sin «Nuevo» para todos
            with self.subTest(tipo):
                self.assertNotEqual(self._arch(self.caja, 'account.payment', tipo).get('create'), '0')
        publicar, cancelar = "//header/button[@name='action_post']", "//header/button[@name='action_cancel']"
        self.assertFalse(self._arch(self.vendedora, 'account.payment', 'list').xpath(publicar))
        self.assertTrue(self._arch(self.caja, 'account.payment', 'list').xpath(publicar))
        cobro = self._cobro_suelto(self.caja)
        self.assertFalse(self._se_ve(self.vendedora, cobro, publicar))
        self.assertFalse(self._se_ve(self.vendedora, cobro, cancelar))
        self.assertTrue(self._se_ve(self.caja, cobro, publicar))
        cobro.action_post()
        self.assertFalse(self._se_ve(self.vendedora, cobro, "//header/button[@name='action_draft']"))
        self.assertTrue(self._se_ve(self.caja, cobro, "//header/button[@name='action_draft']"))
        devolucion = self.env['account.payment'].with_user(self.gerencia).create({
            'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
            'amount': 10.0, 'journal_id': self.efectivo.id})
        self.assertFalse(self._se_ve(self.caja, devolucion, publicar), 'devolver dinero es de Gerencia')
        self.assertTrue(self._se_ve(self.gerencia, devolucion, publicar))

    def test_asistente_sin_saldo_a_favor_ni_diferencia_para_caja(self):
        self._cobros_con_asiento()
        factura = self._factura(monto=100.0)
        manejo = "//field[@name='payment_difference_handling']"
        aviso = "//div[contains(@class, 'o_dcasa_saldo_a_favor')]"
        de_mas = self._asistente(self.caja, factura, amount=150.0)
        self.assertEqual(de_mas.dcasa_aviso_saldo_a_favor,
                         'Estás cobrando más de lo que falta ($100.00). Dejarle saldo a favor lo autoriza solo '
                         'Gerencia: cobra hasta $100.00.')
        self.assertTrue(self._se_ve(self.caja, de_mas, aviso))
        self.assertFalse(self._se_ve(self.caja, de_mas, manejo))
        exacto = self._asistente(self.caja, factura, amount=100.0)
        self.assertFalse(exacto.dcasa_aviso_saldo_a_favor)
        self.assertFalse(self._se_ve(self.caja, exacto, aviso))
        de_gerencia = self._asistente(self.gerencia, factura, amount=150.0)
        self.assertFalse(de_gerencia.dcasa_aviso_saldo_a_favor)
        self.assertFalse(self._se_ve(self.gerencia, de_gerencia, aviso))
        self.assertTrue(self._se_ve(self.gerencia, de_gerencia, manejo), 'Gerencia elige qué hacer con la diferencia')

    def test_globito_del_pago_sin_desconciliar(self):
        factura = self._factura(self.vendedora)
        self._cobrar(self.caja, factura, amount=120.0)  # un abono (con dcasa_invoice, al menos la mitad)
        for usuario, sin in ((self.vendedora, True), (self.caja, None), (self.gerencia, None)):
            with self.subTest(usuario.login):
                contenido = factura.with_user(usuario).invoice_payments_widget['content']
                self.assertEqual(len(contenido), 1)
                self.assertEqual(contenido[0].get('dcasa_sin_desconciliar'), sin)
        rutas = [ruta for ruta, *_resto in self.env['ir.asset']._get_asset_paths('web.assets_backend', {})]
        self.assertTrue(any(ruta.endswith('dcasa_base/static/src/xml/pagos.xml') for ruta in rutas))

    # --- y el servidor lo sigue negando ------------------------------------------------------------------------
    def test_el_servidor_sigue_negando_por_rpc(self):
        factura = self._factura(self.vendedora)
        for usuario in (self.vendedora, self.caja):
            for metodo in ('button_draft', 'button_cancel', 'action_reverse'):
                with self.subTest(usuario=usuario.login, metodo=metodo), negado(self, AccessError, GERENCIA):
                    self._por_rpc(usuario, 'account.move', metodo, factura.ids)
            with self.subTest(usuario=usuario.login, metodo='write'), negado(self, AccessError, GERENCIA):
                self._por_rpc(usuario, 'account.move', 'write', factura.ids, {'state': 'draft'})
        with negado(self, AccessError, COBRO):
            self._por_rpc(self.vendedora, 'account.move', 'action_register_payment', factura.ids)
        with negado(self, AccessError, COBRO):
            call_kw(self.env['account.payment'].with_user(self.vendedora), 'create', [{
                'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id,
                'amount': 10.0, 'journal_id': self.efectivo.id}], {})
        self.assertEqual((factura.state, factura.payment_state), ('posted', 'not_paid'))
        self.assertFalse(factura.reversal_move_ids)
        self._por_rpc(self.gerencia, 'account.move', 'button_draft', factura.ids)
        self.assertEqual(factura.state, 'draft')


@tagged('post_install', '-at_install')
class TestFacturasSueltas(ReglasGerenciaComun):
    """Quien no cobra (la Vendedora) no hace facturas de cliente sueltas: cotiza y factura desde el pedido, para que
    Caja la encuentre. Caja, Gerencia y los administradores sí hacen una suelta."""

    def _valores(self):
        return {'move_type': 'out_invoice', 'partner_id': self.cliente.id,
                'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1,
                                                     'price_unit': 100.0, 'tax_ids': [Command.clear()]})]}

    def _pedido(self):
        """Un pedido confirmado de la vendedora, como lo hace ella en Ventas."""
        pedido = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.cliente.id, 'user_id': self.vendedora.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 100.0,
                                           'tax_ids': [Command.clear()]})]})
        pedido.action_confirm()
        return pedido

    def _facturar(self, pedido, **valores):
        """El asistente «Crear factura» del pedido (normal o anticipo), como la vendedora."""
        asistente = self.env['sale.advance.payment.inv'].with_user(self.vendedora).with_context(
            active_model='sale.order', active_ids=pedido.ids, active_id=pedido.id).create(valores)
        asistente.create_invoices()
        return pedido.sudo().invoice_ids.sorted('id')[-1:].with_user(self.vendedora)

    def test_la_vendedora_no_hace_una_factura_suelta(self):
        Move = self.env['account.move'].with_user(self.vendedora)
        with negado(self, AccessError, COTIZAR):
            Move.create(self._valores())
        with negado(self, AccessError, COTIZAR):
            Move.with_context(default_move_type='out_invoice').create(
                {k: v for k, v in self._valores().items() if k != 'move_type'})
        with negado(self, AccessError, COTIZAR):   # por RPC, igual
            call_kw(Move, 'create', [self._valores()], {})
        self.assertFalse(self.env['account.move'].search([('partner_id', '=', self.cliente.id)]))

    def test_la_vendedora_factura_desde_su_pedido(self):
        factura = self._facturar(self._pedido(), advance_payment_method='delivered')
        self.assertTrue(factura.sudo().line_ids.sale_line_ids)
        factura.action_post()
        self.assertEqual((factura.state, factura.invoice_user_id), ('posted', self.vendedora))

    def test_la_vendedora_factura_un_anticipo_desde_su_pedido(self):
        factura = self._facturar(self._pedido(), advance_payment_method='percentage', amount=50)
        lineas_del_pedido = factura.sudo().line_ids.sale_line_ids
        self.assertTrue(lineas_del_pedido and all(lineas_del_pedido.mapped('is_downpayment')))
        factura.action_post()
        self.assertEqual(factura.amount_total, 50.0)

    def test_no_le_saca_las_lineas_del_pedido(self):
        factura = self._facturar(self._pedido(), advance_payment_method='delivered')
        linea = factura.invoice_line_ids
        with negado(self, AccessError, COTIZAR):
            factura.write({'invoice_line_ids': [
                Command.delete(linea.id),
                Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 10.0})]})
        self.assertEqual(factura.invoice_line_ids, linea)
        factura.write({'invoice_line_ids': [Command.update(linea.id, {'price_unit': 90.0})]})  # editarla, sí
        self.assertEqual(factura.amount_total, 90.0)

    def test_caja_gerencia_y_administrador_hacen_una_suelta(self):
        for usuario in (self.caja, self.gerencia, self.contador, self.admin):
            with self.subTest(usuario=usuario.login):
                factura = self.env['account.move'].with_user(usuario).create(self._valores())
                factura.action_post()
                self.assertEqual(factura.state, 'posted')
        # Y la vendedora sigue trabajando en una suelta que hizo Caja.
        suelta = self.env['account.move'].with_user(self.caja).create(dict(self._valores(),
                                                                          invoice_user_id=self.vendedora.id))
        suelta.with_user(self.vendedora).write({'invoice_line_ids': [Command.create(
            {'product_id': self.producto.id, 'quantity': 1, 'price_unit': 5.0, 'tax_ids': [Command.clear()]})]})

    def test_a_la_vendedora_no_le_sale_nuevo_en_facturas(self):
        def arch(usuario, tipo, contexto=None, accion=False):
            Modelo = self.env['account.move'].with_user(usuario).with_context(**(contexto or {}))
            vistas = Modelo.get_views([(False, tipo)], {'action_id': accion})
            return etree.fromstring(vistas['views'][tipo]['arch'])
        # Como la pide la pantalla (Facturación › Facturas): sin el contexto de la acción, con su action_id.
        facturas = self.env.ref('account.action_move_out_invoice_type').id
        proveedores = self.env.ref('account.action_move_in_invoice_type').id
        for tipo in ('list', 'form', 'kanban'):
            with self.subTest(tipo=tipo):
                self.assertEqual(arch(self.vendedora, tipo, accion=facturas).get('create'), '0')
                self.assertEqual(arch(self.vendedora, tipo, {'default_move_type': 'out_invoice'}).get('create'), '0')
                self.assertNotEqual(arch(self.caja, tipo, accion=facturas).get('create'), '0')
                # Lo demás (facturas de proveedor, asientos) no cambia.
                self.assertNotEqual(arch(self.vendedora, tipo, accion=proveedores).get('create'), '0')
