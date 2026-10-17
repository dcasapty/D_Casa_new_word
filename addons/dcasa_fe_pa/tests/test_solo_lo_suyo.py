"""Factura electrónica con «Cada vendedora ve solo sus documentos» (pedido de la dueña, 2026-10-16).

La Vendedora A no ve el documento electrónico ni sus intentos de una factura de la Vendedora B; B y Caja sí. Caja
publica la nota de crédito de una factura de B sin error, y la nota nace con su documento. Reglas:
security/dcasa_reglas_fe.xml.
"""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FeComun


@tagged('post_install', '-at_install')
class TestFeSoloLoSuyo(FeComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupo):
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login, 'group_ids': [
                Command.set([cls.env.ref('base.group_user').id, cls.env.ref(grupo).id])]})

        cls.a = usuario('fe_sls_a', 'dcasa_base.group_vendedora')
        cls.b = usuario('fe_sls_b', 'dcasa_base.group_vendedora')
        cls.caja = usuario('fe_sls_caja', 'dcasa_base.group_caja')

    def _cerrado(self, registros, usuario):
        self.assertTrue(registros)
        Modelo = registros.browse().with_user(usuario)
        dominio = [('id', 'in', registros.ids)]
        self.assertFalse(Modelo.search(dominio))
        self.assertEqual(Modelo.search_count(dominio), 0)
        self.assertEqual(Modelo._read_group(dominio, [], ['__count']), [(0,)])
        if Modelo._rec_name in Modelo._fields:
            self.assertFalse(Modelo.name_search('', dominio))
        with self.assertRaises(AccessError):
            registros.with_user(usuario).read(['display_name'])

    def _visible(self, registros, usuario):
        self.assertEqual(registros.browse().with_user(usuario).search([('id', 'in', registros.ids)]), registros,
                         usuario.login)

    def test_a_no_ve_el_documento_ni_los_intentos_de_b(self):
        self._activar()
        factura = self._factura(self.contribuyente, invoice_user_id=self.b.id)
        documento = factura.l10n_pa_fe_documento_ids
        documento._procesar()
        intentos = documento.intento_ids
        self.assertTrue(intentos)
        self._cerrado(documento, self.a)
        self._cerrado(intentos, self.a)
        for usuario in (self.b, self.caja):
            with self.subTest(usuario.login):
                self._visible(documento, usuario)
                self._visible(intentos, usuario)
        # Lo que no tiene vendedora lo ven todas.
        libre = self._factura(self.contribuyente, invoice_user_id=False).l10n_pa_fe_documento_ids
        self._visible(libre, self.a)

    def test_caja_publica_la_nota_de_una_factura_de_b(self):
        self._activar()
        factura = self._factura(self.contribuyente, invoice_user_id=self.b.id)
        factura.l10n_pa_fe_documento_ids._procesar()
        reverso = self.env['account.move.reversal'].with_user(self.caja).with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'reason': 'Devolución', 'journal_id': factura.journal_id.id})
        nota = self.env['account.move'].browse(reverso.refund_moves()['res_id'])
        nota.with_user(self.caja).action_post()
        self.assertEqual(nota.state, 'posted')
        self.assertEqual(nota.invoice_user_id, self.b, 'la nota sigue siendo de B')
        self.assertEqual(len(nota.l10n_pa_fe_documento_ids), 1)
        self._visible(nota.l10n_pa_fe_documento_ids, self.b)
        self._cerrado(nota.l10n_pa_fe_documento_ids, self.a)
